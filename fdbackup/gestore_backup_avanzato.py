"""Coordinamento delle strategie avanzate di backup versionato di FDBackup."""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

from fdbackup.metadati_backup_avanzato import ManifestoBackup, carica_manifesto
from fdbackup.filtri_backup import FiltroBackup
from fdbackup.motore_backup_avanzato import MotoreBackupAvanzato, RisultatoBackupAvanzato


TIPI_BACKUP_VERSIONATO = {"completo", "incrementale", "differenziale"}  # Elenca i metodi che producono versioni persistenti concatenate.


@dataclass(slots=True, frozen=True)
class StrategiaBackupAvanzato:
    """Definisce una strategia versionata combinabile senza modificare lo scheduler esistente."""

    metodo: str = "incrementale"  # Seleziona il metodo ordinario eseguito dopo il Full iniziale.
    full_ogni: int = 7  # Richiede un nuovo Full dopo questo numero di versioni successive al Full corrente.
    catene_da_mantenere: int = 3  # Limita il numero di catene Full complete conservate sul disco.
    includi_sottocartelle: bool = True  # Propaga la scelta di scansione al motore avanzato.
    filtro: FiltroBackup | None = None  # Applica include/exclude, dimensioni, attributi e politica reparse prima di hashing/copia.

    def __post_init__(self) -> None:
        """Normalizza e valida la strategia prima che possa raggiungere il filesystem."""
        metodo_normalizzato = self.metodo.strip().lower() if isinstance(self.metodo, str) else ""  # Normalizza il metodo soltanto quando il tipo è corretto.
        if metodo_normalizzato not in {"completo", "incrementale", "differenziale"}:  # Accetta esclusivamente metodi versionati implementati realmente.
            raise ValueError("La strategia richiede un metodo completo, incrementale o differenziale.")  # Rifiuta configurazioni non supportate.
        if not isinstance(self.full_ogni, int) or isinstance(self.full_ogni, bool) or self.full_ogni < 1:  # Richiede una soglia intera positiva reale.
            raise ValueError("'full_ogni' deve essere un intero maggiore o uguale a 1.")  # Impedisce cicli impossibili o ambigui.
        if not isinstance(self.catene_da_mantenere, int) or isinstance(self.catene_da_mantenere, bool) or self.catene_da_mantenere < 1:  # Richiede almeno una catena recuperabile.
            raise ValueError("'catene_da_mantenere' deve essere un intero maggiore o uguale a 1.")  # Evita retention distruttive prive di una copia valida.
        if self.filtro is not None and not isinstance(self.filtro, FiltroBackup):
            raise TypeError("'filtro' deve essere un oggetto FiltroBackup oppure None.")
        if not isinstance(self.includi_sottocartelle, bool):  # Richiede il tipo booleano reale.
            raise TypeError("'includi_sottocartelle' deve essere booleano.")  # Evita conversioni implicite inattese.
        object.__setattr__(self, "metodo", metodo_normalizzato)  # Memorizza la rappresentazione canonica nel modello immutabile.


