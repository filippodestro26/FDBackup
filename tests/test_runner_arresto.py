import tempfile  # Importa TemporaryDirectory per isolare lock e segnale di arresto dal progetto reale.
import threading  # Importa Thread per verificare il sorvegliante del segnale di arresto.
import unittest  # Importa il framework standard della suite FDBackup.
from pathlib import Path  # Importa Path per costruire la radice temporanea del runner.
from unittest.mock import patch  # Importa patch per isolare il logging e verificare le chiamate del runner.

from fdbackup.runner_scheduler import RunnerScheduler  # Importa il runner reale da verificare.


class TestRunnerArresto(unittest.TestCase):
    """Verifica il canale interprocesso usato esclusivamente dall'uscita definitiva della GUI."""

    def test_segnale_stop_termina_runner_senza_controllo(self) -> None:
        """Un segnale già presente deve fermare il runner prima di acquisire nuove occorrenze."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea una cartella applicativa completamente isolata.
            radice = Path(temporanea)  # Converte la radice temporanea in Path.

            with patch("fdbackup.runner_scheduler.configura_logging"):  # Impedisce al test di aprire fdbackup.log nella cartella temporanea.
                runner = RunnerScheduler(radice)  # Costruisce il runner reale mantenendo invariati lock, evento e file di stop.

            runner.file_richiesta_arresto.write_text(
                "stop\n",
                encoding="utf-8",
            )  # Simula il comando Chiudi FDBackup inviato dalla GUI.

            with patch.object(runner, "esegui_controllo") as controllo:  # Sorveglia il calcolo delle pianificazioni senza eseguirlo.
                self.assertEqual(
                    runner.esegui(),
                    0,
                )  # Verifica una conclusione ordinata con codice di successo.

            controllo.assert_not_called()  # Conferma che non venga acquisita nuova attività dopo la richiesta di arresto.

            self.assertFalse(
                runner.file_richiesta_arresto.exists()
            )  # Verifica che il segnale venga consumato per consentire futuri avvii.

    def test_sorvegliante_propaga_stop_durante_lavoro(self) -> None:
        """Il file di stop deve impostare l'evento anche mentre il ciclo principale è occupato in un controllo."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola completamente il segnale dal progetto reale.
            radice = Path(temporanea)  # Converte la cartella temporanea in Path.

            with patch("fdbackup.runner_scheduler.configura_logging"):  # Evita un effetto collaterale non pertinente allo scopo del test.
                runner = RunnerScheduler(radice)  # Crea il runner reale senza aprire il file di log temporaneo.

            sorvegliante = threading.Thread(
                target=runner._sorveglia_richiesta_arresto_esterna,
                name="TestFDBackupSchedulerStop",
            )  # Prepara un thread dedicato esclusivamente alla sorveglianza del file di stop.

            sorvegliante.start()  # Avvia il sorvegliante in parallelo al thread del test.

            runner.file_richiesta_arresto.write_text(
                "stop\n",
                encoding="utf-8",
            )  # Simula l'uscita definitiva mentre il runner sarebbe occupato.

            sorvegliante.join(
                timeout=2.0
            )  # Attende un tempo superiore all'intervallo di polling di 0,5 secondi.

            self.assertTrue(
                runner.evento_arresto.is_set()
            )  # Verifica che il file di stop sia stato trasformato nella richiesta cooperativa di arresto.

            self.assertFalse(
                sorvegliante.is_alive()
            )  # Verifica che il sorvegliante termini dopo aver propagato correttamente la richiesta.


if __name__ == "__main__":  # Consente l'esecuzione diretta del file durante lo sviluppo.
    unittest.main()  # Avvia unittest quando il file viene eseguito come script.