import logging  # Importa il sistema di logging standard per produrre e controllare i messaggi registrati.
import tempfile  # Importa gli strumenti per creare directory temporanee isolate durante i test.
import unittest  # Importa il framework di test standard della libreria Python.
from pathlib import Path  # Importa Path per gestire i percorsi temporanei in modo portabile.
from unittest.mock import patch  # Importa patch per modificare temporaneamente la soglia di rotazione durante il test.

from fdbackup.logging_backup import NOME_LOGGER_FDBACKUP, configura_logging  # Importa il componente di logging che vogliamo verificare.


class TestLoggingBackup(unittest.TestCase):
    """Verifica il comportamento del sistema di logging persistente di FDBackup."""

    def setUp(self) -> None:
        """Prepara una directory temporanea e garantisce uno stato pulito del logger."""

        self._chiudi_handler_fdbackup()  # Elimina eventuali handler FDBackup rimasti aperti da test precedenti.

        self.directory_temporanea = tempfile.TemporaryDirectory()  # Crea una directory temporanea controllata esplicitamente dal test.

        self.percorso_applicazione = Path(self.directory_temporanea.name)  # Converte il percorso temporaneo in un oggetto Path.

    def tearDown(self) -> None:
        """Chiude gli handler prima di eliminare la directory temporanea."""

        self._chiudi_handler_fdbackup()  # Chiude il file di log prima che Windows tenti di eliminare la directory.

        self.directory_temporanea.cleanup()  # Elimina la directory temporanea soltanto dopo la chiusura del file di log.

    def _chiudi_handler_fdbackup(self) -> None:
        """Rimuove e chiude esclusivamente gli handler creati dal modulo di logging di FDBackup."""

        logger_fdbackup = logging.getLogger(NOME_LOGGER_FDBACKUP)  # Recupera il logger principale utilizzato dall'applicazione.

        for handler in list(logger_fdbackup.handlers):  # Scorre una copia della lista per poter rimuovere handler in sicurezza.

            if getattr(handler, "_fdbackup_handler", False):  # Verifica che l'handler appartenga realmente alla configurazione di FDBackup.

                logger_fdbackup.removeHandler(handler)  # Scollega l'handler dal logger prima della chiusura.

                handler.close()  # Chiude il file associato all'handler e libera la risorsa su Windows.

    def _svuota_buffer_log(self) -> None:
        """Forza la scrittura su disco dei messaggi ancora presenti nei buffer degli handler FDBackup."""

        logger_fdbackup = logging.getLogger(NOME_LOGGER_FDBACKUP)  # Recupera il logger principale dell'applicazione.

        for handler in logger_fdbackup.handlers:  # Scorre tutti gli handler attualmente collegati al logger.

            if getattr(handler, "_fdbackup_handler", False):  # Limita l'operazione agli handler gestiti da FDBackup.

                handler.flush()  # Forza la scrittura dei dati ancora presenti nel buffer.

    def test_creazione_cartella_e_file_log(self) -> None:
        """Verifica che la configurazione crei la cartella logs e il file principale."""

        percorso_log = configura_logging(self.percorso_applicazione)  # Configura il logging nella directory temporanea del test.

        self.assertTrue(  # Verifica che la cartella dedicata ai log sia stata creata.
            (self.percorso_applicazione / "logs").is_dir()
        )

        self.assertTrue(percorso_log.is_file())  # Verifica che il file principale di log esista realmente.

        self.assertEqual(  # Verifica che il percorso restituito corrisponda esattamente a quello progettato.
            percorso_log,
            self.percorso_applicazione / "logs" / "fdbackup.log",
        )

    def test_scrittura_messaggio_info(self) -> None:
        """Verifica che un messaggio INFO venga realmente scritto nel file."""

        percorso_log = configura_logging(self.percorso_applicazione)  # Configura il logging nella directory temporanea.

        logger_test = logging.getLogger("fdbackup.test")  # Recupera un logger figlio come faranno i moduli reali dell'applicazione.

        logger_test.info("Messaggio di prova FDBackup")  # Registra un messaggio INFO riconoscibile.

        self._svuota_buffer_log()  # Forza la scrittura del messaggio prima di leggere il file.

        contenuto_log = percorso_log.read_text(encoding="utf-8")  # Legge il file usando la stessa codifica UTF-8 configurata dal logger.

        self.assertIn(  # Verifica che il testo del messaggio sia stato scritto.
            "Messaggio di prova FDBackup",
            contenuto_log,
        )

        self.assertIn("INFO", contenuto_log)  # Verifica che il livello del messaggio sia presente nel log.

        self.assertIn("fdbackup.test", contenuto_log)  # Verifica che venga registrato anche il nome del logger che ha prodotto il messaggio.

    def test_scrittura_caratteri_unicode(self) -> None:
        """Verifica che il file di log gestisca correttamente caratteri Unicode."""

        percorso_log = configura_logging(self.percorso_applicazione)  # Configura il logging nella directory temporanea.

        logger_test = logging.getLogger("fdbackup.test_unicode")  # Recupera un logger figlio dedicato al test Unicode.

        logger_test.info(  # Registra un messaggio contenente caratteri che richiedono una corretta gestione UTF-8.
            "Backup completato: è tutto corretto — prova Unicode"
        )

        self._svuota_buffer_log()  # Forza la scrittura del messaggio sul file.

        contenuto_log = percorso_log.read_text(encoding="utf-8")  # Legge esplicitamente il file come UTF-8.

        self.assertIn(  # Verifica che i caratteri Unicode siano stati conservati senza corruzione.
            "Backup completato: è tutto corretto — prova Unicode",
            contenuto_log,
        )

    def test_seconda_configurazione_non_duplica_handler(self) -> None:
        """Verifica che configurare due volte il logging non aggiunga handler duplicati."""

        configura_logging(self.percorso_applicazione)  # Esegue una prima configurazione del logging.

        configura_logging(self.percorso_applicazione)  # Ripete intenzionalmente la configurazione.

        logger_fdbackup = logging.getLogger(NOME_LOGGER_FDBACKUP)  # Recupera il logger principale dopo entrambe le configurazioni.

        handler_fdbackup = [  # Costruisce una lista contenente soltanto gli handler appartenenti a FDBackup.
            handler
            for handler in logger_fdbackup.handlers
            if getattr(handler, "_fdbackup_handler", False)
        ]

        self.assertEqual(  # Verifica che la seconda configurazione non abbia creato un secondo handler.
            len(handler_fdbackup),
            1,
        )

    def test_seconda_configurazione_non_duplica_messaggi(self) -> None:
        """Verifica che una doppia configurazione non produca righe duplicate nel file."""

        percorso_log = configura_logging(self.percorso_applicazione)  # Configura una prima volta il logging.

        configura_logging(self.percorso_applicazione)  # Ripete volontariamente la configurazione.

        logger_test = logging.getLogger("fdbackup.test_duplicati")  # Recupera un logger figlio dedicato al controllo delle duplicazioni.

        logger_test.info("MESSAGGIO_UNICO_FDBACKUP")  # Registra un solo messaggio facilmente identificabile.

        self._svuota_buffer_log()  # Forza la scrittura completa del messaggio.

        contenuto_log = percorso_log.read_text(encoding="utf-8")  # Legge il contenuto prodotto dal logger.

        self.assertEqual(  # Verifica che il singolo messaggio sia stato scritto una sola volta.
            contenuto_log.count("MESSAGGIO_UNICO_FDBACKUP"),
            1,
        )

    def test_rotazione_file_log(self) -> None:
        """Verifica che il file principale venga ruotato quando supera la dimensione configurata."""

        with patch(  # Sostituisce temporaneamente la soglia reale soltanto durante questo test.
            "fdbackup.logging_backup.DIMENSIONE_MASSIMA_LOG",
            300,
        ):
            percorso_log = configura_logging(self.percorso_applicazione)  # Configura il logger usando temporaneamente la soglia ridotta.

            logger_test = logging.getLogger("fdbackup.test_rotazione")  # Recupera un logger figlio dedicato al test della rotazione.

            for indice in range(20):  # Produce abbastanza record da superare più volte la piccola soglia impostata dal test.
                logger_test.info(  # Scrive un messaggio sufficientemente lungo per provocare il rollover.
                    "Messaggio rotazione numero %d - contenuto di prova per verificare il RotatingFileHandler.",
                    indice,
                )

            self._svuota_buffer_log()  # Forza la scrittura su disco degli ultimi record eventualmente ancora bufferizzati.

            percorso_log_ruotato = percorso_log.with_name(percorso_log.name + ".1")  # Costruisce il nome previsto per il backup più recente del log.

            self.assertTrue(percorso_log.is_file())  # Verifica che il file principale continui a esistere dopo la rotazione.

            self.assertTrue(  # Verifica che almeno il primo file ruotato sia stato realmente creato.
                percorso_log_ruotato.is_file()
            )


if __name__ == "__main__":  # Verifica se il file è stato avviato direttamente anziché importato.
    unittest.main()  # Avvia la suite di test tramite il framework unittest.