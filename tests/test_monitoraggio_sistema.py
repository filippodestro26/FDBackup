import unittest  # Importa il framework standard già usato dal progetto.
from collections import namedtuple  # Importa namedtuple per simulare il risultato di shutil.disk_usage.
from unittest.mock import patch  # Importa patch per isolare i test dal computer reale.

from fdbackup.monitoraggio_sistema import InformazioniUnita, formatta_dimensione, rileva_unita_windows  # Importa il componente da verificare.


class TestMonitoraggioSistema(unittest.TestCase):
    """Verifica il rilevamento delle unità senza dipendere dai dischi realmente presenti sul computer."""

    def test_formatta_dimensione_binaria(self) -> None:
        """La formattazione deve usare multipli binari coerenti con 1024."""
        self.assertEqual(formatta_dimensione(0), "0 B")  # Verifica il caso nullo.
        self.assertEqual(formatta_dimensione(1024), "1.0 KiB")  # Verifica il primo multiplo binario.
        self.assertEqual(formatta_dimensione(1024 ** 3), "1.0 GiB")  # Verifica una capacità tipica mostrata nella Home.

    def test_formatta_dimensione_none(self) -> None:
        """Una misura non disponibile non deve essere trasformata in un valore numerico inventato."""
        self.assertEqual(formatta_dimensione(None), "Non disponibile")  # Verifica il testo neutro previsto.

    def test_formatta_dimensione_rifiuta_valori_non_validi(self) -> None:
        """Il contratto deve rifiutare booleani, tipi errati e valori negativi."""
        with self.assertRaises(TypeError):  # Verifica che bool non venga accettato come int implicito.
            formatta_dimensione(True)  # Passa intenzionalmente un tipo ambiguo.
        with self.assertRaises(ValueError):  # Verifica che una dimensione negativa sia rifiutata.
            formatta_dimensione(-1)  # Passa intenzionalmente un valore impossibile.

    def test_frazione_utilizzata(self) -> None:
        """La frazione usata deve essere direttamente compatibile con una progress bar 0..1."""
        unita = InformazioniUnita("C:\\", 1000, 250, 750)  # Costruisce un'unità controllata al 25 percento.
        self.assertAlmostEqual(unita.frazione_utilizzata, 0.25)  # Verifica il rapporto tra usato e totale.

    def test_unita_inaccessibile_ha_frazione_zero(self) -> None:
        """Un'unità non leggibile deve rimanere rappresentabile senza produrre divisioni o valori falsi."""
        unita = InformazioniUnita("Z:\\", None, None, None, "OSError: non disponibile")  # Simula una rete scollegata.
        self.assertFalse(unita.accessibile)  # Verifica lo stato esplicito di indisponibilità.
        self.assertEqual(unita.frazione_utilizzata, 0.0)  # Verifica il valore neutro per la barra.

    def test_rileva_piu_unita_accessibili(self) -> None:
        """Ogni lettera restituita dal sistema deve produrre statistiche indipendenti."""
        Utilizzo = namedtuple("Utilizzo", "total used free")  # Riproduce il contratto documentato di disk_usage.
        with patch("fdbackup.monitoraggio_sistema.os.listdrives", create=True, return_value=["C:\\", "D:\\"]), patch("fdbackup.monitoraggio_sistema.shutil.disk_usage", side_effect=[Utilizzo(100, 40, 60), Utilizzo(200, 50, 150)]):  # Simula due unità senza usare il filesystem reale.
            unita = rileva_unita_windows()  # Esegue il rilevamento controllato.
        self.assertEqual([elemento.percorso for elemento in unita], ["C:\\", "D:\\"])  # Verifica ordine e percorsi.
        self.assertEqual(unita[0].libero, 60)  # Verifica i dati della prima unità.
        self.assertEqual(unita[1].totale, 200)  # Verifica i dati della seconda unità.

    def test_unita_inaccessibile_non_blocca_le_altre(self) -> None:
        """Un errore su una lettera deve essere isolato e non eliminare le altre unità."""
        Utilizzo = namedtuple("Utilizzo", "total used free")  # Riproduce il risultato di disk_usage.
        with patch("fdbackup.monitoraggio_sistema.os.listdrives", create=True, return_value=["C:\\", "Z:\\"]), patch("fdbackup.monitoraggio_sistema.shutil.disk_usage", side_effect=[Utilizzo(100, 40, 60), OSError("rete non disponibile")]):  # Simula una rete scollegata dopo un disco valido.
            unita = rileva_unita_windows()  # Esegue il rilevamento.
        self.assertTrue(unita[0].accessibile)  # Conferma che il disco valido rimanga utilizzabile.
        self.assertFalse(unita[1].accessibile)  # Conferma che l'errore sia rappresentato nel modello.
        self.assertIn("rete non disponibile", unita[1].errore)  # Mantiene il dettaglio diagnostico senza sollevare l'eccezione.


if __name__ == "__main__":  # Consente anche l'esecuzione diretta del file di test.
    unittest.main()  # Avvia unittest quando il file viene eseguito direttamente.
