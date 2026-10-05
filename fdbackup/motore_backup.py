import hashlib  # Importa gli algoritmi di hashing usati per verificare l'integrità dei file.
import logging  # Importa il sistema di logging standard usato per registrare gli eventi diagnostici del motore.
import os  # Importa le funzioni del sistema operativo usate per percorrere cartelle e confrontare percorsi.
import shutil  # Importa le funzioni di copia dei file e dei relativi metadati supportati.
import threading  # Importa gli strumenti necessari per gestire l'evento di arresto cooperativo.
from dataclasses import dataclass, field  # Importa gli strumenti per definire il risultato del backup.
from pathlib import Path  # Importa Path per gestire i percorsi in modo più sicuro e leggibile.
from typing import Callable  # Importa Callable per descrivere il tipo della funzione di callback.


logger = logging.getLogger(__name__)  # Crea il logger del modulo, collegato gerarchicamente al logger principale "fdbackup".


DIMENSIONE_BLOCCO_HASH = 1024 * 1024  # Definisce blocchi da 1 MiB per calcolare SHA-256 senza caricare tutto il file in memoria.


@dataclass
class RisultatoBackup:
    """Raccoglie tutti i contatori, gli errori e lo stato finale di una singola operazione di backup."""

    file_trovati: int = 0  # Conta quanti file sono stati individuati durante la scansione.
    file_copiati: int = 0  # Conta quanti file sono stati effettivamente copiati e verificati.
    file_ignorati: int = 0  # Conta quanti file erano già identici nella destinazione.
    file_falliti: int = 0  # Conta quanti file non è stato possibile elaborare correttamente.
    cartelle_trovate: int = 0  # Conta le sottocartelle individuate, esclusa la cartella sorgente principale.
    cartelle_create: int = 0  # Conta le sottocartelle che non esistevano e sono state create nella destinazione.
    cartelle_esistenti: int = 0  # Conta le sottocartelle che erano già presenti nella destinazione.
    cartelle_fallite: int = 0  # Conta le sottocartelle che non è stato possibile preparare nella destinazione.
    byte_copiati: int = 0  # Somma il numero di byte dei file copiati con successo.
    annullato: bool = False  # Indica se l'utente ha richiesto l'interruzione del backup.
    errori: list[str] = field(default_factory=list)  # Conserva i messaggi degli errori incontrati durante il backup.

    @property
    def successo(self) -> bool:
        """Restituisce True soltanto se il backup termina senza errori e senza essere annullato."""
        return self.file_falliti == 0 and self.cartelle_fallite == 0 and not self.annullato  # Valuta lo stato complessivo del backup.


# ============================================================
# MOTORE DI BACKUP
# ============================================================

