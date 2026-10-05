import json  # Importa JSON per persistere in modo leggibile lo stato delle occorrenze già acquisite.
import os  # Importa le primitive usate per sincronizzare e sostituire atomicamente il file di stato.
import tempfile  # Importa la creazione sicura di file temporanei nella stessa cartella del file finale.
from dataclasses import dataclass  # Importa dataclass per rappresentare in modo esplicito un'occorrenza pianificata.
from datetime import datetime, timedelta  # Importa gli strumenti temporali necessari al calcolo settimanale delle occorrenze.
from pathlib import Path  # Importa Path per gestire il percorso del file di stato.

from fdbackup.modelli_backup import PianificazioneBackup  # Riusa il modello di pianificazione già validato dal progetto.


GIORNI_RICERCA_OCCORRENZA = 7  # Cerca al massimo nell'ultima settimana perché la pianificazione è settimanale.


@dataclass(slots=True, frozen=True)
class OccorrenzaPianificata:
    """Rappresenta una singola occorrenza settimanale identificabile senza ambiguità dal scheduler."""

    chiave: str  # Conserva la chiave locale YYYY-MM-DDTHH:MM usata per impedire esecuzioni duplicate.
    momento: datetime  # Conserva il datetime locale senza fuso usato esclusivamente per confronti di calendario.


def _momento_locale_senza_fuso(momento: datetime | None = None) -> datetime:
    """Restituisce un datetime locale senza tzinfo per confrontare la pianificazione espressa come ora civile locale."""
    if momento is None:  # Usa l'orologio di sistema soltanto quando il chiamante non fornisce un istante deterministico.
        return datetime.now().astimezone().replace(tzinfo=None)  # Converte prima nell'ora locale e poi mantiene soltanto il calendario civile.
    if not isinstance(momento, datetime):  # Difende il contratto pubblico da valori temporali di tipo errato.
        raise TypeError("Il momento di riferimento deve essere un datetime.")  # Espone un errore esplicito al chiamante.
    if momento.tzinfo is not None:  # Riconosce un datetime consapevole del fuso orario.
        return momento.astimezone().replace(tzinfo=None)  # Converte nell'ora locale del sistema prima di confrontare giorno e HH:MM.
    return momento  # Accetta un datetime naive come ora locale già pronta, utile soprattutto nei test deterministici.


def trova_ultima_occorrenza(pianificazione: PianificazioneBackup, momento: datetime | None = None) -> OccorrenzaPianificata | None:
    """Trova l'ultima occorrenza pianificata non futura nell'ultima settimana, includendo il recupero dopo un riavvio."""
    if not isinstance(pianificazione, PianificazioneBackup):  # Richiede il modello validato usato dal resto di FDBackup.
        raise TypeError("La pianificazione deve essere un oggetto PianificazioneBackup.")  # Rifiuta dizionari e strutture non validate.
    if not pianificazione.abilitata:  # Una pianificazione disabilitata non deve produrre alcun trigger.
        return None  # Comunica esplicitamente l'assenza di un'occorrenza eseguibile.

    adesso = _momento_locale_senza_fuso(momento)  # Normalizza il riferimento temporale una sola volta.
    ora, minuto = (int(parte) for parte in pianificazione.ora.split(":"))  # Estrae ora e minuto dal formato HH:MM già validato dal modello.
    attiva_dal = datetime.strptime(pianificazione.attiva_dal, "%Y-%m-%dT%H:%M:%S") if pianificazione.attiva_dal else None  # Ricostruisce il limite civile locale soltanto per le pianificazioni nuove che lo possiedono.

    for giorni_indietro in range(GIORNI_RICERCA_OCCORRENZA):  # Esamina oggi e i sei giorni precedenti, sufficienti per una regola settimanale.
        giorno = (adesso - timedelta(days=giorni_indietro)).date()  # Calcola la data civile candidata senza alterare l'ora corrente.
        if giorno.weekday() not in pianificazione.giorni:  # Scarta i giorni non selezionati dall'utente.
            continue  # Passa immediatamente alla data precedente.
        candidato = datetime(giorno.year, giorno.month, giorno.day, ora, minuto)  # Costruisce l'orario civile previsto per quella data.
        if candidato <= adesso and (attiva_dal is None or candidato >= attiva_dal):  # Accetta solo scadenze maturate e, quando noto, non antecedenti alla creazione o modifica della regola.
            return OccorrenzaPianificata(candidato.strftime("%Y-%m-%dT%H:%M"), candidato)  # Restituisce la più recente grazie all'ordine della ricerca.

    return None  # Nessuna occorrenza valida è maturata nell'ultima settimana.


