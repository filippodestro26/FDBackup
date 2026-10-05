import logging  # Importa il logging standard per registrare eventuali problemi dell'icona nell'area di notifica.
import threading  # Importa Thread per eseguire il loop nativo dell'icona senza bloccare il mainloop Tk.
from queue import Queue  # Importa Queue per trasferire i comandi dell'icona al thread principale della GUI.

from PIL import Image, ImageDraw  # Importa Pillow per costruire in memoria un'icona indipendente da file grafici esterni.


logger = logging.getLogger(__name__)  # Crea un logger figlio coerente con il resto di FDBackup.
COMANDO_APRI = "apri"  # Definisce il comando inviato alla GUI quando l'utente richiede di riaprire FDBackup.
COMANDO_CHIUDI = "chiudi"  # Definisce il comando inviato alla GUI quando l'utente richiede l'uscita definitiva.


def crea_immagine_tray() -> Image.Image:
    """Crea un'icona semplice e leggibile per l'area di notifica senza dipendere da risorse esterne."""
    immagine = Image.new("RGBA", (64, 64), (0, 0, 0, 0))  # Crea una tela trasparente adatta anche al ridimensionamento di Windows.
    disegno = ImageDraw.Draw(immagine)  # Prepara il contesto grafico usato per disegnare il simbolo.
    disegno.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(20, 105, 190, 255))  # Disegna una base blu riconoscibile e compatta.
    disegno.rectangle((19, 18, 45, 25), fill=(255, 255, 255, 255))  # Disegna la parte superiore della lettera stilizzata B.
    disegno.rectangle((19, 25, 26, 46), fill=(255, 255, 255, 255))  # Disegna l'asta verticale della lettera stilizzata B.
    disegno.rounded_rectangle((24, 25, 45, 35), radius=5, outline=(255, 255, 255, 255), width=6)  # Disegna il primo occhiello della B.
    disegno.rounded_rectangle((24, 35, 45, 46), radius=5, outline=(255, 255, 255, 255), width=6)  # Disegna il secondo occhiello della B.
    return immagine  # Restituisce un oggetto Pillow direttamente accettato da pystray.


class GestoreTray:
    """Gestisce una sola icona Windows e comunica con Tk esclusivamente tramite una coda thread-safe."""

    def __init__(self, coda_comandi: Queue) -> None:
        """Memorizza la coda della GUI senza avviare thread o importare pystray in anticipo."""
        self.coda_comandi = coda_comandi  # Conserva il canale thread-safe verso il mainloop Tk.
        self.icona = None  # Conserva l'istanza pystray soltanto dopo un avvio riuscito.
        self.thread_icona = None  # Conserva il thread nativo dell'icona per poterlo attendere durante l'uscita.

    def _richiedi_apertura(self, _icona=None, _voce=None) -> None:
        """Accoda una richiesta di apertura senza chiamare direttamente alcun metodo Tk dal thread dell'icona."""
        self.coda_comandi.put(COMANDO_APRI)  # Trasferisce l'azione al polling eseguito dal thread principale della GUI.

    def _richiedi_chiusura(self, _icona=None, _voce=None) -> None:
        """Accoda una richiesta di uscita definitiva senza distruggere widget dal thread dell'icona."""
        self.coda_comandi.put(COMANDO_CHIUDI)  # Trasferisce l'azione al thread Tk che possiede la finestra.

    def avvia(self) -> bool:
        """Avvia una sola icona nell'area di notifica e restituisce False se pystray non è disponibile."""
        if self.icona is not None:  # Riconosce un secondo tentativo di avvio della stessa istanza.
            return True  # Evita di creare icone duplicate.
        try:  # Importa la dipendenza opzionale soltanto quando la GUI richiede realmente l'icona.
            import pystray  # Importa pystray localmente così i test dei moduli non grafici restano indipendenti dalla libreria.
        except ImportError:  # Riconosce un ambiente nel quale la dipendenza non è ancora installata.
            logger.error("pystray non è installato: icona nell'area di notifica non disponibile.")  # Registra una diagnosi esplicita nel log persistente.
            return False  # Comunica alla GUI che non deve nascondersi senza un punto di riapertura.
        menu = pystray.Menu(  # Costruisce il menu contestuale mostrato con il pulsante destro su Windows.
            pystray.MenuItem("Apri FDBackup", self._richiedi_apertura, default=True),  # Imposta l'apertura come azione primaria supportata da pystray.
            pystray.MenuItem("Chiudi FDBackup", self._richiedi_chiusura),  # Offre un comando distinto per terminare realmente l'applicazione.
        )  # Chiude la definizione immutabile del menu.
        self.icona = pystray.Icon("FDBackup", crea_immagine_tray(), "FDBackup", menu)  # Crea una sola icona con nome e tooltip riconoscibili.
        self.thread_icona = threading.Thread(target=self.icona.run, name="FDBackupTray", daemon=True)  # Esegue il loop pystray in un thread dedicato, modalità supportata dal backend Windows.
        self.thread_icona.start()  # Avvia l'elaborazione degli eventi dell'icona senza bloccare Tk.
        return True  # Conferma che l'icona è stata predisposta correttamente.

    def arresta(self) -> None:
        """Arresta l'icona in modo idempotente e attende brevemente la conclusione del relativo thread."""
        icona = self.icona  # Copia il riferimento per rendere esplicito lo stato che verrà arrestato.
        thread_icona = self.thread_icona  # Copia il riferimento al thread prima di azzerare lo stato dell'istanza.
        self.icona = None  # Impedisce che ulteriori chiamate considerino ancora attiva l'icona in arresto.
        self.thread_icona = None  # Rimuove il riferimento al thread dalla nuova condizione inattiva.
        if icona is not None:  # Verifica che l'icona sia stata realmente creata.
            icona.stop()  # Chiede a pystray di rimuovere l'icona e terminare il proprio loop.
        if thread_icona is not None and thread_icona.is_alive() and thread_icona is not threading.current_thread():  # Evita join inutili o sul thread corrente.
            thread_icona.join(timeout=2.0)  # Attende un tempo limitato senza rischiare di bloccare indefinitamente la chiusura della GUI.
