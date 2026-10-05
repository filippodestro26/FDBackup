import tempfile  # Importa TemporaryDirectory per creare filesystem di prova isolati.
import unittest  # Importa il framework standard già usato dal progetto.
from pathlib import Path  # Importa Path per costruire i percorsi dei test.

from fdbackup.modelli_backup import JobBackup, SorgenteBackup  # Importa i modelli reali.
from fdbackup.validazione_backup import ValidatoreBackup  # Importa il nuovo validatore da verificare.


class TestValidatoreBackup(unittest.TestCase):
    """Verifica le regole del singolo job e dell'insieme di job."""

    def test_job_valido_con_una_sorgente(self) -> None:
        """Un job normale con una sorgente deve essere accettato."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati")])
            ValidatoreBackup.valida_job(job)

    def test_job_valido_con_piu_sorgenti(self) -> None:
        """Più sorgenti indipendenti verso una sola destinazione devono essere consentite."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(prima, "Prima"), SorgenteBackup(seconda, "Seconda")])
            ValidatoreBackup.valida_job(job)

    def test_job_abilitato_senza_sorgenti_viene_rifiutato(self) -> None:
        """Un job eseguibile deve contenere almeno una sorgente."""
        with tempfile.TemporaryDirectory() as temporanea:
            job = JobBackup("Vuoto", Path(temporanea) / "backup")
            with self.assertRaisesRegex(ValueError, "non contiene alcuna sorgente"):
                ValidatoreBackup.valida_job(job)

    def test_job_disabilitato_senza_sorgenti_viene_ignorato(self) -> None:
        """Un job disabilitato può rimanere configurato senza bloccare l'esecuzione."""
        with tempfile.TemporaryDirectory() as temporanea:
            job = JobBackup("Disabilitato", Path(temporanea) / "backup", abilitato=False)
            ValidatoreBackup.valida_job(job)

    def test_sorgente_inesistente_viene_rifiutata(self) -> None:
        """Una sorgente non disponibile deve essere rilevata prima della copia."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(radice / "manca", "Dati")])
            with self.assertRaisesRegex(ValueError, "non esiste"):
                ValidatoreBackup.valida_job(job)

    def test_sorgente_file_viene_rifiutata(self) -> None:
        """Un file non può essere usato come sorgente di un job."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            file_sorgente = radice / "file.txt"
            file_sorgente.write_text("x", encoding="utf-8")
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(file_sorgente, "Dati")])
            with self.assertRaisesRegex(ValueError, "deve essere una cartella"):
                ValidatoreBackup.valida_job(job)

    def test_destinazione_file_viene_rifiutata(self) -> None:
        """Una destinazione già esistente come file deve essere rifiutata."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            destinazione = radice / "backup"
            destinazione.write_text("x", encoding="utf-8")
            job = JobBackup("Job", destinazione, [SorgenteBackup(sorgente, "Dati")])
            with self.assertRaisesRegex(ValueError, "non è una cartella"):
                ValidatoreBackup.valida_job(job)

    def test_sorgente_duplicata_nello_stesso_job_viene_rifiutata(self) -> None:
        """La stessa cartella non deve essere elaborata due volte nello stesso job."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "A"), SorgenteBackup(sorgente, "B")])
            with self.assertRaisesRegex(ValueError, "stessa sorgente"):
                ValidatoreBackup.valida_job(job)

    def test_sorgenti_annidate_vengono_rifiutate(self) -> None:
        """Due sorgenti annidate nello stesso job causerebbero duplicazione e devono essere bloccate."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            genitore = radice / "dati"
            figlio = genitore / "interno"
            figlio.mkdir(parents=True)
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(genitore, "Dati"), SorgenteBackup(figlio, "Interno")])
            with self.assertRaisesRegex(ValueError, "annidate"):
                ValidatoreBackup.valida_job(job)

    def test_nomi_destinazione_duplicati_vengono_rifiutati(self) -> None:
        """Due sorgenti non devono scrivere nella stessa sottocartella logica."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(prima, "Dati"), SorgenteBackup(seconda, "Dati")])
            with self.assertRaisesRegex(ValueError, "nomi di destinazione duplicati"):
                ValidatoreBackup.valida_job(job)

    def test_nome_destinazione_con_separatore_viene_rifiutato(self) -> None:
        """Il nome logico non deve poter creare arbitrariamente sottopercorsi."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati/Sotto")])
            with self.assertRaisesRegex(ValueError, "separatori"):
                ValidatoreBackup.valida_job(job)

    def test_nome_destinazione_punto_punto_viene_rifiutato(self) -> None:
        """Il nome logico non deve poter risalire alla cartella genitore."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "..")])
            with self.assertRaisesRegex(ValueError, "singola sottocartella"):
                ValidatoreBackup.valida_job(job)

    def test_destinazione_effettiva_dentro_sorgente_viene_rifiutata(self) -> None:
        """La sottocartella effettiva del backup non può ricadere nella sorgente."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "dati"
            sorgente.mkdir()
            job = JobBackup("Job", sorgente, [SorgenteBackup(sorgente, "Backup")])
            with self.assertRaisesRegex(ValueError, "all'interno della sorgente"):
                ValidatoreBackup.valida_job(job)

    def test_due_job_con_destinazioni_diverse_sono_validi(self) -> None:
        """Due job indipendenti devono poter essere configurati insieme."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job1 = JobBackup("Uno", radice / "backup1", [SorgenteBackup(prima, "Prima")])
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(seconda, "Seconda")])
            ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_due_job_con_stessa_destinazione_vengono_rifiutati(self) -> None:
        """La V1 non permette a due job abilitati di condividere la stessa destinazione."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            destinazione = radice / "backup"
            job1 = JobBackup("Uno", destinazione, [SorgenteBackup(prima, "Prima")])
            job2 = JobBackup("Due", destinazione, [SorgenteBackup(seconda, "Seconda")])
            with self.assertRaisesRegex(ValueError, "stessa destinazione"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_destinazioni_annidate_tra_job_vengono_rifiutate(self) -> None:
        """Le radici di backup di due job non devono sovrapporsi."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job1 = JobBackup("Uno", radice / "backup", [SorgenteBackup(prima, "Prima")])
            job2 = JobBackup("Due", radice / "backup" / "interno", [SorgenteBackup(seconda, "Seconda")])
            with self.assertRaisesRegex(ValueError, "annidate"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_sorgente_di_un_job_uguale_destinazione_altro_job_viene_rifiutata(self) -> None:
        """Una catena in cui un job legge la radice scritta da un altro viene bloccata."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            prima.mkdir()
            destinazione_primo = radice / "backup1"
            sorgente_secondo = destinazione_primo
            sorgente_secondo.mkdir()
            job1 = JobBackup("Uno", destinazione_primo, [SorgenteBackup(prima, "Prima")])
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(sorgente_secondo, "Seconda")])
            with self.assertRaisesRegex(ValueError, "si sovrappone"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_sorgente_dentro_destinazione_altro_job_viene_rifiutata(self) -> None:
        """Una sorgente contenuta nella radice di backup di un altro job viene bloccata."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            prima.mkdir()
            backup_primo = radice / "backup1"
            sorgente_secondo = backup_primo / "gia_presente"
            sorgente_secondo.mkdir(parents=True)
            job1 = JobBackup("Uno", backup_primo, [SorgenteBackup(prima, "Prima")])
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(sorgente_secondo, "Seconda")])
            with self.assertRaisesRegex(ValueError, "si sovrappone"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_destinazione_altro_job_dentro_sorgente_viene_rifiutata(self) -> None:
        """La destinazione di un job non può essere creata dentro la sorgente di un altro."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente_primo = radice / "dati"
            sorgente_secondo = radice / "altra"
            sorgente_primo.mkdir()
            sorgente_secondo.mkdir()
            job1 = JobBackup("Uno", radice / "backup1", [SorgenteBackup(sorgente_primo, "Dati")])
            job2 = JobBackup("Due", sorgente_primo / "backup2", [SorgenteBackup(sorgente_secondo, "Altra")])
            with self.assertRaisesRegex(ValueError, "si sovrappone"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_job_disabilitato_non_genera_conflitto_globale(self) -> None:
        """Un job disabilitato non deve impedire l'esecuzione di un job attivo."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            attivo = JobBackup("Attivo", radice / "backup", [SorgenteBackup(sorgente, "Dati")])
            disabilitato = JobBackup("Off", radice / "backup", abilitato=False)
            ValidatoreBackup.valida_job_multipli([attivo, disabilitato])

    def test_id_job_duplicato_viene_rifiutato(self) -> None:
        """Due job abilitati non devono condividere la stessa identità persistente."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job1 = JobBackup("Uno", radice / "backup1", [SorgenteBackup(prima, "Prima")], id_job="stesso-id")
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(seconda, "Seconda")], id_job="stesso-id")
            with self.assertRaisesRegex(ValueError, "stesso identificatore"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_percorsi_con_punto_punto_vengono_normalizzati(self) -> None:
        """La normalizzazione deve impedire che componenti .. aggirino i controlli."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "dati"
            sorgente.mkdir()
            percorso_equivalente = sorgente / ".." / "dati"
            self.assertTrue(ValidatoreBackup.stesso_percorso(sorgente, percorso_equivalente))


    def test_sorgente_dentro_destinazione_proprio_job_viene_rifiutata(self) -> None:
        """Una sorgente non deve trovarsi dentro la radice di backup dello stesso job."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            destinazione = radice / "backup"
            sorgente = destinazione / "gia_presente"
            sorgente.mkdir(parents=True)
            job = JobBackup("Job", destinazione, [SorgenteBackup(sorgente, "Dati")])
            with self.assertRaisesRegex(ValueError, "all'interno della destinazione"):
                ValidatoreBackup.valida_job(job)

    def test_sorgente_uguale_destinazione_proprio_job_viene_rifiutata(self) -> None:
        """La radice di backup non può essere contemporaneamente una sorgente dello stesso job."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            destinazione = radice / "backup"
            destinazione.mkdir()
            job = JobBackup("Job", destinazione, [SorgenteBackup(destinazione, "Dati")])
            with self.assertRaisesRegex(ValueError, "all'interno della sorgente"):
                ValidatoreBackup.valida_job(job)

    def test_id_job_duplicato_anche_se_disabilitato_viene_rifiutato(self) -> None:
        """L'identità persistente dei job deve essere unica anche quando i job non vengono eseguiti."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            primo = JobBackup("Uno", radice / "backup1", abilitato=False, id_job="id-duplicato")
            secondo = JobBackup("Due", radice / "backup2", abilitato=False, id_job="id-duplicato")
            with self.assertRaisesRegex(ValueError, "stesso identificatore"):
                ValidatoreBackup.valida_job_multipli([primo, secondo])

    def test_id_sorgente_duplicato_nello_stesso_job_viene_rifiutato(self) -> None:
        """Due sorgenti distinte non devono condividere la stessa identità persistente."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job = JobBackup("Job", radice / "backup", [
                SorgenteBackup(prima, "Prima", id_sorgente="id-duplicato"),
                SorgenteBackup(seconda, "Seconda", id_sorgente="id-duplicato"),
            ])
            with self.assertRaisesRegex(ValueError, "stesso identificatore"):
                ValidatoreBackup.valida_job_multipli([job])

    def test_id_sorgente_duplicato_tra_job_viene_rifiutato(self) -> None:
        """L'identità di una sorgente deve essere unica nell'intera configurazione."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = radice / "prima"
            seconda = radice / "seconda"
            prima.mkdir()
            seconda.mkdir()
            job1 = JobBackup("Uno", radice / "backup1", [SorgenteBackup(prima, "Prima", id_sorgente="id-duplicato")])
            job2 = JobBackup("Due", radice / "backup2", [SorgenteBackup(seconda, "Seconda", id_sorgente="id-duplicato")])
            with self.assertRaisesRegex(ValueError, "stesso identificatore"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_id_sorgente_duplicato_in_job_disabilitati_viene_rifiutato(self) -> None:
        """Gli ID delle sorgenti restano unici anche nei job temporaneamente disabilitati."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            prima = SorgenteBackup(radice / "prima", "Prima", id_sorgente="id-duplicato")
            seconda = SorgenteBackup(radice / "seconda", "Seconda", id_sorgente="id-duplicato")
            job1 = JobBackup("Uno", radice / "backup1", [prima], abilitato=False)
            job2 = JobBackup("Due", radice / "backup2", [seconda], abilitato=False)
            with self.assertRaisesRegex(ValueError, "stesso identificatore"):
                ValidatoreBackup.valida_job_multipli([job1, job2])

    def test_nome_windows_con_riservato_viene_rifiutato(self) -> None:
        """Un nome DOS riservato non deve diventare una sottocartella di backup."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "CON")])
            with self.assertRaisesRegex(ValueError, "Windows"):
                ValidatoreBackup.valida_job(job)

    def test_nome_windows_nul_con_estensione_viene_rifiutato(self) -> None:
        """Anche un nome DOS riservato seguito da estensione deve essere bloccato."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "NUL.txt")])
            with self.assertRaisesRegex(ValueError, "Windows"):
                ValidatoreBackup.valida_job(job)

    def test_nome_windows_con_carattere_riservato_viene_rifiutato(self) -> None:
        """I caratteri non validi nei nomi Win32 devono essere bloccati prima della copia."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati?")])
            with self.assertRaisesRegex(ValueError, "Windows"):
                ValidatoreBackup.valida_job(job)

    def test_nome_windows_con_punto_finale_viene_rifiutato(self) -> None:
        """Un nome che termina con punto non è affidabile nell'interfaccia Win32."""
        with tempfile.TemporaryDirectory() as temporanea:
            radice = Path(temporanea)
            sorgente = radice / "sorgente"
            sorgente.mkdir()
            job = JobBackup("Job", radice / "backup", [SorgenteBackup(sorgente, "Dati.")])
            with self.assertRaisesRegex(ValueError, "Windows"):
                ValidatoreBackup.valida_job(job)


if __name__ == "__main__":
    unittest.main()
