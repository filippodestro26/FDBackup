import tempfile  # Importa directory temporanee isolate per non creare lock nel progetto reale.
import unittest  # Importa il framework standard della suite FDBackup.
from pathlib import Path  # Importa Path per costruire il file di lock temporaneo.

from fdbackup.blocco_operazione import BloccoFile  # Importa il lock interprocesso reale usato da GUI e scheduler.


class TestBloccoFile(unittest.TestCase):
    """Verifica l'esclusione reciproca e il rilascio idempotente del lock condiviso."""

    def test_prima_istanza_acquisisce_il_lock(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola il file di lock dal progetto reale.
            blocco = BloccoFile(Path(cartella) / "operazione.lock")  # Crea una singola istanza sul file temporaneo.
            try:  # Garantisce il rilascio anche se un'asserzione fallisce.
                self.assertTrue(blocco.acquisisci())  # Verifica che un lock libero possa essere acquisito.
                self.assertTrue(blocco.acquisito)  # Verifica lo stato pubblico dell'istanza.
            finally:  # Esegue sempre la pulizia del descrittore.
                blocco.rilascia()  # Rilascia il lock temporaneo.

    def test_seconda_istanza_non_acquisisce_lo_stesso_lock(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola il test dal filesystem reale.
            percorso = Path(cartella) / "operazione.lock"  # Condivide esattamente lo stesso file tra due istanze.
            primo = BloccoFile(percorso)  # Prepara il primo proprietario.
            secondo = BloccoFile(percorso)  # Prepara il concorrente.
            try:  # Garantisce il rilascio di entrambe le istanze.
                self.assertTrue(primo.acquisisci())  # Acquisisce il lock con la prima istanza.
                self.assertFalse(secondo.acquisisci())  # Verifica che la seconda non possa sovrapporsi.
            finally:  # Pulisce sempre i descrittori aperti.
                secondo.rilascia()  # È sicuro anche quando l'acquisizione non è riuscita.
                primo.rilascia()  # Libera il lock posseduto dalla prima istanza.

    def test_lock_diventa_disponibile_dopo_il_rilascio(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola il file temporaneo.
            percorso = Path(cartella) / "operazione.lock"  # Costruisce il percorso condiviso.
            primo = BloccoFile(percorso)  # Crea il primo proprietario.
            secondo = BloccoFile(percorso)  # Crea il secondo proprietario potenziale.
            self.assertTrue(primo.acquisisci())  # Occupa inizialmente il lock.
            primo.rilascia()  # Libera esplicitamente la risorsa.
            try:  # Garantisce il rilascio della seconda istanza.
                self.assertTrue(secondo.acquisisci())  # Verifica che il lock possa essere riutilizzato immediatamente.
            finally:  # Pulisce il descrittore del secondo proprietario.
                secondo.rilascia()  # Rilascia il lock.

    def test_rilascio_ripetuto_e_sicuro(self):
        with tempfile.TemporaryDirectory() as cartella:  # Isola il file di lock.
            blocco = BloccoFile(Path(cartella) / "operazione.lock")  # Crea una nuova istanza.
            blocco.rilascia()  # Verifica implicitamente che il rilascio senza acquisizione non sollevi errori.
            self.assertTrue(blocco.acquisisci())  # Acquisisce normalmente dopo il rilascio vuoto.
            blocco.rilascia()  # Rilascia una prima volta.
            blocco.rilascia()  # Rilascia una seconda volta senza errore.
            self.assertFalse(blocco.acquisito)  # Conferma lo stato finale libero.


if __name__ == "__main__":  # Permette l'esecuzione diretta del file di test.
    unittest.main()  # Avvia unittest quando richiesto come script.
