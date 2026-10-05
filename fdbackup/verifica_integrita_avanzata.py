"""Verifica di integrità e recuperabilità delle versioni avanzate di FDBackup."""

from __future__ import annotations

import hashlib  # Importa SHA-256 per verificare i payload a blocchi senza caricarli interamente in memoria.
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fdbackup.metadati_backup_avanzato import DIMENSIONE_BLOCCO_HASH, ManifestoBackup
from fdbackup.motore_ripristino_avanzato import MotoreRipristinoAvanzato


@dataclass(slots=True)
class RisultatoVerificaIntegrita:
    """Raccoglie l'esito verificabile del controllo di una versione e della sua catena."""

    id_backup: str = ""  # Conserva l'identità della versione richiesta per rendere il report non ambiguo.
    tipo_backup: str = ""  # Conserva il metodo della versione finale controllata.
    file_verificati: int = 0  # Conta i payload finali letti e confrontati con SHA-256.
    byte_verificati: int = 0  # Somma i byte dei payload finali effettivamente sottoposti a hash.
    versioni_catena: int = 0  # Conta le versioni necessarie a ricostruire lo snapshot richiesto.
    annullato: bool = False  # Indica uno Stop cooperativo osservato durante la verifica.
    errori: list[str] = field(default_factory=list)  # Conserva ogni anomalia strutturale o di contenuto rilevata.

    @property
    def integro(self) -> bool:
        """Restituisce True soltanto quando la verifica termina completa e senza anomalie."""
        return not self.annullato and not self.errori  # Non confonde una verifica interrotta con una versione realmente integra.


