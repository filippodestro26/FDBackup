import json  # Importa JSON per costruire anche casi corrotti o parziali durante i test.
import tempfile  # Importa directory temporanee isolate dal progetto reale.
import unittest  # Importa il framework standard usato dalla suite FDBackup.
from pathlib import Path  # Importa Path per gestire i file temporanei in modo portabile.

from fdbackup.persistenza_attivita_avanzata import LIMITE_RIGHE_PER_SEZIONE, carica_attivita_avanzate, salva_attivita_avanzate  # Importa esclusivamente l'API pubblica da verificare.


class TestPersistenzaAttivitaAvanzata(unittest.TestCase):
    """Verifica che i monitor avanzati sopravvivano ai riavvii e si cancellino soltanto esplicitamente."""

    def test_salvataggio_e_ricaricamento_mantengono_le_quattro_sezioni(self):
        """Strategie, Sincronizza, Ripristino versionato e Verifica integrità devono tornare identici dopo un nuovo caricamento."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola completamente il file persistente dal progetto reale.
            percorso = Path(temporanea) / "attivita_avanzate.json"  # Definisce un archivio dedicato al singolo test.
            registri = {"strategie": ["strategia"], "sincronizza": ["sync"], "ripristino_versionato": ["restore"], "verifica_integrita": ["integrita"]}  # Prepara un evento riconoscibile per ciascuna sezione.
            salva_attivita_avanzate(percorso, registri)  # Simula la persistenza prodotta dalla GUI durante l'uso.
            caricati = carica_attivita_avanzate(percorso)  # Simula un nuovo avvio dell'applicazione.
            self.assertEqual(caricati, registri)  # Richiede che nessuna sezione venga persa o mescolata.

    def test_cancellazione_di_una_sezione_non_cancella_le_altre(self):
        """Il pulsante Cancella attività deve agire soltanto sul monitor scelto."""
        with tempfile.TemporaryDirectory() as temporanea:  # Usa un archivio isolato.
            percorso = Path(temporanea) / "attivita_avanzate.json"  # Definisce il documento del test.
            registri = {"strategie": [], "sincronizza": ["sync"], "ripristino_versionato": ["restore"]}  # Simula Strategie cancellato e gli altri monitor ancora presenti.
            salva_attivita_avanzate(percorso, registri)  # Persiste lo stato dopo la cancellazione esplicita.
            caricati = carica_attivita_avanzate(percorso)  # Ricarica come farebbe un riavvio.
            self.assertEqual(caricati["strategie"], [])  # Richiede che Strategie resti vuoto.
            self.assertEqual(caricati["sincronizza"], ["sync"])  # Richiede che Sincronizza non venga coinvolto.
            self.assertEqual(caricati["ripristino_versionato"], ["restore"])  # Richiede che il ripristino versionato non venga coinvolto.

    def test_file_corrotto_non_impedisce_avvio(self):
        """Un archivio attività corrotto deve produrre registri vuoti invece di bloccare FDBackup."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il documento volutamente invalido.
            percorso = Path(temporanea) / "attivita_avanzate.json"  # Definisce il file da corrompere.
            percorso.write_text("{non-json", encoding="utf-8")  # Scrive intenzionalmente un contenuto non decodificabile.
            caricati = carica_attivita_avanzate(percorso)  # Tenta il caricamento con la stessa API usata dalla GUI.
            self.assertTrue(all(not righe for righe in caricati.values()))  # Richiede un recupero sicuro con tutte le sezioni vuote.

    def test_salvataggio_limita_ogni_sezione_alle_ultime_cinquecento_righe(self):
        """La persistenza deve rispettare il limite già adottato dalla GUI per evitare crescita illimitata."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il documento di grandi dimensioni.
            percorso = Path(temporanea) / "attivita_avanzate.json"  # Definisce il file persistente del test.
            molte_righe = [f"riga-{indice}" for indice in range(LIMITE_RIGHE_PER_SEZIONE + 25)]  # Genera più eventi del massimo consentito.
            salva_attivita_avanzate(percorso, {"strategie": molte_righe, "sincronizza": [], "ripristino_versionato": []})  # Salva un registro oltre soglia.
            caricati = carica_attivita_avanzate(percorso)  # Rilegge il documento normalizzato.
            self.assertEqual(len(caricati["strategie"]), LIMITE_RIGHE_PER_SEZIONE)  # Richiede esattamente il limite previsto.
            self.assertEqual(caricati["strategie"][0], "riga-25")  # Verifica che vengano mantenuti gli eventi più recenti e non i più vecchi.

    def test_file_precedente_senza_verifica_integrita_resta_compatibile(self):
        """Un archivio creato dalla 275/287 deve caricare la nuova sezione vuota senza perdere i registri esistenti."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il documento nel formato storico.
            percorso = Path(temporanea) / "attivita_avanzate.json"  # Definisce il file compatibile da leggere.
            percorso.write_text(json.dumps({"strategie": ["strategia"], "sincronizza": ["sync"], "ripristino_versionato": ["restore"]}), encoding="utf-8")  # Simula esattamente l'assenza della nuova chiave.
            caricati = carica_attivita_avanzate(percorso)  # Carica il formato precedente con la nuova implementazione.
            self.assertEqual(caricati["strategie"], ["strategia"])  # Conserva il registro Strategie.
            self.assertEqual(caricati["sincronizza"], ["sync"])  # Conserva il registro Sincronizza.
            self.assertEqual(caricati["ripristino_versionato"], ["restore"])  # Conserva il registro Ripristino.
            self.assertEqual(caricati["verifica_integrita"], [])  # Inizializza soltanto la nuova sezione con un valore neutro.


if __name__ == "__main__":  # Permette di eseguire direttamente il modulo durante una diagnosi isolata.
    unittest.main()  # Avvia i test quando il file viene eseguito come script.
