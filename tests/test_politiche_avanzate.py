import tempfile, unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from fdbackup.politiche_avanzate import *
from fdbackup.metadati_backup_avanzato import ManifestoBackup

class TestPoliticheAvanzate(unittest.TestCase):
    def test_filtro_include_exclude_estensione_dimensione(self):
        f=FiltroBackup(("docs/*",),("*/tmp/*",),("log",),100)
        self.assertTrue(f.accetta("docs/a.txt",10)); self.assertFalse(f.accetta("docs/a.log",10)); self.assertFalse(f.accetta("foto/a.txt",10)); self.assertFalse(f.accetta("docs/a.txt",101))
    def test_filtro_reparse(self): self.assertFalse(FiltroBackup().accetta("link",0,True))
    def test_filtro_validazione(self):
        with self.assertRaises(ValueError): FiltroBackup(dimensione_massima=-1)
    def test_pianificazione_prossima(self):
        p=PianificazioneCombinata("completo",(0,),9,30); r=datetime(2026,10,2,10); self.assertEqual(p.prossima(r).weekday(),0)
    def test_pianificazione_oggi(self):
        p=PianificazioneCombinata("incrementale",(4,),12); r=datetime(2026,10,2,10); self.assertEqual(p.prossima(r),datetime(2026,10,2,12))
    def test_pianificazione_invalida(self):
        with self.assertRaises(ValueError): PianificazioneCombinata("x",(0,),10)
    def test_retry_successo_dopo_errori(self):
        n=[0]
        def op():
            n[0]+=1
            if n[0]<3: raise OSError("x")
            return 7
        self.assertEqual(PoliticaRetry(3,0).esegui(op, lambda _:None),7)
    def test_retry_esaurito(self):
        with self.assertRaises(OSError): PoliticaRetry(2,0).esegui(lambda: (_ for _ in ()).throw(OSError("x")),lambda _:None)
    def test_retention_tiene_almeno_un_full(self):
        m=ManifestoBackup("a","completo","2026-01-01T00:00:00","s","a","",{},(),())
        self.assertEqual(PoliticaRetention(0,0,0,0).seleziona_full_da_conservare([m]),{"a"})
    def test_report_atomico(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"r.json"; ReportVerifica("x","verificato","ora").salva(p); self.assertIn('"verificato"',p.read_text())
    def test_report_stato_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): ReportVerifica("x","x","ora").salva(Path(d)/"r")
    def test_destinazione_disponibile(self):
        with tempfile.TemporaryDirectory() as d: self.assertTrue(destinazione_disponibile(Path(d),0)[0])
    def test_destinazione_spazio_impossibile(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("fdbackup.politiche_avanzate.shutil.disk_usage") as du:
                du.return_value=type("U",(),{"free":1})(); self.assertFalse(destinazione_disponibile(Path(d),2)[0])
    def test_replica_multipla(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); s=r/"v"; s.mkdir(); (s/"a").write_text("x"); a=r/"a"; b=r/"b"
            es=GestoreDestinazioniMultiple().replica(s,[DestinazioneBackup(a),DestinazioneBackup(b)])
            self.assertEqual(set(es.values()),{"ok"}); self.assertEqual((a/"v"/"a").read_text(),"x")
    def test_replica_non_sovrascrive(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); s=r/"v"; s.mkdir(); x=r/"x"; (x/"v").mkdir(parents=True)
            with self.assertRaises(FileExistsError): GestoreDestinazioniMultiple().replica(s,[DestinazioneBackup(x)])
    def test_dashboard_vuota(self):
        with tempfile.TemporaryDirectory() as d: self.assertEqual(crea_dashboard(Path(d))["versioni"],0)
    def test_reparse_symlink_se_supportato(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); t=r/"t"; t.write_text("x"); l=r/"l"
            try: l.symlink_to(t)
            except OSError: self.skipTest("symlink non disponibile")
            self.assertTrue(rileva_reparse(l))

    def test_retention_dry_run_non_cancella(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(applica_retention_sicura(Path(d), PoliticaRetention(), False), [])
    def test_avviso_spazio(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("fdbackup.politiche_avanzate.shutil.disk_usage") as du:
                du.return_value=type("U",(),{"free":0})(); a=genera_avvisi(Path(d),1); self.assertEqual(a[0].codice,"spazio_insufficiente")
    def test_avviso_corrotto(self):
        with tempfile.TemporaryDirectory() as d:
            a=genera_avvisi(Path(d),0,ReportVerifica("x","corrotto","ora")); self.assertEqual(a[-1].codice,"backup_non_verificato")
    def test_report_periodico(self):
        with tempfile.TemporaryDirectory() as d:
            r=crea_report_periodico([Path(d)]); self.assertEqual(len(r["repository"]),1)

if __name__=='__main__': unittest.main()
