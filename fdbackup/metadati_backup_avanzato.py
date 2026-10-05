"""Metadati persistenti per le strategie avanzate di backup di file di FDBackup."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from fdbackup.filtri_backup import rileva_reparse as filtro_rileva_reparse
from typing import Iterable
from uuid import uuid4


VERSIONE_FORMATO_MANIFESTO = 1  # Identifica la versione del formato JSON per consentire future migrazioni controllate.
NOME_CARTELLA_METADATI = ".backupcore"  # Isola i metadati applicativi dai dati copiati dell'utente.
NOME_FILE_STATO = "stato.json"  # Conserva lo stato corrente della catena associata a una sorgente.
DIMENSIONE_BLOCCO_HASH = 1024 * 1024  # Legge i file a blocchi da 1 MiB senza caricarli interamente in memoria.


@dataclass(slots=True, frozen=True)
class VoceManifesto:
    """Descrive lo stato verificabile di un singolo file della sorgente."""

    percorso_relativo: str  # Conserva il percorso relativo in forma POSIX per rendere stabile il formato persistente.
    dimensione: int  # Conserva la dimensione del file osservata durante la scansione.
    modifica_ns: int  # Conserva il timestamp di modifica con precisione in nanosecondi fornito dal filesystem.
    sha256: str  # Conserva SHA-256 per distinguere in modo affidabile contenuti con stessa dimensione e timestamp.


@dataclass(slots=True)
class ManifestoBackup:
    """Descrive una versione della sorgente e la relazione con la relativa catena di backup."""

    id_backup: str  # Identifica univocamente la versione di backup.
    tipo_backup: str  # Distingue completo, incrementale e differenziale.
    creato_il: str  # Conserva l'istante locale di creazione in formato ISO con secondi.
    sorgente: str  # Conserva la sorgente normalizzata usata per produrre il manifesto.
    id_full_base: str  # Identifica il Full dal quale dipende la catena corrente.
    id_backup_precedente: str = ""  # Identifica il backup precedente per la catena incrementale.
    file: dict[str, VoceManifesto] = field(default_factory=dict)  # Mappa ogni percorso relativo al relativo stato verificato.
    eliminati: tuple[str, ...] = field(default_factory=tuple)  # Registra i percorsi rimossi rispetto alla base logica del backup.
    cartelle: tuple[str, ...] = field(default_factory=tuple)  # Conserva anche le directory, comprese quelle vuote, per un ripristino fedele della struttura.
    versione_formato: int = VERSIONE_FORMATO_MANIFESTO  # Registra esplicitamente il formato persistente usato.


def calcola_sha256(percorso: Path) -> str:
    """Calcola SHA-256 di un file usando lettura incrementale."""
    calcolatore = hashlib.sha256()  # Crea un nuovo contesto SHA-256 indipendente per il file corrente.
    with percorso.open("rb") as file_aperto:  # Apre il file in sola lettura binaria e garantisce la chiusura automatica.
        while True:  # Continua finché il file contiene altri dati da elaborare.
            blocco = file_aperto.read(DIMENSIONE_BLOCCO_HASH)  # Legge un blocco limitato per contenere l'uso di memoria.
            if not blocco:  # Riconosce la fine del file.
                break  # Termina il ciclo senza aggiungere dati inesistenti all'hash.
            calcolatore.update(blocco)  # Aggiorna l'impronta con il blocco appena letto.
    return calcolatore.hexdigest()  # Restituisce la rappresentazione esadecimale stabile dell'impronta.


def crea_manifesto_file(sorgente: Path, includi_sottocartelle: bool = True, filtro=None, funzione_evento=None) -> dict[str, VoceManifesto]:
    """Scansiona la sorgente e restituisce lo stato verificato dei file presenti."""
    sorgente = Path(sorgente).expanduser().resolve(strict=True)  # Normalizza la sorgente e richiede che esista realmente.
    if not sorgente.is_dir():  # Verifica che la radice rappresenti una cartella.
        raise ValueError("La sorgente del manifesto deve essere una cartella.")  # Rifiuta file singoli e oggetti non compatibili.
    risultato: dict[str, VoceManifesto] = {}  # Prepara la mappa ordinata logicamente per percorso relativo.
    candidati: Iterable[Path] = sorgente.rglob("*") if includi_sottocartelle else sorgente.iterdir()  # Seleziona scansione ricorsiva o solo radice.
    for percorso in sorted((elemento for elemento in candidati if elemento.is_file()), key=lambda elemento: elemento.as_posix().casefold()):  # Elabora soltanto file in ordine deterministico.
        relativo = percorso.relative_to(sorgente).as_posix()  # Converte il percorso relativo in rappresentazione portabile.
        statistiche = percorso.stat()  # Legge una volta i metadati necessari al manifesto.
        if filtro is not None:
            accettato, motivo = filtro.valuta(relativo, statistiche.st_size, filtro_rileva_reparse(percorso), percorso)
            if not accettato:
                if funzione_evento is not None:
                    funzione_evento("file_escluso", {"file": relativo, "motivo": motivo or "filtro"})
                continue  # Esclude il file prima di calcolare SHA-256 e prima di qualsiasi copia.
        risultato[relativo] = VoceManifesto(relativo, statistiche.st_size, statistiche.st_mtime_ns, calcola_sha256(percorso))  # Registra contenuto e metadati essenziali.
        if funzione_evento is not None:
            funzione_evento("file_incluso", {"file": relativo})
    return risultato  # Restituisce lo snapshot logico completo della sorgente.



def elenca_cartelle_relative(sorgente: Path, includi_sottocartelle: bool = True, filtro=None, funzione_evento=None) -> tuple[str, ...]:
    """Restituisce le directory relative della sorgente, comprese quelle vuote, in ordine deterministico."""
    sorgente = Path(sorgente).expanduser().resolve(strict=True)  # Normalizza la radice e richiede che esista prima della scansione.
    candidati = sorgente.rglob("*") if includi_sottocartelle else sorgente.iterdir()  # Rispetta la stessa profondità scelta per i file.
    cartelle: list[str] = []
    for elemento in candidati:
        if not elemento.is_dir():
            continue
        relativo = elemento.relative_to(sorgente).as_posix()
        if filtro is not None and not filtro.accetta_cartella(relativo, elemento):
            if funzione_evento is not None:
                motivo = "reparse" if filtro_rileva_reparse(elemento) and filtro.politica_reparse == "ignora" else ("nascosto" if filtro.escludi_nascosti and filtro._nascosto(elemento) else "pattern_esclusione")
                funzione_evento("cartella_esclusa", {"cartella": relativo, "motivo": motivo})
            continue
        cartelle.append(relativo)
    return tuple(sorted(cartelle, key=str.casefold))  # Restituisce un ordine stabile utile a manifesti, test e ripristino.


def nome_cartella_versione(manifesto: ManifestoBackup) -> str:
    """Genera un nome leggibile della versione mantenendo l'UUID completo soltanto nei metadati."""
    data_leggibile = manifesto.creato_il.replace(":", "-").replace("T", "_")  # Rende il timestamp compatibile con i nomi di directory Windows.
    return f"{data_leggibile}_{manifesto.tipo_backup.upper()}_{manifesto.id_backup[:8]}"  # Combina data, metodo e prefisso univoco leggibile.

