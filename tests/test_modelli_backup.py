import unittest  # Importa il framework standard usato dal resto del progetto per i test automatici.
from pathlib import Path  # Importa Path per verificare la normalizzazione dei percorsi.
from uuid import UUID  # Importa UUID per verificare formalmente gli identificatori generati.

from fdbackup.modelli_backup import JobBackup, PianificazioneBackup, SorgenteBackup  # Importa i nuovi modelli da sottoporre a test.


class TestSorgenteBackup(unittest.TestCase):
    """Verifica il contratto dati di una singola sorgente di backup."""

    def test_converte_percorso_stringa_in_path(self) -> None:
        """Una stringa ricevuta dalla configurazione deve diventare un oggetto Path."""
        sorgente = SorgenteBackup("C:/Dati", "Dati")  # Crea una sorgente usando intenzionalmente una stringa.
        self.assertIsInstance(sorgente.percorso, Path)  # Verifica che il modello normalizzi il tipo del percorso.

    def test_genera_id_uuid4_valido(self) -> None:
        """Ogni nuova sorgente deve ricevere un UUID4 valido."""
        sorgente = SorgenteBackup(Path("C:/Dati"), "Dati")  # Crea una sorgente con identificatore automatico.
        identificatore = UUID(sorgente.id_sorgente)  # Analizza la stringa tramite la libreria standard UUID.
        self.assertEqual(identificatore.version, 4)  # Verifica che l'identificatore generato sia effettivamente UUID versione 4.

    def test_due_sorgenti_ricevono_id_diversi(self) -> None:
        """Due sorgenti nuove non devono condividere lo stesso identificatore."""
        prima = SorgenteBackup(Path("C:/Dati"), "Dati")  # Crea la prima sorgente.
        seconda = SorgenteBackup(Path("D:/Foto"), "Foto")  # Crea la seconda sorgente.
        self.assertNotEqual(prima.id_sorgente, seconda.id_sorgente)  # Verifica che le identità siano distinte.

    def test_id_fornito_viene_conservato(self) -> None:
        """Un ID caricato dalla futura configurazione deve rimanere stabile."""
        sorgente = SorgenteBackup(Path("C:/Dati"), "Dati", id_sorgente="sorgente-esistente")  # Simula il caricamento da configurazione.
        self.assertEqual(sorgente.id_sorgente, "sorgente-esistente")  # Verifica che il modello non rigeneri l'identità.

    def test_nome_destinazione_vuoto_viene_rifiutato(self) -> None:
        """Una sorgente senza nome logico non deve essere costruibile."""
        with self.assertRaisesRegex(ValueError, "nome di destinazione"):  # Verifica sia il tipo sia il significato dell'errore.
            SorgenteBackup(Path("C:/Dati"), "   ")  # Tenta di creare una sorgente con nome composto soltanto da spazi.

    def test_id_sorgente_vuoto_viene_rifiutato(self) -> None:
        """Un identificatore esplicitamente vuoto deve essere rifiutato."""
        with self.assertRaisesRegex(ValueError, "identificatore della sorgente"):  # Verifica l'errore previsto dal contratto.
            SorgenteBackup(Path("C:/Dati"), "Dati", id_sorgente="   ")  # Simula una configurazione corrotta.