class GestoreBackupAvanzato:
    """Gestisce catene, scelta automatica del metodo e retention delle versioni avanzate."""

    def __init__(self, evento_arresto: threading.Event | None = None, callback=None) -> None:
        """Crea il coordinatore riutilizzando il motore avanzato già verificato."""
        self.evento_arresto = evento_arresto or threading.Event()  # Usa l'evento del chiamante oppure ne crea uno indipendente.
        self.callback = callback  # Conserva l'eventuale callback senza imporre dipendenze dalla GUI.
        self.motore = MotoreBackupAvanzato(self.evento_arresto, callback)  # Delega copia e sincronizzazione al motore specializzato.

    @staticmethod
    def _normalizza_sorgente(sorgente: Path) -> str:
        """Restituisce la forma assoluta canonica usata per confrontare i manifesti."""
        return str(Path(sorgente).expanduser().resolve(strict=False))  # Mantiene la stessa normalizzazione usata dai manifesti persistenti.

    def elenca_manifesti(self, radice_versioni: Path, sorgente: Path | None = None) -> list[ManifestoBackup]:
        """Carica i manifesti validi presenti nella radice, ignorando directory incomplete prive di manifesto."""
        radice = Path(radice_versioni).expanduser().resolve(strict=False)  # Normalizza la radice senza richiederne l'esistenza.
        if not radice.exists():  # Una destinazione mai usata non contiene ancora versioni.
            return []  # Restituisce una collezione vuota senza creare directory durante una semplice lettura.
        sorgente_normalizzata = self._normalizza_sorgente(sorgente) if sorgente is not None else None  # Prepara l'eventuale filtro per sorgente.
        manifesti_con_ordine: list[tuple[int, ManifestoBackup]] = []  # Associa ogni manifesto al timestamp fisico di pubblicazione per risolvere creazioni nello stesso secondo.
        for percorso in sorted((*radice.glob("*/.backupcore-manifesto.json"), *radice.glob("*/manifesto.json"))):  # Cerca esclusivamente il formato fisico prodotto dal motore avanzato.
            try:  # Isola un eventuale manifesto corrotto senza trasformarlo in una versione valida.
                manifesto = carica_manifesto(percorso)  # Applica la validazione strutturale centralizzata.
                pubblicato_ns = percorso.stat().st_mtime_ns  # Legge l'ordine di pubblicazione con precisione superiore ai secondi del formato persistente.
            except (OSError, ValueError, KeyError, TypeError):  # Un documento illeggibile o incompatibile viene escluso dalla selezione automatica.
                continue  # Lascia intatti i dati sul disco e prosegue con le altre versioni.
            if sorgente_normalizzata is None or manifesto.sorgente == sorgente_normalizzata:  # Applica il filtro soltanto quando richiesto.
                manifesti_con_ordine.append((pubblicato_ns, manifesto))  # Conserva versione e ordine fisico di pubblicazione.
        manifesti_con_ordine.sort(key=lambda elemento: (elemento[0], elemento[1].id_backup))  # Produce un ordine deterministico anche per pubblicazioni estremamente ravvicinate.
        return [manifesto for _, manifesto in manifesti_con_ordine]  # Restituisce soltanto i manifesti ordinati al chiamante.

    @staticmethod
    def _ultimo_full(manifesti: list[ManifestoBackup]) -> ManifestoBackup | None:
        """Restituisce il Full più recente nell'ordine già validato."""
        return next((manifesto for manifesto in reversed(manifesti) if manifesto.tipo_backup == "completo"), None)  # Cerca dalla versione più recente verso la più vecchia.

    @staticmethod
    def _manifesti_catena(manifesti: list[ManifestoBackup], id_full: str) -> list[ManifestoBackup]:
        """Restituisce tutte le versioni appartenenti alla catena indicata."""
        return [manifesto for manifesto in manifesti if manifesto.id_full_base == id_full]  # Usa l'identità persistente invece dei nomi delle directory.

    def esegui_strategia(self, sorgente: Path, radice_versioni: Path, strategia: StrategiaBackupAvanzato) -> RisultatoBackupAvanzato:
        """Esegue Full/Incrementale/Differenziale scegliendo automaticamente basi e rotazione della catena."""
        sorgente = Path(sorgente).expanduser().resolve(strict=True)  # Verifica subito l'esistenza della sorgente richiesta.
        radice_versioni = Path(radice_versioni).expanduser().resolve(strict=False)  # Normalizza la destinazione prima della selezione delle versioni.
        manifesti = self.elenca_manifesti(radice_versioni, sorgente)  # Considera soltanto catene appartenenti alla stessa sorgente.
        ultimo_full = self._ultimo_full(manifesti)  # Individua la base corrente, se presente.
        if strategia.metodo == "completo" or ultimo_full is None:  # Il primo backup e la strategia Full producono sempre una base autonoma.
            risultato = self.motore.esegui_completo(sorgente, radice_versioni, strategia.includi_sottocartelle, strategia.filtro)  # Delega il Full al motore verificato.
        else:  # Incrementale e differenziale richiedono una base già esistente.
            catena_corrente = self._manifesti_catena(manifesti, ultimo_full.id_backup)  # Recupera tutte le versioni della base corrente.
            numero_successivi = max(0, len(catena_corrente) - 1)  # Esclude il Full dal conteggio delle versioni successive.
            if numero_successivi >= strategia.full_ogni:  # Ruota la catena quando è stata raggiunta la soglia configurata.
                risultato = self.motore.esegui_completo(sorgente, radice_versioni, strategia.includi_sottocartelle, strategia.filtro)  # Crea una nuova base prima di proseguire.
            elif strategia.metodo == "incrementale":  # Seleziona la dipendenza immediatamente precedente per la catena incrementale.
                precedente = catena_corrente[-1]  # Usa l'ultima versione valida della stessa catena.
                risultato = self.motore.esegui_incrementale(sorgente, radice_versioni, precedente, strategia.includi_sottocartelle, strategia.filtro)  # Esegue il delta rispetto al precedente.
            else:  # Rimane esclusivamente la strategia differenziale già validata dal modello.
                risultato = self.motore.esegui_differenziale(sorgente, radice_versioni, ultimo_full, strategia.includi_sottocartelle, strategia.filtro)  # Confronta sempre con il Full corrente.
        if risultato.successo and not risultato.annullato:  # Applica retention soltanto dopo la pubblicazione completa della nuova versione.
            self.applica_retention(radice_versioni, sorgente, strategia.catene_da_mantenere)  # Elimina esclusivamente catene intere più vecchie del limite.
        return risultato  # Restituisce senza trasformazioni l'esito del motore sottostante.

    @staticmethod
    def _trova_cartella_versione(radice: Path, id_backup: str) -> Path | None:
        """Risolve una directory versione dal manifesto ignorando in sicurezza documenti corrotti o incompleti."""
        for percorso in (*radice.glob("*/.backupcore-manifesto.json"), *radice.glob("*/manifesto.json")):  # Considera sia il vecchio layout UUID sia i nuovi nomi leggibili.
            try:  # Isola un manifesto danneggiato dalla retention delle altre catene valide.
                manifesto = carica_manifesto(percorso)  # Applica la validazione centralizzata del formato.
            except (OSError, ValueError, KeyError, TypeError):  # Tratta un documento non valido come non selezionabile.
                continue  # Non cancella mai una directory sulla base di metadati non verificati.
            if manifesto.id_backup == id_backup:  # Confronta l'identità persistente completa.
                return percorso.parent  # Restituisce la directory fisica realmente associata al manifesto.
        return None  # Comunica esplicitamente che la versione non è stata risolta.

    def applica_retention(self, radice_versioni: Path, sorgente: Path, catene_da_mantenere: int) -> list[str]:
        """Rimuove catene Full complete più vecchie conservando sempre il numero richiesto di catene recenti."""
        if not isinstance(catene_da_mantenere, int) or isinstance(catene_da_mantenere, bool) or catene_da_mantenere < 1:  # Difende anche l'API pubblica usata indipendentemente dalla strategia.
            raise ValueError("La retention deve mantenere almeno una catena.")  # Impedisce di cancellare tutte le copie per errore di configurazione.
        radice = Path(radice_versioni).expanduser().resolve(strict=False)  # Normalizza la radice delle versioni.
        manifesti = self.elenca_manifesti(radice, sorgente)  # Limita la retention alla sorgente richiesta.
        full = [manifesto for manifesto in manifesti if manifesto.tipo_backup == "completo"]  # Identifica le radici delle catene persistenti.
        if len(full) <= catene_da_mantenere:  # Evita modifiche quando il limite non è superato.
            return []  # Comunica che nessuna catena è stata rimossa.
        id_da_eliminare = {manifesto.id_backup for manifesto in full[:-catene_da_mantenere]}  # Seleziona soltanto i Full più vecchi oltre la retention.
        versioni_da_eliminare = [manifesto for manifesto in manifesti if manifesto.id_full_base in id_da_eliminare]  # Include ogni dipendenza della catena rimossa.
        rimossi: list[str] = []  # Registra gli ID eliminati per logging e test.
        for manifesto in versioni_da_eliminare:  # Elimina una versione alla volta senza toccare catene recenti.
            cartella = self._trova_cartella_versione(radice, manifesto.id_backup)  # Risolve la directory dal manifesto supportando vecchi UUID e nuovi nomi leggibili senza fidarsi di documenti corrotti.
            if cartella is not None and cartella.exists():  # Evita errori per versioni già rimosse esternamente.
                shutil.rmtree(cartella)  # Rimuove dati e manifesto della versione appartenente alla catena scaduta.
                rimossi.append(manifesto.id_backup)  # Registra l'eliminazione completata.
        return rimossi  # Restituisce gli ID effettivamente rimossi.

    def esegui_sincronizzazione(self, metodo: str, sorgente: Path, destinazione: Path, includi_sottocartelle: bool = True) -> RisultatoBackupAvanzato:
        """Espone Update e Mirror con un unico punto di ingresso controllato per GUI e futuri job."""
        metodo_normalizzato = metodo.strip().lower() if isinstance(metodo, str) else ""  # Normalizza l'input senza accettare conversioni arbitrarie.
        if metodo_normalizzato == "update":  # Riconosce la sincronizzazione conservativa senza eliminazioni.
            return self.motore.esegui_update(sorgente, destinazione, includi_sottocartelle)  # Delega al motore già testato.
        if metodo_normalizzato == "mirror":  # Riconosce la sincronizzazione speculare con eliminazioni controllate.
            return self.motore.esegui_mirror(sorgente, destinazione, includi_sottocartelle)  # Delega al motore già testato.
        raise ValueError("Metodo di sincronizzazione non supportato: usare 'update' o 'mirror'.")  # Rifiuta modalità non implementate realmente.
