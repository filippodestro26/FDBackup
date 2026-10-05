import json  # Importa JSON per costruire file di stato corrotti nei test di persistenza.
import tempfile  # Importa directory temporanee isolate dal filesystem reale dell'utente.
import unittest  # Importa il framework standard già usato dalla suite FDBackup.
from datetime import datetime  # Importa datetime per rendere deterministici tutti i test temporali.
from pathlib import Path  # Importa Path per gestire i file temporanei.

from fdbackup.modelli_backup import PianificazioneBackup  # Importa il modello reale validato dal progetto.
from fdbackup.scheduler_backup import acquisisci_occorrenza, carica_stato_scheduler, occorrenza_da_eseguire, salva_stato_scheduler, trova_ultima_occorrenza  # Importa l'API pubblica dello scheduler.


class TestSchedulerBackup(unittest.TestCase):
    """Verifica il calcolo settimanale, il recupero dopo ritardo e la protezione anti-duplicazione."""

    def test_pianificazione_disabilitata_non_produce_occorrenza(self):
        pianificazione = PianificazioneBackup()  # Crea il default disabilitato del modello.
        self.assertIsNone(trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 12, 0)))  # Verifica che non venga inventato alcun trigger.

    def test_occorrenza_odierna_scattata(self):
        pianificazione = PianificazioneBackup(True, (3,), "10:30")  # Il 1 ottobre 2026 è giovedì, indice 3.
        occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 10, 31))  # Simula il controllo un minuto dopo l'orario.
        self.assertIsNotNone(occorrenza)  # Verifica che la scadenza sia stata riconosciuta.
        self.assertEqual(occorrenza.chiave, "2026-10-01T10:30")  # Verifica la chiave locale anti-duplicazione.

    def test_occorrenza_odierna_futura_ripiega_sul_giorno_precedente_configurato(self):
        pianificazione = PianificazioneBackup(True, (2, 3), "10:30")  # Pianifica mercoledì e giovedì.
        occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 9, 0))  # Simula giovedì prima dell'orario previsto.
        self.assertEqual(occorrenza.chiave, "2026-09-30T10:30")  # Recupera l'ultima scadenza maturata del mercoledì.

    def test_recupera_occorrenza_dopo_riavvio_nella_settimana(self):
        pianificazione = PianificazioneBackup(True, (0,), "08:00")  # Pianifica il lunedì mattina.
        occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 12, 0))  # Simula un avvio giovedì dopo alcuni giorni di inattività.
        self.assertEqual(occorrenza.chiave, "2026-09-28T08:00")  # Verifica la politica di catch-up dell'ultima occorrenza settimanale.

    def test_non_recupera_occorrenza_anteriore_all_attivazione(self):
        """Una regola creata oggi non deve trasformare in dovuta una scadenza appartenente a un giorno precedente."""
        pianificazione = PianificazioneBackup(True, (2, 3), "10:30", "2026-10-01T09:00:00")  # Attiva giovedì mattina una regola valida mercoledì e giovedì.
        occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 9, 15))  # Controlla prima dell’orario odierno.
        self.assertIsNone(occorrenza)  # Non recupera il mercoledì perché precede la creazione della regola.

    def test_esegue_prima_occorrenza_successiva_all_attivazione(self):
        """La stessa regola deve diventare eseguibile normalmente non appena matura una scadenza successiva alla sua attivazione."""
        pianificazione = PianificazioneBackup(True, (3,), "10:30", "2026-10-01T09:00:00")  # Attiva la regola prima della scadenza di giovedì.
        occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 10, 31))  # Controlla un minuto dopo la scadenza.
        self.assertEqual(occorrenza.chiave, "2026-10-01T10:30")  # Conferma che il limite non blocchi le occorrenze realmente successive.

    def test_modifica_dopo_orario_odierno_non_esegue_retroattivamente(self):
        """Una regola salvata dopo il proprio orario odierno deve attendere la prossima occorrenza invece di partire subito."""
        pianificazione = PianificazioneBackup(True, (3,), "10:30", "2026-10-01T14:31:45")  # Simula una modifica effettuata molte ore dopo la scadenza odierna.
        occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 14, 32))  # Esegue il controllo immediatamente dopo il salvataggio.
        self.assertIsNone(occorrenza)  # Impedisce il falso catch-up che ha originato il comportamento osservato.

    def test_catch_up_resta_attivo_per_regola_gia_esistente(self):
        """Il recupero dopo inattività deve restare disponibile quando la scadenza persa è successiva alla creazione della regola."""
        pianificazione = PianificazioneBackup(True, (0,), "08:00", "2026-09-20T12:00:00")  # Crea la regola prima del lunedì che verrà perso.
        occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 12, 0))  # Simula il riavvio del giovedì successivo.
        self.assertEqual(occorrenza.chiave, "2026-09-28T08:00")  # Mantiene il recupero dell’ultima vera occorrenza persa.

    def test_stessa_occorrenza_non_viene_restituita_due_volte(self):
        pianificazione = PianificazioneBackup(True, (3,), "10:30")  # Configura una scadenza giovedì.
        stato = {"sorgente": "2026-10-01T10:30"}  # Simula un'occorrenza già acquisita.
        self.assertIsNone(occorrenza_da_eseguire("sorgente", pianificazione, stato, datetime(2026, 10, 1, 18, 0)))  # Impedisce il duplicato nello stesso giorno.

    def test_nuova_settimana_produce_nuova_occorrenza(self):
        pianificazione = PianificazioneBackup(True, (3,), "10:30")  # Configura una scadenza settimanale giovedì.
        stato = {"sorgente": "2026-10-01T10:30"}  # Conserva l'esecuzione della settimana precedente.
        occorrenza = occorrenza_da_eseguire("sorgente", pianificazione, stato, datetime(2026, 10, 8, 10, 31))  # Simula il giovedì successivo.
        self.assertEqual(occorrenza.chiave, "2026-10-08T10:30")  # Verifica che la nuova settimana sia indipendente.

    def test_stato_assente_restituisce_dizionario_vuoto(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola il test in una directory temporanea.
            percorso = Path(cartella) / "stato.json"  # Costruisce un file che non esiste.
            self.assertEqual(carica_stato_scheduler(percorso), {})  # Verifica il comportamento del primo avvio.

    def test_salvataggio_e_caricamento_stato(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola la persistenza dal progetto reale.
            percorso = Path(cartella) / "stato.json"  # Costruisce il percorso temporaneo.
            stato = {"a": "2026-10-01T10:30"}  # Prepara uno stato valido.
            salva_stato_scheduler(percorso, stato)  # Salva tramite la routine atomica reale.
            self.assertEqual(carica_stato_scheduler(percorso), stato)  # Verifica il round trip senza perdita di dati.

    def test_stato_corrotto_solleva_value_error(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola il file corrotto.
            percorso = Path(cartella) / "stato.json"  # Costruisce il percorso temporaneo.
            percorso.write_text("{non-json", encoding="utf-8")  # Scrive intenzionalmente JSON non valido.
            with self.assertRaises(ValueError):  # Richiede che la corruzione non venga nascosta.
                carica_stato_scheduler(percorso)  # Tenta il caricamento del file corrotto.

    def test_acquisizione_persiste_prima_di_restituire(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola il file di stato.
            percorso = Path(cartella) / "stato.json"  # Costruisce il percorso temporaneo.
            pianificazione = PianificazioneBackup(True, (3,), "10:30")  # Prepara una scadenza valida.
            occorrenza = trova_ultima_occorrenza(pianificazione, datetime(2026, 10, 1, 10, 31))  # Calcola l'occorrenza da acquisire.
            nuovo_stato = acquisisci_occorrenza(percorso, {}, "id", occorrenza)  # Marca la scadenza come acquisita.
            self.assertEqual(nuovo_stato["id"], "2026-10-01T10:30")  # Verifica lo stato restituito.
            self.assertEqual(carica_stato_scheduler(percorso)["id"], "2026-10-01T10:30")  # Verifica che la protezione sia realmente su disco.


if __name__ == "__main__":  # Permette anche l'esecuzione diretta del singolo file di test.
    unittest.main()  # Avvia unittest quando il file viene eseguito come script.