class TestJobBackup(unittest.TestCase):
    """Verifica il contratto dati di un job di backup."""

    def test_converte_destinazione_stringa_in_path(self) -> None:
        """La destinazione ricevuta come stringa deve diventare un oggetto Path."""
        job = JobBackup("Documenti", "G:/Backup")  # Crea un job usando intenzionalmente una stringa.
        self.assertIsInstance(job.destinazione, Path)  # Verifica la normalizzazione del tipo.

    def test_genera_id_uuid4_valido(self) -> None:
        """Ogni nuovo job deve ricevere un UUID4 valido."""
        job = JobBackup("Documenti", Path("G:/Backup"))  # Crea un job con ID automatico.
        identificatore = UUID(job.id_job)  # Converte la stringa in UUID per verificarne formalmente il formato.
        self.assertEqual(identificatore.version, 4)  # Verifica che l'ID sia UUID versione 4.

    def test_due_job_ricevono_id_diversi(self) -> None:
        """Due job nuovi devono possedere identità indipendenti."""
        primo = JobBackup("Documenti", Path("G:/Backup"))  # Crea il primo job.
        secondo = JobBackup("Foto", Path("H:/Backup"))  # Crea il secondo job.
        self.assertNotEqual(primo.id_job, secondo.id_job)  # Verifica che gli ID non coincidano.

    def test_id_job_fornito_viene_conservato(self) -> None:
        """Un ID persistito deve poter essere ricaricato senza essere sostituito."""
        job = JobBackup("Documenti", Path("G:/Backup"), id_job="job-esistente")  # Simula un job letto dalla configurazione.
        self.assertEqual(job.id_job, "job-esistente")  # Verifica la stabilità dell'identità.

    def test_liste_sorgenti_predefinite_non_sono_condivise(self) -> None:
        """Ogni job deve possedere una lista sorgenti indipendente."""
        primo = JobBackup("Primo", Path("G:/Backup"))  # Crea un job con la lista predefinita.
        secondo = JobBackup("Secondo", Path("H:/Backup"))  # Crea un altro job con la propria lista.
        primo.sorgenti.append(SorgenteBackup(Path("C:/Dati"), "Dati"))  # Modifica soltanto la lista del primo job.
        self.assertEqual(secondo.sorgenti, [])  # Verifica che il secondo job non sia stato modificato indirettamente.

    def test_lista_passata_viene_copiata(self) -> None:
        """Il job non deve mantenere un alias mutabile della lista ricevuta dal chiamante."""
        sorgente = SorgenteBackup(Path("C:/Dati"), "Dati")  # Prepara una sorgente valida.
        lista_esterna = [sorgente]  # Crea la lista posseduta dal chiamante.
        job = JobBackup("Documenti", Path("G:/Backup"), sorgenti=lista_esterna)  # Costruisce il job dalla lista esterna.
        lista_esterna.clear()  # Modifica successivamente la lista originale.
        self.assertEqual(job.sorgenti, [sorgente])  # Verifica che il job conservi la propria copia della collezione.

    def test_nome_job_vuoto_viene_rifiutato(self) -> None:
        """Un job senza nome leggibile deve essere rifiutato."""
        with self.assertRaisesRegex(ValueError, "nome del job"):  # Verifica l'errore definito dal modello.
            JobBackup("   ", Path("G:/Backup"))  # Tenta di creare un job con nome vuoto dopo la normalizzazione.

    def test_id_job_vuoto_viene_rifiutato(self) -> None:
        """Un job con identificatore esplicitamente vuoto deve essere rifiutato."""
        with self.assertRaisesRegex(ValueError, "identificatore del job"):  # Verifica l'errore previsto.
            JobBackup("Documenti", Path("G:/Backup"), id_job="   ")  # Simula dati persistiti non validi.

    def test_job_accetta_piu_sorgenti(self) -> None:
        """Un singolo job deve poter rappresentare più sorgenti verso la stessa destinazione."""
        sorgenti = [  # Prepara due sorgenti appartenenti allo stesso job.
            SorgenteBackup(Path("C:/Documenti"), "Documenti"),  # Rappresenta la prima sorgente.
            SorgenteBackup(Path("D:/Foto"), "Foto"),  # Rappresenta la seconda sorgente.
        ]
        job = JobBackup("Personale", Path("G:/Backup"), sorgenti=sorgenti)  # Crea il job multi-sorgente.
        self.assertEqual(len(job.sorgenti), 2)  # Verifica che entrambe le sorgenti siano conservate.

    def test_job_puo_essere_disabilitato(self) -> None:
        """Il modello deve poter conservare un job senza richiederne l'esecuzione."""
        job = JobBackup("Archivio", Path("G:/Backup"), abilitato=False)  # Crea un job esplicitamente disabilitato.
        self.assertFalse(job.abilitato)  # Verifica che lo stato venga conservato.

    def test_elemento_sorgente_di_tipo_errato_viene_rifiutato(self) -> None:
        """La collezione sorgenti non deve accettare valori arbitrari."""
        with self.assertRaisesRegex(TypeError, "SorgenteBackup"):  # Verifica che l'errore descriva il tipo richiesto.
            JobBackup("Documenti", Path("G:/Backup"), sorgenti=["C:/Dati"])  # Passa intenzionalmente una stringa al posto del modello.

    def test_nuovo_job_abilita_per_default_le_opzioni_backup(self) -> None:
        """Un nuovo job deve mantenere il comportamento storico finché l’utente non cambia le opzioni."""
        job = JobBackup("Documenti", Path("G:/Backup"))  # Crea un job senza specificare le nuove opzioni.
        self.assertTrue(job.includi_sottocartelle)  # Verifica che la scansione ricorsiva rimanga attiva per impostazione predefinita.
        self.assertTrue(job.verifica_integrita)  # Verifica che il controllo di integrità rimanga attivo per impostazione predefinita.

    def test_job_conserva_opzioni_backup_disabilitate(self) -> None:
        """Il modello deve conservare esplicitamente entrambe le opzioni quando sono disabilitate."""
        job = JobBackup(  # Crea un job specificando le nuove opzioni tramite keyword per evitare ambiguità posizionali.
            "Archivio",  # Assegna il nome leggibile del job.
            Path("G:/Backup"),  # Assegna la destinazione del job.
            includi_sottocartelle=False,  # Disabilita intenzionalmente la futura scansione ricorsiva.
            verifica_integrita=False,  # Disabilita intenzionalmente la futura verifica post-copia.
        )
        self.assertFalse(job.includi_sottocartelle)  # Verifica che il primo valore venga conservato senza conversioni.
        self.assertFalse(job.verifica_integrita)  # Verifica che il secondo valore venga conservato senza conversioni.

    def test_opzioni_backup_richiedono_booleani_reali(self) -> None:
        """Il modello non deve accettare valori ambigui al posto delle nuove opzioni booleane."""
        with self.assertRaisesRegex(TypeError, "includi_sottocartelle"):  # Verifica il rifiuto di una stringa al posto del booleano.
            JobBackup("Archivio", Path("G:/Backup"), includi_sottocartelle="false")  # Passa intenzionalmente un tipo errato.
        with self.assertRaisesRegex(TypeError, "verifica_integrita"):  # Verifica separatamente la seconda opzione.
            JobBackup("Archivio", Path("G:/Backup"), verifica_integrita=1)  # Passa intenzionalmente un intero al posto del booleano.


