"""Motori avanzati non distruttivi per Full, Incrementale, Differenziale, Mirror e Update."""

from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fdbackup.metadati_backup_avanzato import ManifestoBackup, VoceManifesto, crea_manifesto_backup, crea_manifesto_file, elenca_cartelle_relative, nome_cartella_versione, salva_manifesto


@dataclass(slots=True)
class RisultatoBackupAvanzato:
    """Raccoglie l'esito di una singola operazione avanzata."""

    tipo_backup: str  # Identifica la strategia effettivamente eseguita.
    file_copiati: int = 0  # Conta i file materialmente copiati.
    file_eliminati: int = 0  # Conta le eliminazioni effettuate soltanto nelle strategie Mirror.
    byte_copiati: int = 0  # Somma i byte dei file copiati con successo.
    annullato: bool = False  # Indica un arresto cooperativo richiesto dal chiamante.
    errori: list[str] = field(default_factory=list)  # Conserva gli errori incontrati senza nasconderli.
    manifesto: ManifestoBackup | None = None  # Espone il manifesto prodotto dalle strategie versionate.

    @property
    def successo(self) -> bool:
        """Restituisce True soltanto per un'esecuzione conclusa senza errori né annullamento."""
        return not self.annullato and not self.errori  # Combina i due stati che rendono incompleta l'operazione.


