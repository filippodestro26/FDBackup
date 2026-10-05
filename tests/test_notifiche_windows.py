import unittest  # Importa il framework standard già utilizzato dal progetto.
from unittest.mock import patch  # Importa patch per verificare il comportamento fuori da Windows senza dipendenze reali.

from fdbackup.cronologia_backup import RecordOperazione  # Importa il modello reale usato dalle notifiche.
from fdbackup.notifiche_windows import crea_testo_notifica, mostra_notifica_windows  # Importa l'API pubblica da verificare.


class TestNotificheWindows(unittest.TestCase):
    """Verifica che le notifiche siano informative e non possano compromettere il backup."""

    def _record(self, stato="successo", problemi=()):
        """Crea un record deterministico valido per i test del testo e del fallback."""
        return RecordOperazione("2026-10-01T12:21:28+02:00", "backup_singolo", stato, "Backup singolo automatico", 2, 3, 0, 100, problemi)  # Usa valori noti per rendere le asserzioni esplicite.

    def test_testo_notifica_contiene_esito_e_contatori(self):
        """La notifica deve comunicare stato e contatori essenziali dell'operazione conclusa."""
        titolo, corpo = crea_testo_notifica(self._record())  # Costruisce il testo senza dipendere da Windows.
        self.assertIn("completato", titolo)  # Verifica che lo stato sia leggibile nel titolo.
        self.assertIn("Copiati: 2", corpo)  # Verifica il contatore dei file copiati.
        self.assertIn("Identici: 3", corpo)  # Verifica il contatore dei file già identici.
        self.assertIn("Falliti: 0", corpo)  # Verifica il contatore dei fallimenti.

    def test_testo_notifica_include_primo_problema(self):
        """Un esito problematico deve mostrare almeno il primo dettaglio diagnostico."""
        _titolo, corpo = crea_testo_notifica(self._record("problemi", ("File bloccato", "Secondo problema")))  # Simula un record con più problemi.
        self.assertIn("File bloccato", corpo)  # Verifica che il banner contenga il primo problema utile.
        self.assertNotIn("Secondo problema", corpo)  # Evita notifiche eccessivamente lunghe.

    def test_piattaforma_non_windows_non_genera_errori(self):
        """Fuori da Windows la funzione deve degradare silenziosamente senza importare librerie native."""
        with patch("fdbackup.notifiche_windows.os.name", "posix"):  # Simula una piattaforma non Windows.
            self.assertFalse(mostra_notifica_windows(self._record()))  # Verifica il fallback non distruttivo.

    def test_tipo_non_valido_viene_rifiutato(self):
        """La formattazione deve accettare soltanto record già validati dalla cronologia."""
        with self.assertRaises(TypeError):  # Verifica il contratto pubblico esplicito.
            crea_testo_notifica({"stato": "successo"})  # Passa intenzionalmente una struttura non validata.


if __name__ == "__main__":  # Consente l'esecuzione isolata del file durante lo sviluppo.
    unittest.main()  # Avvia i test quando il modulo viene eseguito direttamente.
