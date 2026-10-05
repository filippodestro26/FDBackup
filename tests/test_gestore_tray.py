import queue  # Importa Queue per verificare lo stesso canale thread-safe usato dalla GUI.
import unittest  # Importa il framework standard del progetto.

from fdbackup.gestore_tray import COMANDO_APRI, COMANDO_CHIUDI, GestoreTray, crea_immagine_tray  # Importa le parti testabili senza avviare realmente pystray.


class TestGestoreTray(unittest.TestCase):
    """Verifica che i callback della tray comunichino con Tk soltanto attraverso la coda."""

    def test_immagine_tray_valida(self) -> None:
        """L'icona generata deve avere dimensioni e modalità compatibili con pystray."""
        immagine = crea_immagine_tray()  # Genera l'immagine senza dipendere dal desktop del sistema di test.
        self.assertEqual(immagine.size, (64, 64))  # Verifica una dimensione sufficiente al ridimensionamento Windows.
        self.assertEqual(immagine.mode, "RGBA")  # Verifica il supporto della trasparenza previsto dall'icona.

    def test_callback_apri_accoda_comando(self) -> None:
        """L'apertura non deve richiamare direttamente alcun widget Tk dal thread dell'icona."""
        coda = queue.Queue()  # Crea una coda isolata equivalente a quella posseduta dalla GUI.
        gestore = GestoreTray(coda)  # Costruisce il gestore senza avviare il loop nativo.
        gestore._richiedi_apertura()  # Simula l'attivazione dell'azione primaria dell'icona.
        self.assertEqual(coda.get_nowait(), COMANDO_APRI)  # Verifica il solo effetto previsto del callback.

    def test_callback_chiudi_accoda_comando(self) -> None:
        """L'uscita definitiva deve essere delegata al thread Tk tramite lo stesso canale controllato."""
        coda = queue.Queue()  # Crea una coda isolata per il test.
        gestore = GestoreTray(coda)  # Costruisce il gestore senza dipendere da pystray installato.
        gestore._richiedi_chiusura()  # Simula la voce Chiudi FDBackup.
        self.assertEqual(coda.get_nowait(), COMANDO_CHIUDI)  # Verifica che venga accodato il comando corretto.


if __name__ == "__main__":  # Consente l'esecuzione diretta del file durante lo sviluppo.
    unittest.main()  # Avvia unittest quando richiesto come script.
