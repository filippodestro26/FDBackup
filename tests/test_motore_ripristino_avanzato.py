import tempfile
import threading
import unittest
from pathlib import Path

from fdbackup.motore_backup_avanzato import MotoreBackupAvanzato
from fdbackup.motore_ripristino_avanzato import MotoreRipristinoAvanzato


class TestMotoreRipristinoAvanzato(unittest.TestCase):
    """Verifica la ricostruzione delle versioni avanzate e delle relative dipendenze."""

    def test_ripristina_catena_incrementale_con_eliminazione(self):
        """Ricostruisce lo stato finale usando Full e più incrementali, inclusa una cancellazione logica."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            versioni = radice / "versioni"
            destinazione = radice / "ripristino"
            sorgente.mkdir()
            (sorgente / "a.txt").write_text("A1", encoding="utf-8")
            (sorgente / "b.txt").write_text("B1", encoding="utf-8")
            backup = MotoreBackupAvanzato(threading.Event())
            full = backup.esegui_completo(sorgente, versioni)
            (sorgente / "a.txt").write_text("A2", encoding="utf-8")
            primo = backup.esegui_incrementale(sorgente, versioni, full.manifesto)
            (sorgente / "b.txt").unlink()
            (sorgente / "c.txt").write_text("C1", encoding="utf-8")
            secondo = backup.esegui_incrementale(sorgente, versioni, primo.manifesto)
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(versioni, secondo.manifesto.id_backup, destinazione)
            self.assertTrue(risultato.successo)
            self.assertEqual((destinazione / "a.txt").read_text(encoding="utf-8"), "A2")
            self.assertEqual((destinazione / "c.txt").read_text(encoding="utf-8"), "C1")
            self.assertFalse((destinazione / "b.txt").exists())

    def test_ripristina_differenziale_senza_incrementale_intermedio(self):
        """Ricostruisce un differenziale usando soltanto il Full e il differenziale selezionato."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            versioni = radice / "versioni"
            destinazione = radice / "ripristino"
            sorgente.mkdir()
            (sorgente / "a.txt").write_text("A1", encoding="utf-8")
            backup = MotoreBackupAvanzato(threading.Event())
            full = backup.esegui_completo(sorgente, versioni)
            (sorgente / "a.txt").write_text("A2", encoding="utf-8")
            (sorgente / "b.txt").write_text("B1", encoding="utf-8")
            differenziale = backup.esegui_differenziale(sorgente, versioni, full.manifesto)
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(versioni, differenziale.manifesto.id_backup, destinazione)
            self.assertTrue(risultato.successo)
            self.assertEqual((destinazione / "a.txt").read_text(encoding="utf-8"), "A2")
            self.assertEqual((destinazione / "b.txt").read_text(encoding="utf-8"), "B1")

    def test_ripristino_conservativo_non_sovrascrive_conflitto(self):
        """Conserva un file differente già presente quando sovrascrivi resta False."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            versioni = radice / "versioni"
            destinazione = radice / "ripristino"
            sorgente.mkdir()
            destinazione.mkdir()
            (sorgente / "a.txt").write_text("backup", encoding="utf-8")
            full = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, versioni)
            (destinazione / "a.txt").write_text("locale", encoding="utf-8")
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(versioni, full.manifesto.id_backup, destinazione)
            self.assertTrue(risultato.successo)
            self.assertEqual((destinazione / "a.txt").read_text(encoding="utf-8"), "locale")
            self.assertEqual(risultato.file_ignorati, 1)

    def test_ripristino_ricrea_cartelle_vuote_del_manifesto_finale(self):
        """Il ripristino deve ricostruire anche directory vuote presenti nello snapshot selezionato."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola sorgente, versioni e destinazione.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            (sorgente / "vuota" / "profonda").mkdir(parents=True)  # Crea una struttura senza payload.
            versioni = radice / "versioni"  # Definisce la radice versionata.
            full = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, versioni)  # Produce un manifesto che include le directory.
            destinazione = radice / "ripristino"  # Definisce una destinazione nuova.
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(versioni, full.manifesto.id_backup, destinazione)  # Ripristina il Full.
            self.assertTrue(risultato.successo)  # Richiede un ripristino senza errori.
            self.assertTrue((destinazione / "vuota" / "profonda").is_dir())  # Verifica la struttura vuota finale.

    def test_ripristino_differenziale_ricrea_cartella_vuota_nello_stato_finale(self):
        """Un differenziale senza file finali deve comunque ricreare le directory vuote presenti nella sorgente."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola l'intera catena dal filesystem del progetto.
            radice = Path(temporanea)  # Prepara la radice temporanea del test.
            sorgente = radice / "sorgente"  # Definisce la sorgente controllata.
            versioni = radice / "versioni"  # Definisce la radice delle versioni.
            destinazione = radice / "ripristino"  # Definisce una destinazione nuova.
            (sorgente / "cartella_vuota").mkdir(parents=True)  # Crea la directory vuota che deve sopravvivere al ripristino.
            file_originale = sorgente / "file_originale.txt"  # Definisce il file presente nel Full iniziale.
            file_originale.write_text("stato iniziale", encoding="utf-8")  # Materializza il payload iniziale.
            backup = MotoreBackupAvanzato(threading.Event())  # Crea il motore con Stop non attivato.
            full = backup.esegui_completo(sorgente, versioni)  # Crea la base Full che contiene file e directory vuota.
            file_originale.unlink()  # Elimina il file dalla sorgente per produrre un tombstone differenziale.
            differenziale = backup.esegui_differenziale(sorgente, versioni, full.manifesto)  # Crea uno snapshot finale composto soltanto dalla directory vuota.
            self.assertEqual(differenziale.manifesto.eliminati, ("file_originale.txt",))  # Verifica che il file del Full sia registrato come eliminato.
            self.assertEqual(differenziale.manifesto.cartelle, ("cartella_vuota",))  # Verifica che la directory vuota appartenga allo snapshot finale.
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(versioni, differenziale.manifesto.id_backup, destinazione)  # Ripristina esattamente il differenziale selezionato.
            self.assertTrue(risultato.successo)  # Richiede un recupero completo senza errori.
            self.assertFalse((destinazione / "file_originale.txt").exists())  # Richiede l'applicazione effettiva del tombstone.
            self.assertTrue((destinazione / "cartella_vuota").is_dir())  # Richiede la ricostruzione della directory vuota finale.

    def test_ripristino_notifica_progresso_determinato(self):
        """Il motore deve comunicare totale e avanzamento senza dipendere dalla GUI."""
        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice = Path(cartella_temporanea)
            sorgente = radice / "sorgente"
            versioni = radice / "versioni"
            destinazione = radice / "ripristino"
            sorgente.mkdir()
            (sorgente / "a.txt").write_text("abc", encoding="utf-8")
            motore_backup = MotoreBackupAvanzato(threading.Event())
            risultato_backup = motore_backup.esegui_completo(sorgente, versioni)
            eventi = []
            motore = MotoreRipristinoAvanzato(threading.Event(), funzione_avanzamento=lambda evento, dati: eventi.append((evento, dati)))
            risultato = motore.ripristina(versioni, risultato_backup.manifesto.id_backup, destinazione)
            self.assertTrue(risultato.successo)
            self.assertEqual(eventi[0][0], "inizio_ripristino")
            self.assertEqual(eventi[0][1]["totale_byte"], 3)
            self.assertEqual(eventi[-1][0], "avanzamento_ripristino")
            self.assertEqual(eventi[-1][1]["byte_elaborati"], 3)

    def test_manifesto_con_percorso_traversal_viene_rifiutato(self):
        """Un manifesto alterato non deve poter scrivere o leggere fuori dalla radice controllata."""
        import json  # Importa JSON localmente per mantenere il test indipendente dall'implementazione interna.
        with tempfile.TemporaryDirectory() as temporanea:  # Isola repository e possibile bersaglio esterno.
            radice = Path(temporanea)  # Prepara la radice del test.
            sorgente = radice / "sorgente"  # Definisce la sorgente valida iniziale.
            versioni = radice / "versioni"  # Definisce il repository versionato.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "dato.txt").write_text("dato", encoding="utf-8")  # Crea un file legittimo per ottenere un manifesto reale.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, versioni)  # Produce una versione valida da alterare.
            cartella = next(versioni.glob("*/.backupcore-manifesto.json")).parent  # Risolve l’unica directory fisica prodotta dal Full di questo test isolato.
            percorso_manifesto = cartella / ".backupcore-manifesto.json"  # Identifica il documento da corrompere intenzionalmente.
            dati = json.loads(percorso_manifesto.read_text(encoding="utf-8"))  # Carica il JSON per modificare esclusivamente il percorso logico.
            voce = dati["file"].pop("dato.txt")  # Rimuove la chiave sicura originale.
            voce["percorso_relativo"] = "../fuori.txt"  # Corrompe anche il percorso interno per simulare un manifesto ostile coerente con se stesso.
            dati["file"]["../fuori.txt"] = voce  # Inserisce un traversal che non deve raggiungere il filesystem.
            percorso_manifesto.write_text(json.dumps(dati), encoding="utf-8")  # Salva il documento alterato.
            with self.assertRaisesRegex(ValueError, "non sicuro"):  # Richiede un rifiuto esplicito prima della materializzazione.
                MotoreRipristinoAvanzato(threading.Event()).ripristina(versioni, backup.manifesto.id_backup, radice / "ripristino")  # Tenta il ripristino della versione compromessa.
            self.assertFalse((radice / "fuori.txt").exists())  # Conferma che nessun percorso esterno sia stato materializzato.

    def test_ripristino_selettivo_di_un_singolo_file(self):
        """Il motore deve poter recuperare un solo file senza materializzare gli altri elementi della versione."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola sorgente, repository e destinazione.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente del Full.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "a.txt").write_text("A", encoding="utf-8")  # Crea il file richiesto.
            (sorgente / "b.txt").write_text("B", encoding="utf-8")  # Crea un file che deve restare escluso.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce una versione reale.
            destinazione = radice / "ripristino"  # Definisce la destinazione selettiva.
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(radice / "versioni", backup.manifesto.id_backup, destinazione, selezione=["a.txt"])  # Richiede soltanto il primo file.
            self.assertTrue(risultato.successo)  # Il recupero selettivo deve concludersi senza errori.
            self.assertEqual((destinazione / "a.txt").read_text(encoding="utf-8"), "A")  # Verifica il contenuto richiesto.
            self.assertFalse((destinazione / "b.txt").exists())  # Conferma che il file non selezionato non sia stato materializzato.
            self.assertEqual(risultato.file_ripristinati, 1)  # Richiede contatori coerenti con la selezione.

    def test_ripristino_selettivo_di_cartella_include_discendenti(self):
        """La selezione di una cartella deve recuperare tutti e soltanto i relativi discendenti."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il layout del test.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            (sorgente / "documenti" / "sotto").mkdir(parents=True)  # Crea una gerarchia selezionabile.
            (sorgente / "documenti" / "uno.txt").write_text("1", encoding="utf-8")  # Crea un file diretto della cartella.
            (sorgente / "documenti" / "sotto" / "due.txt").write_text("2", encoding="utf-8")  # Crea un discendente annidato.
            (sorgente / "fuori.txt").write_text("X", encoding="utf-8")  # Crea un file esterno alla selezione.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce il Full.
            destinazione = radice / "ripristino"  # Definisce la destinazione.
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(radice / "versioni", backup.manifesto.id_backup, destinazione, selezione=["documenti"])  # Seleziona l'intero ramo.
            self.assertTrue(risultato.successo)  # Richiede un recupero valido.
            self.assertTrue((destinazione / "documenti" / "uno.txt").is_file())  # Verifica il file diretto.
            self.assertTrue((destinazione / "documenti" / "sotto" / "due.txt").is_file())  # Verifica il discendente annidato.
            self.assertFalse((destinazione / "fuori.txt").exists())  # Conferma l'esclusione del file esterno.

    def test_ripristino_selettivo_preserva_cartella_vuota(self):
        """Una directory vuota selezionata deve essere ricreata anche in assenza di file."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola la struttura vuota.
            radice = Path(temporanea)  # Prepara la radice del test.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            (sorgente / "vuota" / "annidata").mkdir(parents=True)  # Crea una directory realmente vuota nello snapshot.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Registra la struttura nel manifesto.
            destinazione = radice / "ripristino"  # Definisce la destinazione.
            risultato = MotoreRipristinoAvanzato(threading.Event()).ripristina(radice / "versioni", backup.manifesto.id_backup, destinazione, selezione=["vuota"])  # Richiede il ramo vuoto.
            self.assertTrue(risultato.successo)  # La sola struttura di directory è un ripristino valido.
            self.assertTrue((destinazione / "vuota" / "annidata").is_dir())  # Verifica la ricostruzione completa del ramo vuoto.

    def test_ripristino_selettivo_inesistente_viene_rifiutato(self):
        """Una selezione che non appartiene allo snapshot non deve produrre un falso successo vuoto."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il caso negativo.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "presente.txt").write_text("dato", encoding="utf-8")  # Crea l'unico elemento valido.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce il Full.
            with self.assertRaisesRegex(ValueError, "non esiste"):  # Richiede un errore leggibile per la selezione inesistente.
                MotoreRipristinoAvanzato(threading.Event()).ripristina(radice / "versioni", backup.manifesto.id_backup, radice / "ripristino", selezione=["assente.txt"])  # Tenta un recupero privo di corrispondenze.

    def test_ripristino_selettivo_rifiuta_traversal(self):
        """Anche l'input di selezione deve restare confinato alla versione e alla destinazione."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il controllo di sicurezza.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la sorgente.
            (sorgente / "dato.txt").write_text("dato", encoding="utf-8")  # Crea un contenuto valido.
            backup = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, radice / "versioni")  # Produce il Full.
            with self.assertRaisesRegex(ValueError, "non sicuro"):  # Richiede il blocco del traversal prima di qualsiasi copia.
                MotoreRipristinoAvanzato(threading.Event()).ripristina(radice / "versioni", backup.manifesto.id_backup, radice / "ripristino", selezione=["../dato.txt"])  # Tenta di uscire dalla radice logica.


if __name__ == "__main__":
    unittest.main()
