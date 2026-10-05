"""Test del verificatore di integrità delle versioni avanzate di FDBackup."""

import tempfile
import threading
import unittest
from pathlib import Path

from fdbackup.motore_backup_avanzato import MotoreBackupAvanzato
from fdbackup.verifica_integrita_avanzata import VerificatoreIntegritaAvanzata


class TestVerificatoreIntegritaAvanzata(unittest.TestCase):
    """Verifica recuperabilità, corruzione, catene e Stop senza dipendere dalla GUI."""

    @staticmethod
    def trova_cartella_versione(radice: Path, id_backup: str) -> Path:
        """Trova la directory fisica associata all'ID completo memorizzato nel manifesto."""
        for manifesto in radice.glob("*/.backupcore-manifesto.json"):  # Esamina esclusivamente il layout ufficiale delle versioni.
            if id_backup in manifesto.read_text(encoding="utf-8"):  # Usa l'ID completo per identificare senza ambiguità la versione del test.
                return manifesto.parent  # Restituisce la directory che contiene manifesto e payload.
        raise AssertionError("Versione di test non trovata.")  # Fallisce esplicitamente se il setup non ha prodotto il backup atteso.

    def test_full_integro_viene_verificato(self):
        """Un Full non alterato deve risultare interamente recuperabile."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola sorgente e repository.
            radice = Path(temporanea)  # Converte il percorso temporaneo nel tipo usato dai motori.
            sorgente = radice / "sorgente"  # Definisce la sorgente del Full.
            sorgente.mkdir()  # Crea la radice sorgente.
            (sorgente / "a.txt").write_text("alpha", encoding="utf-8")  # Crea un payload noto.
            (sorgente / "b.bin").write_bytes(b"beta")  # Crea un secondo payload binario.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce un Full reale.
            risultato = VerificatoreIntegritaAvanzata().verifica_versione(radice / "versioni", backup.manifesto.id_backup)  # Verifica il repository senza ripristino.
            self.assertTrue(risultato.integro)  # Richiede assenza di anomalie e Stop.
            self.assertEqual(risultato.file_verificati, 2)  # Richiede la lettura di entrambi i payload finali.
            self.assertEqual(risultato.versioni_catena, 1)  # Un Full deve essere autosufficiente.

    def test_corruzione_payload_viene_rilevata(self):
        """Una modifica fisica successiva al backup deve produrre un errore SHA-256."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il repository da altri test.
            radice = Path(temporanea)  # Prepara i percorsi.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "dato.txt").write_text("originale", encoding="utf-8")  # Materializza il contenuto da proteggere.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce il Full e il relativo SHA-256.
            cartella = self.trova_cartella_versione(radice / "versioni", backup.manifesto.id_backup)  # Risolve la directory pubblicata.
            (cartella / "dati" / "dato.txt").write_text("alterato!", encoding="utf-8")  # Corrompe intenzionalmente il payload dopo la pubblicazione.
            risultato = VerificatoreIntegritaAvanzata().verifica_versione(radice / "versioni", backup.manifesto.id_backup)  # Esegue il controllo indipendente.
            self.assertFalse(risultato.integro)  # La versione non deve essere dichiarata integra.
            self.assertTrue(any("SHA-256 non valido" in errore for errore in risultato.errori))  # Richiede una diagnosi crittografica esplicita.

    def test_payload_mancante_viene_rilevato(self):
        """La perdita di un payload necessario deve rendere la versione non recuperabile."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il caso di perdita fisica.
            radice = Path(temporanea)  # Prepara i percorsi temporanei.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "dato.txt").write_text("dato", encoding="utf-8")  # Crea il file da perdere nel repository.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce la versione verificabile.
            cartella = self.trova_cartella_versione(radice / "versioni", backup.manifesto.id_backup)  # Trova il payload fisico.
            (cartella / "dati" / "dato.txt").unlink()  # Simula perdita o cancellazione accidentale del repository.
            risultato = VerificatoreIntegritaAvanzata().verifica_versione(radice / "versioni", backup.manifesto.id_backup)  # Controlla la recuperabilità.
            self.assertFalse(risultato.integro)  # La versione incompleta deve fallire.
            self.assertIn("Payload mancante: dato.txt", risultato.errori)  # Richiede l'identificazione esatta del dato perso.

    def test_catena_incrementale_verifica_payload_provenienti_da_versioni_diverse(self):
        """La verifica di un Incrementale deve seguire l'intera catena e controllare le origini finali corrette."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola Full e Incrementale.
            radice = Path(temporanea)  # Prepara la radice del test.
            sorgente = radice / "sorgente"  # Definisce la sorgente comune.
            versioni = radice / "versioni"  # Definisce il repository versionato.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "stabile.txt").write_text("stabile", encoding="utf-8")  # Crea un file che resterà nel Full.
            completo = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, versioni)  # Crea la base della catena.
            (sorgente / "nuovo.txt").write_text("nuovo", encoding="utf-8")  # Introduce un file presente soltanto nell'Incrementale.
            incrementale = MotoreBackupAvanzato(threading.Event()).esegui_incrementale(sorgente, versioni, completo.manifesto)  # Crea il delta collegato al Full.
            risultato = VerificatoreIntegritaAvanzata().verifica_versione(versioni, incrementale.manifesto.id_backup)  # Verifica lo snapshot finale attraverso entrambe le versioni.
            self.assertTrue(risultato.integro)  # La catena completa deve risultare recuperabile.
            self.assertEqual(risultato.file_verificati, 2)  # Devono essere verificati sia il payload del Full sia quello dell'Incrementale.
            self.assertEqual(risultato.versioni_catena, 2)  # Il report deve dichiarare la dipendenza da due versioni.

    def test_stop_interrompe_la_verifica_senza_dichiararla_integra(self):
        """Uno Stop già impostato deve produrre uno stato annullato e mai un falso esito positivo."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il controllo dello Stop.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "dato.txt").write_text("dato", encoding="utf-8")  # Crea un payload da verificare.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce una versione valida.
            evento = threading.Event()  # Crea l'evento cooperativo dedicato alla verifica.
            evento.set()  # Richiede l'arresto prima della lettura del primo payload.
            risultato = VerificatoreIntegritaAvanzata(evento).verifica_versione(radice / "versioni", backup.manifesto.id_backup)  # Avvia il controllo già annullato.
            self.assertTrue(risultato.annullato)  # Richiede che lo Stop venga esposto nel report.
            self.assertFalse(risultato.integro)  # Una verifica incompleta non deve essere promossa a integra.
            self.assertEqual(risultato.file_verificati, 0)  # Nessun payload deve essere letto dopo lo Stop preventivo.

    def test_eventi_di_progresso_raggiungono_la_fine(self):
        """Il verificatore deve esporre inizio, avanzamento e fine per la futura integrazione GUI."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il test degli eventi.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la sorgente.
            contenuto = b"x" * 1024  # Crea un payload con dimensione nota.
            (sorgente / "dato.bin").write_bytes(contenuto)  # Materializza il file.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce il Full.
            eventi = []  # Raccoglie gli eventi strutturati emessi dal verificatore.
            risultato = VerificatoreIntegritaAvanzata(funzione_avanzamento=lambda evento, dati: eventi.append((evento, dati))).verifica_versione(radice / "versioni", backup.manifesto.id_backup)  # Esegue la verifica con callback.
            self.assertTrue(risultato.integro)  # Conferma che il controllo di prova sia valido.
            self.assertEqual(eventi[0][0], "inizio_verifica")  # Richiede un evento iniziale con denominatori.
            self.assertEqual(eventi[-1][0], "fine_verifica")  # Richiede un evento conclusivo esplicito.
            avanzamenti = [dati for nome, dati in eventi if nome == "avanzamento_verifica"]  # Seleziona gli aggiornamenti numerici.
            self.assertEqual(avanzamenti[-1]["byte_elaborati"], len(contenuto))  # Richiede che il progresso raggiunga il totale logico.

    def test_stop_durante_file_grande_interrompe_tra_blocchi(self):
        """Lo Stop deve essere osservato anche durante l'hash di un singolo file e non soltanto tra file diversi."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola un payload abbastanza grande da richiedere più blocchi hash.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente del test.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "grande.bin").write_bytes(b"x" * (3 * 1024 * 1024))  # Crea tre MiB così il verificatore deve eseguire più letture.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce manifesto e payload validi.
            evento = threading.Event()  # Prepara lo Stop cooperativo.
            def osserva_progresso(nome_evento, dati):
                """Richiede lo Stop non appena il primo blocco del file è stato elaborato."""
                if nome_evento == "avanzamento_verifica" and dati.get("byte_elaborati", 0) > 0:  # Attende che l'hash sia realmente iniziato.
                    evento.set()  # Simula la pressione di Stop durante un file grande.
            risultato = VerificatoreIntegritaAvanzata(evento, osserva_progresso).verifica_versione(radice / "versioni", backup.manifesto.id_backup)  # Esegue il controllo con arresto durante il payload.
            self.assertTrue(risultato.annullato)  # Richiede uno stato esplicitamente incompleto.
            self.assertFalse(risultato.integro)  # Vieta un falso positivo dopo digest parziale.
            self.assertEqual(risultato.file_verificati, 0)  # Il file interrotto non deve essere contato come completamente verificato.
            self.assertGreater(risultato.byte_verificati, 0)  # Conferma che lo Stop sia avvenuto dopo l'inizio reale della lettura.
            self.assertLess(risultato.byte_verificati, 3 * 1024 * 1024)  # Conferma che il verificatore non abbia letto inutilmente l'intero file.


if __name__ == "__main__":
    unittest.main()
