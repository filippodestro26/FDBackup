import hashlib  # Importa SHA-256 per verificare l'integrità dei file durante il ripristino.
import logging  # Importa il sistema di logging standard per registrare gli eventi diagnostici.
import os  # Importa le funzioni del sistema operativo necessarie per confrontare i percorsi e percorrere le directory.
import shutil  # Importa copy2 per copiare i file e i metadati supportati.
import threading  # Importa Event per gestire l'arresto cooperativo del ripristino.
from dataclasses import dataclass, field  # Importa gli strumenti usati per rappresentare il risultato del ripristino.
from pathlib import Path  # Importa Path per gestire file e directory in modo sicuro e leggibile.
from typing import Callable  # Importa Callable per descrivere il tipo della callback degli eventi.


logger = logging.getLogger(__name__)  # Crea il logger del modulo, collegato gerarchicamente al logger principale "fdbackup".


DIMENSIONE_BLOCCO_HASH = 1024 * 1024  # Usa blocchi da 1 MiB per calcolare SHA-256 senza caricare tutto il file in memoria.


@dataclass
class RisultatoRipristino:
    """Raccoglie contatori, conflitti, errori e stato finale di una singola operazione di ripristino."""

    file_trovati: int = 0  # Conta tutti i file individuati nella sorgente del ripristino.
    file_ripristinati: int = 0  # Conta i file copiati e verificati correttamente.
    file_identici: int = 0  # Conta i file già presenti e identici nella destinazione.
    file_conflitto: int = 0  # Conta i file non sovrascritti perché nella destinazione esiste contenuto differente.
    file_falliti: int = 0  # Conta i file che non è stato possibile elaborare per un errore.
    cartelle_trovate: int = 0  # Conta le sottocartelle individuate nella sorgente, esclusa la radice.
    cartelle_create: int = 0  # Conta le sottocartelle create durante il ripristino.
    cartelle_esistenti: int = 0  # Conta le sottocartelle che esistevano già correttamente.
    cartelle_conflitto: int = 0  # Conta i conflitti nei quali al posto di una cartella esiste un altro oggetto.
    cartelle_fallite: int = 0  # Conta le cartelle che non è stato possibile preparare per altri errori.
    byte_ripristinati: int = 0  # Somma i byte dei file effettivamente ripristinati e verificati.
    annullato: bool = False  # Indica se l'utente ha richiesto l'arresto dell'operazione.
    errori: list[str] = field(default_factory=list)  # Conserva errori e conflitti incontrati durante il ripristino.

    @property
    def successo(self) -> bool:
        """Restituisce True soltanto se il ripristino termina senza errori, conflitti o annullamento."""

        return (  # Combina tutte le condizioni richieste per considerare completo il ripristino.
            self.file_falliti == 0
            and self.file_conflitto == 0
            and self.cartelle_fallite == 0
            and self.cartelle_conflitto == 0
            and not self.annullato
        )


