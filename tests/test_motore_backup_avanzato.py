import tempfile
import threading
import unittest
from pathlib import Path

from fdbackup.metadati_backup_avanzato import carica_manifesto
from fdbackup.motore_backup_avanzato import MotoreBackupAvanzato


class TestMotoreBackupAvanzato(unittest.TestCase):
    """Verifica le semantiche fondamentali dei nuovi metodi senza dipendere dalla GUI."""

    @staticmethod
    def trova_cartella_versione(radice: Path, id_backup: str) -> Path:
        """Trova la directory fisica tramite il manifesto, indipendentemente dal nome leggibile usato sul disco."""
        for manifesto_file in radice.glob("*/.backupcore-manifesto.json"):  # Cerca esclusivamente versioni pubblicate con manifesto valido.
            if carica_manifesto(manifesto_file).id_backup == id_backup:  # Confronta l'identità persistente completa.
                return manifesto_file.parent  # Restituisce la directory che contiene dati e metadati.
        raise AssertionError(f"Versione non trovata: {id_backup}")  # Rende esplicito il fallimento del test.

    def test_full_incrementale_differenziale(self):
        """Verifica che Incrementale usi il precedente e Differenziale il Full come basi distinte."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            versioni = radice / "versioni"
            sorgente.mkdir()
            (sorgente / "a.txt").write_text("A1", encoding="utf-8")
            (sorgente / "b.txt").write_text("B1", encoding="utf-8")
            motore = MotoreBackupAvanzato(threading.Event())
            full = motore.esegui_completo(sorgente, versioni)
            self.assertTrue(full.successo)
            self.assertEqual(full.file_copiati, 2)
            (sorgente / "a.txt").write_text("A2", encoding="utf-8")
            (sorgente / "c.txt").write_text("C1", encoding="utf-8")
            incrementale = motore.esegui_incrementale(sorgente, versioni, full.manifesto)
            self.assertTrue(incrementale.successo)
            self.assertEqual(incrementale.file_copiati, 2)
            (sorgente / "c.txt").write_text("C2", encoding="utf-8")
            differenziale = motore.esegui_differenziale(sorgente, versioni, full.manifesto)
            self.assertTrue(differenziale.successo)
            self.assertEqual(differenziale.file_copiati, 2)
            manifesto_salvato = carica_manifesto(self.trova_cartella_versione(versioni, differenziale.manifesto.id_backup) / ".backupcore-manifesto.json")
            self.assertEqual(manifesto_salvato.id_full_base, full.manifesto.id_backup)

    def test_incrementale_registra_eliminazioni(self):
        """Verifica che una rimozione sia registrata nei metadati senza cancellare dati delle versioni precedenti."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            versioni = radice / "versioni"
            sorgente.mkdir()
            (sorgente / "elimina.txt").write_text("dato", encoding="utf-8")
            motore = MotoreBackupAvanzato(threading.Event())
            full = motore.esegui_completo(sorgente, versioni)
            (sorgente / "elimina.txt").unlink()
            incrementale = motore.esegui_incrementale(sorgente, versioni, full.manifesto)
            self.assertEqual(incrementale.manifesto.eliminati, ("elimina.txt",))
            self.assertTrue((self.trova_cartella_versione(versioni, full.manifesto.id_backup) / "dati" / "elimina.txt").exists())

    def test_update_non_elimina_file_solo_destinazione(self):
        """Verifica che Update aggiunga e aggiorni senza propagare eliminazioni."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            destinazione = radice / "destinazione"
            sorgente.mkdir()
            destinazione.mkdir()
            (sorgente / "nuovo.txt").write_text("nuovo", encoding="utf-8")
            (destinazione / "storico.txt").write_text("storico", encoding="utf-8")
            risultato = MotoreBackupAvanzato(threading.Event()).esegui_update(sorgente, destinazione)
            self.assertTrue(risultato.successo)
            self.assertTrue((destinazione / "nuovo.txt").exists())
            self.assertTrue((destinazione / "storico.txt").exists())

    def test_mirror_elimina_solo_dopo_copie_riuscite(self):
        """Verifica la semantica speculare di base con eliminazione dei file estranei."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            destinazione = radice / "destinazione"
            sorgente.mkdir()
            destinazione.mkdir()
            (sorgente / "presente.txt").write_text("nuovo", encoding="utf-8")
            (destinazione / "presente.txt").write_text("vecchio", encoding="utf-8")
            (destinazione / "rimuovi.txt").write_text("rimuovi", encoding="utf-8")
            risultato = MotoreBackupAvanzato(threading.Event()).esegui_mirror(sorgente, destinazione)
            self.assertTrue(risultato.successo)
            self.assertEqual((destinazione / "presente.txt").read_text(encoding="utf-8"), "nuovo")
            self.assertFalse((destinazione / "rimuovi.txt").exists())
            self.assertEqual(risultato.file_eliminati, 1)

    def test_stop_impedisce_copie(self):
        """Verifica che lo Stop già impostato impedisca di iniziare la materializzazione."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            versioni = radice / "versioni"
            sorgente.mkdir()
            (sorgente / "a.txt").write_text("A", encoding="utf-8")
            evento = threading.Event()
            evento.set()
            risultato = MotoreBackupAvanzato(evento).esegui_completo(sorgente, versioni)
            self.assertTrue(risultato.annullato)
            self.assertFalse(risultato.successo)
            self.assertEqual(risultato.file_copiati, 0)
            self.assertFalse((versioni / risultato.manifesto.id_backup / ".backupcore-manifesto.json").exists())

    def test_mirror_non_elimina_file_nelle_sottocartelle_quando_ricorsione_disattivata(self):
        """Verifica che Mirror limitato alla radice non cancelli contenuti annidati fuori dall'ambito richiesto."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola sorgente e destinazione in un filesystem temporaneo.
            radice = Path(temporanea)  # Converte la directory temporanea nel tipo usato dai motori.
            sorgente = radice / "sorgente"  # Prepara la sorgente del Mirror.
            destinazione = radice / "destinazione"  # Prepara la destinazione contenente dati annidati da preservare.
            sorgente.mkdir()  # Crea la sorgente vuota in radice.
            (destinazione / "annidata").mkdir(parents=True)  # Crea una sottocartella che non rientra nella scansione non ricorsiva.
            file_annidato = destinazione / "annidata" / "preserva.txt"  # Definisce il file che non deve essere toccato.
            file_annidato.write_text("dato", encoding="utf-8")  # Materializza il contenuto preesistente.
            motore = MotoreBackupAvanzato(threading.Event())  # Crea il motore con uno Stop non impostato.
            risultato = motore.esegui_mirror(sorgente, destinazione, includi_sottocartelle=False)  # Esegue un Mirror limitato alla sola radice.
            self.assertTrue(risultato.successo)  # Verifica che l'operazione termini senza errori.
            self.assertTrue(file_annidato.exists())  # Conferma che il file annidato resti fuori dall'ambito e venga preservato.
            self.assertEqual(risultato.file_eliminati, 0)  # Conferma che non siano state registrate eliminazioni fuori ambito.

    def test_full_preserva_cartelle_vuote_e_nome_versione_leggibile(self):
        """Il Full deve conservare directory vuote e non esporre un UUID puro come nome della versione."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il layout fisico prodotto dal motore.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            versioni = radice / "versioni"  # Definisce la radice delle versioni.
            (sorgente / "vuota" / "annidata").mkdir(parents=True)  # Crea una struttura priva di file.
            risultato = MotoreBackupAvanzato(threading.Event()).esegui_completo(sorgente, versioni)  # Esegue un Full reale.
            cartella = self.trova_cartella_versione(versioni, risultato.manifesto.id_backup)  # Risolve la directory pubblicata.
            self.assertTrue((cartella / "dati" / "vuota" / "annidata").is_dir())  # Verifica la materializzazione della directory vuota.
            self.assertIn("COMPLETO", cartella.name)  # Richiede un nome comprensibile all'utente.
            self.assertNotEqual(cartella.name, risultato.manifesto.id_backup)  # Mantiene l'UUID completo soltanto nei metadati.
            self.assertIn("vuota/annidata", risultato.manifesto.cartelle)  # Verifica che il ripristino possa ricostruire la struttura.

    def test_callback_avanzamento_raggiunge_totale_byte(self):
        """La copia deve emettere un progresso determinato basato sui byte effettivamente trasferiti."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il test del callback.
            radice = Path(temporanea)  # Prepara i percorsi temporanei.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            sorgente.mkdir()  # Crea la cartella sorgente.
            contenuto = b"x" * (5 * 1024 * 1024)  # Supera un blocco da 4 MiB per richiedere più aggiornamenti.
            (sorgente / "grande.bin").write_bytes(contenuto)  # Materializza il file di prova.
            eventi = []  # Raccoglie gli eventi senza dipendere dalla GUI.
            risultato = MotoreBackupAvanzato(threading.Event(), lambda evento, dati: eventi.append((evento, dati))).esegui_completo(sorgente, radice / "versioni")  # Esegue il Full con callback.
            avanzamenti = [dati for evento, dati in eventi if evento == "avanzamento_copia"]  # Seleziona soltanto gli aggiornamenti numerici.
            self.assertTrue(risultato.successo)  # Richiede una copia valida.
            self.assertGreaterEqual(len(avanzamenti), 2)  # Verifica aggiornamenti anche durante un singolo file grande.
            self.assertEqual(avanzamenti[-1]["byte_elaborati"], len(contenuto))  # Richiede che l'ultimo evento raggiunga il totale reale.
            self.assertEqual(avanzamenti[-1]["totale_byte"], len(contenuto))  # Verifica il denominatore usato dalla percentuale.

    def test_update_e_mirror_preservano_cartelle_vuote_della_sorgente(self):
        """Le sincronizzazioni devono propagare directory vuote; Mirror può rimuovere solo quelle extra."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola entrambe le modalità.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente autorevole.
            destinazione_update = radice / "update"  # Definisce la destinazione Update.
            destinazione_mirror = radice / "mirror"  # Definisce la destinazione Mirror.
            (sorgente / "vuota").mkdir(parents=True)  # Crea una directory vuota da propagare.
            (destinazione_mirror / "extra_vuota").mkdir(parents=True)  # Crea una directory extra che Mirror deve rimuovere.
            motore = MotoreBackupAvanzato(threading.Event())  # Riusa un motore senza Stop impostato.
            self.assertTrue(motore.esegui_update(sorgente, destinazione_update).successo)  # Esegue Update.
            self.assertTrue((destinazione_update / "vuota").is_dir())  # Verifica la propagazione non distruttiva.
            self.assertTrue(motore.esegui_mirror(sorgente, destinazione_mirror).successo)  # Esegue Mirror.
            self.assertTrue((destinazione_mirror / "vuota").is_dir())  # Preserva la directory vuota autorevole.
            self.assertFalse((destinazione_mirror / "extra_vuota").exists())  # Rimuove soltanto la directory extra vuota.

    def test_stop_durante_file_grande_non_pubblica_payload_parziale(self):
        """Uno Stop tra due blocchi deve lasciare intatto un eventuale file finale precedente e rimuovere il temporaneo."""
        with tempfile.TemporaryDirectory() as temporanea:  # Isola il filesystem del test.
            radice = Path(temporanea)  # Prepara la radice temporanea.
            sorgente = radice / "sorgente"  # Definisce la sorgente.
            destinazione = radice / "destinazione"  # Definisce la destinazione Update.
            sorgente.mkdir()  # Crea la sorgente.
            destinazione.mkdir()  # Crea la destinazione.
            (sorgente / "grande.bin").write_bytes(b"n" * (9 * 1024 * 1024))  # Richiede almeno tre blocchi di trasferimento.
            finale = destinazione / "grande.bin"  # Definisce il file preesistente da proteggere.
            finale.write_bytes(b"vecchio")  # Materializza un contenuto che non deve essere troncato dallo Stop.
            evento = threading.Event()  # Crea lo Stop condiviso.
            def callback(nome, dati):  # Osserva il primo blocco senza dipendere dalla GUI.
                if nome == "avanzamento_copia":  # Interrompe soltanto dopo che il temporaneo contiene dati reali.
                    evento.set()  # Richiede l'arresto cooperativo.
            risultato = MotoreBackupAvanzato(evento, callback).esegui_update(sorgente, destinazione)  # Avvia Update e interrompe durante il file.
            self.assertTrue(risultato.annullato)  # Verifica che lo Stop sia stato osservato.
            self.assertEqual(finale.read_bytes(), b"vecchio")  # Conferma che il file finale precedente sia rimasto intatto.
            self.assertFalse((destinazione / ".grande.bin.backupcore-part").exists())  # Verifica la pulizia del payload temporaneo.


if __name__ == "__main__":
    unittest.main()
