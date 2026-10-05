import logging  # Importa il logging per chiudere gli handler creati dal runner durante i test temporanei.
import shutil  # Importa la rimozione ricorsiva usata dopo avere chiuso i file di log su Windows.
import tempfile  # Importa directory temporanee per eseguire integrazioni reali senza toccare i dati dell'utente.
import unittest  # Importa il framework standard già adottato dal progetto.
from datetime import datetime  # Importa l'ora locale usata per creare una scadenza immediatamente maturata.
from pathlib import Path  # Importa Path per costruire sorgenti, destinazioni e config temporanei.

from fdbackup.configurazione import salva_configurazione  # Importa la persistenza reale del config.json.
from fdbackup.modelli_backup import JobBackup, PianificazioneBackup, SorgenteBackup  # Importa i modelli reali di job e pianificazione.
from fdbackup.persistenza_job import salva_job_nella_configurazione, serializza_pianificazione_backup  # Importa la serializzazione usata dalla GUI.
from fdbackup.runner_scheduler import RunnerScheduler  # Importa il runner automatico da verificare end-to-end.


class TestRunnerScheduler(unittest.TestCase):
    """Verifica che il runner copi davvero i dati dovuti e non ripeta la stessa occorrenza."""

    @staticmethod
    def _chiudi_handler_fdbackup():
        """Chiude gli handler FDBackup prima della cancellazione delle directory temporanee su Windows."""
        logger_fdbackup = logging.getLogger("fdbackup")  # Recupera il logger applicativo condiviso configurato dal runner.
        for handler in list(logger_fdbackup.handlers):  # Lavora su una copia perché la raccolta viene modificata durante il ciclo.
            if getattr(handler, "_fdbackup_handler", False):  # Tocca soltanto l'handler persistente appartenente a FDBackup.
                logger_fdbackup.removeHandler(handler)  # Scollega l'handler prima di chiuderne il file sottostante.
                handler.close()  # Chiude il descrittore del log prima che Windows debba cancellare la directory.

    def _crea_cartella_temporanea(self) -> Path:
        """Crea una directory temporanea e registra cleanup nell'ordine corretto per Windows."""
        cartella = Path(tempfile.mkdtemp())  # Crea una directory reale senza affidare subito la cancellazione a un context manager.
        self.addCleanup(shutil.rmtree, cartella, True)  # Registra per prima la cancellazione: essendo LIFO verrà eseguita per ultima.
        self.addCleanup(self._chiudi_handler_fdbackup)  # Registra dopo la chiusura log: verrà eseguita prima della cancellazione.
        return cartella  # Restituisce la radice isolata al test.

    @staticmethod
    def _pianificazione_adesso() -> PianificazioneBackup:
        """Crea una pianificazione valida per il minuto locale corrente così il controllo è immediatamente dovuto."""
        adesso = datetime.now().astimezone()  # Legge l'ora locale con fuso dal sistema di test.
        return PianificazioneBackup(True, (adesso.weekday(),), adesso.strftime("%H:%M"))  # Pianifica il giorno e minuto correnti.

    def test_backup_singolo_automatico_viene_eseguito_una_sola_volta(self):
        radice = self._crea_cartella_temporanea()  # Crea un ambiente isolato con cleanup compatibile con Windows.
        sorgente = radice / "sorgente"  # Crea la sorgente del backup singolo.
        destinazione = radice / "destinazione"  # Prepara la destinazione ancora assente.
        sorgente.mkdir()  # Crea fisicamente la sorgente.
        (sorgente / "dato.txt").write_text("backup automatico", encoding="utf-8")  # Inserisce un file reale da copiare.
        pianificazione = self._pianificazione_adesso()  # Crea una scadenza maturata nel minuto corrente.
        configurazione = {"backup_singolo": {"sorgente": str(sorgente), "destinazione": str(destinazione), "pianificazione": serializza_pianificazione_backup(pianificazione)}}  # Usa lo stesso formato JSON della GUI.
        salva_configurazione(radice / "config.json", configurazione)  # Persiste il documento tramite la routine atomica reale.
        runner = RunnerScheduler(radice)  # Costruisce il runner sulla radice temporanea.
        self.assertTrue(runner.esegui_controllo())  # Verifica che la prima occorrenza venga acquisita ed eseguita.
        self.assertEqual((destinazione / "dato.txt").read_text(encoding="utf-8"), "backup automatico")  # Verifica il contenuto realmente copiato dal motore.
        self.assertFalse(runner.esegui_controllo())  # Verifica che lo stesso minuto pianificato non venga eseguito due volte.

    def test_sorgente_multi_job_automatica_viene_eseguita(self):
        radice = self._crea_cartella_temporanea()  # Crea un ambiente isolato con cleanup compatibile con Windows.
        sorgente = radice / "sorgente_job"  # Prepara la sorgente del job.
        destinazione = radice / "backup_job"  # Prepara la radice di destinazione del job.
        sorgente.mkdir()  # Crea fisicamente la sorgente.
        (sorgente / "job.txt").write_text("multi job automatico", encoding="utf-8")  # Inserisce un file reale da elaborare.
        pianificazione = self._pianificazione_adesso()  # Pianifica la sorgente per il minuto corrente.
        modello_sorgente = SorgenteBackup(sorgente, "sorgente_job", pianificazione=pianificazione)  # Costruisce la sorgente persistente reale.
        job = JobBackup("Job automatico", destinazione, [modello_sorgente])  # Costruisce il job con le opzioni predefinite verificate.
        configurazione = salva_job_nella_configurazione({}, [job])  # Serializza il job nello stesso formato della GUI.
        salva_configurazione(radice / "config.json", configurazione)  # Persiste il config reale.
        runner = RunnerScheduler(radice)  # Costruisce il runner sulla radice temporanea.
        self.assertTrue(runner.esegui_controllo())  # Esegue il controllo dovuto.
        file_copiato = destinazione / "sorgente_job" / "job.txt"  # Calcola la destinazione effettiva secondo il contratto del coordinatore.
        self.assertEqual(file_copiato.read_text(encoding="utf-8"), "multi job automatico")  # Verifica che il coordinatore abbia copiato il contenuto reale.
        self.assertFalse(runner.esegui_controllo())  # Verifica la protezione anti-duplicazione anche per le sorgenti dei job.


if __name__ == "__main__":  # Permette l'esecuzione diretta del file di integrazione.
    unittest.main()  # Avvia unittest quando richiesto come script.
