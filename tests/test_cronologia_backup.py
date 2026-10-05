import tempfile  # Importa TemporaryDirectory per isolare i test dal filesystem reale.
import unittest  # Importa il framework standard del progetto.
from pathlib import Path  # Importa Path per costruire il file temporaneo.

from fdbackup.cronologia_backup import NUMERO_MASSIMO_RECORD, RecordOperazione, aggiungi_record, cancella_cronologia, carica_cronologia, salva_cronologia  # Importa l'API pubblica da verificare.


class TestCronologiaBackup(unittest.TestCase):
    """Verifica persistenza, validazione e limite della cronologia operativa."""

    def crea_record(self, indice: int = 1) -> RecordOperazione:
        """Crea un record deterministico valido per i test."""
        return RecordOperazione(f"2026-10-01T10:00:{indice % 60:02d}+02:00", "backup_singolo", "successo", f"Backup {indice}", indice, 0, 0, indice * 10, ())  # Restituisce un record controllato.

    def test_file_inesistente_restituisce_lista_vuota(self) -> None:
        """Il primo avvio non deve essere trattato come errore."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea un ambiente isolato.
            self.assertEqual(carica_cronologia(Path(temporanea) / "cronologia.json"), [])  # Verifica il risultato neutro.

    def test_round_trip_conserva_i_dati(self) -> None:
        """Un record salvato deve essere ricostruito senza perdita di informazioni."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea un ambiente isolato.
            percorso = Path(temporanea) / "cronologia.json"  # Definisce il file di prova.
            originale = self.crea_record()  # Crea il record atteso.
            salva_cronologia(percorso, [originale])  # Salva il record reale.
            self.assertEqual(carica_cronologia(percorso), [originale])  # Verifica il round-trip completo.

    def test_aggiunta_preserva_ordine(self) -> None:
        """I record devono rimanere dal meno recente al più recente."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea un ambiente isolato.
            percorso = Path(temporanea) / "cronologia.json"  # Definisce il file di prova.
            aggiungi_record(percorso, self.crea_record(1))  # Aggiunge il primo record.
            aggiungi_record(percorso, self.crea_record(2))  # Aggiunge il secondo record.
            self.assertEqual([record.descrizione for record in carica_cronologia(percorso)], ["Backup 1", "Backup 2"])  # Verifica l'ordine.

    def test_limite_conserva_i_record_piu_recenti(self) -> None:
        """La cronologia non deve crescere senza limite."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea un ambiente isolato.
            percorso = Path(temporanea) / "cronologia.json"  # Definisce il file di prova.
            record = [self.crea_record(indice) for indice in range(NUMERO_MASSIMO_RECORD + 5)]  # Supera intenzionalmente il limite.
            salva_cronologia(percorso, record)  # Salva la lista sovradimensionata.
            caricati = carica_cronologia(percorso)  # Rilegge la cronologia effettiva.
            self.assertEqual(len(caricati), NUMERO_MASSIMO_RECORD)  # Verifica il limite.
            self.assertEqual(caricati[0].descrizione, "Backup 5")  # Verifica che siano rimasti i record più recenti.

    def test_json_corrotto_viene_segnalato(self) -> None:
        """La corruzione non deve essere trasformata silenziosamente in cronologia vuota."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea un ambiente isolato.
            percorso = Path(temporanea) / "cronologia.json"  # Definisce il file di prova.
            percorso.write_text("{non-json", encoding="utf-8")  # Scrive dati volutamente invalidi.
            with self.assertRaises(ValueError):  # Richiede un errore controllato.
                carica_cronologia(percorso)  # Tenta il caricamento del file corrotto.

    def test_record_rifiuta_stato_non_valido(self) -> None:
        """Uno stato sconosciuto non deve entrare nella persistenza."""
        with self.assertRaises(ValueError):  # Verifica la validazione del modello.
            RecordOperazione("2026-10-01T10:00:00+02:00", "backup_singolo", "forse", "Backup")  # Usa uno stato non previsto.

    def test_cronologia_accetta_tutti_i_tipi_avanzati_usati_dalla_gui(self) -> None:
        """I tipi prodotti dall'integrazione avanzata devono poter essere registrati senza eccezioni a fine worker."""
        for tipo in ("backup_versionato", "sincronizzazione", "ripristino_versionato", "operazione_avanzata"):  # Copre ogni valore realmente emesso dalla GUI avanzata.
            record = RecordOperazione("2026-10-01T10:00:00+02:00", tipo, "successo", "Operazione avanzata")  # Costruisce il record con il contratto persistente reale.
            self.assertEqual(record.tipo, tipo)  # Conferma che la validazione non interrompa la finalizzazione della GUI.

    def test_cancellazione_elimina_solo_file_cronologia(self) -> None:
        """La cancellazione deve rimuovere cronologia.json senza toccare file tecnici affiancati."""
        with tempfile.TemporaryDirectory() as temporanea:  # Crea una radice isolata equivalente alla cartella applicativa.
            radice = Path(temporanea)  # Converte la directory temporanea in Path.
            percorso_cronologia = radice / "cronologia.json"  # Definisce il solo file che la funzione può eliminare.
            percorso_stato = radice / "stato_scheduler.json"  # Crea un file tecnico che deve rimanere intatto.
            salva_cronologia(percorso_cronologia, [self.crea_record(1)])  # Crea una cronologia reale tramite l'API pubblica.
            percorso_stato.write_text("{}", encoding="utf-8")  # Simula lo stato tecnico dello scheduler.
            cancella_cronologia(percorso_cronologia)  # Esegue la cancellazione richiesta dall'utente.
            self.assertFalse(percorso_cronologia.exists())  # Verifica che la cronologia sia stata realmente rimossa.
            self.assertTrue(percorso_stato.exists())  # Verifica che lo stato scheduler non sia stato toccato.


if __name__ == "__main__":  # Consente anche l'esecuzione diretta del file.
    unittest.main()  # Avvia unittest quando il file viene eseguito direttamente.
