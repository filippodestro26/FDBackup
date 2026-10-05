"""Politiche professionali di FDBackup per verifica, pianificazione, retention, filtri e destinazioni multiple."""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from fdbackup.gestore_backup_avanzato import GestoreBackupAvanzato
from fdbackup.metadati_backup_avanzato import ManifestoBackup, carica_manifesto
from fdbackup.verifica_integrita_avanzata import VerificatoreIntegritaAvanzata

STATI_VERIFICA = {"completato", "verificato", "corrotto", "annullato"}

from fdbackup.filtri_backup import FiltroBackup, rileva_reparse

@dataclass(slots=True, frozen=True)
class PianificazioneCombinata:
    """Descrive più occorrenze settimanali per uno stesso job versionato."""
    metodo: str
    giorni_settimana: tuple[int, ...]
    ora: int
    minuto: int = 0

    def __post_init__(self) -> None:
        if self.metodo not in {"completo", "incrementale", "differenziale"}:
            raise ValueError("Metodo pianificato non supportato.")
        if not self.giorni_settimana or any(type(g) is not int or g < 0 or g > 6 for g in self.giorni_settimana):
            raise ValueError("I giorni devono essere compresi tra 0 e 6.")
        if not 0 <= self.ora <= 23 or not 0 <= self.minuto <= 59:
            raise ValueError("Orario non valido.")

    def prossima(self, riferimento: datetime) -> datetime:
        candidati = []
        for scarto in range(8):
            giorno = riferimento + timedelta(days=scarto)
            if giorno.weekday() in self.giorni_settimana:
                candidato = giorno.replace(hour=self.ora, minute=self.minuto, second=0, microsecond=0)
                if candidato >= riferimento:
                    candidati.append(candidato)
        if not candidati:
            raise RuntimeError("Impossibile calcolare la prossima occorrenza.")
        return min(candidati)

@dataclass(slots=True, frozen=True)
class PoliticaRetry:
    tentativi: int = 3
    attesa_secondi: float = 1.0

    def __post_init__(self) -> None:
        if type(self.tentativi) is not int or self.tentativi < 1 or self.attesa_secondi < 0:
            raise ValueError("Politica retry non valida.")

    def esegui(self, operazione: Callable[[], object], dormi: Callable[[float], None] = time.sleep):
        ultimo = None
        for indice in range(self.tentativi):
            try:
                return operazione()
            except OSError as errore:
                ultimo = errore
                if indice + 1 < self.tentativi:
                    dormi(self.attesa_secondi)
        raise ultimo  # type: ignore[misc]

@dataclass(slots=True, frozen=True)
class PoliticaRetention:
    giornalieri: int = 7
    settimanali: int = 4
    mensili: int = 12
    annuali: int = 3

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 0 for v in (self.giornalieri, self.settimanali, self.mensili, self.annuali)):
            raise ValueError("I limiti retention devono essere interi non negativi.")

    def seleziona_full_da_conservare(self, manifesti: Iterable[ManifestoBackup]) -> set[str]:
        full = sorted((m for m in manifesti if m.tipo_backup == "completo"), key=lambda m: m.creato_il, reverse=True)
        conservati: set[str] = set()
        visti_giorni=set(); visti_settimane=set(); visti_mesi=set(); visti_anni=set()
        for m in full:
            dt = datetime.fromisoformat(m.creato_il)
            chiavi = (("g", dt.date(), self.giornalieri, visti_giorni), ("s", dt.isocalendar()[:2], self.settimanali, visti_settimane), ("m", (dt.year,dt.month), self.mensili, visti_mesi), ("a", dt.year, self.annuali, visti_anni))
            for _, chiave, limite, visti in chiavi:
                if limite and chiave not in visti and len(visti) < limite:
                    visti.add(chiave); conservati.add(m.id_backup)
        if full and not conservati:
            conservati.add(full[0].id_backup)
        return conservati