class MotoreRipristino:
    """
    Esegue il ripristino di una cartella di backup senza dipendere dalla GUI.

    Questa versione utilizza un comportamento conservativo:
    - ricrea la struttura delle directory, comprese le cartelle vuote;
    - copia soltanto file che non esistono ancora nella destinazione;
    - riconosce tramite dimensione e SHA-256 i file già identici;
    - non sovrascrive automaticamente file differenti già presenti;
    - verifica dimensione e SHA-256 dopo ogni copia;
    - supporta l'annullamento cooperativo;
    - registra conflitti ed errori senza interrompere inutilmente l'intero ripristino.

    NOTA:
    shutil.copy2() non garantisce il ripristino completo dei metadati NTFS.
    Proprietario, ACL e Alternate Data Streams richiederanno una gestione
    specifica in una fase successiva del progetto.
    """

    def __init__(
        self,
        evento_arresto: threading.Event,
        funzione_avanzamento: Callable[[str, dict], None] | None = None,
    ):
        """Memorizza l'evento di arresto e la callback opzionale utilizzata per notificare l'avanzamento."""

        self.evento_arresto = evento_arresto  # Conserva l'evento condiviso usato per richiedere l'arresto.
        self.funzione_avanzamento = funzione_avanzamento  # Conserva la funzione destinataria degli eventi del motore.

    def _notifica(self, evento: str, **dati) -> None:
        """Invia un evento al chiamante soltanto quando è stata fornita una callback."""

        if self.funzione_avanzamento is not None:  # Controlla che esista una funzione destinataria.
            self.funzione_avanzamento(evento, dati)  # Invia il nome dell'evento e il relativo dizionario di dati.

    @staticmethod
    def calcola_hash(percorso_file: Path) -> str:
        """Calcola SHA-256 di un file leggendolo progressivamente a blocchi."""

        hash_sha256 = hashlib.sha256()  # Crea un nuovo oggetto SHA-256.

        with percorso_file.open("rb") as file_aperto:  # Apre il file in modalità binaria e ne garantisce la chiusura.
            while True:  # Continua la lettura fino al raggiungimento della fine del file.
                blocco = file_aperto.read(DIMENSIONE_BLOCCO_HASH)  # Legge al massimo 1 MiB per iterazione.

                if not blocco:  # Controlla se non sono rimasti altri byte da leggere.
                    break  # Termina il ciclo quando il file è stato letto completamente.

                hash_sha256.update(blocco)  # Aggiunge il blocco corrente al calcolo SHA-256.

        return hash_sha256.hexdigest()  # Restituisce il digest SHA-256 in formato esadecimale.

    @staticmethod
    def _normalizza_percorso(percorso: Path) -> Path:
        """Espande l'eventuale home utente e normalizza il percorso senza richiedere che esista."""

        return percorso.expanduser().resolve(strict=False)  # Restituisce il percorso assoluto normalizzato.

    @staticmethod
    def _stesso_percorso(primo_percorso: Path, secondo_percorso: Path) -> bool:
        """Confronta due percorsi tenendo conto della normalizzazione del sistema operativo."""

        return os.path.normcase(str(primo_percorso)) == os.path.normcase(
            str(secondo_percorso)
        )  # Confronta le rappresentazioni normalizzate.

    @staticmethod
    def _contenuto_in(percorso_figlio: Path, percorso_genitore: Path) -> bool:
        """Restituisce True quando il primo percorso è contenuto nel secondo."""

        try:  # Prova a rappresentare il percorso figlio relativamente al percorso genitore.
            percorso_figlio.relative_to(percorso_genitore)  # Solleva ValueError se il percorso non è contenuto nel genitore.
            return True  # Conferma che il percorso appartiene all'albero del genitore.

        except ValueError:  # Intercetta il caso in cui i percorsi non abbiano la relazione richiesta.
            return False  # Indica che il percorso non è contenuto nel genitore.

    def valida_percorsi(
        self,
        sorgente_backup: Path,
        destinazione_ripristino: Path,
    ) -> tuple[Path, Path]:
        """Normalizza e valida sorgente e destinazione prima di effettuare qualsiasi ripristino."""

        sorgente_backup = self._normalizza_percorso(
            sorgente_backup
        )  # Normalizza la cartella contenente il backup.

        destinazione_ripristino = self._normalizza_percorso(
            destinazione_ripristino
        )  # Normalizza la destinazione scelta.

        if not sorgente_backup.exists():  # Verifica che la sorgente del ripristino esista.
            raise ValueError(
                "La cartella di backup non esiste."
            )  # Impedisce di avviare un ripristino senza sorgente.

        if not sorgente_backup.is_dir():  # Verifica che la sorgente sia realmente una directory.
            raise ValueError(
                "La sorgente del ripristino deve essere una cartella."
            )  # Rifiuta un file usato come radice del backup.

        if (
            destinazione_ripristino.exists()
            and not destinazione_ripristino.is_dir()
        ):  # Controlla un'eventuale destinazione già esistente.
            raise ValueError(
                "La destinazione del ripristino esiste ma non è una cartella."
            )  # Evita di usare un file come radice.

        if self._stesso_percorso(
            sorgente_backup,
            destinazione_ripristino,
        ):  # Controlla che sorgente e destinazione non coincidano.
            raise ValueError(
                "Sorgente del backup e destinazione del ripristino non possono coincidere."
            )  # Evita operazioni sullo stesso albero.

        if self._contenuto_in(
            destinazione_ripristino,
            sorgente_backup,
        ):  # Controlla che la destinazione non sia dentro il backup.
            raise ValueError(
                "La destinazione del ripristino non può trovarsi all'interno della cartella di backup."
            )  # Evita scansioni ricorsive dei dati creati.

        return sorgente_backup, destinazione_ripristino  # Restituisce i percorsi normalizzati e validati.

    def file_identici(
        self,
        file_backup: Path,
        file_destinazione: Path,
    ) -> bool:
        """Confronta dimensione e SHA-256 per determinare se due file hanno lo stesso contenuto."""

        if not file_destinazione.exists():  # Controlla se nella destinazione esiste già qualcosa con quel percorso.
            return False  # Un file inesistente non può essere identico.

        if not file_destinazione.is_file():  # Controlla che l'oggetto esistente sia realmente un file.
            return False  # Una directory o un altro oggetto non viene considerato identico.

        if (
            file_backup.stat().st_size != file_destinazione.stat().st_size
        ):  # Confronta prima le dimensioni.
            return False  # Dimensioni differenti implicano contenuti differenti.

        hash_backup = self.calcola_hash(
            file_backup
        )  # Calcola SHA-256 del file conservato nel backup.

        hash_destinazione = self.calcola_hash(
            file_destinazione
        )  # Calcola SHA-256 del file già presente.

        return hash_backup == hash_destinazione  # Considera identici i file soltanto quando coincidono anche gli hash.

    def copia_e_verifica(
        self,
        file_backup: Path,
        file_destinazione: Path,
    ) -> int:
        """Copia un file inesistente, ne verifica dimensione e SHA-256 e restituisce i byte ripristinati."""

        if file_destinazione.exists():  # Effettua un'ultima protezione immediatamente prima della copia.
            raise FileExistsError(
                f"La destinazione esiste già e non verrà sovrascritta: '{file_destinazione}'."
            )  # Impedisce una sovrascrittura volontaria.

        dimensione_backup = file_backup.stat().st_size  # Memorizza la dimensione della sorgente prima della copia.

        hash_backup = self.calcola_hash(
            file_backup
        )  # Calcola SHA-256 della sorgente prima della copia.

        file_destinazione.parent.mkdir(
            parents=True,
            exist_ok=True,
        )  # Garantisce l'esistenza della cartella genitore.

        shutil.copy2(
            file_backup,
            file_destinazione,
        )  # Copia il file e i metadati supportati dalla piattaforma.

        dimensione_backup_dopo_copia = (
            file_backup.stat().st_size
        )  # Rilegge la dimensione della sorgente dopo la copia.

        dimensione_destinazione = (
            file_destinazione.stat().st_size
        )  # Legge la dimensione del file appena ripristinato.

        if (
            dimensione_backup != dimensione_backup_dopo_copia
        ):  # Rileva una modifica di dimensione avvenuta durante l'operazione.
            raise IOError(
                f"Il file di backup è cambiato durante il ripristino: '{file_backup}'."
            )  # Non dichiara verificata una sorgente mutata.

        if (
            dimensione_backup != dimensione_destinazione
        ):  # Verifica che la dimensione copiata corrisponda alla sorgente.
            raise IOError(
                f"Verifica fallita per '{file_backup}': dimensione sorgente/destinazione differente."
            )  # Segnala una copia incompleta.

        hash_destinazione = self.calcola_hash(
            file_destinazione
        )  # Calcola SHA-256 del file appena creato.

        if hash_backup != hash_destinazione:  # Confronta l'hash originale con quello del file ripristinato.
            raise IOError(
                f"Verifica SHA-256 fallita per '{file_backup}'."
            )  # Considera fallita la verifica se i contenuti differiscono.

        return dimensione_backup  # Restituisce il numero di byte ripristinati con successo.

    def prepara_cartella_destinazione(
        self,
        cartella_backup: Path,
        sorgente_principale: Path,
        destinazione_principale: Path,
        risultato: RisultatoRipristino,
    ) -> bool:
        """Prepara nella destinazione la cartella equivalente e aggiorna i relativi contatori."""

        percorso_relativo = cartella_backup.relative_to(
            sorgente_principale
        )  # Calcola la posizione della cartella rispetto alla radice del backup.

        cartella_destinazione = (
            destinazione_principale / percorso_relativo
        )  # Costruisce il percorso equivalente nella destinazione.

        if percorso_relativo != Path("."):  # Esclude la radice principale dal conteggio delle sottocartelle.
            risultato.cartelle_trovate += 1  # Registra la sottocartella individuata.

        try:  # Prova a controllare o creare la directory richiesta.
            if cartella_destinazione.exists():  # Verifica se nella destinazione esiste già un oggetto.
                if not cartella_destinazione.is_dir():  # Controlla che l'oggetto esistente sia una directory.
                    risultato.cartelle_conflitto += 1  # Registra il conflitto cartella/oggetto.

                    messaggio = (
                        "Conflitto: dovrebbe essere una cartella ma esiste "
                        f"un altro oggetto: '{cartella_destinazione}'."
                    )  # Costruisce il messaggio diagnostico.

                    risultato.errori.append(
                        messaggio
                    )  # Conserva il conflitto nel risultato finale.

                    logger.warning(
                        messaggio
                    )  # Registra il conflitto nel log persistente.

                    self._notifica(
                        "cartella_conflitto",
                        percorso=str(cartella_destinazione),
                        errore=messaggio,
                    )  # Comunica il conflitto alla callback.

                    return False  # Impedisce di elaborare il contenuto della cartella in conflitto.

                if percorso_relativo != Path("."):  # Evita di contare la radice principale come sottocartella esistente.
                    risultato.cartelle_esistenti += 1  # Registra la directory già presente.

                return True  # Consente di elaborare normalmente il contenuto della cartella.

            cartella_destinazione.mkdir(
                parents=True,
                exist_ok=False,
            )  # Crea la cartella soltanto se non esiste già.

            if percorso_relativo != Path("."):  # Evita di conteggiare la radice principale come sottocartella.
                risultato.cartelle_create += 1  # Registra la nuova directory creata.

            return True  # Conferma che la cartella può essere utilizzata.

        except OSError as errore:  # Gestisce errori del filesystem diversi dai conflitti già classificati.
            risultato.cartelle_fallite += 1  # Incrementa il numero delle cartelle non preparate.

            messaggio = (
                f"Impossibile preparare la cartella '{cartella_destinazione}': {errore}"
            )  # Costruisce il messaggio diagnostico.

            risultato.errori.append(
                messaggio
            )  # Conserva l'errore nel risultato finale.

            logger.error(
                messaggio
            )  # Registra l'errore nel log persistente.

            self._notifica(
                "errore_cartella",
                percorso=str(cartella_destinazione),
                errore=messaggio,
            )  # Invia l'errore alla callback.

            return False  # Impedisce di elaborare il contenuto della cartella non disponibile.

    def esegui(
        self,
        sorgente_backup: Path,
        destinazione_ripristino: Path,
    ) -> RisultatoRipristino:
        """Esegue il ripristino conservativo dell'intera struttura contenuta nella cartella di backup."""

        sorgente_backup, destinazione_ripristino = self.valida_percorsi(
            sorgente_backup,
            destinazione_ripristino,
        )  # Valida i percorsi prima di effettuare modifiche.

        risultato = RisultatoRipristino()  # Crea il contenitore che raccoglierà l'esito dell'operazione.

        logger.info(
            "Ripristino avviato. Sorgente='%s' Destinazione='%s'",
            sorgente_backup,
            destinazione_ripristino,
        )  # Registra l'inizio del ripristino nel log persistente.

        self._notifica(
            "inizio",
            sorgente=str(sorgente_backup),
            destinazione=str(destinazione_ripristino),
        )  # Comunica alla futura GUI che il ripristino è iniziato.

        for (
            radice_corrente,
            nomi_cartelle,
            nomi_file,
        ) in os.walk(sorgente_backup):  # Percorre ricorsivamente l'intera sorgente del ripristino.

            if self.evento_arresto.is_set():  # Controlla la richiesta di arresto prima di elaborare la directory corrente.
                risultato.annullato = True  # Registra che l'operazione è stata interrotta.
                break  # Termina la scansione principale.

            cartella_backup = Path(
                radice_corrente
            )  # Converte la directory corrente in un oggetto Path.

            nomi_cartelle.sort()  # Ordina le sottocartelle per rendere deterministica la scansione.
            nomi_file.sort()  # Ordina i file per rendere prevedibile l'ordine di elaborazione.

            risultato.file_trovati += len(
                nomi_file
            )  # Conta subito i file individuati nella directory, anche se il ramo non potrà essere ripristinato.

            cartella_disponibile = self.prepara_cartella_destinazione(
                cartella_backup,
                sorgente_backup,
                destinazione_ripristino,
                risultato,
            )  # Prepara la cartella equivalente nella destinazione.

            if not cartella_disponibile:  # Controlla se la cartella presenta un conflitto o un errore.
                nomi_cartelle[:] = []  # Impedisce a os.walk di scendere nelle sottocartelle del ramo non ripristinabile.
                continue  # Passa alla prossima directory disponibile.

            for nome_file in nomi_file:  # Elabora singolarmente tutti i file presenti nella directory corrente.
                if self.evento_arresto.is_set():  # Controlla la richiesta di arresto prima di iniziare un nuovo file.
                    risultato.annullato = True  # Registra l'interruzione richiesta dall'utente.
                    break  # Interrompe il ciclo dei file della directory corrente.

                file_backup = (
                    cartella_backup / nome_file
                )  # Costruisce il percorso completo del file nel backup.

                percorso_relativo = file_backup.relative_to(
                    sorgente_backup
                )  # Calcola la posizione relativa del file.

                file_destinazione = (
                    destinazione_ripristino / percorso_relativo
                )  # Costruisce il percorso corrispondente nella destinazione.

                try:  # Prova a classificare e, se necessario, ripristinare il file.
                    if file_destinazione.exists():  # Verifica se nella destinazione esiste già qualcosa con lo stesso percorso.
                        if (
                            file_destinazione.is_file()
                            and self.file_identici(
                                file_backup,
                                file_destinazione,
                            )
                        ):  # Controlla se il file già presente è identico.
                            risultato.file_identici += 1  # Registra il file che non necessita di ripristino.

                            self._notifica(
                                "file_identico",
                                percorso=str(percorso_relativo),
                            )  # Comunica che il file era già corretto.

                            continue  # Evita qualsiasi scrittura sul file esistente.

                        risultato.file_conflitto += 1  # Registra un file differente o un conflitto file/cartella.

                        messaggio = (
                            "Conflitto: la destinazione esiste già e non verrà "
                            f"sovrascritta: '{file_destinazione}'."
                        )  # Costruisce il messaggio del conflitto.

                        risultato.errori.append(
                            messaggio
                        )  # Conserva il conflitto nel risultato finale.

                        logger.warning(
                            messaggio
                        )  # Registra il conflitto nel log persistente.

                        self._notifica(
                            "file_conflitto",
                            percorso=str(percorso_relativo),
                            errore=messaggio,
                        )  # Comunica il conflitto alla callback.

                        continue  # Lascia completamente intatto l'oggetto già presente.

                    byte_ripristinati = self.copia_e_verifica(
                        file_backup,
                        file_destinazione,
                    )  # Copia e verifica il nuovo file.

                    risultato.file_ripristinati += 1  # Registra il file ripristinato correttamente.

                    risultato.byte_ripristinati += (
                        byte_ripristinati
                    )  # Aggiorna il totale dei byte effettivamente ripristinati.

                    self._notifica(
                        "file_ripristinato",
                        percorso=str(percorso_relativo),
                        byte=byte_ripristinati,
                    )  # Comunica il completamento del singolo file.

                except (OSError, ValueError) as errore:  # Gestisce gli errori previsti durante lettura, confronto, copia o verifica.
                    risultato.file_falliti += 1  # Incrementa il numero dei file falliti.

                    messaggio = (
                        f"Errore durante il ripristino di '{file_backup}': {errore}"
                    )  # Costruisce un messaggio diagnostico completo.

                    risultato.errori.append(
                        messaggio
                    )  # Conserva l'errore nel risultato finale.

                    logger.error(
                        messaggio
                    )  # Registra l'errore nel log persistente.

                    self._notifica(
                        "errore_file",
                        percorso=str(percorso_relativo),
                        errore=messaggio,
                    )  # Comunica alla callback il fallimento del file.

            if risultato.annullato:  # Controlla se il ciclo dei file è terminato per una richiesta di arresto.
                break  # Interrompe anche la scansione delle directory.

        if risultato.annullato:  # Controlla se il ripristino è terminato a causa di una richiesta di arresto.
            logger.warning(
                "Ripristino annullato. Ripristinati=%d Identici=%d Conflitti=%d Falliti=%d",
                risultato.file_ripristinati,
                risultato.file_identici,
                risultato.file_conflitto,
                risultato.file_falliti,
            )  # Registra nel log persistente il riepilogo dell'operazione annullata.

        else:  # Gestisce il caso in cui la scansione sia terminata senza una richiesta di arresto.
            logger.info(
                "Ripristino terminato. Ripristinati=%d Identici=%d Conflitti=%d Falliti=%d Cartelle_conflitto=%d",
                risultato.file_ripristinati,
                risultato.file_identici,
                risultato.file_conflitto,
                risultato.file_falliti,
                risultato.cartelle_conflitto,
            )  # Registra nel log persistente il riepilogo dell'operazione terminata.

        self._notifica(
            "fine",
            risultato=risultato,
        )  # Comunica sempre la conclusione del ripristino passando lo stesso oggetto risultato restituito dal metodo.

        return risultato  # Restituisce al chiamante il risultato completo del ripristino.