def crea_manifesto_backup(tipo_backup: str, sorgente: Path, file: dict[str, VoceManifesto], id_full_base: str = "", id_backup_precedente: str = "", eliminati: tuple[str, ...] = (), cartelle: tuple[str, ...] = ()) -> ManifestoBackup:
    """Crea un manifesto di versione validando il tipo richiesto."""
    tipo_normalizzato = tipo_backup.strip().lower()  # Normalizza il tipo per evitare differenze puramente grafiche.
    if tipo_normalizzato not in {"completo", "incrementale", "differenziale"}:  # Limita il formato ai metodi realmente supportati dal motore di catena.
        raise ValueError("Tipo di backup avanzato non supportato.")  # Evita manifesti con semantica sconosciuta.
    id_backup = str(uuid4())  # Genera un'identità indipendente dal nome delle cartelle fisiche.
    full_base = id_backup if tipo_normalizzato == "completo" else id_full_base.strip()  # Un Full è la propria base; gli altri devono riferirsi a un Full esistente.
    if not full_base:  # Verifica che incrementale e differenziale abbiano una base valida.
        raise ValueError("Un backup incrementale o differenziale richiede un Full di base.")  # Impedisce catene orfane.
    return ManifestoBackup(id_backup=id_backup, tipo_backup=tipo_normalizzato, creato_il=datetime.now().isoformat(timespec="seconds"), sorgente=str(Path(sorgente).expanduser().resolve(strict=False)), id_full_base=full_base, id_backup_precedente=id_backup_precedente.strip(), file=dict(file), eliminati=tuple(sorted(set(eliminati))), cartelle=tuple(sorted(set(cartelle))))  # Restituisce un documento completo e deterministico.


