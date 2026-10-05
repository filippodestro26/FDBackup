import json  # Importa JSON per verificare che le strutture prodotte siano realmente serializzabili.
import tempfile  # Importa TemporaryDirectory per verificare il ciclo completo attraverso un file reale.
import unittest  # Importa il framework standard già usato dal progetto.
from pathlib import Path  # Importa Path per verificare il round-trip dei percorsi.

from fdbackup.configurazione import carica_configurazione, salva_configurazione  # Importa il livello reale che legge e scrive config.json.
from fdbackup.modelli_backup import JobBackup, PianificazioneBackup, SorgenteBackup  # Importa i modelli reali.
from fdbackup.persistenza_job import (  # Importa le funzioni pubbliche del nuovo modulo.
    carica_job_dalla_configurazione,
    deserializza_job_backup,
    deserializza_pianificazione_backup,
    deserializza_sorgente_backup,
    salva_job_nella_configurazione,
    serializza_job_backup,
    serializza_pianificazione_backup,
    serializza_sorgente_backup,
)


class TestPersistenzaJob(unittest.TestCase):
    """Verifica la conversione affidabile tra modelli dei job e configurazione JSON."""

    def test_serializza_sorgente_in_tipi_json_compatibili(self) -> None:
        """Path deve diventare stringa e l'identità deve essere conservata."""
        sorgente = SorgenteBackup(Path("C:/Dati"), "Dati", id_sorgente="sorgente-1")
        dati = serializza_sorgente_backup(sorgente)
        self.assertEqual(dati["id_sorgente"], "sorgente-1")
        self.assertEqual(dati["percorso"], str(Path("C:/Dati")))
        json.dumps(dati)

    def test_deserializza_sorgente_conserva_id_e_percorso(self) -> None:
        """Il caricamento non deve generare un nuovo ID."""
        dati = {"id_sorgente": "id-originale", "percorso": "C:/Dati", "nome_destinazione": "Archivio"}
        sorgente = deserializza_sorgente_backup(dati)
        self.assertEqual(sorgente.id_sorgente, "id-originale")
        self.assertEqual(sorgente.percorso, Path("C:/Dati"))
        self.assertEqual(sorgente.nome_destinazione, "Archivio")

    def test_serializza_job_completo(self) -> None:
        """Il documento del job deve contenere identità, stato e sorgenti."""
        job = JobBackup("Lavoro", Path("G:/Backup"), [SorgenteBackup(Path("C:/Dati"), "Dati", id_sorgente="s1")], False, "j1")
        dati = serializza_job_backup(job)
        self.assertEqual(dati["id_job"], "j1")
        self.assertFalse(dati["abilitato"])
        self.assertEqual(dati["sorgenti"][0]["id_sorgente"], "s1")
        json.dumps(dati)

    def test_round_trip_job_conserva_tutti_i_dati(self) -> None:
        """Serializzazione e caricamento devono ricostruire lo stesso modello logico."""
        originale = JobBackup("Personale", Path("G:/Backup"), [SorgenteBackup(Path("C:/Documenti"), "Documenti", id_sorgente="s1"), SorgenteBackup(Path("D:/Foto"), "Foto", id_sorgente="s2")], True, "job-1")
        caricato = deserializza_job_backup(serializza_job_backup(originale))
        self.assertEqual(caricato.id_job, originale.id_job)
        self.assertEqual(caricato.nome, originale.nome)
        self.assertEqual(caricato.destinazione, originale.destinazione)
        self.assertEqual(caricato.abilitato, originale.abilitato)
        self.assertEqual([(s.id_sorgente, s.percorso, s.nome_destinazione) for s in caricato.sorgenti], [(s.id_sorgente, s.percorso, s.nome_destinazione) for s in originale.sorgenti])

    def test_salvataggio_preserva_altre_chiavi_configurazione(self) -> None:
        """La nuova persistenza non deve cancellare impostazioni GUI già presenti."""
        configurazione = {"banner": "banner.png", "tema": "dark"}
        job = JobBackup("Job", Path("G:/Backup"), [], False, "j1")
        nuova = salva_job_nella_configurazione(configurazione, [job])
        self.assertEqual(nuova["banner"], "banner.png")
        self.assertEqual(nuova["tema"], "dark")
        self.assertNotIn("job_backup", configurazione)

    def test_configurazione_senza_sezione_job_restituisce_lista_vuota(self) -> None:
        """Un vecchio config.json senza job deve restare compatibile."""
        self.assertEqual(carica_job_dalla_configurazione({"banner": "x.png"}), [])

    def test_lista_job_vuota_e_valida(self) -> None:
        """Una configurazione che salva esplicitamente zero job deve essere valida."""
        configurazione = salva_job_nella_configurazione({}, [])
        self.assertEqual(carica_job_dalla_configurazione(configurazione), [])

    def test_round_trip_di_piu_job_mantiene_ordine_e_id(self) -> None:
        """Più job devono essere ricostruiti nello stesso ordine."""
        primo = JobBackup("Uno", Path("G:/Uno"), [], False, "j1")
        secondo = JobBackup("Due", Path("H:/Due"), [], False, "j2")
        caricati = carica_job_dalla_configurazione(salva_job_nella_configurazione({}, [primo, secondo]))
        self.assertEqual([job.id_job for job in caricati], ["j1", "j2"])

    def test_id_sorgente_mancante_viene_rifiutato(self) -> None:
        """Una sorgente persistita senza identità non deve ricevere silenziosamente un nuovo UUID."""
        with self.assertRaisesRegex(ValueError, "identificatore"):
            deserializza_sorgente_backup({"percorso": "C:/Dati", "nome_destinazione": "Dati"})

    def test_percorso_sorgente_non_stringa_viene_rifiutato(self) -> None:
        """Il formato persistito richiede esplicitamente una stringa."""
        with self.assertRaisesRegex(ValueError, "percorso"):
            deserializza_sorgente_backup({"id_sorgente": "s1", "percorso": 123, "nome_destinazione": "Dati"})

    def test_nome_destinazione_mancante_viene_rifiutato(self) -> None:
        """Una sorgente incompleta deve essere riconosciuta come configurazione non valida."""
        with self.assertRaisesRegex(ValueError, "nome di destinazione"):
            deserializza_sorgente_backup({"id_sorgente": "s1", "percorso": "C:/Dati"})

    def test_id_job_mancante_viene_rifiutato(self) -> None:
        """Un job persistito senza identità non deve ricevere silenziosamente un nuovo UUID."""
        dati = {"nome": "Job", "destinazione": "G:/Backup", "abilitato": True, "sorgenti": []}
        with self.assertRaisesRegex(ValueError, "identificatore"):
            deserializza_job_backup(dati)

    def test_nome_job_mancante_viene_rifiutato(self) -> None:
        """Un job persistito deve avere un nome valido."""
        dati = {"id_job": "j1", "destinazione": "G:/Backup", "abilitato": True, "sorgenti": []}
        with self.assertRaisesRegex(ValueError, "nome"):
            deserializza_job_backup(dati)

    def test_destinazione_job_non_stringa_viene_rifiutata(self) -> None:
        """La destinazione persistita deve avere il tipo previsto."""
        dati = {"id_job": "j1", "nome": "Job", "destinazione": 42, "abilitato": True, "sorgenti": []}
        with self.assertRaisesRegex(ValueError, "destinazione"):
            deserializza_job_backup(dati)

    def test_abilitato_deve_essere_booleano(self) -> None:
        """La stringa 'false' non deve essere interpretata erroneamente come True."""
        dati = {"id_job": "j1", "nome": "Job", "destinazione": "G:/Backup", "abilitato": "false", "sorgenti": []}
        with self.assertRaisesRegex(ValueError, "abilitato"):
            deserializza_job_backup(dati)

    def test_sorgenti_devono_essere_lista(self) -> None:
        """La collezione persistita deve essere un array JSON."""
        dati = {"id_job": "j1", "nome": "Job", "destinazione": "G:/Backup", "abilitato": True, "sorgenti": {}}
        with self.assertRaisesRegex(ValueError, "lista"):
            deserializza_job_backup(dati)

    def test_sezione_job_non_lista_viene_rifiutata(self) -> None:
        """Una sezione presente ma corrotta non deve essere confusa con l'assenza di job."""
        with self.assertRaisesRegex(ValueError, "lista"):
            carica_job_dalla_configurazione({"job_backup": {}})

    def test_un_job_corrotto_fa_fallire_atomicamente_il_caricamento(self) -> None:
        """Non devono essere restituiti soltanto alcuni job quando la sezione è parzialmente corrotta."""
        valido = serializza_job_backup(JobBackup("Valido", Path("G:/Backup"), [], False, "j1"))
        corrotto = {"id_job": "j2", "nome": "Rotto", "destinazione": "H:/Backup", "abilitato": "no", "sorgenti": []}
        with self.assertRaisesRegex(ValueError, "Configurazione dei job"):
            carica_job_dalla_configurazione({"job_backup": [valido, corrotto]})

    def test_configurazione_non_dizionario_viene_rifiutata(self) -> None:
        """L'API pubblica non accetta strutture arbitrarie."""
        with self.assertRaises(TypeError):
            carica_job_dalla_configurazione([])


    def test_round_trip_end_to_end_attraverso_file_configurazione(self) -> None:
        """Verifica l'intero percorso JobBackup -> dizionario -> config.json -> dizionario -> JobBackup."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea una directory isolata eliminata automaticamente al termine del test.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo nel tipo Path usato dal progetto.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file reale attraversato dal test end-to-end.

            primo_job = JobBackup(  # Costruisce il primo job con due sorgenti per verificare anche l'ordine interno.
                nome="Personale",  # Assegna un nome leggibile che dovrà sopravvivere al round-trip.
                destinazione=radice_test / "backup_personale",  # Usa una destinazione reale rappresentabile come Path.
                sorgenti=[  # Definisce due sorgenti persistenti nello stesso job.
                    SorgenteBackup(radice_test / "documenti", "Documenti", id_sorgente="sorgente-documenti"),  # Crea la prima sorgente con ID stabile.
                    SorgenteBackup(radice_test / "foto", "Foto", id_sorgente="sorgente-foto"),  # Crea la seconda sorgente con un ID differente.
                ],
                abilitato=True,  # Mantiene il primo job abilitato per verificare il booleano persistito.
                id_job="job-personale",  # Assegna un ID noto che non deve essere rigenerato durante il caricamento.
            )

            secondo_job = JobBackup(  # Costruisce un secondo job per verificare anche l'ordine globale.
                nome="Lavoro",  # Assegna il nome del secondo job.
                destinazione=radice_test / "backup_lavoro",  # Definisce una destinazione distinta.
                sorgenti=[  # Definisce una sola sorgente nel secondo job.
                    SorgenteBackup(radice_test / "progetti", "Progetti", id_sorgente="sorgente-progetti"),  # Mantiene un terzo ID sorgente stabile.
                ],
                abilitato=False,  # Disabilita intenzionalmente il secondo job per verificare la persistenza dello stato.
                id_job="job-lavoro",  # Assegna un secondo ID noto e distinto.
            )

            configurazione_iniziale = {  # Simula impostazioni dell'applicazione già presenti prima del salvataggio dei job.
                "banner": "banner_è.png",  # Usa anche un carattere Unicode per attraversare realmente la codifica UTF-8.
                "tema": "dark",  # Aggiunge una seconda chiave estranea alla persistenza dei job.
            }

            configurazione_da_salvare = salva_job_nella_configurazione(  # Inserisce i job nella configurazione senza scrivere ancora il file.
                configurazione_iniziale,  # Passa la configurazione preesistente che deve essere preservata.
                [primo_job, secondo_job],  # Passa i due job nell'ordine che dovrà essere conservato.
            )

            salva_configurazione(  # Attraversa il vero livello di salvataggio atomico della configurazione.
                percorso_configurazione,  # Indica il file config.json temporaneo.
                configurazione_da_salvare,  # Scrive la struttura completa con impostazioni e job.
            )

            self.assertTrue(percorso_configurazione.is_file())  # Verifica che il file reale sia stato creato.

            configurazione_riletta = carica_configurazione(percorso_configurazione)  # Rilegge il JSON usando l'API reale dell'applicazione.
            job_riletti = carica_job_dalla_configurazione(configurazione_riletta)  # Ricostruisce i modelli persistenti dal dizionario riletto.

            self.assertEqual(configurazione_riletta["banner"], "banner_è.png")  # Verifica che una chiave estranea e Unicode sia rimasta invariata.
            self.assertEqual(configurazione_riletta["tema"], "dark")  # Verifica che anche le altre impostazioni siano state preservate.
            self.assertEqual([job.id_job for job in job_riletti], ["job-personale", "job-lavoro"])  # Verifica identità e ordine globale dei job.
            self.assertEqual([job.nome for job in job_riletti], ["Personale", "Lavoro"])  # Verifica che i nomi leggibili siano stati ricostruiti.
            self.assertEqual([job.abilitato for job in job_riletti], [True, False])  # Verifica che lo stato abilitato/disabilitato sia sopravvissuto.
            self.assertEqual(job_riletti[0].destinazione, primo_job.destinazione)  # Verifica il round-trip del percorso di destinazione del primo job.
            self.assertEqual(job_riletti[1].destinazione, secondo_job.destinazione)  # Verifica il round-trip del percorso di destinazione del secondo job.
            self.assertEqual(  # Verifica insieme ID, percorso e nome logico delle sorgenti del primo job.
                [(sorgente.id_sorgente, sorgente.percorso, sorgente.nome_destinazione) for sorgente in job_riletti[0].sorgenti],
                [(sorgente.id_sorgente, sorgente.percorso, sorgente.nome_destinazione) for sorgente in primo_job.sorgenti],
            )
            self.assertEqual(  # Verifica gli stessi dati persistenti per la sorgente del secondo job.
                [(sorgente.id_sorgente, sorgente.percorso, sorgente.nome_destinazione) for sorgente in job_riletti[1].sorgenti],
                [(sorgente.id_sorgente, sorgente.percorso, sorgente.nome_destinazione) for sorgente in secondo_job.sorgenti],
            )

    def test_serializza_job_conserva_le_opzioni_backup(self) -> None:
        """La persistenza deve scrivere esplicitamente entrambe le nuove opzioni del job."""
        job = JobBackup("Opzioni", Path("G:/Backup"), [], True, "j-opzioni", False, False)  # Usa anche la firma posizionale completa per verificare l’ordine compatibile dei campi.
        dati = serializza_job_backup(job)  # Converte il modello nella struttura destinata al JSON.
        self.assertIs(dati["includi_sottocartelle"], False)  # Verifica che la prima opzione venga serializzata come booleano JSON compatibile.
        self.assertIs(dati["verifica_integrita"], False)  # Verifica che la seconda opzione venga serializzata come booleano JSON compatibile.
        json.dumps(dati)  # Verifica che l’intera struttura rimanga serializzabile dalla libreria standard.

    def test_round_trip_conserva_le_opzioni_backup(self) -> None:
        """Serializzazione e deserializzazione devono conservare i valori delle nuove opzioni."""
        originale = JobBackup(  # Costruisce un job con una combinazione non predefinita delle opzioni.
            "Opzioni",  # Assegna il nome del job.
            Path("G:/Backup"),  # Assegna la destinazione persistente.
            [],  # Non servono sorgenti per verificare il puro round-trip del modello.
            False,  # Mantiene il job disabilitato per evitare di coinvolgere la validazione filesystem.
            "j-opzioni",  # Usa un ID noto per verificare che la firma precedente rimanga compatibile.
            False,  # Disabilita la scansione delle sottocartelle.
            True,  # Mantiene attiva la verifica di integrità.
        )
        caricato = deserializza_job_backup(serializza_job_backup(originale))  # Esegue il round-trip completo in memoria.
        self.assertFalse(caricato.includi_sottocartelle)  # Verifica la conservazione della prima opzione.
        self.assertTrue(caricato.verifica_integrita)  # Verifica la conservazione della seconda opzione.

    def test_vecchio_job_senza_nuove_opzioni_usa_valori_compatibili(self) -> None:
        """Un job salvato prima delle nuove opzioni deve continuare a usare il comportamento storico."""
        dati_vecchi = {  # Simula esattamente la struttura persistita prima dell’introduzione delle nuove chiavi.
            "id_job": "job-storico",  # Mantiene un’identità persistente valida.
            "nome": "Storico",  # Mantiene un nome valido.
            "destinazione": "G:/Backup",  # Mantiene una destinazione valida.
            "abilitato": False,  # Usa un booleano reale come richiesto dal formato precedente.
            "sorgenti": [],  # Mantiene una lista sorgenti valida per un job disabilitato.
        }
        caricato = deserializza_job_backup(dati_vecchi)  # Carica il documento senza aggiungere manualmente le nuove chiavi.
        self.assertTrue(caricato.includi_sottocartelle)  # Conferma la compatibilità con la precedente scansione ricorsiva sempre attiva.
        self.assertTrue(caricato.verifica_integrita)  # Conferma la compatibilità con la precedente verifica sempre attiva.

    def test_includi_sottocartelle_deve_essere_booleano(self) -> None:
        """Una nuova chiave presente ma di tipo errato deve essere considerata configurazione corrotta."""
        dati = {"id_job": "j1", "nome": "Job", "destinazione": "G:/Backup", "abilitato": False, "sorgenti": [], "includi_sottocartelle": "false"}  # Inserisce intenzionalmente una stringa non valida.
        with self.assertRaisesRegex(ValueError, "includi_sottocartelle"):  # Verifica un errore esplicito e riconoscibile.
            deserializza_job_backup(dati)  # Tenta di ricostruire il job dalla configurazione corrotta.

    def test_verifica_integrita_deve_essere_booleano(self) -> None:
        """La verifica di integrità persistita deve accettare soltanto un vero booleano JSON."""
        dati = {"id_job": "j1", "nome": "Job", "destinazione": "G:/Backup", "abilitato": False, "sorgenti": [], "verifica_integrita": 1}  # Inserisce intenzionalmente un intero non valido.
        with self.assertRaisesRegex(ValueError, "verifica_integrita"):  # Verifica che l’errore identifichi precisamente la chiave corrotta.
            deserializza_job_backup(dati)  # Tenta di ricostruire il job con il tipo errato.


    def test_serializza_e_deserializza_pianificazione(self) -> None:
        """La pianificazione deve attraversare il formato JSON senza perdere stato, giorni o ora."""
        originale = PianificazioneBackup(True, [0, 2, 4], "18:30", "2026-10-01T14:31:45")
        dati = serializza_pianificazione_backup(originale)
        json.dumps(dati)
        caricata = deserializza_pianificazione_backup(dati)
        self.assertTrue(caricata.abilitata)
        self.assertEqual(caricata.giorni, (0, 2, 4))
        self.assertEqual(caricata.ora, "18:30")
        self.assertEqual(caricata.attiva_dal, "2026-10-01T14:31:45")  # Verifica che il limite anti-recupero retroattivo sopravviva al round-trip.

    def test_pianificazione_storica_senza_attivazione_resta_compatibile(self) -> None:
        """Le configurazioni create prima del nuovo limite devono continuare a caricarsi senza inventare una data di attivazione."""
        dati = {"abilitata": True, "giorni": [0], "ora": "18:30"}  # Simula il formato persistente precedente.
        caricata = deserializza_pianificazione_backup(dati)  # Carica la struttura tramite il percorso reale di compatibilità.
        self.assertEqual(caricata.attiva_dal, "")  # Mantiene il comportamento storico di catch-up quando l’origine temporale non è conoscibile.

    def test_round_trip_sorgente_conserva_pianificazione(self) -> None:
        """La pianificazione appartiene alla sorgente e deve essere conservata nel suo round-trip."""
        originale = SorgenteBackup(Path("C:/Dati"), "Dati", "s1", PianificazioneBackup(True, [1, 3], "20:15"))
        caricata = deserializza_sorgente_backup(serializza_sorgente_backup(originale))
        self.assertTrue(caricata.pianificazione.abilitata)
        self.assertEqual(caricata.pianificazione.giorni, (1, 3))
        self.assertEqual(caricata.pianificazione.ora, "20:15")

    def test_vecchia_sorgente_senza_pianificazione_resta_disabilitata(self) -> None:
        """Una sorgente storica non deve iniziare automaticamente a eseguire backup programmati."""
        dati = {"id_sorgente": "s1", "percorso": "C:/Dati", "nome_destinazione": "Dati"}
        caricata = deserializza_sorgente_backup(dati)
        self.assertFalse(caricata.pianificazione.abilitata)
        self.assertEqual(caricata.pianificazione.giorni, ())
        self.assertEqual(caricata.pianificazione.ora, "")

    def test_pianificazione_presente_deve_essere_oggetto(self) -> None:
        """Una chiave presente ma strutturalmente corrotta deve produrre un errore esplicito."""
        dati = {"id_sorgente": "s1", "percorso": "C:/Dati", "nome_destinazione": "Dati", "pianificazione": []}
        with self.assertRaisesRegex(ValueError, "oggetto JSON"):
            deserializza_sorgente_backup(dati)

    def test_pianificazione_persistita_rifiuta_abilitata_non_booleana(self) -> None:
        """La persistenza non deve interpretare stringhe come stato booleano."""
        dati = {"abilitata": "true", "giorni": [0], "ora": "18:30"}
        with self.assertRaisesRegex(ValueError, "abilitata"):
            deserializza_pianificazione_backup(dati)

    def test_pianificazione_persistita_rifiuta_giorni_non_lista(self) -> None:
        """Il documento JSON deve rappresentare i giorni con un array."""
        dati = {"abilitata": True, "giorni": "0,1", "ora": "18:30"}
        with self.assertRaisesRegex(ValueError, "lista"):
            deserializza_pianificazione_backup(dati)

    def test_pianificazione_persistita_rifiuta_ora_non_stringa(self) -> None:
        """L'ora persistita deve conservare il contratto testuale HH:MM."""
        dati = {"abilitata": True, "giorni": [0], "ora": 1830}
        with self.assertRaisesRegex(ValueError, "ora"):
            deserializza_pianificazione_backup(dati)

    def test_pianificazione_persistita_propaga_errori_semantici(self) -> None:
        """Duplicati, giorni fuori intervallo e ore invalide devono restare configurazioni corrotte."""
        casi = (
            {"abilitata": True, "giorni": [0, 0], "ora": "18:30"},
            {"abilitata": True, "giorni": [7], "ora": "18:30"},
            {"abilitata": True, "giorni": [0], "ora": "24:00"},
        )
        for dati in casi:
            with self.subTest(dati=dati):
                with self.assertRaisesRegex(ValueError, "pianificazione salvata non è valida"):
                    deserializza_pianificazione_backup(dati)


if __name__ == "__main__":
    unittest.main()
