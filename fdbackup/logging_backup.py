import logging  # Importa il sistema di logging standard di Python.
from logging.handlers import RotatingFileHandler  # Importa l'handler che permette di ruotare automaticamente i file di log.
from pathlib import Path  # Importa Path per gestire in modo sicuro i percorsi di file e cartelle.


# Definisce il nome del logger principale utilizzato dai moduli di FDBackup.
NOME_LOGGER_FDBACKUP = "fdbackup"

# Definisce la dimensione massima del file di log corrente prima della rotazione.
DIMENSIONE_MASSIMA_LOG = 2 * 1024 * 1024

# Definisce quanti file di log precedenti devono essere conservati.
NUMERO_BACKUP_LOG = 5


def configura_logging(cartella_applicazione: Path) -> Path:
    """Configura il logging persistente di FDBackup e restituisce il percorso del file di log."""

    # Costruisce il percorso della cartella dedicata ai log.
    cartella_log = cartella_applicazione / "logs"

    # Crea la cartella dei log e le eventuali cartelle mancanti senza errore se esiste già.
    cartella_log.mkdir(parents=True, exist_ok=True)

    # Costruisce il percorso completo del file di log principale.
    percorso_log = cartella_log / "fdbackup.log"

    # Recupera il logger principale dell'applicazione.
    logger_fdbackup = logging.getLogger(NOME_LOGGER_FDBACKUP)

    # Imposta INFO come livello minimo registrato dal logger applicativo.
    logger_fdbackup.setLevel(logging.INFO)

    # Evita che i messaggi vengano inoltrati anche al logger root e quindi duplicati.
    logger_fdbackup.propagate = False

    # Controlla se il nostro handler è già stato configurato.
    handler_esistente = next(
        (
            handler
            for handler in logger_fdbackup.handlers
            if getattr(handler, "_fdbackup_handler", False)
        ),
        None,
    )

    # Configura un nuovo handler soltanto se FDBackup non ne possiede già uno.
    if handler_esistente is None:

        # Crea un handler con rotazione automatica del file al raggiungimento della dimensione massima.
        handler_file = RotatingFileHandler(
            filename=percorso_log,
            maxBytes=DIMENSIONE_MASSIMA_LOG,
            backupCount=NUMERO_BACKUP_LOG,
            encoding="utf-8",
        )

        # Contrassegna l'handler per riconoscerlo in eventuali chiamate successive.
        handler_file._fdbackup_handler = True

        # Registra nel file soltanto messaggi dal livello INFO in su.
        handler_file.setLevel(logging.INFO)

        # Definisce il formato uniforme utilizzato per ogni riga del file di log.
        formato_log = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Applica il formato appena definito all'handler del file.
        handler_file.setFormatter(formato_log)

        # Collega l'handler al logger principale di FDBackup.
        logger_fdbackup.addHandler(handler_file)

    # Restituisce il percorso del file per permettere all'applicazione e ai test di conoscerne la posizione.
    return percorso_log