class VerificatoreIntegritaAvanzata:
    """Verifica catena, disponibilità dei payload e SHA-256 dello snapshot finale senza ripristinarlo."""

    def __init__(self, evento_arresto: threading.Event | None = None, funzione_avanzamento: Callable[[str, dict], None] | None = None) -> None:
        """Memorizza Stop e callback mantenendo il verificatore indipendente dalla GUI."""
        self.evento_arresto = evento_arresto if evento_arresto is not None else threading.Event()  # Usa un evento dedicato quando il chiamante non ne fornisce uno.
        self.funzione_avanzamento = funzione_avanzamento  # Conserva la callback opzionale per progresso e monitoraggio.

    def _notifica(self, evento: str, **dati) -> None:
        """Inoltra un evento strutturato soltanto quando esiste un destinatario."""
        if self.funzione_avanzamento is not None:  # Evita overhead e dipendenze quando il verificatore è usato senza interfaccia.
            self.funzione_avanzamento(evento, dati)  # Trasmette dati puri senza accedere direttamente a Tk o ad altri componenti GUI.

    @staticmethod
    def _costruisci_origini(catena: list[tuple[ManifestoBackup, Path]]) -> dict[str, Path]:
        """Ricostruisce la mappa file-payload finale applicando nell'ordine versioni e tombstone."""
        origini: dict[str, Path] = {}  # Prepara la mappa logica che rappresenta lo snapshot materializzabile.
        for manifesto, cartella_versione in catena:  # Applica ogni versione dal Full fino a quella richiesta.
            for relativo in manifesto.eliminati:  # Applica prima le eliminazioni dichiarate dalla versione.
                origini.pop(relativo, None)  # Rimuove il file dalla vista logica senza fallire se era già assente.
            cartella_dati = cartella_versione / "dati"  # Risolve il contenitore fisico ufficiale dei payload della versione.
            for relativo in manifesto.file:  # Esamina lo snapshot dichiarato dal manifesto corrente.
                candidato = cartella_dati / Path(relativo)  # Costruisce il possibile payload fisico relativo alla versione corrente.
                if candidato.is_file():  # Fa prevalere soltanto un payload realmente presente in questa versione.
                    origini[relativo] = candidato  # Aggiorna l'origine più recente disponibile per il file logico.
        return origini  # Restituisce la mappa pronta per la verifica crittografica dello snapshot finale.

    def verifica_versione(self, radice_versioni: Path, id_backup: str) -> RisultatoVerificaIntegrita:
        """Verifica che una versione sia ricostruibile e che ogni payload finale corrisponda al relativo SHA-256."""
        risultato = RisultatoVerificaIntegrita(id_backup=id_backup.strip())  # Prepara un report anche quando la validazione strutturale fallisce.
        try:  # Converte anomalie strutturali in un risultato consultabile invece di mascherarle come successo.
            indice = MotoreRipristinoAvanzato._carica_indice(radice_versioni)  # Riusa l'indicizzazione validata usata dal ripristino reale.
            catena = MotoreRipristinoAvanzato._costruisci_catena(indice, risultato.id_backup)  # Richiede una catena completa e semanticamente valida.
            manifesto_finale = catena[-1][0]  # Usa lo snapshot finale come autorità sul contenuto che deve essere recuperabile.
            risultato.tipo_backup = manifesto_finale.tipo_backup  # Registra il metodo della versione verificata nel report.
            risultato.versioni_catena = len(catena)  # Registra quante versioni sono necessarie al recupero.
            origini = self._costruisci_origini(catena)  # Ricostruisce dove si trova fisicamente ogni file finale.
            attesi = set(manifesto_finale.file)  # Costruisce l'insieme autorevole dei file che devono essere recuperabili.
            disponibili = set(origini)  # Costruisce l'insieme dei file per i quali esiste un payload nella catena.
            mancanti = sorted(attesi - disponibili, key=str.casefold)  # Individua payload indispensabili che non sono più presenti.
            inattesi = sorted(disponibili - attesi, key=str.casefold)  # Individua incoerenze logiche che non appartengono allo snapshot finale.
            for relativo in mancanti:  # Registra ogni payload mancante separatamente per una diagnosi precisa.
                risultato.errori.append(f"Payload mancante: {relativo}")  # Rende immediatamente identificabile il file non recuperabile.
            for relativo in inattesi:  # Registra eventuali elementi logici residui non previsti dal manifesto finale.
                risultato.errori.append(f"Payload logico inatteso: {relativo}")  # Evidenzia una catena semanticamente incoerente.
            totale_byte = sum(voce.dimensione for voce in manifesto_finale.file.values())  # Calcola il denominatore della verifica a byte.
            self._notifica("inizio_verifica", totale_file=len(attesi), totale_byte=totale_byte, versioni_catena=len(catena))  # Comunica il lavoro totale prima degli hash.
            byte_elaborati = 0  # Conta i byte già verificati con successo o comunque elaborati.
            for relativo in sorted(attesi & disponibili, key=str.casefold):  # Verifica soltanto i file finali che possiedono un payload fisico.
                if self.evento_arresto.is_set():  # Osserva lo Stop prima di iniziare un nuovo hash potenzialmente costoso.
                    risultato.annullato = True  # Distingue esplicitamente un controllo incompleto da un fallimento d'integrità.
                    break  # Non continua a leggere altri file dopo la richiesta di arresto.
                voce = manifesto_finale.file[relativo]  # Recupera dimensione e SHA-256 attesi dallo snapshot finale.
                payload = origini[relativo]  # Recupera il payload più recente necessario alla ricostruzione.
                try:  # Isola errori I/O e differenze di contenuto per singolo file.
                    dimensione_reale = payload.stat().st_size  # Legge la dimensione fisica prima dell'hash per una diagnosi rapida.
                    if dimensione_reale != voce.dimensione:  # Rileva subito troncamenti o alterazioni della lunghezza.
                        risultato.errori.append(f"Dimensione non valida: {relativo} (attesa {voce.dimensione}, trovata {dimensione_reale})")  # Registra valori atteso/reale.
                    calcolatore = hashlib.sha256()  # Crea un contesto SHA-256 indipendente per il payload corrente.
                    byte_file_letti = 0  # Conta i byte realmente letti dal file corrente per progresso e Stop cooperativo.
                    with payload.open("rb") as file_aperto:  # Apre il payload in sola lettura binaria e ne garantisce la chiusura.
                        while True:  # Legge a blocchi per limitare memoria e latenza dello Stop anche sui file molto grandi.
                            if self.evento_arresto.is_set():  # Osserva lo Stop tra due blocchi invece di attendere la fine dell'intero file.
                                risultato.annullato = True  # Marca il controllo come incompleto senza generare un falso errore di hash.
                                break  # Interrompe immediatamente la lettura del payload corrente.
                            blocco = file_aperto.read(DIMENSIONE_BLOCCO_HASH)  # Usa la stessa dimensione di blocco adottata dalla creazione dei manifesti.
                            if not blocco:  # Riconosce la fine del file.
                                break  # Conclude l'hash soltanto quando tutti i dati sono stati letti.
                            calcolatore.update(blocco)  # Aggiorna SHA-256 con il blocco appena letto.
                            byte_file_letti += len(blocco)  # Aggiorna i byte realmente elaborati del file corrente.
                            risultato.byte_verificati += len(blocco)  # Registra il volume realmente sottoposto a hash anche se uno Stop interrompe il controllo.
                            avanzamento_corrente = min(totale_byte, byte_elaborati + min(byte_file_letti, voce.dimensione))  # Limita il progresso logico al totale atteso anche se un file è cresciuto dopo il backup.
                            self._notifica("avanzamento_verifica", file=relativo, byte_elaborati=avanzamento_corrente, totale_byte=totale_byte)  # Espone progresso fluido anche durante file grandi.
                    if risultato.annullato:  # Evita confronti su un digest parziale dopo una richiesta di Stop.
                        break  # Esce dal ciclo dei file lasciando esplicito lo stato incompleto.
                    hash_reale = calcolatore.hexdigest()  # Converte il digest completo nella rappresentazione persistita nei manifesti.
                    if hash_reale != voce.sha256:  # Confronta l'impronta con quella registrata quando lo snapshot fu creato.
                        risultato.errori.append(f"SHA-256 non valido: {relativo}")  # Segnala corruzione o alterazione del contenuto.
                    risultato.file_verificati += 1  # Conta il file soltanto dopo una lettura completa e un confronto effettivo.
                    byte_elaborati += voce.dimensione  # Avanza il lavoro logico completato secondo lo snapshot atteso.
                except OSError as errore:  # Cattura file diventati inaccessibili durante la scansione o errori del filesystem.
                    risultato.errori.append(f"{relativo}: {type(errore).__name__}: {errore}")  # Conserva tipo e messaggio diagnostico senza interrompere gli altri controlli.
            self._notifica("fine_verifica", integro=risultato.integro, file_verificati=risultato.file_verificati, errori=len(risultato.errori))  # Comunica l'esito conclusivo in forma strutturata.
        except (OSError, ValueError, KeyError, TypeError) as errore:  # Gestisce radici, manifesti e catene non validi come fallimenti verificabili.
            risultato.errori.append(f"{type(errore).__name__}: {errore}")  # Registra l'errore strutturale nel report invece di dichiarare la versione integra.
        return risultato  # Restituisce sempre un report esplicito utilizzabile da GUI, test e futuri controlli automatici.