class MotoreBackup:
    """
    Esegue la logica di backup senza dipendere direttamente dalla GUI.

    Questa versione:
    - ricrea la struttura delle directory, comprese le cartelle vuote;
    - confronta dimensione e SHA-256 per riconoscere i file identici;
    - verifica SHA-256 dopo ogni copia;
    - supporta l'annullamento cooperativo;
    - raccoglie gli errori senza interrompere inutilmente l'intero lavoro.

    NOTA:
    shutil.copy2() non rappresenta ancora un backup completo dei metadati NTFS.
    La gestione completa di ACL, proprietario, Alternate Data Streams e VSS
    verrà affrontata in una fase successiva del progetto.
    """

    def __init__(
        self,
        evento_arresto: threading.Event,
        funzione_avanzamento: Callable[[str, dict], None] | None = None,
        includi_sottocartelle: bool = True,
        verifica_integrita: bool = True,
    ):
        """Memorizza l'evento di arresto e la callback usata per inviare aggiornamenti alla GUI."""
        self.evento_arresto = evento_arresto  # Conserva l'evento condiviso usato per richiedere l'arresto del backup.
        self.funzione_avanzamento = funzione_avanzamento  # Conserva la funzione che riceve gli eventi prodotti dal motore.

        if not isinstance(includi_sottocartelle, bool):  # Verifica che la scelta sulla scansione ricorsiva sia realmente booleana.
            raise TypeError("L'opzione includi_sottocartelle deve essere un valore booleano.")  # Rifiuta valori ambigui che potrebbero alterare la scansione.

        if not isinstance(verifica_integrita, bool):  # Verifica che la scelta sulla verifica post-copia sia realmente booleana.
            raise TypeError("L'opzione verifica_integrita deve essere un valore booleano.")  # Rifiuta valori ambigui che potrebbero disattivare involontariamente la verifica.

        self.includi_sottocartelle = includi_sottocartelle  # Conserva la scelta che controlla la discesa nelle sottocartelle.
        self.verifica_integrita = verifica_integrita  # Conserva la scelta che controlla SHA-256 dopo la copia.

    def _notifica(self, evento: str, **dati) -> None:
        """Invia un evento alla GUI soltanto quando è stata fornita una callback."""
        if self.funzione_avanzamento is not None:  # Controlla che esista una funzione destinataria degli eventi.
            self.funzione_avanzamento(evento, dati)  # Invia il nome dell'evento e i relativi dati.

    @staticmethod
    def calcola_hash(percorso_file: Path) -> str:
        """Calcola e restituisce il digest SHA-256 di un file leggendo il contenuto a blocchi."""
        hash_sha256 = hashlib.sha256()  # Crea un nuovo oggetto SHA-256 per il file corrente.

        with percorso_file.open("rb") as file_aperto:  # Apre il file in modalità binaria e garantisce la chiusura automatica.
            while True:  # Continua a leggere finché non viene raggiunta la fine del file.
                blocco = file_aperto.read(DIMENSIONE_BLOCCO_HASH)  # Legge al massimo 1 MiB per volta.
                if not blocco:  # Controlla se la lettura ha raggiunto la fine del file.
                    break  # Termina il ciclo quando non rimangono dati da leggere.
                hash_sha256.update(blocco)  # Aggiunge il blocco corrente al calcolo SHA-256.

        return hash_sha256.hexdigest()  # Restituisce il digest SHA-256 in formato esadecimale.

    @staticmethod
    def _normalizza_percorso(percorso: Path) -> Path:
        """Espande l'eventuale home utente e normalizza il percorso senza richiedere che esista."""
        return percorso.expanduser().resolve(strict=False)  # Restituisce il percorso assoluto normalizzato.

    @staticmethod
    def _stesso_percorso(primo_percorso: Path, secondo_percorso: Path) -> bool:
        """Confronta due percorsi normalizzando la differenza tra maiuscole e minuscole gestita dal sistema."""
        return os.path.normcase(str(primo_percorso)) == os.path.normcase(str(secondo_percorso))  # Confronta le rappresentazioni normalizzate.

    @staticmethod
    def _contenuto_in(percorso_figlio: Path, percorso_genitore: Path) -> bool:
        """Restituisce True quando il primo percorso è contenuto nel secondo percorso."""
        try:  # Prova a rappresentare il percorso figlio relativamente al percorso genitore.
            percorso_figlio.relative_to(percorso_genitore)  # Solleva ValueError quando il figlio non appartiene al genitore.
            return True  # Conferma che il percorso è contenuto nel genitore.
        except ValueError:  # Intercetta esclusivamente il caso in cui i percorsi non abbiano la relazione richiesta.
            return False  # Indica che il percorso non è contenuto nel genitore.

    def valida_percorsi(self, sorgente: Path, destinazione: Path) -> tuple[Path, Path]:
        """Normalizza e valida sorgente e destinazione prima di iniziare qualsiasi copia."""
        sorgente = self._normalizza_percorso(sorgente)  # Normalizza il percorso della sorgente.
        destinazione = self._normalizza_percorso(destinazione)  # Normalizza il percorso della destinazione.

        if not sorgente.exists():  # Verifica che la sorgente esista realmente.
            raise ValueError("La cartella sorgente non esiste.")  # Blocca il backup se la sorgente non esiste.

        if not sorgente.is_dir():  # Verifica che la sorgente sia una directory.
            raise ValueError("La sorgente deve essere una cartella.")  # Blocca il backup se la sorgente non è una directory.

        if destinazione.exists() and not destinazione.is_dir():  # Controlla che una destinazione già esistente sia una cartella.
            raise ValueError("La destinazione esiste ma non è una cartella.")  # Evita di usare un file come radice del backup.

        if self._stesso_percorso(sorgente, destinazione):  # Impedisce di usare lo stesso percorso come sorgente e destinazione.
            raise ValueError("Sorgente e destinazione non possono coincidere.")  # Segnala la configurazione non valida.

        if self._contenuto_in(destinazione, sorgente):  # Verifica che la destinazione non sia annidata dentro la sorgente.
            raise ValueError("La destinazione non può trovarsi all'interno della cartella sorgente.")  # Evita copie ricorsive del backup dentro se stesso.

        return sorgente, destinazione  # Restituisce i due percorsi normalizzati e validati.

    def file_identici(self, sorgente: Path, destinazione: Path) -> bool:
        """Confronta prima la dimensione e poi SHA-256 per stabilire se due file sono identici."""
        if not destinazione.exists():  # Controlla se il file di destinazione esiste.
            return False  # Un file inesistente non può essere identico alla sorgente.

        if not destinazione.is_file():  # Controlla che la destinazione sia effettivamente un file.
            return False  # Un oggetto che non è un file non viene considerato identico.

        if sorgente.stat().st_size != destinazione.stat().st_size:  # Confronta le dimensioni per evitare hash inutili quando differiscono.
            return False  # Dimensioni differenti implicano contenuti differenti.

        hash_sorgente = self.calcola_hash(sorgente)  # Calcola SHA-256 del file sorgente.
        hash_destinazione = self.calcola_hash(destinazione)  # Calcola SHA-256 del file già presente nella destinazione.

        return hash_sorgente == hash_destinazione  # Considera identici i file soltanto se anche gli hash coincidono.

    def copia_e_verifica(self, sorgente: Path, destinazione: Path) -> int:
        """Copia un file, verifica dimensione e SHA-256 e restituisce il numero di byte copiati."""
        dimensione_sorgente = sorgente.stat().st_size  # Legge la dimensione iniziale del file sorgente.
        hash_sorgente = self.calcola_hash(sorgente) if self.verifica_integrita else None  # Calcola SHA-256 prima della copia soltanto quando è richiesta la verifica completa.

        destinazione.parent.mkdir(parents=True, exist_ok=True)  # Garantisce che la directory genitore del file di destinazione esista.
        shutil.copy2(sorgente, destinazione)  # Copia il file e i metadati supportati da copy2.

        dimensione_sorgente_dopo_copia = sorgente.stat().st_size  # Rilegge la dimensione della sorgente dopo la copia.
        dimensione_destinazione = destinazione.stat().st_size  # Legge la dimensione del file appena copiato.

        if dimensione_sorgente != dimensione_sorgente_dopo_copia:  # Rileva almeno una modifica di dimensione avvenuta durante la copia.
            raise IOError(f"La sorgente è cambiata durante la copia: '{sorgente}'.")  # Non dichiara verificata una copia basata su una sorgente mutata.

        if dimensione_sorgente != dimensione_destinazione:  # Verifica che sorgente e destinazione abbiano la stessa dimensione.
            raise IOError(f"Verifica fallita per '{sorgente}': dimensione sorgente/destinazione differente.")  # Registra una copia non valida.

        if self.verifica_integrita:  # Esegue la verifica crittografica post-copia soltanto quando l'opzione del job è attiva.
            hash_destinazione = self.calcola_hash(destinazione)  # Calcola SHA-256 del file presente nella destinazione dopo la copia.

            if hash_sorgente != hash_destinazione:  # Confronta l'hash originale con quello del file copiato.
                raise IOError(f"Verifica SHA-256 fallita per '{sorgente}'.")  # Considera fallita la copia se i contenuti non coincidono.

        return dimensione_sorgente  # Restituisce il numero di byte copiati con successo.

    def prepara_cartella_destinazione(
        self,
        cartella_sorgente: Path,
        sorgente_principale: Path,
        destinazione_principale: Path,
        risultato: RisultatoBackup,
    ) -> bool:
        """Ricrea nella destinazione la cartella corrente e aggiorna i contatori delle directory."""
        percorso_relativo = cartella_sorgente.relative_to(sorgente_principale)  # Calcola la posizione della cartella rispetto alla radice sorgente.
        cartella_destinazione = destinazione_principale / percorso_relativo  # Costruisce il percorso equivalente nella destinazione.

        if percorso_relativo != Path("."):  # Esclude la radice sorgente dal conteggio delle sottocartelle.
            risultato.cartelle_trovate += 1  # Registra la sottocartella incontrata durante la scansione.

        try:  # Prova a verificare o creare la directory equivalente nella destinazione.
            if cartella_destinazione.exists():  # Controlla se nella destinazione esiste già un oggetto con quel percorso.
                if not cartella_destinazione.is_dir():  # Verifica che l'oggetto esistente sia realmente una directory.
                    raise NotADirectoryError(f"Il percorso di destinazione esiste ma non è una cartella: '{cartella_destinazione}'.")  # Impedisce di trattare un file come directory.

                if percorso_relativo != Path("."):  # Evita di conteggiare la radice di destinazione come sottocartella esistente.
                    risultato.cartelle_esistenti += 1  # Registra che la sottocartella era già presente.

                    self._notifica("cartella_esistente", cartella=str(percorso_relativo))  # Comunica alla GUI che la sottocartella era già presente.

                return True  # Conferma che la directory è pronta per contenere file o altre cartelle.

            cartella_destinazione.mkdir(parents=True, exist_ok=False)  # Crea la directory e gli eventuali genitori mancanti.

            if percorso_relativo != Path("."):  # Evita di conteggiare la radice di destinazione come normale sottocartella.
                risultato.cartelle_create += 1  # Registra la nuova sottocartella creata.

                self._notifica("cartella_creata", cartella=str(percorso_relativo))  # Comunica alla GUI la creazione della sottocartella.

            return True  # Conferma che la directory è stata preparata correttamente.

        except OSError as errore:  # Gestisce errori del filesystem durante la preparazione della directory.
            if percorso_relativo == Path("."):  # Verifica se l'errore riguarda la radice della destinazione.
                raise  # Propaga l'errore perché senza la radice non è possibile eseguire il backup.

            risultato.cartelle_fallite += 1  # Incrementa il numero di sottocartelle non preparate correttamente.
            messaggio = f"{cartella_sorgente}: {type(errore).__name__}: {errore}"  # Costruisce un messaggio diagnostico completo.
            risultato.errori.append(messaggio)  # Conserva il messaggio nel risultato finale.

            logger.error(  # Registra nel log persistente l'errore incontrato durante la preparazione della sottocartella.
                "Errore durante la preparazione della cartella | cartella=%s | tipo=%s | errore=%s",
                cartella_sorgente,
                type(errore).__name__,
                errore,
            )

            self._notifica("errore_cartella", cartella=str(percorso_relativo), errore=messaggio)  # Comunica l'errore alla GUI.
            return False  # Indica al ciclo principale di non elaborare il contenuto di questa directory.

    def esegui(self, sorgente: Path, destinazione: Path) -> RisultatoBackup:
        """Esegue la scansione, ricrea le directory, copia i file modificati e restituisce il risultato finale."""
        risultato = RisultatoBackup()  # Crea il contenitore che accumulerà contatori ed errori.
        sorgente, destinazione = self.valida_percorsi(sorgente, destinazione)  # Valida e normalizza i percorsi prima di toccare il filesystem.

        logger.info(  # Registra nel log persistente l'avvio effettivo del backup.
            "Backup avviato | sorgente=%s | destinazione=%s",
            sorgente,
            destinazione,
        )

        self._notifica("inizio", sorgente=str(sorgente), destinazione=str(destinazione))  # Comunica alla GUI l'inizio effettivo del backup.

        for radice, cartelle, file_nella_cartella in os.walk(sorgente):  # Percorre ricorsivamente l'albero della sorgente.
            if self.evento_arresto.is_set():  # Controlla se l'utente ha richiesto l'arresto.
                risultato.annullato = True  # Registra che il backup è stato annullato.
                break  # Interrompe la scansione delle directory.

            percorso_radice = Path(radice)  # Converte la radice restituita da os.walk in un oggetto Path.

            if not self.includi_sottocartelle:  # Controlla se il job deve limitarsi ai file presenti direttamente nella radice sorgente.
                cartelle[:] = []  # Svuota in-place la lista di os.walk affinché non venga visitata alcuna sottocartella.

            if not self.prepara_cartella_destinazione(percorso_radice, sorgente, destinazione, risultato):  # Prepara anche le directory che non contengono file.
                cartelle[:] = []  # Impedisce a os.walk di scendere nelle sottocartelle di una directory non preparabile.
                continue  # Passa alla prossima directory disponibile.

            for nome_file in file_nella_cartella:  # Elabora tutti i file presenti nella directory corrente.
                if self.evento_arresto.is_set():  # Controlla nuovamente l'eventuale richiesta di arresto prima di ogni file.
                    risultato.annullato = True  # Registra l'annullamento nel risultato.
                    break  # Interrompe il ciclo dei file della directory corrente.

                risultato.file_trovati += 1  # Incrementa il numero totale di file individuati.
                percorso_sorgente = percorso_radice / nome_file  # Costruisce il percorso completo del file sorgente.

                try:  # Isola gli errori del singolo file per consentire al backup di proseguire sugli altri file.
                    percorso_relativo = percorso_sorgente.relative_to(sorgente)  # Calcola il percorso relativo del file.
                    percorso_destinazione = destinazione / percorso_relativo  # Costruisce il percorso equivalente nella destinazione.

                    self._notifica(
                        "file",
                        file=str(percorso_relativo),
                        trovati=risultato.file_trovati,
                        copiati=risultato.file_copiati,
                        ignorati=risultato.file_ignorati,
                        falliti=risultato.file_falliti,
                    )  # Comunica alla GUI quale file sta per essere elaborato.

                    if self.file_identici(percorso_sorgente, percorso_destinazione):  # Verifica se il file è già identico nella destinazione.
                        risultato.file_ignorati += 1  # Incrementa il contatore dei file che non richiedono una nuova copia.
                        self._notifica("ignorato", file=str(percorso_relativo))  # Comunica alla GUI che il file è già identico.
                        continue  # Passa direttamente al file successivo.

                    byte_copiati = self.copia_e_verifica(percorso_sorgente, percorso_destinazione)  # Copia il file e ne verifica l'integrità.
                    risultato.file_copiati += 1  # Incrementa il numero di file copiati con successo.
                    risultato.byte_copiati += byte_copiati  # Somma la dimensione del file ai byte copiati complessivi.
                    self._notifica("copiato", file=str(percorso_relativo), byte=byte_copiati)  # Comunica alla GUI la copia completata.

                except (OSError, ValueError) as errore:  # Gestisce gli errori previsti relativi al file o al suo percorso.
                    risultato.file_falliti += 1  # Incrementa il numero di file falliti.
                    messaggio = f"{percorso_sorgente}: {type(errore).__name__}: {errore}"  # Costruisce un messaggio diagnostico.
                    risultato.errori.append(messaggio)  # Conserva l'errore nel risultato finale.

                    logger.error(  # Registra nel log persistente l'errore relativo al singolo file.
                        "Errore durante il backup del file | file=%s | tipo=%s | errore=%s",
                        percorso_sorgente,
                        type(errore).__name__,
                        errore,
                    )

                    self._notifica("errore", file=str(percorso_sorgente), errore=messaggio)  # Comunica l'errore alla GUI.

            if risultato.annullato:  # Controlla se il ciclo dei file è terminato a causa di una richiesta di arresto.
                break  # Interrompe anche il ciclo esterno di os.walk.

        if risultato.annullato:  # Controlla se l'operazione è terminata a causa di una richiesta di arresto.
            logger.warning(  # Registra nel log persistente l'annullamento richiesto dall'utente.
                "Backup annullato | trovati=%d | copiati=%d | identici=%d | falliti=%d",
                risultato.file_trovati,
                risultato.file_copiati,
                risultato.file_ignorati,
                risultato.file_falliti,
            )

        else:  # Gestisce il caso in cui il motore abbia terminato normalmente la scansione.
            logger.info(  # Registra nel log persistente il riepilogo conclusivo del backup.
                "Backup terminato | trovati=%d | copiati=%d | identici=%d | falliti=%d | byte_copiati=%d | cartelle_fallite=%d",
                risultato.file_trovati,
                risultato.file_copiati,
                risultato.file_ignorati,
                risultato.file_falliti,
                risultato.byte_copiati,
                risultato.cartelle_fallite,
            )

        self._notifica("fine", risultato=risultato)  # Comunica la conclusione del motore alla callback.
        return risultato  # Restituisce tutti i contatori e gli eventuali errori al chiamante.