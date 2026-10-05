import json  # Importa il supporto JSON necessario per leggere e scrivere la configurazione.
import logging  # Importa il sistema di logging standard per registrare gli eventi diagnostici.
import os  # Importa le primitive del sistema operativo usate per sincronizzare e sostituire il file in sicurezza.
import tempfile  # Importa la creazione sicura di file temporanei con nomi non prevedibili.
from pathlib import Path  # Importa Path per gestire il percorso del file di configurazione.


logger = logging.getLogger(__name__)  # Crea il logger del modulo, che eredita la configurazione dal logger principale "fdbackup".


def carica_configurazione(percorso_configurazione: Path) -> dict:
    """Legge un file JSON di configurazione e restituisce sempre un dizionario utilizzabile."""

    if not percorso_configurazione.exists():  # Controlla se il file di configurazione esiste già.
        return {}  # Restituisce una configurazione vuota quando il file non è ancora stato creato.

    try:  # Prova ad aprire, decodificare e interpretare il contenuto del file JSON.
        with percorso_configurazione.open("r", encoding="utf-8-sig") as file_configurazione:  # Legge UTF-8 normale e accetta anche un eventuale BOM iniziale.
            dati = json.load(file_configurazione)  # Converte il documento JSON nel corrispondente oggetto Python.

        if isinstance(dati, dict):  # Verifica che la radice del documento JSON sia un oggetto rappresentato da un dizionario.
            return dati  # Restituisce la configurazione quando la struttura è quella prevista.

        return {}  # Rifiuta strutture JSON valide ma non adatte a rappresentare la configurazione dell'applicazione.

    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as errore:  # Gestisce problemi di accesso, codifica e sintassi JSON.
        logger.error(  # Registra il problema nel sistema di logging senza interrompere l'applicazione.
            "Impossibile leggere la configurazione '%s': %s",
            percorso_configurazione,
            errore,
        )
        return {}  # Restituisce una configurazione vuota per consentire al chiamante di continuare in sicurezza.


def salva_configurazione(percorso_configurazione: Path, configurazione: dict) -> None:
    """Salva la configurazione in UTF-8 sostituendo il file finale solo dopo una scrittura temporanea completa."""

    percorso_configurazione = Path(percorso_configurazione)  # Normalizza anche un eventuale percorso compatibile con Path ricevuto dal chiamante.
    descrittore_temporaneo, nome_temporaneo = tempfile.mkstemp(  # Crea in modo sicuro un file temporaneo univoco già aperto dal sistema operativo.
        prefix=f".{percorso_configurazione.name}.",  # Usa un prefisso riconoscibile senza riutilizzare direttamente il nome del file finale.
        suffix=".tmp",  # Aggiunge un suffisso esplicito che identifica il file come temporaneo.
        dir=percorso_configurazione.parent,  # Crea il temporaneo nella stessa directory per evitare una sostituzione tra filesystem differenti.
        text=True,  # Richiede un descrittore destinato a essere usato in modalità testuale.
    )
    percorso_temporaneo = Path(nome_temporaneo)  # Converte il nome assoluto restituito da mkstemp in un oggetto Path.

    try:  # Protegge l'intera sequenza affinché un errore lasci intatto l'eventuale file di configurazione precedente.
        with os.fdopen(descrittore_temporaneo, "w", encoding="utf-8", newline="\n") as file_temporaneo:  # Trasforma il descrittore già aperto in un file testuale gestito da context manager.
            json.dump(configurazione, file_temporaneo, indent=4, ensure_ascii=False)  # Serializza il documento completo nel file temporaneo preservando i caratteri Unicode.
            file_temporaneo.flush()  # Trasferisce al sistema operativo i dati ancora presenti nei buffer Python.
            os.fsync(file_temporaneo.fileno())  # Chiede al sistema operativo di sincronizzare sul disco i dati del file temporaneo prima della sostituzione.

        os.replace(percorso_temporaneo, percorso_configurazione)  # Sostituisce il file finale soltanto dopo che il temporaneo è stato scritto, sincronizzato e chiuso.

    except Exception:  # Intercetta qualsiasi errore soltanto per poter ripulire il temporaneo, lasciando poi propagare l'eccezione originale.
        try:  # Tenta la pulizia senza nascondere l'errore principale che ha impedito il salvataggio.
            percorso_temporaneo.unlink(missing_ok=True)  # Elimina l'eventuale file temporaneo rimasto dopo serializzazione, sincronizzazione o sostituzione fallita.
        except OSError:  # Gestisce un eventuale errore secondario durante la sola pulizia del file temporaneo.
            logger.warning(  # Registra la mancata pulizia senza sostituire l'eccezione originale del salvataggio.
                "Impossibile eliminare il file temporaneo di configurazione '%s'.",
                percorso_temporaneo,
            )
        raise  # Propaga l'errore originale affinché il chiamante sappia che la configurazione non è stata salvata.