@dataclass(slots=True)
class ReportVerifica:
    id_backup: str
    stato: str
    creato_il: str
    file_verificati: int = 0
    byte_verificati: int = 0
    errori: list[str] = field(default_factory=list)

    def salva(self, percorso: Path) -> None:
        if self.stato not in STATI_VERIFICA:
            raise ValueError("Stato verifica non valido.")
        percorso = Path(percorso)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        tmp = percorso.with_suffix(percorso.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(percorso)

class GestoreAffidabilita:
    """Verifica versioni, produce report persistenti e offre un test di recuperabilità non distruttivo."""
    def verifica(self, radice: Path, id_backup: str, cartella_report: Path | None = None) -> ReportVerifica:
        esito = VerificatoreIntegritaAvanzata().verifica_versione(radice, id_backup)
        stato = "annullato" if esito.annullato else ("verificato" if esito.integro else "corrotto")
        report = ReportVerifica(id_backup, stato, datetime.now().isoformat(timespec="seconds"), esito.file_verificati, esito.byte_verificati, list(esito.errori))
        if cartella_report is not None:
            report.salva(Path(cartella_report) / f"verifica_{id_backup}.json")
        return report

    def test_recuperabilita(self, radice: Path, id_backup: str, destinazione_temporanea: Path) -> ReportVerifica:
        from fdbackup.motore_ripristino_avanzato import MotoreRipristinoAvanzato
        import threading
        destinazione = Path(destinazione_temporanea)
        if destinazione.exists() and any(destinazione.iterdir()):
            raise ValueError("La destinazione del test di recuperabilità deve essere vuota.")
        esito = MotoreRipristinoAvanzato(threading.Event()).ripristina(radice, id_backup, destinazione, sovrascrivi=True)
        verifica = self.verifica(radice, id_backup)
        if esito.errori or esito.annullato:
            verifica.stato = "corrotto" if esito.errori else "annullato"
            verifica.errori.extend(esito.errori)
        return verifica

@dataclass(slots=True, frozen=True)
class DestinazioneBackup:
    percorso: Path
    obbligatoria: bool = True

class GestoreDestinazioniMultiple:
    """Replica una versione pubblicata su più destinazioni locali/SMB montate con verifica dei file copiati."""
    def replica(self, cartella_versione: Path, destinazioni: Iterable[DestinazioneBackup]) -> dict[str, str]:
        sorgente = Path(cartella_versione).resolve(strict=True)
        risultati: dict[str,str] = {}
        for voce in destinazioni:
            destinazione = Path(voce.percorso).expanduser().resolve(strict=False)
            try:
                destinazione.mkdir(parents=True, exist_ok=True)
                arrivo = destinazione / sorgente.name
                if arrivo.exists():
                    raise FileExistsError(f"La versione esiste già: {arrivo}")
                shutil.copytree(sorgente, arrivo, symlinks=True)
                risultati[str(destinazione)] = "ok"
            except OSError as errore:
                risultati[str(destinazione)] = f"errore: {errore}"
                if voce.obbligatoria:
                    raise
        return risultati

def destinazione_disponibile(percorso: Path, byte_richiesti: int = 0) -> tuple[bool, str]:
    """Controlla esistenza/scrivibilità e spazio disponibile senza creare dati di backup."""
    percorso = Path(percorso).expanduser().resolve(strict=False)
    esistente = percorso if percorso.exists() else next((p for p in percorso.parents if p.exists()), None)
    if esistente is None:
        return False, "Nessun percorso padre disponibile."
    try:
        spazio = shutil.disk_usage(esistente).free
    except OSError as errore:
        return False, str(errore)
    if spazio < max(0, byte_richiesti):
        return False, f"Spazio insufficiente: {spazio} byte disponibili."
    return True, "Disponibile"

def crea_dashboard(radice: Path) -> dict[str, object]:
    """Produce statistiche e stato d'integrità delle versioni senza modificare il repository."""
    gestore = GestoreBackupAvanzato()
    manifesti = gestore.elenca_manifesti(radice)
    conteggi = {"completo": 0, "incrementale": 0, "differenziale": 0}
    dettagli: list[dict[str, object]] = []
    verificatore = VerificatoreIntegritaAvanzata()
    for manifesto in manifesti:
        conteggi[manifesto.tipo_backup] += 1
        esito = verificatore.verifica_versione(radice, manifesto.id_backup)
        stato = "annullato" if esito.annullato else ("verificato" if esito.integro else "corrotto")
        dettagli.append({"id_backup": manifesto.id_backup, "tipo": manifesto.tipo_backup, "creato_il": manifesto.creato_il, "stato": stato, "errori": list(esito.errori)})
    anomalie = sum(1 for voce in dettagli if voce["stato"] != "verificato")
    return {"versioni": len(manifesti), "tipi": conteggi, "ultimo_backup": manifesti[-1].creato_il if manifesti else None, "anomalie": anomalie, "dettagli": dettagli}

def pianifica_retention(radice: Path, politica: PoliticaRetention) -> tuple[list[Path], list[Path]]:
    """Restituisce (conservare, eliminare) per catene intere; non cancella mai dati durante la pianificazione."""
    radice = Path(radice).expanduser().resolve(strict=False)
    gestore = GestoreBackupAvanzato()
    manifesti = gestore.elenca_manifesti(radice)
    full_conservati = politica.seleziona_full_da_conservare(manifesti)
    conservare: list[Path] = []; eliminare: list[Path] = []
    for manifesto in manifesti:
        cartella = gestore._trova_cartella_versione(radice, manifesto.id_backup)
        if cartella is None:
            continue
        (conservare if manifesto.id_full_base in full_conservati else eliminare).append(cartella)
    return conservare, eliminare

def applica_retention_sicura(radice: Path, politica: PoliticaRetention, conferma: bool = False) -> list[Path]:
    """Elimina soltanto catene complete selezionate dalla retention e solo con conferma esplicita."""
    _, eliminare = pianifica_retention(radice, politica)
    if not conferma:
        return eliminare
    eliminate: list[Path] = []
    for cartella in eliminare:
        if cartella.exists() and cartella.parent.resolve() == Path(radice).expanduser().resolve(strict=False):
            shutil.rmtree(cartella); eliminate.append(cartella)
    return eliminate

@dataclass(slots=True, frozen=True)
class AvvisoBackup:
    livello: str
    codice: str
    messaggio: str

def genera_avvisi(destinazione: Path, byte_richiesti: int = 0, report: ReportVerifica | None = None) -> list[AvvisoBackup]:
    """Genera alert strutturati per destinazione, spazio e integrità senza dipendere dalla GUI."""
    avvisi: list[AvvisoBackup] = []
    disponibile, dettaglio = destinazione_disponibile(destinazione, byte_richiesti)
    if not disponibile:
        codice = "spazio_insufficiente" if "Spazio insufficiente" in dettaglio else "destinazione_non_disponibile"
        avvisi.append(AvvisoBackup("errore", codice, dettaglio))
    if report is not None and report.stato != "verificato":
        avvisi.append(AvvisoBackup("errore", "backup_non_verificato", f"Stato integrità: {report.stato}"))
    return avvisi

def crea_report_periodico(radici: Iterable[Path]) -> dict[str, object]:
    """Aggrega più repository in un report serializzabile adatto a dashboard e notifiche periodiche."""
    repository=[]
    for radice in radici:
        try:
            dati=crea_dashboard(radice); dati["radice"]=str(Path(radice)); dati["disponibile"]=True
        except OSError as errore:
            dati={"radice":str(Path(radice)),"disponibile":False,"errore":str(errore)}
        repository.append(dati)
    return {"generato_il":datetime.now().isoformat(timespec="seconds"),"repository":repository}

@dataclass(slots=True, frozen=True)
class PianificazioneAvanzata:
    """Regola oraria/giornaliera/settimanale/mensile per un metodo versionato."""
    metodo: str
    frequenza: str
    ora: int = 0
    minuto: int = 0
    giorni_settimana: tuple[int, ...] = ()
    giorno_mese: int | None = None

    def __post_init__(self) -> None:
        if self.metodo not in {"completo", "incrementale", "differenziale"}:
            raise ValueError("Metodo pianificato non supportato.")
        if self.frequenza not in {"oraria", "giornaliera", "settimanale", "mensile"}:
            raise ValueError("Frequenza non supportata.")
        if not 0 <= self.ora <= 23 or not 0 <= self.minuto <= 59:
            raise ValueError("Orario non valido.")
        if self.frequenza == "settimanale" and (not self.giorni_settimana or any(type(g) is not int or not 0 <= g <= 6 for g in self.giorni_settimana)):
            raise ValueError("La pianificazione settimanale richiede giorni 0..6.")
        if self.frequenza == "mensile" and (type(self.giorno_mese) is not int or not 1 <= self.giorno_mese <= 31):
            raise ValueError("La pianificazione mensile richiede un giorno 1..31.")

    def occorrenza_precedente(self, riferimento: datetime) -> datetime | None:
        """Calcola l'ultima occorrenza civile non futura, senza inventare giorni mensili inesistenti."""
        if self.frequenza == "oraria":
            candidato = riferimento.replace(minute=self.minuto, second=0, microsecond=0)
            return candidato if candidato <= riferimento else candidato - timedelta(hours=1)
        if self.frequenza == "giornaliera":
            candidato = riferimento.replace(hour=self.ora, minute=self.minuto, second=0, microsecond=0)
            return candidato if candidato <= riferimento else candidato - timedelta(days=1)
        if self.frequenza == "settimanale":
            candidati = []
            for scarto in range(8):
                giorno = riferimento - timedelta(days=scarto)
                if giorno.weekday() in self.giorni_settimana:
                    candidato = giorno.replace(hour=self.ora, minute=self.minuto, second=0, microsecond=0)
                    if candidato <= riferimento:
                        candidati.append(candidato)
            return max(candidati) if candidati else None
        import calendar
        anno, mese = riferimento.year, riferimento.month
        for _ in range(2):
            ultimo = calendar.monthrange(anno, mese)[1]
            if self.giorno_mese <= ultimo:
                candidato = riferimento.replace(year=anno, month=mese, day=self.giorno_mese, hour=self.ora, minute=self.minuto, second=0, microsecond=0)
                if candidato <= riferimento:
                    return candidato
            mese -= 1
            if mese == 0:
                mese = 12; anno -= 1
        return None


def seleziona_pianificazioni_dovute(regole: Iterable[PianificazioneAvanzata], stato: dict[str, str], riferimento: datetime) -> list[tuple[int, PianificazioneAvanzata, datetime]]:
    """Seleziona più regole dovute per lo stesso job, mantenendo anti-duplicazione per regola."""
    dovute=[]
    for indice, regola in enumerate(regole):
        occorrenza=regola.occorrenza_precedente(riferimento)
        if occorrenza is None:
            continue
        chiave=occorrenza.isoformat(timespec="minutes")
        if stato.get(str(indice)) != chiave:
            dovute.append((indice, regola, occorrenza))
    return sorted(dovute, key=lambda x:(x[2], x[0]))


@dataclass(slots=True)
class EsitoAffidabilita:
    """Esito aggregato backup + verifica + recuperabilità."""
    risultato_backup: object
    report_verifica: ReportVerifica | None = None
    report_recuperabilita: ReportVerifica | None = None

    @property
    def stato(self) -> str:
        risultato=self.risultato_backup
        if getattr(risultato, "annullato", False): return "annullato"
        if getattr(risultato, "errori", None): return "corrotto"
        if self.report_verifica is not None and self.report_verifica.stato != "verificato": return "corrotto"
        if self.report_recuperabilita is not None and self.report_recuperabilita.stato != "verificato": return "corrotto"
        return "verificato" if self.report_verifica is not None else "completato"


def esegui_strategia_affidabile(sorgente: Path, radice: Path, strategia, verifica_automatica: bool = True, test_recuperabilita: bool = False, cartella_report: Path | None = None, gestore: GestoreBackupAvanzato | None = None) -> EsitoAffidabilita:
    """Esegue una strategia e, solo se pubblicata con successo, verifica automaticamente la nuova versione."""
    gestore = gestore or GestoreBackupAvanzato()
    risultato = gestore.esegui_strategia(sorgente, radice, strategia)
    esito = EsitoAffidabilita(risultato)
    manifesto = getattr(risultato, "manifesto", None)
    if not getattr(risultato, "successo", False) or manifesto is None:
        return esito
    affidabilita=GestoreAffidabilita()
    if verifica_automatica:
        esito.report_verifica=affidabilita.verifica(radice, manifesto.id_backup, cartella_report)
    if test_recuperabilita and (esito.report_verifica is None or esito.report_verifica.stato == "verificato"):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="fdbackup-recuperabilita-") as temporanea:
            esito.report_recuperabilita=affidabilita.test_recuperabilita(radice, manifesto.id_backup, Path(temporanea))
    return esito


def esegui_con_retry_e_destinazione(operazione: Callable[[], object], destinazione: Path, byte_richiesti: int = 0, politica: PoliticaRetry | None = None) -> tuple[str, object | None, str]:
    """Preflight destinazione + retry I/O; una destinazione offline viene saltata senza avviare copie."""
    disponibile, dettaglio=destinazione_disponibile(destinazione, byte_richiesti)
    if not disponibile:
        return "saltato", None, dettaglio
    try:
        valore=(politica or PoliticaRetry()).esegui(operazione)
        return "completato", valore, "OK"
    except OSError as errore:
        return "errore", None, f"{type(errore).__name__}: {errore}"


def salva_report_periodico(percorso: Path, radici: Iterable[Path]) -> dict[str, object]:
    """Genera e salva atomicamente il report periodico JSON."""
    report=crea_report_periodico(radici)
    percorso=Path(percorso); percorso.parent.mkdir(parents=True, exist_ok=True)
    temporaneo=percorso.with_suffix(percorso.suffix+".tmp")
    temporaneo.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporaneo.replace(percorso)
    return report
