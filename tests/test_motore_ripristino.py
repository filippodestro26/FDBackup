import tempfile  # Importa TemporaryDirectory per creare ambienti di test isolati.
import threading  # Importa Event per simulare il meccanismo di arresto del motore.
import unittest  # Importa il framework di test automatici della libreria standard.
from pathlib import Path  # Importa Path per gestire file e cartelle.

from fdbackup.motore_ripristino import MotoreRipristino  # Importa il motore reale da verificare.


class TestMotoreRipristino(unittest.TestCase):
    """Contiene i test automatici del motore di ripristino di FDBackup."""

    def test_ripristina_file_nuovo(self) -> None:
        """Verifica che un file assente nella destinazione venga ripristinato e verificato."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente del ripristino.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la cartella sorgente.

            file_backup = sorgente_backup / "documento.txt"  # Definisce il file da ripristinare.
            contenuto = "Contenuto originale FDBackup"  # Definisce un contenuto conosciuto.

            file_backup.write_text(
                contenuto,
                encoding="utf-8",
            )  # Scrive il file nella sorgente.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore di ripristino.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            file_ripristinato = (
                destinazione_ripristino / "documento.txt"
            )  # Costruisce il percorso del file atteso.

            self.assertTrue(
                file_ripristinato.is_file()
            )  # Verifica che il file sia stato creato.

            self.assertEqual(
                file_ripristinato.read_text(encoding="utf-8"),
                contenuto,
            )  # Verifica che il contenuto sia corretto.

            self.assertEqual(
                risultato.file_trovati,
                1,
            )  # Verifica che sia stato trovato un file.

            self.assertEqual(
                risultato.file_ripristinati,
                1,
            )  # Verifica che il file sia stato ripristinato.

            self.assertEqual(
                risultato.file_identici,
                0,
            )  # Verifica che nessun file fosse già identico.

            self.assertEqual(
                risultato.file_conflitto,
                0,
            )  # Verifica l'assenza di conflitti.

            self.assertEqual(
                risultato.file_falliti,
                0,
            )  # Verifica l'assenza di errori sui file.

            self.assertEqual(
                risultato.byte_ripristinati,
                file_backup.stat().st_size,
            )  # Verifica il numero di byte ripristinati.

            self.assertTrue(
                risultato.successo
            )  # Verifica che il risultato sia considerato riuscito.

    def test_file_identico_non_viene_ricopiato(self) -> None:
        """Verifica che un file già identico nella destinazione venga lasciato invariato."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.
            destinazione_ripristino.mkdir()  # Crea la destinazione.

            contenuto = "Contenuto identico"  # Definisce il contenuto comune.

            file_backup = sorgente_backup / "documento.txt"  # Definisce il file del backup.
            file_destinazione = (
                destinazione_ripristino / "documento.txt"
            )  # Definisce il file già presente.

            file_backup.write_text(
                contenuto,
                encoding="utf-8",
            )  # Scrive il file nel backup.

            file_destinazione.write_text(
                contenuto,
                encoding="utf-8",
            )  # Scrive lo stesso contenuto nella destinazione.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertEqual(
                risultato.file_trovati,
                1,
            )  # Verifica che il file sia stato individuato.

            self.assertEqual(
                risultato.file_ripristinati,
                0,
            )  # Verifica che il file non sia stato ricopiato.

            self.assertEqual(
                risultato.file_identici,
                1,
            )  # Verifica che il file sia stato riconosciuto come identico.

            self.assertEqual(
                risultato.file_conflitto,
                0,
            )  # Verifica l'assenza di conflitti.

            self.assertEqual(
                risultato.byte_ripristinati,
                0,
            )  # Verifica che nessun byte sia stato ricopiato.

            self.assertTrue(
                risultato.successo
            )  # Verifica che il risultato sia positivo.

    def test_file_differente_genera_conflitto_senza_sovrascrittura(self) -> None:
        """Verifica che un file differente già presente non venga mai sovrascritto automaticamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.
            destinazione_ripristino.mkdir()  # Crea la destinazione.

            file_backup = sorgente_backup / "documento.txt"  # Definisce il file del backup.
            file_destinazione = (
                destinazione_ripristino / "documento.txt"
            )  # Definisce il file dell'utente.

            file_backup.write_text(
                "VERSIONE BACKUP",
                encoding="utf-8",
            )  # Scrive il contenuto del backup.

            file_destinazione.write_text(
                "VERSIONE UTENTE",
                encoding="utf-8",
            )  # Scrive il contenuto da preservare.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertEqual(
                file_destinazione.read_text(encoding="utf-8"),
                "VERSIONE UTENTE",
            )  # Verifica che il contenuto dell'utente sia rimasto intatto.

            self.assertEqual(
                risultato.file_trovati,
                1,
            )  # Verifica che il file sia stato individuato.

            self.assertEqual(
                risultato.file_ripristinati,
                0,
            )  # Verifica che il file non sia stato copiato.

            self.assertEqual(
                risultato.file_conflitto,
                1,
            )  # Verifica che sia stato registrato un conflitto.

            self.assertEqual(
                risultato.file_falliti,
                0,
            )  # Verifica che un conflitto non sia classificato come errore I/O.

            self.assertFalse(
                risultato.successo
            )  # Verifica che un conflitto renda incompleto il ripristino.

            self.assertEqual(
                len(risultato.errori),
                1,
            )  # Verifica che il conflitto sia stato registrato nel riepilogo.

    def test_file_stessa_dimensione_ma_contenuto_diverso_genera_conflitto(self) -> None:
        """Verifica che SHA-256 rilevi contenuti differenti anche con la stessa dimensione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.
            destinazione_ripristino.mkdir()  # Crea la destinazione.

            file_backup = sorgente_backup / "prova.txt"  # Definisce il file del backup.
            file_destinazione = destinazione_ripristino / "prova.txt"  # Definisce il file locale.

            file_backup.write_text(
                "AAAA",
                encoding="utf-8",
            )  # Scrive quattro caratteri nella sorgente.

            file_destinazione.write_text(
                "BBBB",
                encoding="utf-8",
            )  # Scrive quattro caratteri differenti nella destinazione.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertEqual(
                file_backup.stat().st_size,
                file_destinazione.stat().st_size,
            )  # Conferma che le dimensioni coincidano.

            self.assertEqual(
                file_destinazione.read_text(encoding="utf-8"),
                "BBBB",
            )  # Verifica che il file locale non sia stato modificato.

            self.assertEqual(
                risultato.file_conflitto,
                1,
            )  # Verifica che il contenuto differente sia stato rilevato.

            self.assertEqual(
                risultato.file_identici,
                0,
            )  # Verifica che i file non siano considerati identici.

            self.assertFalse(
                risultato.successo
            )  # Verifica che il conflitto renda incompleto il ripristino.

    def test_ripristina_file_vuoto(self) -> None:
        """Verifica che un file di zero byte venga ripristinato correttamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.

            file_vuoto = sorgente_backup / "vuoto.txt"  # Definisce il file vuoto.
            file_vuoto.touch()  # Crea fisicamente il file di zero byte.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            file_ripristinato = (
                destinazione_ripristino / "vuoto.txt"
            )  # Costruisce il percorso atteso.

            self.assertTrue(
                file_ripristinato.is_file()
            )  # Verifica che il file sia stato creato.

            self.assertEqual(
                file_ripristinato.stat().st_size,
                0,
            )  # Verifica che il file rimanga vuoto.

            self.assertEqual(
                risultato.file_ripristinati,
                1,
            )  # Verifica che sia stato ripristinato.

            self.assertEqual(
                risultato.byte_ripristinati,
                0,
            )  # Verifica che il conteggio dei byte sia zero.

            self.assertTrue(
                risultato.successo
            )  # Verifica che l'operazione sia riuscita.

    def test_ripristina_cartella_vuota(self) -> None:
        """Verifica che una cartella vuota presente nel backup venga ricreata nella destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.
            (sorgente_backup / "cartella_vuota").mkdir()  # Crea una cartella vuota.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertTrue(
                (destinazione_ripristino / "cartella_vuota").is_dir()
            )  # Verifica che la cartella sia stata ricreata.

            self.assertEqual(
                risultato.cartelle_trovate,
                1,
            )  # Verifica che una sottocartella sia stata trovata.

            self.assertEqual(
                risultato.cartelle_create,
                1,
            )  # Verifica che una sottocartella sia stata creata.

            self.assertEqual(
                risultato.cartelle_conflitto,
                0,
            )  # Verifica l'assenza di conflitti.

            self.assertTrue(
                risultato.successo
            )  # Verifica che il ripristino sia riuscito.

    def test_ripristina_cartelle_vuote_annidate(self) -> None:
        """Verifica che più cartelle vuote annidate vengano ricreate completamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.

            cartella_profonda = (
                sorgente_backup / "livello_1" / "livello_2" / "livello_3"
            )  # Definisce una struttura di tre sottocartelle.

            cartella_profonda.mkdir(
                parents=True
            )  # Crea l'intera struttura annidata.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            destinazione_profonda = (
                destinazione_ripristino
                / "livello_1"
                / "livello_2"
                / "livello_3"
            )  # Costruisce il percorso atteso.

            self.assertTrue(
                destinazione_profonda.is_dir()
            )  # Verifica che l'intera struttura esista.

            self.assertEqual(
                risultato.cartelle_trovate,
                3,
            )  # Verifica il numero delle sottocartelle trovate.

            self.assertEqual(
                risultato.cartelle_create,
                3,
            )  # Verifica il numero delle sottocartelle create.

            self.assertTrue(
                risultato.successo
            )  # Verifica il successo complessivo.

    def test_struttura_annidata_con_file_viene_ripristinata(self) -> None:
        """Verifica il ripristino di file collocati in più livelli di sottocartelle."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            cartella_annidata = (
                sorgente_backup / "documenti" / "progetti"
            )  # Definisce una struttura annidata.

            cartella_annidata.mkdir(
                parents=True
            )  # Crea sorgente e sottocartelle.

            file_radice = sorgente_backup / "radice.txt"  # Definisce un file nella radice.
            file_profondo = cartella_annidata / "progetto.txt"  # Definisce un file annidato.

            file_radice.write_text(
                "RADICE",
                encoding="utf-8",
            )  # Scrive il primo file.

            file_profondo.write_text(
                "PROGETTO",
                encoding="utf-8",
            )  # Scrive il secondo file.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertEqual(
                (destinazione_ripristino / "radice.txt").read_text(
                    encoding="utf-8"
                ),
                "RADICE",
            )  # Verifica il file nella radice.

            self.assertEqual(
                (
                    destinazione_ripristino
                    / "documenti"
                    / "progetti"
                    / "progetto.txt"
                ).read_text(encoding="utf-8"),
                "PROGETTO",
            )  # Verifica il file annidato.

            self.assertEqual(
                risultato.file_trovati,
                2,
            )  # Verifica che siano stati individuati entrambi i file.

            self.assertEqual(
                risultato.file_ripristinati,
                2,
            )  # Verifica che entrambi i file siano stati ripristinati.

            self.assertEqual(
                risultato.cartelle_trovate,
                2,
            )  # Verifica il conteggio delle sottocartelle.

            self.assertEqual(
                risultato.cartelle_create,
                2,
            )  # Verifica il conteggio delle cartelle create.

            self.assertTrue(
                risultato.successo
            )  # Verifica il successo complessivo.

    def test_file_solo_nella_destinazione_non_viene_eliminato(self) -> None:
        """Verifica che il ripristino non elimini file presenti soltanto nella destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.
            destinazione_ripristino.mkdir()  # Crea la destinazione.

            file_estraneo = (
                destinazione_ripristino / "file_utente.txt"
            )  # Definisce un file presente solo nella destinazione.

            file_estraneo.write_text(
                "Questo file deve rimanere",
                encoding="utf-8",
            )  # Scrive il contenuto da preservare.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertTrue(
                file_estraneo.is_file()
            )  # Verifica che il file sia ancora presente.

            self.assertEqual(
                file_estraneo.read_text(encoding="utf-8"),
                "Questo file deve rimanere",
            )  # Verifica che il contenuto sia rimasto intatto.

            self.assertTrue(
                risultato.successo
            )  # Verifica che il file estraneo non generi un errore.

    def test_sorgente_inesistente_viene_rifiutata(self) -> None:
        """Verifica che il motore rifiuti una cartella di backup inesistente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup_inesistente"  # Definisce una sorgente inesistente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            with self.assertRaisesRegex(
                ValueError,
                r"^La cartella di backup non esiste\.$",
            ):  # Verifica tipo e messaggio dell'eccezione.
                motore.esegui(
                    sorgente_backup,
                    destinazione_ripristino,
                )  # Tenta di eseguire il ripristino.

            self.assertFalse(
                destinazione_ripristino.exists()
            )  # Verifica che non siano state effettuate modifiche.

    def test_sorgente_file_viene_rifiutata(self) -> None:
        """Verifica che un file non possa essere usato come sorgente del ripristino."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup.txt"  # Definisce una sorgente che sarà un file.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.write_text(
                "Non sono una cartella",
                encoding="utf-8",
            )  # Crea il file sorgente.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            with self.assertRaisesRegex(
                ValueError,
                r"^La sorgente del ripristino deve essere una cartella\.$",
            ):  # Verifica tipo e messaggio dell'eccezione.
                motore.esegui(
                    sorgente_backup,
                    destinazione_ripristino,
                )  # Tenta il ripristino.

    def test_destinazione_file_viene_rifiutata(self) -> None:
        """Verifica che un file non possa essere usato come radice della destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "destinazione.txt"  # Definisce una destinazione che sarà un file.

            sorgente_backup.mkdir()  # Crea la sorgente.

            destinazione_ripristino.write_text(
                "Non sono una cartella",
                encoding="utf-8",
            )  # Crea il file destinazione.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            with self.assertRaisesRegex(
                ValueError,
                r"^La destinazione del ripristino esiste ma non è una cartella\.$",
            ):  # Verifica tipo e messaggio dell'eccezione.
                motore.esegui(
                    sorgente_backup,
                    destinazione_ripristino,
                )  # Tenta il ripristino.

    def test_sorgente_e_destinazione_uguali_vengono_rifiutate(self) -> None:
        """Verifica che sorgente e destinazione non possano coincidere."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.

            sorgente_backup.mkdir()  # Crea la sorgente.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            with self.assertRaisesRegex(
                ValueError,
                r"^Sorgente del backup e destinazione del ripristino non possono coincidere\.$",
            ):  # Verifica tipo e messaggio dell'eccezione.
                motore.esegui(
                    sorgente_backup,
                    sorgente_backup,
                )  # Usa intenzionalmente lo stesso percorso.

    def test_destinazione_dentro_sorgente_viene_rifiutata(self) -> None:
        """Verifica che la destinazione non possa trovarsi dentro il backup."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = sorgente_backup / "ripristino"  # Inserisce la destinazione nella sorgente.

            sorgente_backup.mkdir()  # Crea la sorgente.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            with self.assertRaisesRegex(
                ValueError,
                r"^La destinazione del ripristino non può trovarsi all'interno della cartella di backup\.$",
            ):  # Verifica tipo e messaggio dell'eccezione.
                motore.esegui(
                    sorgente_backup,
                    destinazione_ripristino,
                )  # Tenta il ripristino con percorsi non ammessi.

    def test_file_del_backup_incontra_cartella_nella_destinazione(self) -> None:
        """Verifica il conflitto tra un file del backup e una cartella omonima nella destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.
            destinazione_ripristino.mkdir()  # Crea la destinazione.

            file_backup = sorgente_backup / "elemento"  # Definisce un file nel backup.

            file_backup.write_text(
                "Sono un file",
                encoding="utf-8",
            )  # Crea il file nella sorgente.

            cartella_esistente = (
                destinazione_ripristino / "elemento"
            )  # Definisce l'oggetto omonimo nella destinazione.

            cartella_esistente.mkdir()  # Crea una directory al posto del file.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertTrue(
                cartella_esistente.is_dir()
            )  # Verifica che la cartella sia rimasta intatta.

            self.assertEqual(
                risultato.file_trovati,
                1,
            )  # Verifica che il file del backup sia stato individuato.

            self.assertEqual(
                risultato.file_conflitto,
                1,
            )  # Verifica che il conflitto sia stato registrato.

            self.assertEqual(
                risultato.file_ripristinati,
                0,
            )  # Verifica che non sia avvenuta alcuna copia.

            self.assertFalse(
                risultato.successo
            )  # Verifica che il conflitto renda incompleto il ripristino.

    def test_cartella_del_backup_incontra_file_nella_destinazione(self) -> None:
        """Verifica il conflitto tra una cartella del backup e un file omonimo nella destinazione."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.
            destinazione_ripristino.mkdir()  # Crea la destinazione.

            cartella_backup = sorgente_backup / "documenti"  # Definisce una cartella nel backup.
            cartella_backup.mkdir()  # Crea la cartella.

            file_interno = cartella_backup / "interno.txt"  # Definisce un file nel ramo in conflitto.

            file_interno.write_text(
                "File interno",
                encoding="utf-8",
            )  # Crea il file nella cartella del backup.

            file_conflitto = (
                destinazione_ripristino / "documenti"
            )  # Definisce un file con lo stesso nome della cartella.

            file_conflitto.write_text(
                "Questo file deve rimanere",
                encoding="utf-8",
            )  # Crea il file da proteggere.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Esegue il ripristino.

            self.assertTrue(
                file_conflitto.is_file()
            )  # Verifica che l'oggetto preesistente sia rimasto un file.

            self.assertEqual(
                file_conflitto.read_text(encoding="utf-8"),
                "Questo file deve rimanere",
            )  # Verifica che il contenuto non sia stato modificato.

            self.assertEqual(
                risultato.cartelle_trovate,
                1,
            )  # Verifica che la cartella del backup sia stata individuata.

            self.assertEqual(
                risultato.cartelle_conflitto,
                1,
            )  # Verifica che sia stato registrato un conflitto di cartella.

            self.assertEqual(
                risultato.file_trovati,
                1,
            )  # Verifica la correzione: il file nel ramo in conflitto deve essere comunque contato.

            self.assertEqual(
                risultato.file_ripristinati,
                0,
            )  # Verifica che il file interno non sia stato copiato.

            self.assertFalse(
                risultato.successo
            )  # Verifica che il conflitto renda incompleto il ripristino.

    def test_arresto_prima_dellesecuzione_annulla_il_ripristino(self) -> None:
        """Verifica che uno stop già richiesto impedisca qualsiasi copia."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.

            sorgente_backup.mkdir()  # Crea la sorgente.

            file_backup = sorgente_backup / "documento.txt"  # Definisce un file da non copiare.

            file_backup.write_text(
                "Non deve essere copiato",
                encoding="utf-8",
            )  # Crea il file nel backup.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            evento_arresto.set()  # Richiede lo stop prima dell'esecuzione.

            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            risultato = motore.esegui(
                sorgente_backup,
                destinazione_ripristino,
            )  # Avvia il ripristino con lo stop già richiesto.

            self.assertTrue(
                risultato.annullato
            )  # Verifica che il risultato registri l'annullamento.

            self.assertFalse(
                risultato.successo
            )  # Verifica che un ripristino annullato non sia considerato riuscito.

            self.assertEqual(
                risultato.file_ripristinati,
                0,
            )  # Verifica che nessun file sia stato copiato.

            self.assertEqual(
                risultato.byte_ripristinati,
                0,
            )  # Verifica che nessun byte sia stato ripristinato.

            self.assertFalse(
                destinazione_ripristino.exists()
            )  # Verifica che la destinazione non sia stata creata.

    def test_copia_e_verifica_rifiuta_sovrascrittura_diretta(self) -> None:
        """Verifica che copia_e_verifica protegga un file già esistente anche se chiamato direttamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.

            file_backup = radice_test / "backup.txt"  # Definisce il file sorgente.
            file_destinazione = radice_test / "destinazione.txt"  # Definisce il file destinazione.

            file_backup.write_text(
                "BACKUP",
                encoding="utf-8",
            )  # Scrive il contenuto del backup.

            file_destinazione.write_text(
                "UTENTE",
                encoding="utf-8",
            )  # Scrive il contenuto da proteggere.

            evento_arresto = threading.Event()  # Crea l'evento di arresto.
            motore = MotoreRipristino(evento_arresto)  # Crea il motore.

            with self.assertRaisesRegex(
                FileExistsError,
                r"^La destinazione esiste già e non verrà sovrascritta:",
            ):  # Verifica che il metodo rifiuti la sovrascrittura.
                motore.copia_e_verifica(
                    file_backup,
                    file_destinazione,
                )  # Richiama direttamente il metodo di copia.

            self.assertEqual(
                file_destinazione.read_text(encoding="utf-8"),
                "UTENTE",
            )  # Verifica che il file preesistente sia rimasto intatto.


    def test_evento_finale_contiene_lo_stesso_risultato(self) -> None:
        """Verifica che un ripristino normale termini con fine e con lo stesso oggetto risultato restituito."""
        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.
            sorgente_backup.mkdir()  # Crea la sorgente.
            (sorgente_backup / "documento.txt").write_text("Contenuto di prova", encoding="utf-8")  # Crea il file di prova.
            eventi: list[tuple[str, dict]] = []  # Conserva gli eventi ricevuti.

            def callback(evento: str, dati: dict) -> None:
                """Registra gli eventi prodotti dal motore."""
                eventi.append((evento, dati))  # Memorizza evento e dati.

            evento_arresto = threading.Event()  # Crea il controllo di arresto.
            motore = MotoreRipristino(evento_arresto, callback)  # Crea il motore con callback.
            risultato = motore.esegui(sorgente_backup, destinazione_ripristino)  # Esegue il ripristino.
            ultimo_evento, ultimi_dati = eventi[-1]  # Recupera l'evento terminale.
            self.assertEqual(ultimo_evento, "fine")  # Verifica l'evento terminale comune.
            self.assertIn("risultato", ultimi_dati)  # Verifica la presenza del risultato.
            self.assertIs(ultimi_dati["risultato"], risultato)  # Verifica che sia lo stesso oggetto.
            self.assertFalse(risultato.annullato)  # Verifica che non sia annullato.
            self.assertTrue(risultato.successo)  # Verifica il successo.

    def test_evento_finale_dopo_annullamento_contiene_lo_stesso_risultato(self) -> None:
        """Verifica che anche un ripristino annullato termini con fine e con lo stesso oggetto risultato."""
        with tempfile.TemporaryDirectory() as cartella_temporanea:
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            sorgente_backup = radice_test / "backup"  # Definisce la sorgente.
            destinazione_ripristino = radice_test / "ripristino"  # Definisce la destinazione.
            sorgente_backup.mkdir()  # Crea la sorgente.
            (sorgente_backup / "documento.txt").write_text("Non copiare", encoding="utf-8")  # Crea il file di prova.
            eventi: list[tuple[str, dict]] = []  # Conserva gli eventi ricevuti.

            def callback(evento: str, dati: dict) -> None:
                """Registra gli eventi prodotti dal motore."""
                eventi.append((evento, dati))  # Memorizza evento e dati.

            evento_arresto = threading.Event()  # Crea il controllo di arresto.
            evento_arresto.set()  # Richiede lo stop prima dell'esecuzione.
            motore = MotoreRipristino(evento_arresto, callback)  # Crea il motore con callback.
            risultato = motore.esegui(sorgente_backup, destinazione_ripristino)  # Esegue il ripristino annullato.
            nomi_eventi = [nome_evento for nome_evento, _ in eventi]  # Estrae i nomi degli eventi.
            ultimo_evento, ultimi_dati = eventi[-1]  # Recupera l'evento terminale.
            self.assertEqual(ultimo_evento, "fine")  # Verifica l'evento terminale comune.
            self.assertNotIn("annullato", nomi_eventi)  # Verifica l'assenza del vecchio evento terminale.
            self.assertIn("risultato", ultimi_dati)  # Verifica la presenza del risultato.
            self.assertIs(ultimi_dati["risultato"], risultato)  # Verifica che sia lo stesso oggetto.
            self.assertTrue(risultato.annullato)  # Verifica lo stato di annullamento.
            self.assertFalse(risultato.successo)  # Verifica che non sia un successo.
            self.assertFalse(destinazione_ripristino.exists())  # Verifica che la destinazione non sia stata creata.


if __name__ == "__main__":
    unittest.main()  # Permette di eseguire direttamente il file di test.