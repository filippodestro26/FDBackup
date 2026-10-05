import os  # Importa le funzioni del sistema operativo necessarie per enumerare le unità su Windows.
import shutil  # Importa disk_usage per leggere capacità totale, spazio usato e spazio libero.
from dataclasses import dataclass  # Importa dataclass per rappresentare in modo esplicito lo stato di una singola unità.


@dataclass(slots=True, frozen=True)
class InformazioniUnita:
    """Rappresenta lo stato leggibile di un'unità rilevata dal sistema operativo."""

    percorso: str  # Conserva la radice dell'unità, per esempio C:\\.
    totale: int | None  # Conserva la capacità totale in byte oppure None quando l'unità non è accessibile.
    usato: int | None  # Conserva lo spazio utilizzato in byte oppure None quando non è disponibile.
    libero: int | None  # Conserva lo spazio libero in byte oppure None quando non è disponibile.
    errore: str | None = None  # Conserva un eventuale problema di accesso senza perdere l'unità dall'elenco.

    @property
    def accessibile(self) -> bool:
        """Indica se le statistiche dell'unità sono state lette correttamente."""
        return self.errore is None and self.totale is not None and self.usato is not None and self.libero is not None  # Richiede tutte le misure e l'assenza di errori.

    @property
    def frazione_utilizzata(self) -> float:
        """Restituisce una frazione compresa tra 0 e 1 adatta alla barra grafica della Home."""
        if not self.accessibile or self.totale is None or self.usato is None or self.totale <= 0:  # Gestisce unità non accessibili o capacità anomala.
            return 0.0  # Mantiene la barra in uno stato neutro e valido.
        return max(0.0, min(1.0, self.usato / self.totale))  # Limita difensivamente il valore all'intervallo supportato dalla progress bar.


def formatta_dimensione(numero_byte: int | None) -> str:
    """Converte un numero di byte in una rappresentazione binaria leggibile senza perdere il valore originale."""
    if numero_byte is None:  # Riconosce una misura non disponibile.
        return "Non disponibile"  # Evita di mostrare numeri inventati.
    if isinstance(numero_byte, bool) or not isinstance(numero_byte, int):  # Richiede un conteggio intero reale di byte.
        raise TypeError("La dimensione deve essere espressa come numero intero di byte.")  # Segnala un contratto di chiamata errato.
    if numero_byte < 0:  # Rifiuta valori impossibili per una capacità disco.
        raise ValueError("La dimensione in byte non può essere negativa.")  # Mantiene coerente la rappresentazione.

    unita = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")  # Usa multipli binari coerenti con il divisore 1024.
    valore = float(numero_byte)  # Usa un valore decimale soltanto per la formattazione finale.
    indice = 0  # Parte dall'unità base byte.
    while valore >= 1024.0 and indice < len(unita) - 1:  # Scala il valore finché esiste un'unità più adatta.
        valore /= 1024.0  # Converte nel multiplo binario successivo.
        indice += 1  # Avanza all'etichetta corrispondente.

    if indice == 0:  # Mantiene i byte come interi perché non richiedono decimali.
        return f"{numero_byte} B"  # Restituisce il conteggio esatto dei byte.
    return f"{valore:.1f} {unita[indice]}"  # Mostra una cifra decimale per una lettura rapida nella dashboard.


def rileva_unita_windows() -> list[InformazioniUnita]:
    """Enumera le lettere di unità visibili a Windows e legge lo spazio disponibile senza interrompersi su unità inaccessibili."""
    funzione_lista_unita = getattr(os, "listdrives", None)  # Recupera l'API introdotta in Python 3.12 senza assumere che esista su altre piattaforme.
    if funzione_lista_unita is None:  # Riconosce un interprete o sistema che non espone l'API Windows richiesta.
        raise OSError("Il rilevamento delle unità della Home è disponibile su Windows con Python 3.12 o successivo.")  # Fornisce un errore esplicito al livello chiamante.

    percorsi_unita = funzione_lista_unita()  # Chiede a Windows l'elenco delle lettere di unità attualmente note.
    informazioni = []  # Prepara il risultato mantenendo lo stesso ordine restituito dal sistema.

    for percorso_unita in percorsi_unita:  # Analizza ogni unità separatamente perché alcune possono essere non accessibili.
        try:  # Isola gli errori di una singola unità, inclusi supporti mancanti o unità di rete non raggiungibili.
            utilizzo = shutil.disk_usage(percorso_unita)  # Legge totale, usato e libero in byte attraverso la libreria standard.
            informazioni.append(InformazioniUnita(percorso_unita, utilizzo.total, utilizzo.used, utilizzo.free))  # Pubblica le statistiche reali lette dal sistema.
        except OSError as errore:  # Gestisce l'inaccessibilità documentata delle unità senza far fallire l'intera dashboard.
            informazioni.append(InformazioniUnita(percorso_unita, None, None, None, f"{type(errore).__name__}: {errore}"))  # Mantiene visibile l'unità indicando che i dati non sono disponibili.

    return informazioni  # Restituisce tutte le unità, comprese quelle temporaneamente non accessibili.
