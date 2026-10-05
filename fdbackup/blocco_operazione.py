import os  # Importa le primitive di basso livello necessarie al file di lock.
from pathlib import Path  # Importa Path per costruire il percorso del lock in modo esplicito.


class BloccoFile:
    """Mantiene un lock esclusivo tra processi finché il file rimane aperto dall'istanza corrente."""

    def __init__(self, percorso: Path) -> None:
        """Memorizza il percorso del lock senza acquisirlo implicitamente."""
        self.percorso = Path(percorso)  # Normalizza il percorso ricevuto dal chiamante.
        self._file = None  # Conserva il file aperto soltanto dopo un'acquisizione riuscita.

    @property
    def acquisito(self) -> bool:
        """Indica se questa istanza possiede attualmente il lock."""
        return self._file is not None  # Il descrittore aperto rappresenta la proprietà del lock.

    def acquisisci(self) -> bool:
        """Prova ad acquisire il lock senza attendere e restituisce False quando un altro processo lo possiede."""
        if self.acquisito:  # Rende idempotente una seconda richiesta della stessa istanza.
            return True  # Conferma il lock già posseduto.
        self.percorso.parent.mkdir(parents=True, exist_ok=True)  # Garantisce l'esistenza della cartella del lock.
        file_lock = self.percorso.open("a+b")  # Apre o crea il file mantenendolo disponibile per tutta la durata del lock.
        file_lock.seek(0, os.SEEK_END)  # Controlla la dimensione senza leggere il byte che un altro processo potrebbe avere già bloccato su Windows.
        if file_lock.tell() == 0:  # Verifica che il file appena creato non contenga ancora il byte usato come regione di lock.
            file_lock.write(b"0")  # Scrive un byte neutro soltanto quando il file è realmente vuoto.
            file_lock.flush()  # Rende disponibile il byte prima di tentare il lock a livello di sistema operativo.
        file_lock.seek(0)  # Posiziona il cursore sul primo byte, cioè sulla regione che verrà bloccata.
        try:  # Seleziona l'API nativa disponibile sulla piattaforma corrente.
            if os.name == "nt":  # Usa il locking CRT previsto su Windows, piattaforma di destinazione di FDBackup.
                import msvcrt  # Importa l'API Windows soltanto quando realmente disponibile.
                msvcrt.locking(file_lock.fileno(), msvcrt.LK_NBLCK, 1)  # Tenta un lock esclusivo non bloccante sul primo byte.
            else:  # Mantiene testabilità e comportamento equivalente sui sistemi POSIX.
                import fcntl  # Importa flock soltanto sulle piattaforme che lo espongono.
                fcntl.flock(file_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # Tenta un lock esclusivo non bloccante.
        except (OSError, BlockingIOError):  # Riconosce un lock già posseduto da un altro processo.
            file_lock.close()  # Chiude immediatamente il descrittore non utilizzato.
            return False  # Comunica al chiamante che l'operazione concorrente non deve partire.
        self._file = file_lock  # Conserva il descrittore aperto per mantenere vivo il lock.
        return True  # Conferma l'acquisizione esclusiva.

    def rilascia(self) -> None:
        """Rilascia il lock posseduto da questa istanza senza eliminare il file segnaposto."""
        if self._file is None:  # Gestisce in modo sicuro rilasci ripetuti o mai acquisiti.
            return  # Non esegue operazioni inutili.
        try:  # Tenta lo sblocco esplicito prima della chiusura del descrittore.
            self._file.seek(0)  # Riporta il cursore sul byte bloccato.
            if os.name == "nt":  # Usa la controparte Windows dell'acquisizione.
                import msvcrt  # Importa l'API soltanto sulla piattaforma compatibile.
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)  # Sblocca il primo byte.
            else:  # Usa flock sui sistemi POSIX.
                import fcntl  # Importa l'API POSIX soltanto quando disponibile.
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)  # Rilascia il lock esclusivo.
        finally:  # Garantisce sempre la chiusura anche se lo sblocco esplicito produce un errore.
            self._file.close()  # Chiude il descrittore, che costituisce anche una seconda garanzia di rilascio dal sistema operativo.
            self._file = None  # Aggiorna lo stato interno dell'istanza.

    def __enter__(self):
        """Permette l'uso opzionale del lock come context manager."""
        if not self.acquisisci():  # Prova ad acquisire senza attendere.
            raise BlockingIOError(f"Il lock '{self.percorso}' è già in uso.")  # Evita di entrare nel blocco senza esclusività reale.
        return self  # Restituisce l'istanza acquisita al blocco with.

    def __exit__(self, tipo_eccezione, valore_eccezione, traceback) -> None:
        """Rilascia sempre il lock all'uscita dal context manager."""
        self.rilascia()  # Delega alla routine idempotente di rilascio.