def serializza_manifesto(manifesto: ManifestoBackup) -> dict:
    """Converte un manifesto in una struttura JSON compatibile."""
    dati = asdict(manifesto)  # Converte ricorsivamente dataclass e voci annidate in dizionari semplici.
    dati["eliminati"] = list(manifesto.eliminati)  # Usa un array JSON esplicito per i percorsi eliminati.
    dati["cartelle"] = list(manifesto.cartelle)  # Serializza esplicitamente la struttura delle directory, comprese quelle vuote.
    return dati  # Restituisce il documento pronto per json.dump.


def valida_percorso_relativo_manifesto(percorso: str) -> str:
    """Valida un percorso persistito impedendo assoluti, traversal e sintassi non portabile nel repository."""
    if not isinstance(percorso, str) or not percorso:  # Richiede una stringa relativa non vuota per ogni elemento persistito.
        raise ValueError("Il manifesto contiene un percorso relativo non valido.")  # Rifiuta valori che non possono identificare un elemento del repository.
    if "\\" in percorso or "\x00" in percorso or ":" in percorso:  # Rifiuta separatori Windows, NUL e prefissi/ADS che potrebbero cambiare semantica su Windows.
        raise ValueError(f"Percorso del manifesto non sicuro: {percorso!r}")  # Impedisce interpretazioni dipendenti dalla piattaforma.
    normalizzato = PurePosixPath(percorso)  # Interpreta il formato persistente dichiarato come POSIX indipendentemente dal sistema operativo corrente.
    if normalizzato.is_absolute() or any(parte in {"", ".", ".."} for parte in normalizzato.parts):  # Blocca percorsi assoluti e attraversamenti fuori dalla destinazione.
        raise ValueError(f"Percorso del manifesto non sicuro: {percorso!r}")  # Non consente a metadati corrotti di uscire dalla radice controllata.
    canonico = normalizzato.as_posix()  # Produce la rappresentazione canonica usata da FDBackup nei confronti e nel filesystem.
    if canonico != percorso:  # Richiede che il documento sia già nella forma canonica prevista dal formato.
        raise ValueError(f"Percorso del manifesto non canonico: {percorso!r}")  # Evita alias differenti dello stesso oggetto logico.
    return canonico  # Restituisce il percorso validato pronto per l'uso controllato.


