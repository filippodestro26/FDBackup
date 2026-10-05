import json  # Importa JSON per salvare una cronologia strutturata e leggibile.
import os  # Importa le primitive usate per sincronizzare e sostituire atomicamente il file finale.
import tempfile  # Importa la creazione sicura di file temporanei nella stessa cartella della cronologia.
from dataclasses import asdict, dataclass  # Importa gli strumenti standard per rappresentare e serializzare un record.
from datetime import datetime  # Importa datetime per validare e generare timestamp ISO locali.
from pathlib import Path  # Importa Path per gestire il percorso del file senza dipendere dalla GUI.

NUMERO_MASSIMO_RECORD = 100  # Limita la crescita del file mantenendo gli ultimi cento eventi operativi.


@dataclass(slots=True, frozen=True)
class RecordOperazione:
    """Rappresenta un'esecuzione conclusa di backup o ripristino con dati sufficienti per la Home."""

    timestamp: str  # Conserva data e ora locali in formato ISO fino ai secondi.
    tipo: str  # Distingue backup_singolo, backup_multiplo e ripristino.
    stato: str  # Conserva uno stato normalizzato: successo, problemi, fallito oppure annullato.
    descrizione: str  # Conserva una descrizione breve e leggibile dell'operazione.
    file_copiati: int = 0  # Conta i file copiati o ripristinati con successo.
    file_ignorati: int = 0  # Conta i file già identici e quindi non ricopiati.
    file_falliti: int = 0  # Conta i file che hanno prodotto un errore.
    byte_copiati: int = 0  # Conserva i byte effettivamente copiati o ripristinati.
    problemi: tuple[str, ...] = ()  # Conserva messaggi diagnostici sintetici senza dipendere dal log testuale.

    def __post_init__(self) -> None:
        """Valida il record prima che possa essere persistito."""
        try:  # Verifica che il timestamp sia un ISO datetime realmente interpretabile.
            datetime.fromisoformat(self.timestamp)  # Analizza il timestamp senza modificarlo.
        except (TypeError, ValueError) as errore:  # Riconosce timestamp mancanti o non validi.
            raise ValueError("Il timestamp della cronologia non è valido.") from errore  # Impedisce record temporalmente ambigui.
        if self.tipo not in {"backup_singolo", "backup_multiplo", "ripristino", "backup_versionato", "sincronizzazione", "ripristino_versionato", "operazione_avanzata"}:  # Limita i tipi alle operazioni realmente gestite.
            raise ValueError("Il tipo di operazione della cronologia non è valido.")  # Rifiuta valori inventati o corrotti.
        if self.stato not in {"successo", "problemi", "fallito", "annullato"}:  # Limita lo stato a valori stabili per la GUI.
            raise ValueError("Lo stato della cronologia non è valido.")  # Rifiuta stati non previsti.
        if not isinstance(self.descrizione, str) or not self.descrizione.strip():  # Richiede una descrizione realmente leggibile.
            raise ValueError("La descrizione della cronologia non può essere vuota.")  # Evita righe anonime nella Home.
        for valore in (self.file_copiati, self.file_ignorati, self.file_falliti, self.byte_copiati):  # Controlla tutti i contatori numerici.
            if isinstance(valore, bool) or not isinstance(valore, int) or valore < 0:  # Esclude booleani, tipi errati e numeri negativi.
                raise ValueError("I contatori della cronologia devono essere interi non negativi.")  # Mantiene dati coerenti.
        if not isinstance(self.problemi, tuple) or any(not isinstance(problema, str) for problema in self.problemi):  # Richiede una tupla di testi.
            raise ValueError("I problemi della cronologia devono essere una tupla di stringhe.")  # Evita strutture JSON inattese.


def crea_record_operazione(tipo: str, stato: str, descrizione: str, file_copiati: int = 0, file_ignorati: int = 0, file_falliti: int = 0, byte_copiati: int = 0, problemi: tuple[str, ...] = ()) -> RecordOperazione:
    """Crea un record usando l'ora locale corrente soltanto al termine reale dell'operazione."""
    return RecordOperazione(datetime.now().astimezone().isoformat(timespec="seconds"), tipo, stato, descrizione.strip(), file_copiati, file_ignorati, file_falliti, byte_copiati, tuple(problemi))  # Costruisce un record validato e pronto al salvataggio.