class MotoreBackupAvanzato:
    """Implementa strategie aggiuntive senza modificare il MotoreBackup storico già stabile."""

    def __init__(self, evento_arresto: threading.Event, funzione_avanzamento: Callable[[str, dict], None] | None = None) -> None:
        """Memorizza arresto cooperativo e callback opzionale."""
        self.evento_arresto = evento_arresto  # Condivide l'evento di Stop con il livello orchestratore.
        self.funzione_avanzamento = funzione_avanzamento  # Conserva la callback senza imporre dipendenze dalla GUI.

    def _notifica(self, evento: str, **dati) -> None:
        """Invia un evento soltanto quando il chiamante ha fornito una callback."""
        if self.funzione_avanzamento is not None:  # Evita chiamate quando il motore è usato senza interfaccia.
            self.funzione_avanzamento(evento, dati)  # Inoltra evento e dati strutturati.

    @staticmethod
    def _valida_percorsi(sorgente: Path, destinazione: Path) -> tuple[Path, Path]:
        """Normalizza e valida una coppia sorgente-destinazione evitando ricorsione e coincidenza."""
        sorgente = Path(sorgente).expanduser().resolve(strict=True)  # Richiede una sorgente realmente esistente.
        destinazione = Path(destinazione).expanduser().resolve(strict=False)  # Normalizza anche una destinazione non ancora creata.
        if not sorgente.is_dir():  # Accetta soltanto cartelle come sorgenti.
            raise ValueError("La sorgente deve essere una cartella.")  # Rifiuta file e oggetti non compatibili.
        if destinazione.exists() and not destinazione.is_dir():  # Verifica la natura di una destinazione esistente.
            raise ValueError("La destinazione esiste ma non è una cartella.")  # Evita di sovrascrivere un file con una directory.
        if sorgente == destinazione:  # Impedisce una sincronizzazione della cartella con se stessa.
            raise ValueError("Sorgente e destinazione non possono coincidere.")  # Blocca una configurazione priva di significato.
        if sorgente in destinazione.parents:  # Impedisce che la destinazione venga creata dentro la sorgente.
            raise ValueError("La destinazione non può trovarsi all'interno della sorgente.")  # Evita ricorsioni incontrollate.
        return sorgente, destinazione  # Restituisce i percorsi pronti per l'operazione.

    def _copia_selezione(self, sorgente: Path, destinazione: Path, percorsi: list[str], risultato: RisultatoBackupAvanzato) -> None:
        """Copia atomicamente la selezione notificando un avanzamento a byte, utile anche per file molto grandi."""
        totale_byte = sum((sorgente / Path(relativo)).stat().st_size for relativo in percorsi)  # Calcola il lavoro di copia dopo che la scansione ha stabilito la selezione reale.
        byte_elaborati = 0  # Conta i byte trasferiti nella fase corrente senza confonderli con i soli byte pubblicati con successo.
        self._notifica("inizio_copia", totale_byte=totale_byte, totale_file=len(percorsi))  # Permette alla GUI di passare dalla fase Analisi alla percentuale determinata.
        for relativo in percorsi:  # Elabora i file in ordine deterministico fornito dal chiamante.
            if self.evento_arresto.is_set():  # Controlla lo Stop prima di iniziare un nuovo file.
                risultato.annullato = True  # Registra l'interruzione cooperativa.
                return  # Non avvia altre copie dopo la richiesta di arresto.
            origine = sorgente / Path(relativo)  # Ricostruisce il percorso reale nella sorgente.
            arrivo = destinazione / Path(relativo)  # Ricostruisce il percorso equivalente nella destinazione.
            temporaneo = arrivo.with_name(f".{arrivo.name}.backupcore-part")  # Usa un payload temporaneo nella stessa directory per evitare file finali parziali.
            try:  # Isola gli errori di un file per consentire un riepilogo completo.
                arrivo.parent.mkdir(parents=True, exist_ok=True)  # Prepara la gerarchia necessaria alla copia.
                temporaneo.unlink(missing_ok=True)  # Elimina esclusivamente un residuo temporaneo FDBackup con lo stesso nome.
                with origine.open("rb") as file_sorgente, temporaneo.open("wb") as file_destinazione:  # Apre sorgente e temporaneo con chiusura garantita.
                    while True:  # Trasferisce a blocchi per aggiornare percentuale e Stop anche sui file grandi.
                        if self.evento_arresto.is_set():  # Osserva lo Stop tra due blocchi invece di attendere la fine di un file da gigabyte.
                            risultato.annullato = True  # Registra l'arresto richiesto dall'utente.
                            break  # Esce dal ciclo mantenendo intatto l'eventuale file finale precedente.
                        blocco = file_sorgente.read(4 * 1024 * 1024)  # Legge blocchi da 4 MiB per bilanciare I/O e frequenza degli aggiornamenti.
                        if not blocco:  # Riconosce la fine del file.
                            break  # Termina il trasferimento senza scritture vuote.
                        file_destinazione.write(blocco)  # Scrive il blocco nel file temporaneo.
                        byte_elaborati += len(blocco)  # Aggiorna il progresso della fase di copia.
                        self._notifica("avanzamento_copia", file=relativo, byte_elaborati=byte_elaborati, totale_byte=totale_byte)  # Invia dati numerici senza toccare la GUI dal worker.
                if risultato.annullato:  # Gestisce uno Stop osservato durante il trasferimento del file.
                    temporaneo.unlink(missing_ok=True)  # Rimuove il payload incompleto prima di uscire.
                    return  # Non pubblica né conta il file parziale.
                shutil.copystat(origine, temporaneo)  # Replica i metadati supportati da copy2 dopo il trasferimento del contenuto.
                os.replace(temporaneo, arrivo)  # Pubblica atomicamente il file completo sullo stesso filesystem.
                risultato.file_copiati += 1  # Aggiorna il contatore soltanto dopo una copia riuscita.
                risultato.byte_copiati += origine.stat().st_size  # Somma la dimensione effettiva del file copiato.
                self._notifica("file_copiato", file=relativo)  # Comunica il progresso al livello superiore.
            except OSError as errore:  # Raccoglie gli errori del filesystem senza trasformarli in successo.
                temporaneo.unlink(missing_ok=True)  # Tenta di non lasciare residui parziali dopo un errore di I/O.
                risultato.errori.append(f"{relativo}: {type(errore).__name__}: {errore}")  # Conserva percorso, tipo e messaggio diagnostico.

    @staticmethod
    def _crea_cartelle_vuote(sorgente: Path, destinazione: Path, includi_sottocartelle: bool, filtro=None) -> tuple[str, ...]:
        """Materializza la struttura delle directory e restituisce l'elenco persistibile nel manifesto."""
        cartelle = elenca_cartelle_relative(sorgente, includi_sottocartelle, filtro)  # Acquisisce anche le directory che non contengono file.
        for relativo in cartelle:  # Riproduce la struttura prima dei payload per preservare anche i rami vuoti.
            (destinazione / Path(relativo)).mkdir(parents=True, exist_ok=True)  # Crea idempotentemente la directory relativa.
        return cartelle  # Restituisce la struttura usata dal manifesto e dal ripristino.

    @staticmethod
    def _differenze(corrente: dict[str, VoceManifesto], base: dict[str, VoceManifesto]) -> tuple[list[str], tuple[str, ...]]:
        """Calcola file nuovi/modificati e file eliminati rispetto a una base."""
        modificati = sorted(percorso for percorso, voce in corrente.items() if percorso not in base or voce.sha256 != base[percorso].sha256)  # Seleziona aggiunte e variazioni di contenuto.
        eliminati = tuple(sorted(percorso for percorso in base if percorso not in corrente))  # Registra le eliminazioni senza applicarle ai backup versionati.
        return modificati, eliminati  # Restituisce entrambe le categorie necessarie al ripristino futuro.

    def esegui_completo(self, sorgente: Path, radice_versioni: Path, includi_sottocartelle: bool = True, filtro=None) -> RisultatoBackupAvanzato:
        """Crea una versione Full autonoma con manifesto completo della sorgente."""
        sorgente, radice_versioni = self._valida_percorsi(sorgente, radice_versioni)  # Valida i percorsi prima di produrre dati.
        stato = crea_manifesto_file(sorgente, includi_sottocartelle, filtro, self.funzione_avanzamento)  # Acquisisce uno snapshot logico verificato della sorgente.
        cartelle = elenca_cartelle_relative(sorgente, includi_sottocartelle, filtro, self.funzione_avanzamento)  # Acquisisce anche le directory vuote nello snapshot Full.
        manifesto = crea_manifesto_backup("completo", sorgente, stato, cartelle=cartelle)  # Crea l'identità della nuova base Full.
        cartella_versione = radice_versioni / nome_cartella_versione(manifesto)  # Isola fisicamente la versione dalle altre copie.
        risultato = RisultatoBackupAvanzato("completo", manifesto=manifesto)  # Prepara il risultato pubblico dell'operazione.
        self._crea_cartelle_vuote(sorgente, cartella_versione / "dati", includi_sottocartelle, filtro)  # Materializza anche i rami vuoti della sorgente.
        self._copia_selezione(sorgente, cartella_versione / "dati", sorted(stato), risultato)  # Materializza tutti i file presenti nel Full.
        if risultato.successo:  # Pubblica i metadati soltanto se tutti i file sono stati copiati correttamente.
            salva_manifesto(cartella_versione / ".backupcore-manifesto.json", manifesto)  # Rende la versione ricostruibile e verificabile.
        return risultato  # Restituisce contatori, errori e manifesto.

    def esegui_incrementale(self, sorgente: Path, radice_versioni: Path, manifesto_precedente: ManifestoBackup, includi_sottocartelle: bool = True, filtro=None) -> RisultatoBackupAvanzato:
        """Copia soltanto aggiunte/modifiche rispetto al backup precedente della stessa catena."""
        sorgente, radice_versioni = self._valida_percorsi(sorgente, radice_versioni)  # Valida i percorsi prima del confronto.
        corrente = crea_manifesto_file(sorgente, includi_sottocartelle, filtro, self.funzione_avanzamento)  # Acquisisce lo stato corrente completo per un confronto affidabile.
        modificati, eliminati = self._differenze(corrente, manifesto_precedente.file)  # Confronta con la versione immediatamente precedente.
        cartelle = elenca_cartelle_relative(sorgente, includi_sottocartelle, filtro, self.funzione_avanzamento)  # Conserva la struttura corrente, incluse directory vuote.
        manifesto = crea_manifesto_backup("incrementale", sorgente, corrente, manifesto_precedente.id_full_base, manifesto_precedente.id_backup, eliminati, cartelle)  # Collega esplicitamente la nuova versione alla catena.
        cartella_versione = radice_versioni / nome_cartella_versione(manifesto)  # Assegna una directory indipendente alla versione incrementale.
        risultato = RisultatoBackupAvanzato("incrementale", manifesto=manifesto)  # Prepara l'esito dell'operazione.
        self._crea_cartelle_vuote(sorgente, cartella_versione / "dati", includi_sottocartelle, filtro)  # Mantiene visibile anche la struttura di directory della versione.
        self._copia_selezione(sorgente, cartella_versione / "dati", modificati, risultato)  # Copia soltanto i file cambiati rispetto al precedente.
        if risultato.successo:  # Evita di pubblicare una versione incompleta come valida.
            salva_manifesto(cartella_versione / ".backupcore-manifesto.json", manifesto)  # Persiste metadati e relazione di catena.
        return risultato  # Restituisce l'esito completo.

    def esegui_differenziale(self, sorgente: Path, radice_versioni: Path, manifesto_full: ManifestoBackup, includi_sottocartelle: bool = True, filtro=None) -> RisultatoBackupAvanzato:
        """Copia aggiunte/modifiche rispetto al Full di base, indipendentemente dai differenziali precedenti."""
        if manifesto_full.tipo_backup != "completo" or manifesto_full.id_backup != manifesto_full.id_full_base:  # Verifica che il riferimento sia realmente un Full autonomo.
            raise ValueError("Il backup differenziale richiede il manifesto del Full di base.")  # Impedisce dipendenze semantiche errate.
        sorgente, radice_versioni = self._valida_percorsi(sorgente, radice_versioni)  # Valida i percorsi prima del confronto.
        corrente = crea_manifesto_file(sorgente, includi_sottocartelle, filtro, self.funzione_avanzamento)  # Acquisisce lo stato corrente completo.
        modificati, eliminati = self._differenze(corrente, manifesto_full.file)  # Confronta sempre e soltanto con il Full di base.
        cartelle = elenca_cartelle_relative(sorgente, includi_sottocartelle, filtro, self.funzione_avanzamento)  # Conserva la struttura corrente rispettando i filtri.
        manifesto = crea_manifesto_backup("differenziale", sorgente, corrente, manifesto_full.id_backup, manifesto_full.id_backup, eliminati, cartelle)  # Registra il legame diretto con il Full.
        cartella_versione = radice_versioni / nome_cartella_versione(manifesto)  # Isola la versione differenziale in una directory dedicata.
        risultato = RisultatoBackupAvanzato("differenziale", manifesto=manifesto)  # Prepara l'esito dell'operazione.
        self._copia_selezione(sorgente, cartella_versione / "dati", modificati, risultato)  # Materializza soltanto le differenze dal Full.
        if risultato.successo:  # Pubblica il manifesto soltanto per una copia completa dei file richiesti.
            salva_manifesto(cartella_versione / ".backupcore-manifesto.json", manifesto)  # Rende persistente la versione differenziale.
        return risultato  # Restituisce l'esito completo.

    def esegui_update(self, sorgente: Path, destinazione: Path, includi_sottocartelle: bool = True) -> RisultatoBackupAvanzato:
        """Aggiorna la destinazione con file nuovi/modificati senza eliminare elementi già presenti soltanto a destinazione."""
        sorgente, destinazione = self._valida_percorsi(sorgente, destinazione)  # Valida la coppia prima di modificare il filesystem.
        corrente = crea_manifesto_file(sorgente, includi_sottocartelle)  # Acquisisce lo stato della sorgente.
        esistente = crea_manifesto_file(destinazione, True) if destinazione.exists() else {}  # Acquisisce lo stato della destinazione quando già presente.
        modificati, _ = self._differenze(corrente, esistente)  # Ignora volutamente le eliminazioni della sorgente secondo la semantica Update.
        risultato = RisultatoBackupAvanzato("update")  # Prepara l'esito della sincronizzazione conservativa.
        self._crea_cartelle_vuote(sorgente, destinazione, includi_sottocartelle)  # Propaga anche le directory vuote senza eliminare elementi extra.
        self._copia_selezione(sorgente, destinazione, modificati, risultato)  # Copia aggiunte e modifiche senza rimuovere altri file.
        return risultato  # Restituisce l'esito dell'aggiornamento.

    def esegui_mirror(self, sorgente: Path, destinazione: Path, includi_sottocartelle: bool = True) -> RisultatoBackupAvanzato:
        """Allinea la destinazione alla sorgente copiando variazioni ed eliminando gli elementi non più presenti nella sorgente."""
        sorgente, destinazione = self._valida_percorsi(sorgente, destinazione)  # Valida la coppia prima dell'operazione distruttiva.
        corrente = crea_manifesto_file(sorgente, includi_sottocartelle)  # Acquisisce lo stato autorevole della sorgente.
        esistente = crea_manifesto_file(destinazione, includi_sottocartelle) if destinazione.exists() else {}  # Usa la stessa profondità della sorgente per evitare eliminazioni fuori dall’ambito richiesto.
        modificati, eliminati = self._differenze(corrente, esistente)  # Determina sia copie sia rimozioni necessarie all'allineamento.
        risultato = RisultatoBackupAvanzato("mirror")  # Prepara l'esito della sincronizzazione speculare.
        cartelle_sorgente = set(self._crea_cartelle_vuote(sorgente, destinazione, includi_sottocartelle))  # Propaga anche le directory vuote e conserva l'insieme autorevole.
        self._copia_selezione(sorgente, destinazione, modificati, risultato)  # Applica prima le copie per ridurre il rischio di perdita in caso di errore iniziale.
        if not risultato.successo:  # Non applica eliminazioni se la fase di copia ha prodotto errori o è stata annullata.
            return risultato  # Mantiene la destinazione più conservativa in presenza di problemi.
        for relativo in eliminati:  # Elimina soltanto file che esistono a destinazione ma non nella sorgente.
            if self.evento_arresto.is_set():  # Controlla lo Stop prima di ogni eliminazione.
                risultato.annullato = True  # Registra l'interruzione cooperativa.
                break  # Interrompe immediatamente le eliminazioni successive.
            bersaglio = destinazione / Path(relativo)  # Costruisce il percorso da rimuovere all'interno della destinazione validata.
            try:  # Isola eventuali errori di cancellazione.
                bersaglio.unlink()  # Elimina il file non più presente nella sorgente.
                risultato.file_eliminati += 1  # Conta l'eliminazione riuscita.
                self._notifica("file_eliminato", file=relativo)  # Comunica l'operazione distruttiva al livello superiore.
            except OSError as errore:  # Raccoglie il problema senza nasconderlo.
                risultato.errori.append(f"{relativo}: {type(errore).__name__}: {errore}")  # Conserva una diagnostica completa.
        if destinazione.exists() and includi_sottocartelle:  # Pulisce directory vuote soltanto quando la sincronizzazione comprende realmente le sottocartelle.
            cartelle = sorted((elemento for elemento in destinazione.rglob("*") if elemento.is_dir()), key=lambda elemento: len(elemento.parts), reverse=True)  # Ordina dal livello più profondo alla radice.
            for cartella in cartelle:  # Tenta di rimuovere esclusivamente cartelle extra rimaste vuote.
                relativo_cartella = cartella.relative_to(destinazione).as_posix()  # Confronta la directory con lo stesso formato relativo usato per la sorgente.
                if relativo_cartella in cartelle_sorgente:  # Una directory presente nella sorgente deve esistere anche se è vuota.
                    continue  # Preserva la struttura autorevole invece di ripulirla come residuo.
                try:  # Considera normale che una cartella extra non sia vuota.
                    cartella.rmdir()  # Rimuove la directory extra soltanto quando il filesystem la considera vuota.
                except OSError:  # Ignora cartelle non vuote o non eliminabili perché i dati restano comunque preservati.
                    pass  # Non trasforma la presenza di contenuti legittimi in un errore del Mirror.
        return risultato  # Restituisce copie, eliminazioni ed eventuali problemi.
