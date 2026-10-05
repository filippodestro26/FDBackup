import tempfile  # Importa gli strumenti per creare cartelle temporanee usate esclusivamente durante i test.
import threading  # Importa gli strumenti necessari per creare l'evento di arresto del motore.
import unittest  # Importa il framework di test automatici incluso nella libreria standard di Python.
from pathlib import Path  # Importa Path per gestire i percorsi di file e cartelle.
from unittest.mock import patch  # Importa patch per simulare copie corrotte e controllare le chiamate SHA-256.

from fdbackup.motore_backup import MotoreBackup  # Importa il motore reale di FDBackup da sottoporre ai test.


class TestMotoreBackup(unittest.TestCase):
    """Contiene i test automatici dedicati al motore di FDBackup."""

    def test_copia_file_nuovo(self) -> None:
        """Verifica che un file nuovo venga copiato correttamente nella destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce il file sorgente usato dal test.
            file_sorgente = sorgente / "prova.txt"

            # Scrive nel file un contenuto conosciuto.
            file_sorgente.write_text(
                "Test automatico FDBackup",
                encoding="utf-8",
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di backup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il backup.
            risultato = motore.esegui(sorgente, destinazione)

            # Costruisce il percorso atteso del file nella destinazione.
            file_destinazione = destinazione / "prova.txt"

            # Verifica che il file sia stato creato nella destinazione.
            self.assertTrue(file_destinazione.is_file())

            # Verifica che il contenuto sorgente e destinazione coincida.
            self.assertEqual(
                file_sorgente.read_text(encoding="utf-8"),
                file_destinazione.read_text(encoding="utf-8"),
            )

            # Verifica che sia stato trovato esattamente un file.
            self.assertEqual(risultato.file_trovati, 1)

            # Verifica che sia stato copiato esattamente un file.
            self.assertEqual(risultato.file_copiati, 1)

            # Verifica che nessun file sia stato ignorato come già identico.
            self.assertEqual(risultato.file_ignorati, 0)

            # Verifica che nessun file abbia prodotto errori.
            self.assertEqual(risultato.file_falliti, 0)

            # Verifica che il backup sia considerato riuscito.
            self.assertTrue(risultato.successo)

    def test_secondo_backup_riconosce_file_identico(self) -> None:
        """Verifica che un secondo backup non ricopi un file rimasto invariato."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce il file sorgente che verrà sottoposto a due backup.
            file_sorgente = sorgente / "prova.txt"

            # Scrive un contenuto conosciuto nel file sorgente.
            file_sorgente.write_text(
                "File che non cambia tra due backup",
                encoding="utf-8",
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore.
            motore = MotoreBackup(evento_arresto)

            # Esegue il primo backup per creare il file nella destinazione.
            primo_risultato = motore.esegui(sorgente, destinazione)

            # Esegue immediatamente un secondo backup senza modificare il file.
            secondo_risultato = motore.esegui(sorgente, destinazione)

            # Verifica che il primo backup abbia effettivamente copiato il file.
            self.assertEqual(primo_risultato.file_copiati, 1)

            # Verifica che il secondo backup abbia trovato esattamente un file.
            self.assertEqual(secondo_risultato.file_trovati, 1)

            # Verifica che il secondo backup non abbia eseguito copie inutili.
            self.assertEqual(secondo_risultato.file_copiati, 0)

            # Verifica che il file sia stato riconosciuto come già identico.
            self.assertEqual(secondo_risultato.file_ignorati, 1)

            # Verifica che il secondo backup non abbia prodotto errori.
            self.assertEqual(secondo_risultato.file_falliti, 0)

            # Verifica che anche il secondo backup sia considerato riuscito.
            self.assertTrue(secondo_risultato.successo)

    def test_modifica_stessa_dimensione_viene_rilevata(self) -> None:
        """Verifica che una modifica del contenuto venga rilevata anche quando la dimensione non cambia."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce il file sorgente che verrà modificato durante il test.
            file_sorgente = sorgente / "prova.txt"

            # Scrive il primo contenuto di quattro byte nel file sorgente.
            file_sorgente.write_text(
                "AAAA",
                encoding="utf-8",
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il primo backup per creare la copia iniziale.
            primo_risultato = motore.esegui(sorgente, destinazione)

            # Definisce il percorso del file creato nella destinazione.
            file_destinazione = destinazione / "prova.txt"

            # Verifica che il primo backup abbia copiato il file.
            self.assertEqual(primo_risultato.file_copiati, 1)

            # Verifica che la destinazione contenga inizialmente il primo contenuto.
            self.assertEqual(
                file_destinazione.read_text(encoding="utf-8"),
                "AAAA",
            )

            # Sostituisce il contenuto mantenendo invariata la dimensione.
            file_sorgente.write_text(
                "BBBB",
                encoding="utf-8",
            )

            # Verifica esplicitamente che sorgente e destinazione abbiano la stessa dimensione.
            self.assertEqual(
                file_sorgente.stat().st_size,
                file_destinazione.stat().st_size,
            )

            # Esegue il secondo backup dopo la modifica del contenuto.
            secondo_risultato = motore.esegui(sorgente, destinazione)

            # Verifica che il file modificato sia stato copiato nuovamente.
            self.assertEqual(secondo_risultato.file_copiati, 1)

            # Verifica che il file non sia stato erroneamente classificato come identico.
            self.assertEqual(secondo_risultato.file_ignorati, 0)

            # Verifica che non siano stati registrati errori.
            self.assertEqual(secondo_risultato.file_falliti, 0)

            # Verifica che la destinazione contenga ora il nuovo contenuto.
            self.assertEqual(
                file_destinazione.read_text(encoding="utf-8"),
                "BBBB",
            )

            # Verifica direttamente che SHA-256 di sorgente e destinazione coincidano dopo la copia.
            self.assertEqual(
                MotoreBackup.calcola_hash(file_sorgente),
                MotoreBackup.calcola_hash(file_destinazione),
            )

            # Verifica che il secondo backup sia considerato riuscito.
            self.assertTrue(secondo_risultato.successo)

    def test_copia_file_vuoto(self) -> None:
        """Verifica che un file vuoto da zero byte venga copiato e verificato correttamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce il percorso del file vuoto nella sorgente.
            file_sorgente = sorgente / "file_vuoto.txt"

            # Crea un file completamente vuoto.
            file_sorgente.touch()

            # Verifica che il file sorgente abbia realmente dimensione zero.
            self.assertEqual(file_sorgente.stat().st_size, 0)

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il backup del file vuoto.
            risultato = motore.esegui(sorgente, destinazione)

            # Costruisce il percorso atteso del file nella destinazione.
            file_destinazione = destinazione / "file_vuoto.txt"

            # Verifica che il file vuoto sia stato realmente creato nella destinazione.
            self.assertTrue(file_destinazione.is_file())

            # Verifica che anche il file copiato abbia dimensione zero.
            self.assertEqual(file_destinazione.stat().st_size, 0)

            # Verifica che il motore abbia trovato esattamente un file.
            self.assertEqual(risultato.file_trovati, 1)

            # Verifica che il file vuoto sia stato considerato correttamente copiato.
            self.assertEqual(risultato.file_copiati, 1)

            # Verifica che nessun file sia stato classificato come già identico.
            self.assertEqual(risultato.file_ignorati, 0)

            # Verifica che non siano stati registrati errori relativi ai file.
            self.assertEqual(risultato.file_falliti, 0)

            # Verifica che siano stati registrati zero byte copiati.
            self.assertEqual(risultato.byte_copiati, 0)

            # Verifica che SHA-256 della sorgente e della destinazione coincidano.
            self.assertEqual(
                MotoreBackup.calcola_hash(file_sorgente),
                MotoreBackup.calcola_hash(file_destinazione),
            )

            # Verifica che il risultato complessivo sia considerato positivo.
            self.assertTrue(risultato.successo)

    def test_crea_cartella_vuota(self) -> None:
        """Verifica che una cartella vuota venga ricreata correttamente nella destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce la sottocartella vuota che dovrà essere copiata.
            cartella_vuota_sorgente = sorgente / "cartella_vuota"

            # Crea fisicamente la sottocartella lasciandola completamente vuota.
            cartella_vuota_sorgente.mkdir()

            # Verifica che la cartella sorgente sia realmente vuota prima del backup.
            self.assertEqual(
                list(cartella_vuota_sorgente.iterdir()),
                [],
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il backup della struttura contenente la cartella vuota.
            risultato = motore.esegui(sorgente, destinazione)

            # Costruisce il percorso atteso della cartella vuota nella destinazione.
            cartella_vuota_destinazione = destinazione / "cartella_vuota"

            # Verifica che la sottocartella sia stata realmente creata nella destinazione.
            self.assertTrue(cartella_vuota_destinazione.is_dir())

            # Verifica che anche la cartella nella destinazione sia rimasta vuota.
            self.assertEqual(
                list(cartella_vuota_destinazione.iterdir()),
                [],
            )

            # Verifica che non siano stati trovati file durante il backup.
            self.assertEqual(risultato.file_trovati, 0)

            # Verifica che non siano stati copiati file.
            self.assertEqual(risultato.file_copiati, 0)

            # Verifica che sia stata individuata esattamente una sottocartella.
            self.assertEqual(risultato.cartelle_trovate, 1)

            # Verifica che sia stata creata esattamente una sottocartella.
            self.assertEqual(risultato.cartelle_create, 1)

            # Verifica che nessuna sottocartella abbia prodotto errori.
            self.assertEqual(risultato.cartelle_fallite, 0)

            # Verifica che il backup della cartella vuota sia considerato riuscito.
            self.assertTrue(risultato.successo)

    def test_crea_cartelle_vuote_nidificate(self) -> None:
        """Verifica che più livelli di cartelle vuote vengano ricreati correttamente nella destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce il primo livello della struttura di cartelle vuote.
            livello1 = sorgente / "livello1"

            # Definisce il secondo livello all'interno del primo.
            livello2 = livello1 / "livello2"

            # Definisce il terzo livello all'interno del secondo.
            livello3 = livello2 / "livello3"

            # Crea contemporaneamente tutti i livelli della struttura.
            livello3.mkdir(parents=True)

            # Verifica che la cartella più profonda sia realmente vuota.
            self.assertEqual(
                list(livello3.iterdir()),
                [],
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il backup della struttura di cartelle vuote.
            risultato = motore.esegui(sorgente, destinazione)

            # Costruisce il percorso atteso del primo livello nella destinazione.
            livello1_destinazione = destinazione / "livello1"

            # Costruisce il percorso atteso del secondo livello nella destinazione.
            livello2_destinazione = livello1_destinazione / "livello2"

            # Costruisce il percorso atteso del terzo livello nella destinazione.
            livello3_destinazione = livello2_destinazione / "livello3"

            # Verifica che il primo livello sia stato creato come directory.
            self.assertTrue(livello1_destinazione.is_dir())

            # Verifica che il secondo livello sia stato creato come directory.
            self.assertTrue(livello2_destinazione.is_dir())

            # Verifica che il terzo livello sia stato creato come directory.
            self.assertTrue(livello3_destinazione.is_dir())

            # Verifica che la cartella più profonda sia rimasta vuota.
            self.assertEqual(
                list(livello3_destinazione.iterdir()),
                [],
            )

            # Verifica che nessun file sia stato trovato.
            self.assertEqual(risultato.file_trovati, 0)

            # Verifica che nessun file sia stato copiato.
            self.assertEqual(risultato.file_copiati, 0)

            # Verifica che siano state individuate esattamente tre sottocartelle.
            self.assertEqual(risultato.cartelle_trovate, 3)

            # Verifica che siano state create esattamente tre sottocartelle.
            self.assertEqual(risultato.cartelle_create, 3)

            # Verifica che nessuna sottocartella fosse già presente nella destinazione.
            self.assertEqual(risultato.cartelle_esistenti, 0)

            # Verifica che nessuna sottocartella abbia prodotto errori.
            self.assertEqual(risultato.cartelle_fallite, 0)

            # Verifica che l'intera operazione sia considerata riuscita.
            self.assertTrue(risultato.successo)

    def test_rifiuta_sorgente_uguale_destinazione(self) -> None:
        """Verifica che il motore rifiuti un backup quando sorgente e destinazione coincidono."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce una cartella usata contemporaneamente come sorgente e destinazione.
            percorso_comune = radice_test / "cartella_comune"

            # Crea fisicamente la cartella utilizzata dal test.
            percorso_comune.mkdir()

            # Definisce un file per verificare che il contenuto non venga alterato.
            file_originale = percorso_comune / "prova.txt"

            # Scrive un contenuto conosciuto nel file originale.
            file_originale.write_text(
                "Questo file non deve essere modificato.",
                encoding="utf-8",
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Verifica che sorgente e destinazione uguali generino un ValueError.
            with self.assertRaises(ValueError) as contesto_errore:
                # Tenta volutamente di eseguire un backup non valido.
                motore.esegui(percorso_comune, percorso_comune)

            # Verifica che il messaggio dell'eccezione descriva esattamente il problema.
            self.assertEqual(
                str(contesto_errore.exception),
                "Sorgente e destinazione non possono coincidere.",
            )

            # Verifica che il file originale esista ancora.
            self.assertTrue(file_originale.is_file())

            # Verifica che il contenuto del file originale non sia stato modificato.
            self.assertEqual(
                file_originale.read_text(encoding="utf-8"),
                "Questo file non deve essere modificato.",
            )

    def test_rifiuta_destinazione_dentro_sorgente(self) -> None:
        """Verifica che il motore rifiuti una destinazione contenuta nella sorgente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella che verrà utilizzata come sorgente.
            sorgente = radice_test / "sorgente"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce un file nella sorgente per verificare che non venga modificato.
            file_originale = sorgente / "prova.txt"

            # Scrive un contenuto conosciuto nel file sorgente.
            file_originale.write_text(
                "Contenuto originale.",
                encoding="utf-8",
            )

            # Definisce volutamente la destinazione all'interno della sorgente.
            destinazione = sorgente / "backup_interno"

            # Verifica che la destinazione non esista prima dell'esecuzione.
            self.assertFalse(destinazione.exists())

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Verifica che il motore generi un ValueError prima di iniziare il backup.
            with self.assertRaises(ValueError) as contesto_errore:
                # Tenta volutamente di eseguire il backup con una configurazione non valida.
                motore.esegui(sorgente, destinazione)

            # Verifica che il messaggio dell'eccezione corrisponda alla protezione prevista.
            self.assertEqual(
                str(contesto_errore.exception),
                "La destinazione non può trovarsi all'interno della cartella sorgente.",
            )

            # Verifica che il motore non abbia creato la destinazione non valida.
            self.assertFalse(destinazione.exists())

            # Verifica che il file originale sia ancora presente.
            self.assertTrue(file_originale.is_file())

            # Verifica che il contenuto originale non sia stato modificato.
            self.assertEqual(
                file_originale.read_text(encoding="utf-8"),
                "Contenuto originale.",
            )

    def test_rifiuta_sorgente_inesistente(self) -> None:
        """Verifica che il motore rifiuti un percorso sorgente che non esiste."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce volutamente un percorso sorgente che non verrà creato.
            sorgente = radice_test / "sorgente_inesistente"

            # Definisce la destinazione che non dovrà essere creata dal motore.
            destinazione = radice_test / "destinazione"

            # Verifica che la sorgente sia realmente inesistente prima del test.
            self.assertFalse(sorgente.exists())

            # Verifica che anche la destinazione sia inesistente prima del test.
            self.assertFalse(destinazione.exists())

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Verifica che il motore generi un ValueError per la sorgente inesistente.
            with self.assertRaises(ValueError) as contesto_errore:
                # Tenta volutamente di eseguire un backup con una sorgente inesistente.
                motore.esegui(sorgente, destinazione)

            # Verifica che il messaggio identifichi precisamente il problema rilevato.
            self.assertEqual(
                str(contesto_errore.exception),
                "La cartella sorgente non esiste.",
            )

            # Verifica nuovamente che la sorgente non sia stata creata accidentalmente.
            self.assertFalse(sorgente.exists())

            # Verifica che la destinazione non sia stata creata prima del rifiuto.
            self.assertFalse(destinazione.exists())

    def test_rifiuta_sorgente_che_e_un_file(self) -> None:
        """Verifica che il motore rifiuti una sorgente esistente che non è una cartella."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce un percorso che verrà creato come normale file.
            sorgente = radice_test / "sorgente_file.txt"

            # Scrive un contenuto nel file che verrà volutamente usato come sorgente.
            sorgente.write_text(
                "Questo è un file e non una cartella.",
                encoding="utf-8",
            )

            # Definisce la destinazione che non dovrà essere creata.
            destinazione = radice_test / "destinazione"

            # Verifica che la sorgente esista realmente.
            self.assertTrue(sorgente.exists())

            # Verifica che la sorgente sia effettivamente un file.
            self.assertTrue(sorgente.is_file())

            # Verifica che la sorgente non sia una directory.
            self.assertFalse(sorgente.is_dir())

            # Verifica che la destinazione non esista prima dell'esecuzione.
            self.assertFalse(destinazione.exists())

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Verifica che il motore rifiuti il file utilizzato impropriamente come sorgente.
            with self.assertRaises(ValueError) as contesto_errore:
                # Tenta volutamente di avviare il backup usando un file come sorgente.
                motore.esegui(sorgente, destinazione)

            # Verifica che il messaggio dell'eccezione identifichi esattamente il problema.
            self.assertEqual(
                str(contesto_errore.exception),
                "La sorgente deve essere una cartella.",
            )

            # Verifica che il file sorgente esista ancora dopo il rifiuto.
            self.assertTrue(sorgente.is_file())

            # Verifica che il contenuto del file sorgente non sia stato modificato.
            self.assertEqual(
                sorgente.read_text(encoding="utf-8"),
                "Questo è un file e non una cartella.",
            )

            # Verifica che il motore non abbia creato la destinazione.
            self.assertFalse(destinazione.exists())

    def test_rifiuta_destinazione_che_e_un_file(self) -> None:
        """Verifica che il motore rifiuti una destinazione esistente che non è una cartella."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente valida utilizzata dal test.
            sorgente = radice_test / "sorgente"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce un file valido all'interno della sorgente.
            file_sorgente = sorgente / "prova.txt"

            # Scrive un contenuto conosciuto nel file sorgente.
            file_sorgente.write_text(
                "Contenuto che non deve essere copiato.",
                encoding="utf-8",
            )

            # Definisce il percorso che verrà impropriamente usato come destinazione.
            destinazione = radice_test / "destinazione"

            # Crea un normale file nel percorso destinato al backup.
            destinazione.write_text(
                "Contenuto originale della destinazione.",
                encoding="utf-8",
            )

            # Verifica che la sorgente sia una directory valida.
            self.assertTrue(sorgente.is_dir())

            # Verifica che il percorso di destinazione esista realmente.
            self.assertTrue(destinazione.exists())

            # Verifica che la destinazione sia un file e non una cartella.
            self.assertTrue(destinazione.is_file())

            # Memorizza il contenuto originale della destinazione prima del tentativo.
            contenuto_destinazione_originale = destinazione.read_text(
                encoding="utf-8",
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Verifica che il motore rifiuti una destinazione esistente che è un file.
            with self.assertRaises(ValueError) as contesto_errore:
                # Tenta volutamente di avviare il backup verso un file.
                motore.esegui(sorgente, destinazione)

            # Verifica il messaggio realmente previsto dal motore.
            self.assertEqual(
                str(contesto_errore.exception),
                "La destinazione esiste ma non è una cartella.",
            )

            # Verifica che il percorso di destinazione sia ancora un normale file.
            self.assertTrue(destinazione.is_file())

            # Verifica che il contenuto originale della destinazione non sia stato modificato.
            self.assertEqual(
                destinazione.read_text(encoding="utf-8"),
                contenuto_destinazione_originale,
            )

            # Verifica che anche il file presente nella sorgente sia rimasto invariato.
            self.assertEqual(
                file_sorgente.read_text(encoding="utf-8"),
                "Contenuto che non deve essere copiato.",
            )

    def test_conflitto_file_cartella(self) -> None:
        """Verifica che un file nella destinazione non possa sostituire una cartella richiesta dalla sorgente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente principale.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione principale.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente principale.
            sorgente.mkdir()

            # Crea fisicamente la cartella destinazione principale.
            destinazione.mkdir()

            # Definisce nella sorgente una sottocartella che dovrà essere ricreata.
            cartella_conflitto_sorgente = sorgente / "test_conflitto"

            # Crea la sottocartella nella sorgente.
            cartella_conflitto_sorgente.mkdir()

            # Definisce un file all'interno della sottocartella sorgente.
            file_interno_sorgente = cartella_conflitto_sorgente / "prova.txt"

            # Scrive un contenuto nel file per verificare che il motore non possa elaborarlo.
            file_interno_sorgente.write_text(
                "Questo file si trova dentro la cartella in conflitto.",
                encoding="utf-8",
            )

            # Definisce nella destinazione lo stesso percorso della sottocartella sorgente.
            percorso_conflitto_destinazione = destinazione / "test_conflitto"

            # Crea però un normale file al posto della directory richiesta.
            percorso_conflitto_destinazione.write_text(
                "Questo file non deve essere modificato o eliminato.",
                encoding="utf-8",
            )

            # Memorizza il contenuto originale del file in conflitto.
            contenuto_originale = percorso_conflitto_destinazione.read_text(
                encoding="utf-8",
            )

            # Verifica che nella sorgente l'oggetto sia realmente una directory.
            self.assertTrue(cartella_conflitto_sorgente.is_dir())

            # Verifica che nella destinazione l'oggetto con lo stesso nome sia realmente un file.
            self.assertTrue(percorso_conflitto_destinazione.is_file())

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il backup e conserva il risultato restituito dal motore.
            risultato = motore.esegui(sorgente, destinazione)

            # Verifica che il motore abbia individuato la sottocartella sorgente.
            self.assertEqual(risultato.cartelle_trovate, 1)

            # Verifica che la cartella in conflitto non sia stata considerata creata.
            self.assertEqual(risultato.cartelle_create, 0)

            # Verifica che la cartella in conflitto non sia stata considerata già esistente correttamente.
            self.assertEqual(risultato.cartelle_esistenti, 0)

            # Verifica che il conflitto sia stato registrato come una cartella fallita.
            self.assertEqual(risultato.cartelle_fallite, 1)

            # Verifica che nessun file interno alla cartella non preparabile sia stato elaborato.
            self.assertEqual(risultato.file_trovati, 0)

            # Verifica che nessun file sia stato copiato.
            self.assertEqual(risultato.file_copiati, 0)

            # Verifica che nessun file sia stato classificato come identico.
            self.assertEqual(risultato.file_ignorati, 0)

            # Verifica che non venga registrato un errore di file separato dal conflitto della cartella.
            self.assertEqual(risultato.file_falliti, 0)

            # Verifica che il motore abbia conservato esattamente un errore diagnostico.
            self.assertEqual(len(risultato.errori), 1)

            # Verifica che il tipo di errore registrato sia NotADirectoryError.
            self.assertIn(
                "NotADirectoryError",
                risultato.errori[0],
            )

            # Verifica che il messaggio registrato descriva il conflitto con un oggetto non-directory.
            self.assertIn(
                "Il percorso di destinazione esiste ma non è una cartella:",
                risultato.errori[0],
            )

            # Verifica che il file preesistente nella destinazione esista ancora.
            self.assertTrue(percorso_conflitto_destinazione.is_file())

            # Verifica che il file preesistente nella destinazione non sia stato modificato.
            self.assertEqual(
                percorso_conflitto_destinazione.read_text(encoding="utf-8"),
                contenuto_originale,
            )

            # Verifica che il motore non abbia creato il file interno sotto il percorso in conflitto.
            self.assertFalse(
                (percorso_conflitto_destinazione / "prova.txt").exists(),
            )

            # Verifica che il backup complessivo non venga considerato riuscito.
            self.assertFalse(risultato.successo)

            # Verifica che il backup non venga erroneamente classificato come annullato.
            self.assertFalse(risultato.annullato)

    def test_file_eliminato_dalla_sorgente_rimane_nella_destinazione(self) -> None:
        """Verifica che un file eliminato dalla sorgente non venga cancellato dalla destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce il file che verrà inizialmente sottoposto a backup.
            file_sorgente = sorgente / "file_da_eliminare.txt"

            # Scrive un contenuto conosciuto nel file sorgente.
            file_sorgente.write_text(
                "Questo contenuto deve rimanere nella destinazione.",
                encoding="utf-8",
            )

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il primo backup per creare il file nella destinazione.
            primo_risultato = motore.esegui(sorgente, destinazione)

            # Costruisce il percorso del file copiato nella destinazione.
            file_destinazione = destinazione / "file_da_eliminare.txt"

            # Verifica che il primo backup abbia copiato esattamente un file.
            self.assertEqual(primo_risultato.file_copiati, 1)

            # Verifica che il primo backup non abbia prodotto errori.
            self.assertEqual(primo_risultato.file_falliti, 0)

            # Verifica che il file esista realmente nella destinazione dopo il primo backup.
            self.assertTrue(file_destinazione.is_file())

            # Memorizza il contenuto presente nella destinazione prima dell'eliminazione dalla sorgente.
            contenuto_destinazione = file_destinazione.read_text(
                encoding="utf-8",
            )

            # Elimina il file esclusivamente dalla cartella sorgente.
            file_sorgente.unlink()

            # Verifica che il file non esista più nella sorgente.
            self.assertFalse(file_sorgente.exists())

            # Verifica che la copia precedente sia ancora presente nella destinazione.
            self.assertTrue(file_destinazione.is_file())

            # Esegue un secondo backup dopo l'eliminazione del file dalla sorgente.
            secondo_risultato = motore.esegui(sorgente, destinazione)

            # Verifica che il secondo backup non trovi più alcun file nella sorgente.
            self.assertEqual(secondo_risultato.file_trovati, 0)

            # Verifica che il secondo backup non copi alcun file.
            self.assertEqual(secondo_risultato.file_copiati, 0)

            # Verifica che nessun file venga classificato come identico.
            self.assertEqual(secondo_risultato.file_ignorati, 0)

            # Verifica che il secondo backup non registri errori relativi ai file.
            self.assertEqual(secondo_risultato.file_falliti, 0)

            # Verifica che il file precedentemente copiato esista ancora nella destinazione.
            self.assertTrue(file_destinazione.is_file())

            # Verifica che il contenuto del file rimasto nella destinazione non sia stato alterato.
            self.assertEqual(
                file_destinazione.read_text(encoding="utf-8"),
                contenuto_destinazione,
            )

            # Verifica che il secondo backup non abbia registrato errori.
            self.assertEqual(secondo_risultato.errori, [])

            # Verifica che il secondo backup non sia stato annullato.
            self.assertFalse(secondo_risultato.annullato)

            # Verifica che il secondo backup venga considerato completato correttamente.
            self.assertTrue(secondo_risultato.successo)

    def test_contatori_cartelle_esistenti(self) -> None:
        """Verifica che le sottocartelle già presenti nella destinazione vengano conteggiate correttamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente principale.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione principale.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente principale.
            sorgente.mkdir()

            # Crea fisicamente la cartella destinazione principale.
            destinazione.mkdir()

            # Definisce una sottocartella presente nella sorgente.
            cartella_esistente_sorgente = sorgente / "cartella_esistente"

            # Crea fisicamente la sottocartella nella sorgente.
            cartella_esistente_sorgente.mkdir()

            # Definisce il percorso equivalente nella destinazione.
            cartella_esistente_destinazione = destinazione / "cartella_esistente"

            # Crea preventivamente la stessa sottocartella nella destinazione.
            cartella_esistente_destinazione.mkdir()

            # Verifica che la sottocartella sorgente sia realmente una directory.
            self.assertTrue(cartella_esistente_sorgente.is_dir())

            # Verifica che la sottocartella destinazione esista già prima del backup.
            self.assertTrue(cartella_esistente_destinazione.is_dir())

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea un'istanza reale del motore di FDBackup.
            motore = MotoreBackup(evento_arresto)

            # Esegue il backup della struttura contenente la sottocartella già esistente.
            risultato = motore.esegui(sorgente, destinazione)

            # Verifica che sia stata trovata esattamente una sottocartella.
            self.assertEqual(risultato.cartelle_trovate, 1)

            # Verifica che nessuna nuova sottocartella sia stata creata.
            self.assertEqual(risultato.cartelle_create, 0)

            # Verifica che la sottocartella già presente sia stata conteggiata come esistente.
            self.assertEqual(risultato.cartelle_esistenti, 1)

            # Verifica che nessuna cartella abbia prodotto errori.
            self.assertEqual(risultato.cartelle_fallite, 0)

            # Verifica che nessun file sia stato trovato.
            self.assertEqual(risultato.file_trovati, 0)

            # Verifica che nessun file sia stato copiato.
            self.assertEqual(risultato.file_copiati, 0)

            # Verifica che nessun file sia stato classificato come identico.
            self.assertEqual(risultato.file_ignorati, 0)

            # Verifica che nessun file abbia prodotto errori.
            self.assertEqual(risultato.file_falliti, 0)

            # Verifica che la lista degli errori sia vuota.
            self.assertEqual(risultato.errori, [])

            # Verifica che il backup non sia stato annullato.
            self.assertFalse(risultato.annullato)

            # Verifica che il backup venga considerato riuscito.
            self.assertTrue(risultato.successo)

            # Verifica che la sottocartella preesistente continui a essere una directory.
            self.assertTrue(cartella_esistente_destinazione.is_dir())

    def test_stop_prima_dellesecuzione(self) -> None:
        """Verifica che uno Stop già richiesto impedisca l'elaborazione dei file."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce un file che sarebbe normalmente elaborato dal backup.
            file_sorgente = sorgente / "file_non_da_copiare.txt"

            # Scrive un contenuto conosciuto nel file sorgente.
            file_sorgente.write_text(
                "Questo file non deve essere elaborato perché lo Stop è già attivo.",
                encoding="utf-8",
            )

            # Verifica che il file sorgente esista realmente prima del test.
            self.assertTrue(file_sorgente.is_file())

            # Crea l'evento di arresto che verrà passato al motore.
            evento_arresto = threading.Event()

            # Attiva l'evento prima dell'avvio del backup per simulare uno Stop già richiesto.
            evento_arresto.set()

            # Verifica che l'evento di arresto risulti effettivamente attivo.
            self.assertTrue(evento_arresto.is_set())

            # Crea il motore utilizzando l'evento di arresto già attivato.
            motore = MotoreBackup(evento_arresto)

            # Esegue il backup con la richiesta di arresto già presente.
            risultato = motore.esegui(sorgente, destinazione)

            # Verifica che il risultato registri correttamente l'annullamento.
            self.assertTrue(risultato.annullato)

            # Verifica che nessun file sia stato conteggiato come trovato.
            self.assertEqual(risultato.file_trovati, 0)

            # Verifica che nessun file sia stato copiato.
            self.assertEqual(risultato.file_copiati, 0)

            # Verifica che nessun file sia stato classificato come identico.
            self.assertEqual(risultato.file_ignorati, 0)

            # Verifica che nessun file sia stato classificato come fallito.
            self.assertEqual(risultato.file_falliti, 0)

            # Verifica che non siano stati conteggiati byte copiati.
            self.assertEqual(risultato.byte_copiati, 0)

            # Verifica che nessuna sottocartella sia stata elaborata.
            self.assertEqual(risultato.cartelle_trovate, 0)

            # Verifica che nessuna sottocartella sia stata creata.
            self.assertEqual(risultato.cartelle_create, 0)

            # Verifica che nessuna sottocartella sia stata conteggiata come già esistente.
            self.assertEqual(risultato.cartelle_esistenti, 0)

            # Verifica che nessuna cartella abbia prodotto errori.
            self.assertEqual(risultato.cartelle_fallite, 0)

            # Verifica che l'annullamento volontario non venga registrato come errore.
            self.assertEqual(risultato.errori, [])

            # Costruisce il percorso che il file avrebbe avuto nella destinazione.
            file_destinazione = destinazione / "file_non_da_copiare.txt"

            # Verifica che il file non sia stato copiato nella destinazione.
            self.assertFalse(file_destinazione.exists())

            # Verifica che un backup annullato non venga considerato riuscito.
            self.assertFalse(risultato.successo)

            # Verifica che il file originale nella sorgente sia rimasto presente.
            self.assertTrue(file_sorgente.is_file())

            # Verifica che il contenuto originale del file sorgente non sia stato modificato.
            self.assertEqual(
                file_sorgente.read_text(encoding="utf-8"),
                "Questo file non deve essere elaborato perché lo Stop è già attivo.",
            )


    def test_eventi_callback_motore(self) -> None:
        """Verifica che il motore invii alla callback gli eventi e i dati previsti durante copia e confronto."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            # Converte il percorso temporaneo principale in un oggetto Path.
            radice_test = Path(cartella_temporanea)

            # Definisce la cartella sorgente dell'ambiente di test.
            sorgente = radice_test / "sorgente"

            # Definisce la cartella destinazione dell'ambiente di test.
            destinazione = radice_test / "destinazione"

            # Crea fisicamente la cartella sorgente.
            sorgente.mkdir()

            # Definisce il file che verrà utilizzato per verificare gli eventi del motore.
            file_sorgente = sorgente / "prova_callback.txt"

            # Definisce un contenuto conosciuto per poter verificare anche il numero di byte copiati.
            contenuto_file = "Test callback FDBackup"

            # Scrive il contenuto conosciuto nel file sorgente.
            file_sorgente.write_text(
                contenuto_file,
                encoding="utf-8",
            )

            # Crea una lista che conserverà gli eventi ricevuti durante la prima esecuzione.
            eventi_prima_esecuzione = []

            # Definisce la callback utilizzata durante la prima esecuzione del backup.
            def callback_prima_esecuzione(evento: str, dati: dict) -> None:
                """Registra il nome dell'evento e i relativi dati ricevuti dal motore."""
                eventi_prima_esecuzione.append((evento, dati))

            # Crea l'evento di arresto richiesto dal motore.
            evento_arresto = threading.Event()

            # Crea il motore collegandolo alla callback della prima esecuzione.
            motore_prima_esecuzione = MotoreBackup(
                evento_arresto,
                callback_prima_esecuzione,
            )

            # Esegue il primo backup, nel quale il file deve essere copiato.
            primo_risultato = motore_prima_esecuzione.esegui(
                sorgente,
                destinazione,
            )

            # Estrae soltanto i nomi degli eventi ricevuti durante la prima esecuzione.
            nomi_eventi_prima_esecuzione = [
                evento
                for evento, dati in eventi_prima_esecuzione
            ]

            # Verifica l'esatta sequenza degli eventi prevista per la copia di un file nuovo.
            self.assertEqual(
                nomi_eventi_prima_esecuzione,
                [
                    "inizio",
                    "file",
                    "copiato",
                    "fine",
                ],
            )

            # Recupera i dati associati all'evento iniziale.
            dati_inizio_prima_esecuzione = eventi_prima_esecuzione[0][1]

            # Verifica che l'evento iniziale contenga il percorso corretto della sorgente.
            self.assertEqual(
                dati_inizio_prima_esecuzione["sorgente"],
                str(sorgente),
            )

            # Verifica che l'evento iniziale contenga il percorso corretto della destinazione.
            self.assertEqual(
                dati_inizio_prima_esecuzione["destinazione"],
                str(destinazione),
            )

            # Recupera i dati associati all'evento che segnala il file in elaborazione.
            dati_file_prima_esecuzione = eventi_prima_esecuzione[1][1]

            # Verifica che il percorso relativo comunicato per il file sia corretto.
            self.assertEqual(
                dati_file_prima_esecuzione["file"],
                "prova_callback.txt",
            )

            # Verifica che il contatore dei file trovati sia già stato incrementato.
            self.assertEqual(
                dati_file_prima_esecuzione["trovati"],
                1,
            )

            # Verifica che prima della copia nessun file risulti ancora copiato.
            self.assertEqual(
                dati_file_prima_esecuzione["copiati"],
                0,
            )

            # Verifica che prima della copia nessun file risulti ignorato.
            self.assertEqual(
                dati_file_prima_esecuzione["ignorati"],
                0,
            )

            # Verifica che prima della copia nessun file risulti fallito.
            self.assertEqual(
                dati_file_prima_esecuzione["falliti"],
                0,
            )

            # Recupera i dati associati all'evento di copia completata.
            dati_copiato_prima_esecuzione = eventi_prima_esecuzione[2][1]

            # Verifica che l'evento di copia faccia riferimento al file corretto.
            self.assertEqual(
                dati_copiato_prima_esecuzione["file"],
                "prova_callback.txt",
            )

            # Calcola il numero di byte realmente occupati dal contenuto UTF-8 scritto nel file.
            byte_attesi = len(contenuto_file.encode("utf-8"))

            # Verifica che l'evento di copia comunichi il numero corretto di byte copiati.
            self.assertEqual(
                dati_copiato_prima_esecuzione["byte"],
                byte_attesi,
            )

            # Recupera i dati associati all'evento finale della prima esecuzione.
            dati_fine_prima_esecuzione = eventi_prima_esecuzione[3][1]

            # Verifica che la callback finale riceva lo stesso oggetto risultato restituito da esegui.
            self.assertIs(
                dati_fine_prima_esecuzione["risultato"],
                primo_risultato,
            )

            # Verifica che il primo backup abbia copiato esattamente un file.
            self.assertEqual(
                primo_risultato.file_copiati,
                1,
            )

            # Verifica che il primo backup non abbia ignorato alcun file.
            self.assertEqual(
                primo_risultato.file_ignorati,
                0,
            )

            # Verifica che il primo backup sia terminato correttamente.
            self.assertTrue(primo_risultato.successo)

            # Costruisce il percorso del file che deve essere stato creato nella destinazione.
            file_destinazione = destinazione / "prova_callback.txt"

            # Verifica che il file sia stato realmente copiato nella destinazione.
            self.assertTrue(file_destinazione.is_file())

            # Verifica che il contenuto copiato corrisponda al contenuto originale.
            self.assertEqual(
                file_destinazione.read_text(encoding="utf-8"),
                contenuto_file,
            )

            # Crea una nuova lista per isolare gli eventi prodotti dalla seconda esecuzione.
            eventi_seconda_esecuzione = []

            # Definisce la callback utilizzata durante la seconda esecuzione del backup.
            def callback_seconda_esecuzione(evento: str, dati: dict) -> None:
                """Registra separatamente gli eventi prodotti dal secondo backup."""
                eventi_seconda_esecuzione.append((evento, dati))

            # Crea un nuovo evento di arresto non attivato per la seconda esecuzione.
            secondo_evento_arresto = threading.Event()

            # Crea un nuovo motore collegato alla callback della seconda esecuzione.
            motore_seconda_esecuzione = MotoreBackup(
                secondo_evento_arresto,
                callback_seconda_esecuzione,
            )

            # Esegue nuovamente il backup senza modificare il file sorgente.
            secondo_risultato = motore_seconda_esecuzione.esegui(
                sorgente,
                destinazione,
            )

            # Estrae soltanto i nomi degli eventi ricevuti durante la seconda esecuzione.
            nomi_eventi_seconda_esecuzione = [
                evento
                for evento, dati in eventi_seconda_esecuzione
            ]

            # Verifica l'esatta sequenza prevista quando il file è già identico.
            self.assertEqual(
                nomi_eventi_seconda_esecuzione,
                [
                    "inizio",
                    "file",
                    "ignorato",
                    "fine",
                ],
            )

            # Recupera i dati dell'evento iniziale della seconda esecuzione.
            dati_inizio_seconda_esecuzione = eventi_seconda_esecuzione[0][1]

            # Verifica nuovamente il percorso sorgente comunicato alla callback.
            self.assertEqual(
                dati_inizio_seconda_esecuzione["sorgente"],
                str(sorgente),
            )

            # Verifica nuovamente il percorso destinazione comunicato alla callback.
            self.assertEqual(
                dati_inizio_seconda_esecuzione["destinazione"],
                str(destinazione),
            )

            # Recupera i dati dell'evento file della seconda esecuzione.
            dati_file_seconda_esecuzione = eventi_seconda_esecuzione[1][1]

            # Verifica che anche nella seconda esecuzione venga comunicato il file corretto.
            self.assertEqual(
                dati_file_seconda_esecuzione["file"],
                "prova_callback.txt",
            )

            # Verifica che nella seconda esecuzione sia stato trovato esattamente un file.
            self.assertEqual(
                dati_file_seconda_esecuzione["trovati"],
                1,
            )

            # Verifica che prima del confronto nessun file risulti copiato.
            self.assertEqual(
                dati_file_seconda_esecuzione["copiati"],
                0,
            )

            # Verifica che al momento dell'evento file il contatore degli ignorati sia ancora zero.
            self.assertEqual(
                dati_file_seconda_esecuzione["ignorati"],
                0,
            )

            # Verifica che non risultino file falliti.
            self.assertEqual(
                dati_file_seconda_esecuzione["falliti"],
                0,
            )

            # Recupera i dati dell'evento che segnala il file come identico.
            dati_ignorato_seconda_esecuzione = eventi_seconda_esecuzione[2][1]

            # Verifica che l'evento ignorato faccia riferimento al file corretto.
            self.assertEqual(
                dati_ignorato_seconda_esecuzione["file"],
                "prova_callback.txt",
            )

            # Recupera i dati dell'evento finale della seconda esecuzione.
            dati_fine_seconda_esecuzione = eventi_seconda_esecuzione[3][1]

            # Verifica che l'evento finale contenga lo stesso risultato restituito dal secondo esegui.
            self.assertIs(
                dati_fine_seconda_esecuzione["risultato"],
                secondo_risultato,
            )

            # Verifica che il secondo backup abbia trovato esattamente un file.
            self.assertEqual(
                secondo_risultato.file_trovati,
                1,
            )

            # Verifica che il secondo backup non abbia ricopiato il file.
            self.assertEqual(
                secondo_risultato.file_copiati,
                0,
            )

            # Verifica che il secondo backup abbia classificato il file come identico.
            self.assertEqual(
                secondo_risultato.file_ignorati,
                1,
            )

            # Verifica che il secondo backup non abbia registrato file falliti.
            self.assertEqual(
                secondo_risultato.file_falliti,
                0,
            )

            # Verifica che la seconda esecuzione non abbia registrato errori.
            self.assertEqual(
                secondo_risultato.errori,
                [],
            )

            # Verifica che la seconda esecuzione non sia stata annullata.
            self.assertFalse(secondo_risultato.annullato)

            # Verifica che anche la seconda esecuzione sia considerata riuscita.
            self.assertTrue(secondo_risultato.successo)

    def test_sottocartelle_disabilitate_copia_solo_file_radice(self) -> None:
        """Con l'opzione disattivata il motore non deve attraversare né ricreare le sottocartelle."""
        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un filesystem isolato per il test.
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente = radice_test / "sorgente"  # Definisce la radice sorgente.
            destinazione = radice_test / "destinazione"  # Definisce la radice destinazione.
            sottocartella = sorgente / "interna"  # Definisce una sottocartella che non deve essere visitata.
            sottocartella.mkdir(parents=True)  # Crea sorgente e sottocartella in un'unica operazione.
            (sorgente / "radice.txt").write_text("radice", encoding="utf-8")  # Crea un file direttamente nella radice.
            (sottocartella / "interno.txt").write_text("interno", encoding="utf-8")  # Crea un file che deve essere escluso.
            motore = MotoreBackup(threading.Event(), includi_sottocartelle=False)  # Crea il motore limitato alla sola radice.
            risultato = motore.esegui(sorgente, destinazione)  # Esegue il backup con la nuova opzione.
            self.assertTrue((destinazione / "radice.txt").is_file())  # Verifica che il file di primo livello sia stato copiato.
            self.assertFalse((destinazione / "interna").exists())  # Verifica che la sottocartella non sia stata ricreata.
            self.assertEqual(risultato.file_trovati, 1)  # Conta soltanto il file realmente appartenente all'ambito di scansione.
            self.assertEqual(risultato.cartelle_trovate, 0)  # Non conta cartelle che l'opzione ha escluso dall'elaborazione.

    def test_verifica_integrita_disabilitata_non_calcola_hash_post_copia(self) -> None:
        """Senza verifica integrità un file nuovo deve essere copiato senza calcolare SHA-256."""
        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in Path.
            sorgente = radice_test / "sorgente"  # Definisce la sorgente.
            destinazione = radice_test / "destinazione"  # Definisce la destinazione.
            sorgente.mkdir()  # Crea la cartella sorgente.
            (sorgente / "nuovo.txt").write_text("contenuto", encoding="utf-8")  # Crea un file nuovo che non richiede confronto incrementale.
            motore = MotoreBackup(threading.Event(), verifica_integrita=False)  # Disattiva soltanto la verifica SHA-256 post-copia.
            with patch.object(motore, "calcola_hash", wraps=motore.calcola_hash) as hash_controllato:  # Conta ogni eventuale calcolo SHA-256.
                risultato = motore.esegui(sorgente, destinazione)  # Esegue il backup del file nuovo.
            self.assertEqual(hash_controllato.call_count, 0)  # Conferma che per un file nuovo non è stato calcolato alcun hash.
            self.assertEqual(risultato.file_copiati, 1)  # Conferma che la copia è comunque riuscita.

    def test_verifica_integrita_disabilitata_mantiene_confronto_file_identici(self) -> None:
        """L'opzione non deve eliminare SHA-256 usato per riconoscere in sicurezza i file già identici."""
        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in Path.
            sorgente = radice_test / "sorgente"  # Definisce la sorgente.
            destinazione = radice_test / "destinazione"  # Definisce la destinazione.
            sorgente.mkdir()  # Crea la sorgente.
            destinazione.mkdir()  # Crea la destinazione già esistente.
            (sorgente / "uguale.txt").write_text("identico", encoding="utf-8")  # Scrive il file sorgente.
            (destinazione / "uguale.txt").write_text("identico", encoding="utf-8")  # Scrive un file destinazione identico.
            motore = MotoreBackup(threading.Event(), verifica_integrita=False)  # Disattiva la sola verifica successiva alla copia.
            with patch.object(motore, "calcola_hash", wraps=motore.calcola_hash) as hash_controllato:  # Osserva gli hash del confronto incrementale.
                risultato = motore.esegui(sorgente, destinazione)  # Esegue il secondo backup logico.
            self.assertEqual(hash_controllato.call_count, 2)  # Richiede ancora un hash per sorgente e uno per destinazione.
            self.assertEqual(risultato.file_ignorati, 1)  # Conferma che il file viene riconosciuto come già identico.
            self.assertEqual(risultato.file_copiati, 0)  # Conferma che il file identico non viene ricopiato.

    def test_verifica_integrita_attiva_rileva_copia_con_contenuto_diverso_ma_stessa_dimensione(self) -> None:
        """La verifica attiva deve rilevare una destinazione corrotta anche quando la dimensione coincide."""
        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in Path.
            sorgente = radice_test / "sorgente"  # Definisce la sorgente.
            destinazione = radice_test / "destinazione"  # Definisce la destinazione.
            sorgente.mkdir()  # Crea la cartella sorgente.
            (sorgente / "dato.bin").write_bytes(b"AAAA")  # Crea un contenuto sorgente di quattro byte.
            motore = MotoreBackup(threading.Event(), verifica_integrita=True)  # Mantiene attiva la verifica completa predefinita.
            def copia_corrompendo(_sorgente: Path, percorso_destinazione: Path) -> None:  # Simula una copia che produce dati diversi della stessa dimensione.
                percorso_destinazione.write_bytes(b"BBBB")  # Scrive quattro byte differenti per superare il solo controllo dimensionale.
            with patch("fdbackup.motore_backup.shutil.copy2", side_effect=copia_corrompendo):  # Sostituisce copy2 esclusivamente durante il test.
                risultato = motore.esegui(sorgente, destinazione)  # Esegue il backup simulando la corruzione.
            self.assertEqual(risultato.file_falliti, 1)  # Conferma che SHA-256 rileva la copia non integra.
            self.assertEqual(risultato.file_copiati, 0)  # Una copia non verificata non viene conteggiata come riuscita.
            self.assertIn("Verifica SHA-256 fallita", risultato.errori[0])  # Verifica che l'errore identifichi la causa reale.


if __name__ == "__main__":
    # Avvia automaticamente unittest se il file viene eseguito direttamente.
    unittest.main()