def carica_stato_scheduler(percorso: Path) -> dict[str, str]:
    """Carica le ultime occorrenze acquisite; un file assente equivale a uno scheduler mai eseguito."""
    percorso = Path(percorso)  # Normalizza il percorso ricevuto dal chiamante.
    if not percorso.exists():  # Gestisce il primo avvio senza considerarlo un errore.
        return {}  # Restituisce uno stato vuoto pronto all'uso.
    try:  # Protegge lettura, decodifica e parsing del documento persistente.
        dati = json.loads(percorso.read_text(encoding="utf-8-sig"))  # Legge UTF-8 accettando anche un eventuale BOM.
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as errore:  # Intercetta file illeggibile o JSON corrotto.
        raise ValueError(f"Impossibile leggere lo stato dello scheduler: {errore}") from errore  # Non nasconde una possibile perdita dello stato anti-duplicazione.
    if not isinstance(dati, dict):  # Richiede una mappa identificatore -> occorrenza.
        raise ValueError("Lo stato dello scheduler deve essere un oggetto JSON.")  # Rifiuta strutture incompatibili.
    stato: dict[str, str] = {}  # Prepara una copia validata indipendente dal JSON originale.
    for identificatore, chiave in dati.items():  # Valida ogni coppia prima di pubblicare lo stato.
        if not isinstance(identificatore, str) or not identificatore.strip():  # Richiede una chiave persistente non vuota.
            raise ValueError("Lo stato dello scheduler contiene un identificatore non valido.")  # Evita collisioni o record anonimi.
        if not isinstance(chiave, str):  # Richiede la chiave temporale nel formato testuale previsto.
            raise ValueError("Lo stato dello scheduler contiene un'occorrenza non valida.")  # Rifiuta numeri, null e oggetti.
        try:  # Verifica che la chiave rappresenti realmente data e ora fino ai minuti.
            datetime.strptime(chiave, "%Y-%m-%dT%H:%M")  # Analizza rigorosamente il formato persistente.
        except ValueError as errore:  # Converte il dettaglio di parsing nel contratto del modulo.
            raise ValueError("Lo stato dello scheduler contiene un'occorrenza non valida.") from errore  # Mantiene il file corrotto visibile al chiamante.
        stato[identificatore.strip()] = chiave  # Pubblica la coppia soltanto dopo la validazione completa.
    return stato  # Restituisce la mappa pronta per il controllo anti-duplicazione.


def salva_stato_scheduler(percorso: Path, stato: dict[str, str]) -> None:
    """Salva atomicamente lo stato anti-duplicazione dello scheduler nella stessa directory del file finale."""
    percorso = Path(percorso)  # Normalizza il percorso finale.
    if not isinstance(stato, dict):  # Difende il confine del modulo da strutture arbitrarie.
        raise TypeError("Lo stato dello scheduler deve essere un dizionario.")  # Impedisce serializzazioni ambigue.
    percorso.parent.mkdir(parents=True, exist_ok=True)  # Garantisce l'esistenza della cartella contenitore.
    descrittore, nome_temporaneo = tempfile.mkstemp(prefix=f".{percorso.name}.", suffix=".tmp", dir=percorso.parent, text=True)  # Crea un temporaneo univoco nello stesso filesystem.
    temporaneo = Path(nome_temporaneo)  # Converte il nome restituito in Path.
    try:  # Protegge l'intera sequenza di persistenza.
        with os.fdopen(descrittore, "w", encoding="utf-8", newline="\n") as file_temporaneo:  # Prende possesso del descrittore già aperto.
            json.dump(stato, file_temporaneo, ensure_ascii=False, indent=2, sort_keys=True)  # Scrive uno stato leggibile e deterministico.
            file_temporaneo.write("\n")  # Termina il documento con newline.
            file_temporaneo.flush()  # Svuota i buffer Python prima della sincronizzazione.
            os.fsync(file_temporaneo.fileno())  # Chiede al sistema operativo di sincronizzare i dati del temporaneo.
        os.replace(temporaneo, percorso)  # Sostituisce il file finale soltanto dopo una scrittura completa.
    except Exception:  # Garantisce la pulizia senza nascondere l'errore originale.
        temporaneo.unlink(missing_ok=True)  # Elimina l'eventuale file temporaneo rimasto.
        raise  # Propaga il problema al chiamante.


def occorrenza_da_eseguire(identificatore: str, pianificazione: PianificazioneBackup, stato: dict[str, str], momento: datetime | None = None) -> OccorrenzaPianificata | None:
    """Restituisce l'ultima occorrenza dovuta soltanto se non è già stata acquisita per lo stesso identificatore."""
    if not isinstance(identificatore, str) or not identificatore.strip():  # Richiede un identificatore persistente stabile.
        raise ValueError("L'identificatore della pianificazione non può essere vuoto.")  # Evita record anti-duplicazione anonimi.
    if not isinstance(stato, dict):  # Richiede lo stato caricato dal modulo.
        raise TypeError("Lo stato dello scheduler deve essere un dizionario.")  # Rifiuta collezioni incompatibili.
    occorrenza = trova_ultima_occorrenza(pianificazione, momento)  # Calcola l'ultima scadenza maturata secondo il calendario locale.
    if occorrenza is None:  # Gestisce pianificazioni disabilitate o senza scadenze maturate.
        return None  # Non produce lavoro.
    if stato.get(identificatore.strip()) == occorrenza.chiave:  # Confronta la chiave dell'ultima acquisizione persistita.
        return None  # Impedisce una seconda esecuzione della stessa occorrenza anche dopo un riavvio.
    return occorrenza  # Espone l'occorrenza ancora da acquisire.


def acquisisci_occorrenza(percorso_stato: Path, stato: dict[str, str], identificatore: str, occorrenza: OccorrenzaPianificata) -> dict[str, str]:
    """Marca un'occorrenza come acquisita prima dell'avvio del backup e persiste immediatamente la protezione anti-duplicazione."""
    if not isinstance(occorrenza, OccorrenzaPianificata):  # Richiede un'occorrenza prodotta dal calcolo validato.
        raise TypeError("L'occorrenza deve essere un oggetto OccorrenzaPianificata.")  # Rifiuta valori temporali non strutturati.
    nuovo_stato = dict(stato)  # Lavora su una copia per non pubblicare in memoria uno stato non ancora scritto.
    nuovo_stato[identificatore.strip()] = occorrenza.chiave  # Registra la scadenza prima dell'esecuzione per privilegiare l'assenza di duplicati.
    salva_stato_scheduler(percorso_stato, nuovo_stato)  # Persiste atomicamente la nuova acquisizione.
    return nuovo_stato  # Restituisce lo stato aggiornato soltanto dopo il salvataggio riuscito.
