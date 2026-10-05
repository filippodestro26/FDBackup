import tempfile  # Importa TemporaryDirectory per creare filesystem di prova isolati.
import threading  # Importa Event per verificare l'arresto cooperativo condiviso.
import unittest  # Importa il framework standard già usato dal progetto.
from pathlib import Path  # Importa Path per costruire sorgenti e destinazioni temporanee.
from unittest.mock import patch  # Importa patch per simulare in modo controllato errori fatali e Stop.

from fdbackup.gestore_backup import GestoreBackup  # Importa il coordinatore da verificare.
from fdbackup.modelli_backup import JobBackup, SorgenteBackup  # Importa i modelli reali già verificati.
from fdbackup.motore_backup import RisultatoBackup  # Importa il risultato reale del motore per i test controllati.


class TestGestoreBackup(unittest.TestCase):
    """Verifica l'orchestrazione sequenziale dei job senza dipendere dalla GUI."""

    def test_esegue_una_sorgente_nella_sottocartella_assegnata(self) -> None:
        """Una sorgente deve essere copiata dentro destinazione_job/nome_destinazione."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            (sorgente / "file.txt").write_text("contenuto", encoding="utf-8")
            destinazione = radice / "backup"
            job = JobBackup("Job", destinazione, [SorgenteBackup(sorgente, "Dati")])
            risultato = GestoreBackup(threading.Event()).esegui([job])
            self.assertEqual((destinazione / "Dati" / "file.txt").read_text(encoding="utf-8"), "contenuto")
            self.assertTrue(risultato.successo)

    def test_esegue_piu_sorgenti_dello_stesso_job_in_sottocartelle_distinte(self) -> None:
        """Ogni sorgente dello stesso job deve mantenere la propria radice logica."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            (prima / "a.txt").write_text("A", encoding="utf-8")
            (seconda / "b.txt").write_text("B", encoding="utf-8")
            destinazione = radice / "backup"
            job = JobBackup("Job", destinazione, [SorgenteBackup(prima, "Prima"), SorgenteBackup(seconda, "Seconda")])
            risultato = GestoreBackup(threading.Event()).esegui([job])
            self.assertTrue((destinazione / "Prima" / "a.txt").is_file())
            self.assertTrue((destinazione / "Seconda" / "b.txt").is_file())
            self.assertEqual(risultato.sorgenti_eseguite, 2)

    def test_esegue_piu_job_in_ordine_sequenziale(self) -> None:
        """Il coordinatore deve completare i job nell'ordine ricevuto senza creare thread propri."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente1 = radice / "s1"
            sorgente2 = radice / "s2"
            sorgente1.mkdir()
            sorgente2.mkdir()
            eventi = []
            job1 = JobBackup("Uno", radice / "backup1", [SorgenteBackup(sorgente1, "S1")])
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(sorgente2, "S2")])
            GestoreBackup(threading.Event(), lambda evento, dati: eventi.append((evento, dati))).esegui([job1, job2])
            sequenza_job = [dati["nome_job"] for evento, dati in eventi if evento == "inizio_job"]
            self.assertEqual(sequenza_job, ["Uno", "Due"])

    def test_job_disabilitato_non_viene_eseguito(self) -> None:
        """I job disabilitati devono restare in configurazione senza produrre lavoro."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Off", radice / "backup", [SorgenteBackup(sorgente, "Dati")], abilitato=False)
            risultato = GestoreBackup(threading.Event()).esegui([job])
            self.assertEqual(risultato.risultati_job, [])
            self.assertFalse((radice / "backup").exists())

    def test_validazione_globale_avviene_prima_della_prima_copia(self) -> None:
        """Un secondo job non valido deve impedire anche l'avvio del primo job valido."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            valida = radice / "valida"
            valida.mkdir()
            (valida / "file.txt").write_text("dato", encoding="utf-8")
            job1 = JobBackup("Valido", radice / "backup1", [SorgenteBackup(valida, "Dati")])
            job2 = JobBackup("Non valido", radice / "backup2", [SorgenteBackup(radice / "inesistente", "Manca")])
            with self.assertRaisesRegex(ValueError, "non esiste"):
                GestoreBackup(threading.Event()).esegui([job1, job2])
            self.assertFalse((radice / "backup1").exists())

    def test_stop_impostato_prima_dellesecuzione_non_avvia_job(self) -> None:
        """Uno Stop già richiesto deve impedire l'avvio di qualsiasi job dopo la validazione."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            evento = threading.Event()
            evento.set()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati")])
            risultato = GestoreBackup(evento).esegui([job])
            self.assertTrue(risultato.annullato)
            self.assertEqual(risultato.risultati_job, [])

    def test_stop_durante_prima_sorgente_non_avvia_la_seconda(self) -> None:
        """Quando il motore osserva lo Stop, il coordinatore non deve iniziare sorgenti successive."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            evento = threading.Event()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(prima, "Prima"), SorgenteBackup(seconda, "Seconda")])

            def esecuzione_simulata(_motore, _sorgente, _destinazione):
                evento.set()
                return RisultatoBackup(annullato=True)

            with patch("fdbackup.gestore_backup.MotoreBackup.esegui", new=esecuzione_simulata):
                risultato = GestoreBackup(evento).esegui([job])

            self.assertTrue(risultato.annullato)
            self.assertEqual(risultato.sorgenti_eseguite, 1)

    def test_stop_durante_primo_job_non_avvia_il_secondo(self) -> None:
        """Una richiesta di arresto deve fermare anche la sequenza dei job."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            evento = threading.Event()
            job1 = JobBackup("Uno", radice / "backup1", [SorgenteBackup(prima, "Prima")])
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(seconda, "Seconda")])

            def esecuzione_simulata(_motore, _sorgente, _destinazione):
                evento.set()
                return RisultatoBackup(annullato=True)

            with patch("fdbackup.gestore_backup.MotoreBackup.esegui", new=esecuzione_simulata):
                risultato = GestoreBackup(evento).esegui([job1, job2])

            self.assertEqual([esito.nome_job for esito in risultato.risultati_job], ["Uno"])

    def test_errore_fatale_di_una_sorgente_non_blocca_job_successivo(self) -> None:
        """Un errore runtime circoscritto deve essere registrato e non impedire i job successivi."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job1 = JobBackup("Uno", radice / "backup1", [SorgenteBackup(prima, "Prima")])
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(seconda, "Seconda")])
            chiamate = {"numero": 0}

            def esecuzione_simulata(_motore, _sorgente, _destinazione):
                chiamate["numero"] += 1
                if chiamate["numero"] == 1:
                    raise OSError("errore simulato")
                return RisultatoBackup()

            with patch("fdbackup.gestore_backup.MotoreBackup.esegui", new=esecuzione_simulata):
                risultato = GestoreBackup(threading.Event()).esegui([job1, job2])

            self.assertEqual(len(risultato.risultati_job), 2)
            self.assertIsNotNone(risultato.risultati_job[0].risultati_sorgenti[0].errore_fatale)
            self.assertTrue(risultato.risultati_job[1].risultati_sorgenti[0].successo)

    def test_errore_fatale_non_rende_successo_il_risultato_globale(self) -> None:
        """La prosecuzione dopo un errore non deve nascondere il fallimento complessivo."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati")])

            with patch("fdbackup.gestore_backup.MotoreBackup.esegui", side_effect=OSError("errore simulato")):
                risultato = GestoreBackup(threading.Event()).esegui([job])

            self.assertFalse(risultato.successo)

    def test_eventi_del_motore_vengono_inoltrati_con_contesto(self) -> None:
        """Gli eventi del motore devono conservare job e sorgente per la futura GUI multi-job."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            (sorgente / "file.txt").write_text("dato", encoding="utf-8")
            sorgente_modello = SorgenteBackup(sorgente, "Dati")
            job = JobBackup("Job", radice / "backup", [sorgente_modello])
            eventi = []
            GestoreBackup(threading.Event(), lambda evento, dati: eventi.append((evento, dati))).esegui([job])
            inoltrati = [dati for evento, dati in eventi if evento == "evento_motore"]
            self.assertTrue(inoltrati)
            self.assertTrue(all(dati["id_job"] == job.id_job for dati in inoltrati))
            self.assertTrue(all(dati["id_sorgente"] == sorgente_modello.id_sorgente for dati in inoltrati))

    def test_evento_finale_contiene_lo_stesso_risultato_restituito(self) -> None:
        """La callback finale deve ricevere esattamente l'oggetto restituito dal coordinatore."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati")])
            eventi = []
            risultato = GestoreBackup(threading.Event(), lambda evento, dati: eventi.append((evento, dati))).esegui([job])
            risultato_evento = [dati["risultato"] for evento, dati in eventi if evento == "fine_esecuzione"]
            self.assertEqual(len(risultato_evento), 1)
            self.assertIs(risultato_evento[0], risultato)

    def test_seconda_esecuzione_riutilizza_semantica_identici_del_motore(self) -> None:
        """Il coordinatore non deve alterare il comportamento incrementale già verificato del MotoreBackup."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            (sorgente / "file.txt").write_text("dato", encoding="utf-8")
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati")])
            gestore = GestoreBackup(threading.Event())
            primo = gestore.esegui([job])
            secondo = gestore.esegui([job])
            self.assertEqual(primo.risultati_job[0].risultati_sorgenti[0].risultato_backup.file_copiati, 1)
            self.assertEqual(secondo.risultati_job[0].risultati_sorgenti[0].risultato_backup.file_ignorati, 1)

    def test_propaga_opzione_sottocartelle_del_job_al_motore(self) -> None:
        """Il coordinatore deve rispettare l'opzione del job senza reinterpretarla."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea un filesystem isolato.
            radice = Path(temporanea)  # Converte la directory temporanea in Path.
            sorgente = radice / "sorgente"  # Definisce la sorgente del job.
            interna = sorgente / "interna"  # Definisce una sottocartella che deve essere esclusa.
            interna.mkdir(parents=True)  # Crea la struttura sorgente.
            (sorgente / "radice.txt").write_text("radice", encoding="utf-8")  # Crea un file di primo livello.
            (interna / "interno.txt").write_text("interno", encoding="utf-8")  # Crea un file annidato.
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati")], includi_sottocartelle=False)  # Configura il job per la sola radice.
            risultato = GestoreBackup(threading.Event()).esegui([job])  # Esegue il job attraverso il coordinatore reale.
            destinazione_sorgente = radice / "backup" / "Dati"  # Ricostruisce la destinazione effettiva assegnata alla sorgente.
            self.assertTrue((destinazione_sorgente / "radice.txt").is_file())  # Verifica la copia del file di primo livello.
            self.assertFalse((destinazione_sorgente / "interna").exists())  # Verifica che il coordinatore abbia propagato l'esclusione delle sottocartelle.
            self.assertTrue(risultato.successo)  # Conferma che l'esecuzione limitata è comunque un backup riuscito.

    def test_propaga_opzione_verifica_integrita_del_job_al_motore(self) -> None:
        """Il coordinatore deve passare al motore anche la scelta sulla verifica SHA-256 post-copia."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea un ambiente temporaneo isolato.
            radice = Path(temporanea)  # Converte la directory temporanea in Path.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "file.txt").write_text("dato", encoding="utf-8")  # Crea un file nuovo.
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati")], verifica_integrita=False)  # Disattiva la verifica post-copia nel modello persistente.
            with patch("fdbackup.motore_backup.MotoreBackup.calcola_hash", wraps=__import__("fdbackup.motore_backup", fromlist=["MotoreBackup"]).MotoreBackup.calcola_hash) as hash_controllato:  # Osserva i calcoli SHA-256 effettuati dal motore creato dal coordinatore.
                risultato = GestoreBackup(threading.Event()).esegui([job])  # Esegue il job attraverso il coordinatore reale.
            self.assertEqual(hash_controllato.call_count, 0)  # Un file nuovo non deve essere sottoposto a SHA-256 quando la verifica è disattivata.
            self.assertTrue(risultato.successo)  # Conferma che la copia senza verifica SHA-256 post-copia è considerata riuscita.


if __name__ == "__main__":
    unittest.main()  # Permette anche l'esecuzione diretta del file di test.