def deserializza_manifesto(dati: dict) -> ManifestoBackup:
    """Ricostruisce un manifesto persistito applicando controlli strutturali minimi."""
    if not isinstance(dati, dict) or dati.get("versione_formato") != VERSIONE_FORMATO_MANIFESTO:  # Accetta soltanto il formato esplicitamente supportato.
        raise ValueError("Formato del manifesto FDBackup non supportato.")  # Evita interpretazioni silenziose di dati incompatibili.
    file_salvati = dati.get("file")  # Recupera la mappa dei file persistiti.
    if not isinstance(file_salvati, dict):  # Richiede una mappa percorso-metadati.
        raise ValueError("Il manifesto non contiene una mappa file valida.")  # Segnala una struttura corrotta.
    file: dict[str, VoceManifesto] = {}  # Prepara la mappa soltanto dopo la validazione di ogni percorso persistito.
    for chiave, valore in file_salvati.items():  # Valida separatamente chiave e metadati per impedire traversal durante verifica e ripristino.
        relativo = valida_percorso_relativo_manifesto(chiave)  # Richiede un percorso POSIX relativo canonico e sicuro.
        if not isinstance(valore, dict):  # Richiede metadati strutturati per ogni file.
            raise ValueError(f"Metadati file non validi per {relativo!r}.")  # Rifiuta manifesti corrotti prima dell'accesso al filesystem.
        voce = VoceManifesto(**valore)  # Ricostruisce la voce tipizzata dopo il controllo della struttura minima.
        if valida_percorso_relativo_manifesto(voce.percorso_relativo) != relativo:  # Richiede coerenza tra chiave della mappa e percorso interno.
            raise ValueError(f"Percorso incoerente nel manifesto: {relativo!r}.")  # Evita due identità logiche differenti per lo stesso record.
        if voce.dimensione < 0 or voce.modifica_ns < 0:  # Rifiuta metadati numerici impossibili.
            raise ValueError(f"Metadati numerici non validi per {relativo!r}.")  # Impedisce contatori e verifiche con valori corrotti.
        if len(voce.sha256) != 64 or any(carattere not in "0123456789abcdefABCDEF" for carattere in voce.sha256):  # Richiede una rappresentazione SHA-256 esadecimale completa.
            raise ValueError(f"SHA-256 non valido per {relativo!r}.")  # Non accetta impronte malformate come riferimento di integrità.
        file[relativo] = voce  # Pubblica la voce soltanto dopo tutti i controlli di sicurezza e coerenza.
    eliminati_grezzi = dati.get("eliminati", ())  # Recupera i tombstone dichiarati dal documento.
    cartelle_grezze = dati.get("cartelle", ())  # Recupera la struttura delle directory dichiarata dal documento.
    if not isinstance(eliminati_grezzi, (list, tuple)) or not isinstance(cartelle_grezze, (list, tuple)):  # Richiede collezioni ordinate serializzabili.
        raise ValueError("Il manifesto contiene elenchi di percorsi non validi.")  # Blocca strutture incompatibili prima del ripristino.
    eliminati = tuple(valida_percorso_relativo_manifesto(percorso) for percorso in eliminati_grezzi)  # Valida ogni tombstone prima che possa influire sulla catena.
    cartelle = tuple(valida_percorso_relativo_manifesto(percorso) for percorso in cartelle_grezze)  # Valida ogni directory prima che possa essere creata a destinazione.
    tipo_backup = str(dati["tipo_backup"]).strip().lower()  # Normalizza il metodo persistito prima di applicare le invarianti della catena.
    if tipo_backup not in {"completo", "incrementale", "differenziale"}:  # Accetta soltanto strategie che il motore sa ricostruire deterministicamente.
        raise ValueError("Tipo di backup del manifesto non supportato.")  # Rifiuta semantiche sconosciute prima dell'indicizzazione.
    id_backup = str(dati["id_backup"]).strip()  # Normalizza l'identità della versione.
    id_full_base = str(dati["id_full_base"]).strip()  # Normalizza il riferimento alla base Full.
    id_backup_precedente = str(dati.get("id_backup_precedente", "")).strip()  # Normalizza l'eventuale dipendenza precedente.
    if not id_backup or not id_full_base:  # Ogni versione deve avere identità propria e base dichiarata.
        raise ValueError("Il manifesto non contiene identificatori di catena validi.")  # Impedisce versioni anonime o orfane.
    if tipo_backup == "completo" and (id_full_base != id_backup or id_backup_precedente):  # Un Full deve essere autosufficiente e non dipendere da altre versioni.
        raise ValueError("Il manifesto Full contiene dipendenze di catena non valide.")  # Rifiuta una base che non possa essere considerata autonoma.
    if tipo_backup == "incrementale" and not id_backup_precedente:  # Ogni Incrementale deve dichiarare la versione immediatamente precedente.
        raise ValueError("Il manifesto Incrementale non dichiara il backup precedente.")  # Evita catene non percorribili.
    if tipo_backup == "differenziale" and id_backup_precedente != id_full_base:  # Il Differenziale dipende direttamente e soltanto dal Full di base.
        raise ValueError("Il manifesto Differenziale non punta direttamente al Full di base.")  # Rifiuta dipendenze incompatibili con la semantica implementata.
    return ManifestoBackup(id_backup=id_backup, tipo_backup=tipo_backup, creato_il=str(dati["creato_il"]), sorgente=str(dati["sorgente"]), id_full_base=id_full_base, id_backup_precedente=id_backup_precedente, file=file, eliminati=eliminati, cartelle=cartelle, versione_formato=int(dati["versione_formato"]))  # Ricostruisce il documento completo soltanto dopo tutte le invarianti.


def salva_manifesto(percorso: Path, manifesto: ManifestoBackup) -> None:
    """Salva atomicamente un manifesto JSON in UTF-8."""
    percorso = Path(percorso)  # Normalizza il percorso ricevuto dal chiamante.
    percorso.parent.mkdir(parents=True, exist_ok=True)  # Crea la directory dei metadati quando non esiste.
    temporaneo = percorso.with_suffix(percorso.suffix + ".tmp")  # Usa un file temporaneo nella stessa directory per una sostituzione atomica.
    with temporaneo.open("w", encoding="utf-8", newline="\n") as file_aperto:  # Scrive il documento con codifica e newline deterministici.
        json.dump(serializza_manifesto(manifesto), file_aperto, ensure_ascii=False, indent=2, sort_keys=True)  # Serializza in forma leggibile e stabile.
        file_aperto.flush()  # Forza il passaggio dei dati dal buffer Python al sistema operativo.
    temporaneo.replace(percorso)  # Sostituisce atomicamente l'eventuale manifesto precedente sullo stesso filesystem.


def carica_manifesto(percorso: Path) -> ManifestoBackup:
    """Carica e valida un manifesto JSON precedentemente salvato."""
    with Path(percorso).open("r", encoding="utf-8") as file_aperto:  # Apre il documento in sola lettura UTF-8.
        dati = json.load(file_aperto)  # Decodifica il JSON lasciando alla funzione dedicata la validazione del modello.
    return deserializza_manifesto(dati)  # Restituisce il manifesto tipizzato e validato.