class TestPianificazioneBackup(unittest.TestCase):
    """Verifica il contratto dati della pianificazione associata a una singola sorgente."""

    def test_default_disabilitato_e_non_configurato(self) -> None:
        """Una nuova pianificazione non deve attivare automaticamente alcuna esecuzione."""
        pianificazione = PianificazioneBackup()
        self.assertFalse(pianificazione.abilitata)
        self.assertEqual(pianificazione.giorni, ())
        self.assertEqual(pianificazione.ora, "")

    def test_pianificazione_abilitata_valida(self) -> None:
        """Giorni 0-6 e ora HH:MM devono produrre un modello utilizzabile."""
        pianificazione = PianificazioneBackup(True, [0, 1, 4], "18:30")
        self.assertEqual(pianificazione.giorni, (0, 1, 4))
        self.assertEqual(pianificazione.ora, "18:30")

    def test_attivazione_valida_viene_conservata(self) -> None:
        """Una pianificazione nuova può dichiarare l’istante civile locale dal quale la regola diventa effettiva."""
        pianificazione = PianificazioneBackup(True, [0], "18:30", "2026-10-01T14:31:45")  # Costruisce una regola con limite temporale esplicito.
        self.assertEqual(pianificazione.attiva_dal, "2026-10-01T14:31:45")  # Verifica che il valore validato non venga alterato.

    def test_attivazione_con_formato_non_valido_viene_rifiutata(self) -> None:
        """Il limite temporale deve essere deterministico fino ai secondi per evitare confronti ambigui."""
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DDTHH:MM:SS"):  # Richiede il formato persistente documentato dal modello.
            PianificazioneBackup(True, [0], "18:30", "2026-10-01 14:31")  # Passa intenzionalmente un formato incompleto e ambiguo.

    def test_abilitata_deve_essere_booleana(self) -> None:
        """Lo stato non deve accettare stringhe o conversioni implicite."""
        with self.assertRaisesRegex(TypeError, "abilitata"):
            PianificazioneBackup("true", [0], "18:30")

    def test_giorno_booleano_viene_rifiutato(self) -> None:
        """True e False non devono essere accettati come 1 e 0 nonostante l'ereditarietà di bool da int."""
        with self.assertRaisesRegex(TypeError, "intero"):
            PianificazioneBackup(True, [True], "18:30")

    def test_giorno_fuori_intervallo_viene_rifiutato(self) -> None:
        """La settimana interna ammette esclusivamente valori da 0 a 6."""
        with self.assertRaisesRegex(ValueError, "0 e 6"):
            PianificazioneBackup(True, [7], "18:30")

    def test_giorni_duplicati_vengono_rifiutati(self) -> None:
        """Uno stesso giorno non deve produrre due trigger equivalenti."""
        with self.assertRaisesRegex(ValueError, "duplicati"):
            PianificazioneBackup(True, [0, 0], "18:30")

    def test_formato_ora_deve_essere_hh_mm_rigoroso(self) -> None:
        """Il modello deve rifiutare formati abbreviati o componenti fuori intervallo."""
        for ora_non_valida in ("9:00", "24:00", "23:60", "18:30:00"):
            with self.subTest(ora=ora_non_valida):
                with self.assertRaisesRegex(ValueError, "HH:MM"):
                    PianificazioneBackup(True, [0], ora_non_valida)

    def test_pianificazione_attiva_richiede_giorni_e_ora(self) -> None:
        """Una pianificazione abilitata ma incompleta non deve essere accettata."""
        with self.assertRaisesRegex(ValueError, "almeno un giorno"):
            PianificazioneBackup(True, [], "18:30")
        with self.assertRaisesRegex(ValueError, "specificare un'ora"):
            PianificazioneBackup(True, [0], "")

    def test_due_sorgenti_non_condividono_la_stessa_pianificazione_default(self) -> None:
        """Il default_factory deve creare un oggetto di pianificazione distinto per ogni sorgente."""
        prima = SorgenteBackup(Path("C:/Uno"), "Uno")
        seconda = SorgenteBackup(Path("C:/Due"), "Due")
        self.assertIsNot(prima.pianificazione, seconda.pianificazione)

    def test_sorgente_rifiuta_pianificazione_di_tipo_errato(self) -> None:
        """SorgenteBackup deve accettare soltanto il modello dedicato e non dizionari grezzi."""
        with self.assertRaisesRegex(TypeError, "PianificazioneBackup"):
            SorgenteBackup(Path("C:/Dati"), "Dati", pianificazione={})


if __name__ == "__main__":
    unittest.main()  # Permette di eseguire direttamente questo file oltre alla discovery dell'intera suite.
