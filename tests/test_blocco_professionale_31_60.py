import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fdbackup.filtri_backup import FiltroBackup
from fdbackup.gestore_backup_avanzato import GestoreBackupAvanzato, StrategiaBackupAvanzato
from fdbackup.politiche_avanzate import (
    EsitoAffidabilita, GestoreDestinazioniMultiple, DestinazioneBackup,
    PianificazioneAvanzata, PoliticaRetention, ReportVerifica,
    applica_retention_sicura, crea_report_periodico, esegui_con_retry_e_destinazione,
    esegui_strategia_affidabile, genera_avvisi, pianifica_retention,
    salva_report_periodico, seleziona_pianificazioni_dovute,
)

class TestBloccoProfessionale3160(unittest.TestCase):
    def test_filtro_integrato_esclude_estensione_e_dimensione(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); s=r/'s'; repo=r/'repo'; s.mkdir()
            (s/'ok.txt').write_text('ok'); (s/'no.log').write_text('x'); (s/'grande.txt').write_text('123456')
            filtro=FiltroBackup(estensioni_escluse=('log',), dimensione_massima=5)
            es=GestoreBackupAvanzato().esegui_strategia(s,repo,StrategiaBackupAvanzato('completo',filtro=filtro))
            self.assertTrue(es.successo); self.assertEqual(set(es.manifesto.file), {'ok.txt'}); self.assertEqual(es.file_copiati,1)

    def test_filtro_include_exclude_pattern_integrato(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); s=r/'s'; repo=r/'repo'; (s/'docs').mkdir(parents=True); (s/'tmp').mkdir()
            (s/'docs'/'a.txt').write_text('a'); (s/'tmp'/'b.txt').write_text('b')
            f=FiltroBackup(includi=('docs/*',), escludi=('tmp/*',))
            es=GestoreBackupAvanzato().esegui_strategia(s,repo,StrategiaBackupAvanzato('completo',filtro=f))
            self.assertEqual(set(es.manifesto.file),{'docs/a.txt'})

    def test_filtro_dimensione_minima(self):
        self.assertFalse(FiltroBackup(dimensione_minima=5).accetta('a',4))
        self.assertTrue(FiltroBackup(dimensione_minima=5).accetta('a',5))

    def test_filtro_range_invalido(self):
        with self.assertRaises(ValueError): FiltroBackup(dimensione_minima=10, dimensione_massima=2)

    def test_pianificazione_oraria(self):
        p=PianificazioneAvanzata('incrementale','oraria',minuto=15)
        self.assertEqual(p.occorrenza_precedente(datetime(2026,10,2,19,10)),datetime(2026,10,2,18,15))

    def test_pianificazione_giornaliera(self):
        p=PianificazioneAvanzata('completo','giornaliera',ora=3,minuto=30)
        self.assertEqual(p.occorrenza_precedente(datetime(2026,10,2,2)),datetime(2026,10,1,3,30))

    def test_pianificazione_settimanale(self):
        p=PianificazioneAvanzata('differenziale','settimanale',ora=9,giorni_settimana=(0,4))
        self.assertEqual(p.occorrenza_precedente(datetime(2026,10,2,20)).weekday(),4)

    def test_pianificazione_mensile_salva_giorno_inesistente(self):
        p=PianificazioneAvanzata('completo','mensile',ora=1,giorno_mese=31)
        self.assertEqual(p.occorrenza_precedente(datetime(2026,4,30,20)),datetime(2026,3,31,1))

    def test_piu_pianificazioni_stesso_job(self):
        r=[PianificazioneAvanzata('completo','settimanale',ora=8,giorni_settimana=(4,)),PianificazioneAvanzata('incrementale','giornaliera',ora=9)]
        dovute=seleziona_pianificazioni_dovute(r,{},datetime(2026,10,2,10))
        self.assertEqual([x[1].metodo for x in dovute],['completo','incrementale'])

    def test_anti_duplicazione_pianificazione_avanzata(self):
        r=[PianificazioneAvanzata('incrementale','giornaliera',ora=9)]
        stato={'0':'2026-10-02T09:00'}
        self.assertEqual(seleziona_pianificazioni_dovute(r,stato,datetime(2026,10,2,10)),[])

    def test_post_backup_verifica_automatica(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); s=r/'s'; repo=r/'repo'; report=r/'report'; s.mkdir(); (s/'a').write_text('abc')
            es=esegui_strategia_affidabile(s,repo,StrategiaBackupAvanzato('completo'),True,False,report)
            self.assertEqual(es.stato,'verificato'); self.assertEqual(es.report_verifica.stato,'verificato'); self.assertTrue(list(report.glob('verifica_*.json')))

    def test_test_recuperabilita_automatico(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); s=r/'s'; repo=r/'repo'; s.mkdir(); (s/'a').write_text('abc')
            es=esegui_strategia_affidabile(s,repo,StrategiaBackupAvanzato('completo'),True,True)
            self.assertEqual(es.report_recuperabilita.stato,'verificato'); self.assertEqual(es.stato,'verificato')

    def test_stato_corrotto_se_verifica_fallisce(self):
        oggetto=type('R',(),{'annullato':False,'errori':[]})()
        es=EsitoAffidabilita(oggetto,ReportVerifica('x','corrotto','ora'))
        self.assertEqual(es.stato,'corrotto')

    def test_destinazione_offline_viene_saltata(self):
        with patch('fdbackup.politiche_avanzate.destinazione_disponibile',return_value=(False,'offline')):
            stato,valore,dettaglio=esegui_con_retry_e_destinazione(lambda: 1,Path('/x'))
            self.assertEqual((stato,valore,dettaglio),('saltato',None,'offline'))

    def test_retry_operazione_io(self):
        with tempfile.TemporaryDirectory() as d:
            n=[0]
            def op():
                n[0]+=1
                if n[0]<2: raise OSError('temporaneo')
                return 9
            with patch('fdbackup.politiche_avanzate.time.sleep',return_value=None):
                stato,valore,_=esegui_con_retry_e_destinazione(op,Path(d))
            self.assertEqual((stato,valore),('completato',9)); self.assertEqual(n[0],2)

    def test_alert_destinazione_non_disponibile(self):
        with patch('fdbackup.politiche_avanzate.destinazione_disponibile',return_value=(False,'offline')):
            self.assertEqual(genera_avvisi(Path('/x'))[0].codice,'destinazione_non_disponibile')

    def test_alert_non_verificato(self):
        with tempfile.TemporaryDirectory() as d:
            a=genera_avvisi(Path(d),0,ReportVerifica('x','completato','ora'))
            self.assertEqual(a[-1].codice,'backup_non_verificato')

    def test_report_periodico_persistente(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.json'; dati=salva_report_periodico(p,[Path(d)])
            self.assertTrue(p.exists()); self.assertEqual(len(dati['repository']),1)

    def test_dashboard_con_versione(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); s=r/'s'; repo=r/'repo'; s.mkdir(); (s/'a').write_text('x')
            GestoreBackupAvanzato().esegui_strategia(s,repo,StrategiaBackupAvanzato('completo'))
            self.assertEqual(crea_report_periodico([repo])['repository'][0]['versioni'],1)

    def test_destinazioni_multiple_obbligatoria_fallisce(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); v=r/'v'; v.mkdir(); (v/'a').write_text('x'); dst=r/'dst'; (dst/'v').mkdir(parents=True)
            with self.assertRaises(FileExistsError): GestoreDestinazioniMultiple().replica(v,[DestinazioneBackup(dst,True)])

    def test_destinazioni_multiple_opzionale_prosegue(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); v=r/'v'; v.mkdir(); (v/'a').write_text('x'); male=r/'male'; (male/'v').mkdir(parents=True); bene=r/'bene'
            es=GestoreDestinazioniMultiple().replica(v,[DestinazioneBackup(male,False),DestinazioneBackup(bene,True)])
            self.assertTrue(es[str(male)].startswith('errore:')); self.assertEqual(es[str(bene)],'ok')

    def test_retention_dry_run_non_modifica_repository(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); prima=set(r.iterdir()); applica_retention_sicura(r,PoliticaRetention(),False); self.assertEqual(prima,set(r.iterdir()))

    def test_progress_error_gui_non_resta_100(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        self.assertIn('self.progresso_ripristino_versionato = 0.0',testo)
        self.assertIn('self.percentuale_ripristino_versionato.configure(text="0%")',testo)

    def test_gui_espone_verifica_post_backup(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        self.assertIn('Verifica SHA-256 automatica dopo il backup', testo)
        self.assertIn('GestoreAffidabilita()', testo)

    def test_gui_espone_test_recuperabilita(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        self.assertIn('Test automatico di recuperabilità', testo)
        self.assertIn('test_recuperabilita(destinazione', testo)

    def test_gui_espone_filtri_e_reparse(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        for voce in ('Includi: estensioni o pattern', 'Escludi: pattern o percorsi', 'Solo estensioni escluse', 'Escludi nascosti', 'Escludi sola lettura', 'Reparse:'):
            self.assertIn(voce, testo)
        self.assertIn('FiltroBackup(', testo)

    def test_gui_espone_retention_dashboard_report(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        for voce in ('Anteprima retention', 'Dashboard', 'Salva report'):
            self.assertIn(voce, testo)
        self.assertIn('pianifica_retention(', testo)
        self.assertIn('salva_report_periodico(', testo)

    def test_gui_espone_destinazioni_multiple(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        self.assertIn('Destinazioni aggiuntive', testo)
        self.assertIn('GestoreDestinazioniMultiple().replica', testo)

    def test_gui_preflight_destinazione_prima_strategia(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        self.assertIn('destinazione_disponibile(destinazione)', testo)
        self.assertIn('Destinazione non disponibile:', testo)

    def test_gui_conserva_opzioni_professionali_navigando(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        for chiave in ('"verifica": self.variabile_verifica_post_backup.get()', '"recuperabilita": self.variabile_test_recuperabilita.get()', '"destinazioni_extra": self.campo_destinazioni_aggiuntive.get()', '"ret_g": self.campo_retention_giorni.get()'):
            self.assertIn(chiave, testo)

    def test_gui_replica_solo_versione_pubblicata(self):
        testo=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
        self.assertIn('if getattr(risultato, "successo", False) and manifesto is not None:', testo)
        self.assertIn('_trova_cartella_versione(destinazione, manifesto.id_backup)', testo)

if __name__=='__main__': unittest.main()
