import tempfile  # Importa gli strumenti per creare cartelle temporanee isolate durante i test.
import unittest  # Importa il framework di test automatici incluso nella libreria standard di Python.
from pathlib import Path  # Importa Path per gestire i percorsi dei file di configurazione.
from unittest.mock import patch  # Importa patch per simulare in modo controllato errori e chiamate di sistema.

from fdbackup.configurazione import carica_configurazione, salva_configurazione  # Importa le funzioni reali da sottoporre ai test.


class TestConfigurazione(unittest.TestCase):
    """Contiene i test automatici dedicati alla gestione della configurazione di FDBackup."""

    def test_file_inesistente_restituisce_dizionario_vuoto(self) -> None:
        """Verifica che un file di configurazione inesistente produca una configurazione vuota."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea una cartella temporanea eliminata automaticamente al termine del test.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in un oggetto Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce un file di configurazione che non viene creato.

            self.assertFalse(percorso_configurazione.exists())  # Verifica che il file sia realmente inesistente prima del test.

            configurazione = carica_configurazione(percorso_configurazione)  # Tenta di caricare la configurazione inesistente.

            self.assertEqual(configurazione, {})  # Verifica che venga restituito un dizionario vuoto.
            self.assertFalse(percorso_configurazione.exists())  # Verifica che la lettura non abbia creato accidentalmente il file.

    def test_carica_json_utf8_valido(self) -> None:
        """Verifica che un oggetto JSON UTF-8 valido venga caricato correttamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in un oggetto Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file di configurazione usato dal test.

            percorso_configurazione.write_text(  # Scrive manualmente una configurazione JSON valida.
                '{"banner": "prova.png"}',
                encoding="utf-8",
            )

            configurazione = carica_configurazione(percorso_configurazione)  # Carica il documento attraverso il modulo reale.

            self.assertEqual(  # Verifica che il documento sia stato convertito nel dizionario atteso.
                configurazione,
                {"banner": "prova.png"},
            )

    def test_carica_json_utf8_con_bom(self) -> None:
        """Verifica che un documento JSON UTF-8 con BOM venga letto correttamente."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in un oggetto Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file utilizzato dal test.

            percorso_configurazione.write_text(  # Scrive il JSON aggiungendo intenzionalmente il BOM UTF-8.
                '{"banner": "prova_bom.png"}',
                encoding="utf-8-sig",
            )

            configurazione = carica_configurazione(percorso_configurazione)  # Legge il file attraverso la funzione reale.

            self.assertEqual(  # Verifica che il BOM non alteri il contenuto caricato.
                configurazione,
                {"banner": "prova_bom.png"},
            )

    def test_json_non_valido_restituisce_dizionario_vuoto(self) -> None:
        """Verifica che un documento JSON sintatticamente errato venga gestito senza propagare l'errore."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in un oggetto Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file utilizzato dal test.

            percorso_configurazione.write_text(  # Scrive intenzionalmente un documento JSON non valido.
                "{json non valido",
                encoding="utf-8",
            )

            configurazione = carica_configurazione(percorso_configurazione)  # Tenta di leggere il documento corrotto.

            self.assertEqual(configurazione, {})  # Verifica che l'errore venga trasformato in una configurazione vuota.

    def test_codifica_utf8_non_valida_restituisce_dizionario_vuoto(self) -> None:
        """Verifica che byte non decodificabili come UTF-8 vengano gestiti senza interrompere il programma."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in un oggetto Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file utilizzato dal test.

            percorso_configurazione.write_bytes(b"\xff\xfe\xfa")  # Scrive intenzionalmente una sequenza non valida come documento UTF-8.

            configurazione = carica_configurazione(percorso_configurazione)  # Tenta di leggere il file con codifica non valida.

            self.assertEqual(configurazione, {})  # Verifica che venga restituita una configurazione vuota.

    def test_json_non_dizionario_restituisce_dizionario_vuoto(self) -> None:
        """Verifica che un JSON valido ma diverso da un oggetto venga rifiutato."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in un oggetto Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file utilizzato dal test.

            percorso_configurazione.write_text(  # Scrive una lista JSON valida ma non adatta alla configurazione.
                '["uno", "due"]',
                encoding="utf-8",
            )

            configurazione = carica_configurazione(percorso_configurazione)  # Carica il documento attraverso la funzione reale.

            self.assertEqual(configurazione, {})  # Verifica che una struttura diversa da un dizionario venga rifiutata.

    def test_salvataggio_e_rilettura_utf8(self) -> None:
        """Verifica che una configurazione possa essere salvata e riletta senza perdere caratteri Unicode."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un ambiente temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte il percorso temporaneo in un oggetto Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file che verrà creato durante il test.
            configurazione_originale = {"banner": "immagine_è_prova.png"}  # Definisce dati contenenti un carattere Unicode significativo.

            salva_configurazione(percorso_configurazione, configurazione_originale)  # Salva la configurazione utilizzando la funzione reale.

            self.assertTrue(percorso_configurazione.is_file())  # Verifica che il file sia stato effettivamente creato.

            contenuto_binario = percorso_configurazione.read_bytes()  # Legge i byte reali scritti sul disco.

            self.assertFalse(  # Verifica che la funzione di salvataggio non abbia aggiunto un BOM UTF-8.
                contenuto_binario.startswith(b"\xef\xbb\xbf"),
            )

            contenuto_testuale = percorso_configurazione.read_text(encoding="utf-8")  # Decodifica esplicitamente il file come UTF-8.

            self.assertIn(  # Verifica che il carattere Unicode sia stato conservato correttamente nel documento.
                "immagine_è_prova.png",
                contenuto_testuale,
            )

            configurazione_riletta = carica_configurazione(percorso_configurazione)  # Rilegge il file attraverso la funzione reale.

            self.assertEqual(  # Verifica il round-trip completo salvataggio e successivo caricamento.
                configurazione_riletta,
                configurazione_originale,
            )

    def test_salvataggio_sincronizza_il_file_temporaneo_prima_della_sostituzione(self) -> None:
        """Verifica che il salvataggio esegua fsync prima di sostituire il file finale."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea una directory temporanea nella quale isolare il file di configurazione.
            percorso_configurazione = Path(cartella_temporanea) / "config.json"  # Definisce il percorso finale da salvare.

            with patch("fdbackup.configurazione.os.fsync") as fsync_simulato:  # Osserva la chiamata senza dipendere dal comportamento fisico del disco del test.
                salva_configurazione(percorso_configurazione, {"valore": 1})  # Esegue il salvataggio reale mantenendo simulata soltanto la sincronizzazione.

            fsync_simulato.assert_called_once()  # Verifica che la sincronizzazione sia stata richiesta esattamente una volta.
            self.assertEqual(carica_configurazione(percorso_configurazione), {"valore": 1})  # Verifica che il documento finale sia comunque corretto.

    def test_errore_serializzazione_non_danneggia_configurazione_precedente(self) -> None:
        """Verifica che un dato non serializzabile non tronchi o sostituisca un config.json già valido."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un filesystem temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file finale da proteggere.
            configurazione_precedente = {"stato": "valido"}  # Prepara il contenuto che deve sopravvivere al tentativo fallito.
            salva_configurazione(percorso_configurazione, configurazione_precedente)  # Crea una configurazione valida già esistente.

            with self.assertRaises(TypeError):  # Verifica che json.dump segnali normalmente il valore non serializzabile.
                salva_configurazione(percorso_configurazione, {"oggetto": object()})  # Tenta di salvare un oggetto che JSON non può rappresentare.

            self.assertEqual(carica_configurazione(percorso_configurazione), configurazione_precedente)  # Verifica che il file precedente sia rimasto integro.
            self.assertEqual(list(radice_test.glob(".config.json.*.tmp")), [])  # Verifica che il temporaneo parziale sia stato rimosso.

    def test_errore_sostituzione_non_danneggia_configurazione_precedente(self) -> None:
        """Verifica che un errore di os.replace lasci intatto il file precedente e ripulisca il temporaneo."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea un filesystem temporaneo isolato.
            radice_test = Path(cartella_temporanea)  # Converte la directory temporanea in Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file finale da proteggere.
            configurazione_precedente = {"stato": "precedente"}  # Prepara il contenuto già persistito.
            salva_configurazione(percorso_configurazione, configurazione_precedente)  # Crea il file valido iniziale.

            with patch("fdbackup.configurazione.os.replace", side_effect=OSError("sostituzione simulata fallita")):  # Simula un errore del sistema operativo nel solo passaggio finale.
                with self.assertRaisesRegex(OSError, "sostituzione simulata fallita"):  # Verifica che l'errore originale venga propagato al chiamante.
                    salva_configurazione(percorso_configurazione, {"stato": "nuovo"})  # Tenta un aggiornamento che non deve raggiungere il file finale.

            self.assertEqual(carica_configurazione(percorso_configurazione), configurazione_precedente)  # Verifica che il file precedente non sia stato alterato.
            self.assertEqual(list(radice_test.glob(".config.json.*.tmp")), [])  # Verifica che il file temporaneo sia stato eliminato dopo il fallimento.

    def test_salvataggio_riuscito_non_lascia_file_temporanei(self) -> None:
        """Verifica che dopo una sostituzione riuscita nella directory rimanga soltanto il file finale."""

        with tempfile.TemporaryDirectory() as cartella_temporanea:  # Crea una directory temporanea controllata.
            radice_test = Path(cartella_temporanea)  # Converte la directory in Path.
            percorso_configurazione = radice_test / "config.json"  # Definisce il file finale.

            salva_configurazione(percorso_configurazione, {"stato": "nuovo"})  # Esegue un salvataggio atomico completo.

            self.assertTrue(percorso_configurazione.is_file())  # Verifica che il file finale sia presente.
            self.assertEqual(list(radice_test.glob(".config.json.*.tmp")), [])  # Verifica che os.replace abbia consumato il temporaneo senza residui.


if __name__ == "__main__":
    unittest.main()  # Avvia automaticamente i test se il file viene eseguito direttamente.
