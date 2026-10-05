"""Test del coordinamento delle strategie avanzate di FDBackup."""

import tempfile
import threading
import unittest
from pathlib import Path

from fdbackup.metadati_backup_avanzato import carica_manifesto
from fdbackup.gestore_backup_avanzato import GestoreBackupAvanzato, StrategiaBackupAvanzato


class TestGestoreBackupAvanzato(unittest.TestCase):
    """Verifica rotazione, dipendenze, retention e sincronizzazione del coordinatore avanzato."""

    def setUp(self) -> None:
        """Crea filesystem temporaneo isolato per ogni test."""
        self.temporaneo = tempfile.TemporaryDirectory()  # Isola completamente i dati di ogni test.
        self.radice = Path(self.temporaneo.name)  # Converte la directory temporanea nel tipo usato dal progetto.
        self.sorgente = self.radice / "sorgente"  # Definisce la sorgente comune ai test.
        self.versioni = self.radice / "versioni"  # Definisce la radice delle versioni.
        self.sorgente.mkdir()  # Crea la sorgente reale.
        (self.sorgente / "a.txt").write_text("A1", encoding="utf-8")  # Inserisce un primo contenuto verificabile.
        self.gestore = GestoreBackupAvanzato(threading.Event())  # Crea il coordinatore con evento di arresto indipendente.

    def tearDown(self) -> None:
        """Rimuove tutte le risorse temporanee del test."""
        self.temporaneo.cleanup()  # Elimina ricorsivamente il filesystem isolato.

    def test_incrementale_crea_full_iniziale_e_poi_delta(self) -> None:
        """La strategia incrementale deve auto-inizializzarsi con un Full e poi creare un Incrementale."""
        strategia = StrategiaBackupAvanzato("incrementale", full_ogni=5, catene_da_mantenere=2)  # Configura una catena sufficientemente lunga.
        primo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Esegue il primo passaggio privo di base.
        self.assertEqual(primo.tipo_backup, "completo")  # Richiede l'auto-inizializzazione con Full.
        (self.sorgente / "a.txt").write_text("A2", encoding="utf-8")  # Modifica il contenuto dopo il Full.
        secondo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Esegue il secondo passaggio della stessa strategia.
        self.assertEqual(secondo.tipo_backup, "incrementale")  # Richiede il delta incrementale.
        self.assertEqual(secondo.manifesto.id_backup_precedente, primo.manifesto.id_backup)  # Verifica la dipendenza dal backup immediatamente precedente.

    def test_differenziale_rimane_legato_al_full(self) -> None:
        """Due differenziali consecutivi devono dipendere entrambi dallo stesso Full."""
        strategia = StrategiaBackupAvanzato("differenziale", full_ogni=5, catene_da_mantenere=2)  # Configura una catena differenziale.
        full = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Produce automaticamente il Full iniziale.
        (self.sorgente / "a.txt").write_text("A2", encoding="utf-8")  # Introduce la prima variazione.
        primo_diff = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Produce il primo differenziale.
        (self.sorgente / "b.txt").write_text("B1", encoding="utf-8")  # Introduce una seconda variazione indipendente.
        secondo_diff = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Produce il secondo differenziale.
        self.assertEqual(primo_diff.manifesto.id_backup_precedente, full.manifesto.id_backup)  # Richiede il legame diretto del primo differenziale.
        self.assertEqual(secondo_diff.manifesto.id_backup_precedente, full.manifesto.id_backup)  # Richiede lo stesso legame per il differenziale successivo.

    def test_rotazione_full_rispetta_la_soglia(self) -> None:
        """Raggiunto il numero configurato di delta deve iniziare automaticamente una nuova catena Full."""
        strategia = StrategiaBackupAvanzato("incrementale", full_ogni=1, catene_da_mantenere=3)  # Richiede un nuovo Full dopo un solo delta.
        primo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Produce il Full iniziale.
        (self.sorgente / "a.txt").write_text("A2", encoding="utf-8")  # Prepara il primo delta.
        secondo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Produce l'unico incrementale consentito.
        (self.sorgente / "a.txt").write_text("A3", encoding="utf-8")  # Prepara la rotazione successiva.
        terzo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Deve aprire una nuova catena.
        self.assertEqual(primo.tipo_backup, "completo")  # Conferma la base iniziale.
        self.assertEqual(secondo.tipo_backup, "incrementale")  # Conferma il delta intermedio.
        self.assertEqual(terzo.tipo_backup, "completo")  # Conferma la rotazione automatica.
        self.assertNotEqual(primo.manifesto.id_backup, terzo.manifesto.id_backup)  # Richiede identità distinte per le due basi.

    def test_retention_elimina_intera_catena_vecchia(self) -> None:
        """La retention deve eliminare Full e dipendenze della catena scaduta senza toccare quella corrente."""
        strategia = StrategiaBackupAvanzato("incrementale", full_ogni=1, catene_da_mantenere=1)  # Mantiene una sola catena completa.
        primo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Crea la prima base.
        (self.sorgente / "a.txt").write_text("A2", encoding="utf-8")  # Prepara il delta della prima catena.
        secondo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Crea il delta dipendente.
        (self.sorgente / "a.txt").write_text("A3", encoding="utf-8")  # Forza la successiva rotazione.
        terzo = self.gestore.esegui_strategia(self.sorgente, self.versioni, strategia)  # Crea il nuovo Full e applica retention.
        self.assertFalse((self.versioni / primo.manifesto.id_backup).exists())  # Richiede la rimozione del vecchio Full.
        self.assertFalse((self.versioni / secondo.manifesto.id_backup).exists())  # Richiede la rimozione del delta dipendente.
        self.assertTrue(any(carica_manifesto(percorso).id_backup == terzo.manifesto.id_backup for percorso in self.versioni.glob("*/.backupcore-manifesto.json")))  # Conserva la nuova catena valida indipendentemente dal nome leggibile della directory.

    def test_update_conserva_file_solo_destinazione_e_mirror_lo_elimina(self) -> None:
        """Update e Mirror devono mantenere semantiche distruttive differenti."""
        destinazione = self.radice / "destinazione"  # Definisce una destinazione separata dalle versioni.
        destinazione.mkdir()  # Crea la directory necessaria al test.
        (destinazione / "vecchio.txt").write_text("vecchio", encoding="utf-8")  # Inserisce un file presente soltanto a destinazione.
        update = self.gestore.esegui_sincronizzazione("update", self.sorgente, destinazione)  # Applica la modalità conservativa.
        self.assertTrue(update.successo)  # Richiede il completamento dell'Update.
        self.assertTrue((destinazione / "vecchio.txt").exists())  # Update non deve propagare l'eliminazione.
        mirror = self.gestore.esegui_sincronizzazione("mirror", self.sorgente, destinazione)  # Applica successivamente la modalità speculare.
        self.assertTrue(mirror.successo)  # Richiede il completamento del Mirror.
        self.assertFalse((destinazione / "vecchio.txt").exists())  # Mirror deve rendere la destinazione equivalente alla sorgente.

    def test_strategia_rifiuta_valori_pericolosi(self) -> None:
        """Configurazioni non supportate o retention nulla devono essere rifiutate prima dell'I/O."""
        with self.assertRaises(ValueError):  # Verifica il metodo sconosciuto.
            StrategiaBackupAvanzato("mirror")  # Mirror non appartiene alle catene versionate.
        with self.assertRaises(ValueError):  # Verifica la retention distruttiva.
            StrategiaBackupAvanzato("incrementale", catene_da_mantenere=0)  # Non deve essere possibile eliminare tutte le catene.

    def test_elenco_manifesti_supporta_anche_vecchio_layout_uuid(self):
        """Le versioni create dal checkpoint 240 devono restare leggibili dopo l'introduzione dei nomi directory descrittivi."""
        risultato = self.gestore.esegui_strategia(self.sorgente, self.versioni, StrategiaBackupAvanzato("completo"))  # Produce una versione con il nuovo layout.
        cartella_nuova = next(percorso.parent for percorso in self.versioni.glob("*/.backupcore-manifesto.json") if carica_manifesto(percorso).id_backup == risultato.manifesto.id_backup)  # Risolve la directory pubblicata.
        cartella_vecchia = self.versioni / risultato.manifesto.id_backup  # Ricostruisce il layout UUID usato dal checkpoint precedente.
        cartella_nuova.rename(cartella_vecchia)  # Simula una versione realmente creata dalla build 240.
        manifesti = self.gestore.elenca_manifesti(self.versioni, self.sorgente)  # Carica le versioni senza dipendere dal nome fisico.
        self.assertEqual([manifesto.id_backup for manifesto in manifesti], [risultato.manifesto.id_backup])  # Conferma la retrocompatibilità.


if __name__ == "__main__":
    unittest.main()  # Permette l'esecuzione diretta del modulo di test.
