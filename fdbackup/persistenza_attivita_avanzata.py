import json  # Importa il formato JSON usato per mantenere leggibili e portabili i registri Attività avanzati.
from pathlib import Path  # Importa Path per gestire il file persistente senza concatenazioni testuali fragili.


SEZIONI_ATTIVITA_SUPPORTATE = ("strategie", "sincronizza", "ripristino_versionato", "verifica_integrita")  # Definisce le sezioni avanzate autorizzate a usare questo archivio, mantenendo compatibili i file creati dalle versioni precedenti.
LIMITE_RIGHE_PER_SEZIONE = 500  # Limita la crescita del file mantenendo le stesse cinquecento righe già mostrate dalla GUI.


def _normalizza_registro(registro) -> list[str]:
    """Converte un valore caricato in un elenco sicuro di righe testuali limitato agli eventi più recenti."""
    if not isinstance(registro, list):  # Rifiuta strutture diverse dall'elenco previsto senza propagare dati corrotti alla GUI.
        return []  # Riparte da un registro vuoto quando la singola sezione non è valida.
    righe = [str(riga) for riga in registro if isinstance(riga, str)]  # Mantiene soltanto stringhe realmente persistite come eventi Attività.
    return righe[-LIMITE_RIGHE_PER_SEZIONE:]  # Conserva esclusivamente la finestra massima supportata dalla GUI.


def carica_attivita_avanzate(percorso: Path) -> dict[str, list[str]]:
    """Carica i registri avanzati; un file assente o corrotto produce registri vuoti senza impedire l'avvio."""
    percorso = Path(percorso)  # Normalizza il percorso ricevuto dal chiamante.
    registri = {sezione: [] for sezione in SEZIONI_ATTIVITA_SUPPORTATE}  # Prepara sempre tutte le chiavi richieste dalla GUI.
    try:  # Isola l'avvio dell'applicazione da file mancanti, illeggibili o JSON incompleti.
        with percorso.open("r", encoding="utf-8") as file_aperto:  # Apre il documento persistente in sola lettura UTF-8.
            dati = json.load(file_aperto)  # Decodifica il JSON prima della validazione delle singole sezioni.
    except (FileNotFoundError, OSError, json.JSONDecodeError):  # Gestisce normalmente primo avvio, problemi temporanei e documento corrotto.
        return registri  # Restituisce una struttura valida senza modificare automaticamente il file problematico.
    if not isinstance(dati, dict):  # Richiede un oggetto JSON con una chiave distinta per ogni sezione.
        return registri  # Ignora una radice incompatibile invece di interpretarla in modo ambiguo.
    for sezione in SEZIONI_ATTIVITA_SUPPORTATE:  # Valida indipendentemente ciascun registro supportato.
        registri[sezione] = _normalizza_registro(dati.get(sezione, []))  # Mantiene le sezioni valide e svuota soltanto quelle malformate.
    return registri  # Restituisce i registri pronti per essere assegnati allo stato della GUI.


def salva_attivita_avanzate(percorso: Path, registri: dict[str, list[str]]) -> None:
    """Salva atomicamente i registri avanzati così la chiusura del programma non cancella l'Attività."""
    percorso = Path(percorso)  # Normalizza il percorso destinazione.
    percorso.parent.mkdir(parents=True, exist_ok=True)  # Garantisce l'esistenza della cartella che conterrà il documento.
    dati = {sezione: _normalizza_registro(registri.get(sezione, [])) for sezione in SEZIONI_ATTIVITA_SUPPORTATE}  # Serializza soltanto sezioni note e valori validi.
    temporaneo = percorso.with_suffix(percorso.suffix + ".tmp")  # Prepara un file temporaneo nella stessa directory per la sostituzione atomica.
    with temporaneo.open("w", encoding="utf-8", newline="\n") as file_aperto:  # Scrive il documento completo prima di sostituire quello precedente.
        json.dump(dati, file_aperto, ensure_ascii=False, indent=2, sort_keys=True)  # Mantiene il file leggibile e deterministico per diagnosi future.
        file_aperto.flush()  # Scarica il buffer Python prima della sostituzione del file definitivo.
    temporaneo.replace(percorso)  # Pubblica in un solo passaggio il nuovo stato dei registri.