def carica_cronologia(percorso: Path) -> list[RecordOperazione]:
    """Carica la cronologia; un file assente restituisce una lista vuota mentre dati corrotti sollevano ValueError."""
    percorso = Path(percorso)  # Normalizza il percorso ricevuto dal chiamante.
    if not percorso.exists():  # Riconosce il primo avvio dell'applicazione.
        return []  # Non considera errore l'assenza della cronologia.
    try:  # Protegge lettura, decodifica e parsing JSON.
        dati = json.loads(percorso.read_text(encoding="utf-8-sig"))  # Legge UTF-8 accettando anche un eventuale BOM.
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as errore:  # Intercetta file illeggibile o JSON corrotto.
        raise ValueError(f"Impossibile leggere la cronologia: {errore}") from errore  # Espone un errore controllato al chiamante.
    if not isinstance(dati, list):  # Richiede un array JSON come radice del documento.
        raise ValueError("La cronologia deve contenere un array JSON.")  # Rifiuta strutture incompatibili.
    record = []  # Prepara la lista tipizzata da restituire.
    for elemento in dati:  # Valida ogni elemento senza correggerlo silenziosamente.
        if not isinstance(elemento, dict):  # Richiede un oggetto JSON per ogni record.
            raise ValueError("Ogni elemento della cronologia deve essere un oggetto JSON.")  # Blocca elementi ambigui.
        problemi = elemento.get("problemi", [])  # Recupera l'elenco persistito dei problemi.
        if not isinstance(problemi, list):  # Verifica il formato JSON previsto.
            raise ValueError("Il campo problemi della cronologia deve essere un array JSON.")  # Evita conversioni implicite.
        try:  # Costruisce il modello usando valori espliciti.
            record.append(RecordOperazione(timestamp=elemento["timestamp"], tipo=elemento["tipo"], stato=elemento["stato"], descrizione=elemento["descrizione"], file_copiati=elemento.get("file_copiati", 0), file_ignorati=elemento.get("file_ignorati", 0), file_falliti=elemento.get("file_falliti", 0), byte_copiati=elemento.get("byte_copiati", 0), problemi=tuple(problemi)))  # Ricostruisce e valida il record.
        except (KeyError, TypeError, ValueError) as errore:  # Converte errori strutturali in un unico contratto pubblico.
            raise ValueError(f"Record della cronologia non valido: {errore}") from errore  # Non nasconde la corruzione del file.
    return record[-NUMERO_MASSIMO_RECORD:]  # Applica il limite anche a file creati da versioni precedenti.


def salva_cronologia(percorso: Path, record: list[RecordOperazione]) -> None:
    """Salva atomicamente gli ultimi record della cronologia in UTF-8."""
    percorso = Path(percorso)  # Normalizza il percorso finale.
    percorso.parent.mkdir(parents=True, exist_ok=True)  # Garantisce l'esistenza della cartella contenitore.
    record_limitati = list(record)[-NUMERO_MASSIMO_RECORD:]  # Mantiene soltanto la coda più recente.
    dati = []  # Prepara una struttura composta da tipi JSON nativi.
    for elemento in record_limitati:  # Serializza ogni record dopo averne verificato il tipo.
        if not isinstance(elemento, RecordOperazione):  # Impedisce di salvare dizionari non validati.
            raise TypeError("La cronologia può contenere soltanto RecordOperazione.")  # Mantiene il confine del modello.
        voce = asdict(elemento)  # Converte la dataclass in un nuovo dizionario.
        voce["problemi"] = list(elemento.problemi)  # Converte la tupla in array JSON.
        dati.append(voce)  # Aggiunge il record serializzabile.
    descrittore, nome_temporaneo = tempfile.mkstemp(prefix=f".{percorso.name}.", suffix=".tmp", dir=percorso.parent, text=True)  # Crea un temporaneo nella stessa directory.
    temporaneo = Path(nome_temporaneo)  # Converte il nome restituito in Path.
    try:  # Protegge la sequenza di scrittura e sostituzione.
        with os.fdopen(descrittore, "w", encoding="utf-8", newline="\n") as file_temporaneo:  # Prende possesso del descrittore aperto.
            json.dump(dati, file_temporaneo, ensure_ascii=False, indent=2)  # Scrive un JSON leggibile senza perdere caratteri italiani.
            file_temporaneo.write("\n")  # Termina il documento con newline.
            file_temporaneo.flush()  # Svuota i buffer Python prima della sincronizzazione.
            os.fsync(file_temporaneo.fileno())  # Chiede al sistema operativo di sincronizzare i dati del temporaneo.
        os.replace(temporaneo, percorso)  # Sostituisce atomicamente il file finale nello stesso filesystem.
    except Exception:  # Garantisce la pulizia del temporaneo per qualunque errore di scrittura.
        temporaneo.unlink(missing_ok=True)  # Elimina il file parziale senza toccare la cronologia precedente.
        raise  # Propaga l'errore originale al chiamante.



def cancella_cronologia(percorso: Path) -> None:
    """Elimina soltanto il file della cronologia utente senza creare o modificare altri file applicativi."""
    percorso = Path(percorso)  # Normalizza il percorso ricevuto dal chiamante senza derivare percorsi di stato o configurazione.
    try:  # Tenta la rimozione mantenendo idempotente il caso di primo avvio o cronologia già vuota.
        percorso.unlink()  # Elimina esclusivamente il file indicato dal chiamante.
    except FileNotFoundError:  # Riconosce che non esiste alcuna cronologia persistente da cancellare.
        return  # Considera già raggiunto lo stato richiesto senza creare un file vuoto.

def aggiungi_record(percorso: Path, nuovo_record: RecordOperazione) -> list[RecordOperazione]:
    """Aggiunge un record alla cronologia esistente e restituisce la nuova lista limitata."""
    record = carica_cronologia(percorso)  # Carica lo stato precedente prima di modificarlo.
    record.append(nuovo_record)  # Aggiunge il nuovo evento in coda cronologica.
    record = record[-NUMERO_MASSIMO_RECORD:]  # Applica immediatamente il limite massimo.
    salva_cronologia(percorso, record)  # Persiste la nuova cronologia in modo atomico.
    return record  # Restituisce la lista aggiornata utile alla GUI.
