import unittest
from pathlib import Path


class TestBrandingFDBackup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.radice = Path(__file__).resolve().parents[1]
        cls.gui = (cls.radice / "main.py").read_text(encoding="utf-8")

    def test_branding_pubblico_fdbackup(self):
        self.assertIn("FDBackup", self.gui)
        self.assertNotIn("BackupCore", self.gui)

    def test_retention_ha_etichette_esplicite(self):
        self.assertIn('text="Retention"', self.gui)
        for testo in ("Giornalieri", "Settimanali", "Mensili", "Annuali"):
            self.assertIn(f'(\"{testo}\",', self.gui)
        self.assertNotIn('text="G / S / M / A"', self.gui)

    def test_placeholder_strategie_non_vengono_cancellati_al_ritorno_nel_menu(self):
        blocco = self.gui[self.gui.index("if self.valori_strategia_gui:"):self.gui.index('if self.operazione_avanzata_in_corso == "strategie"')]
        for chiave in ("includi", "escludi", "estensioni", "minimo", "massimo", "destinazioni_extra"):
            self.assertIn(f'"{chiave}"', blocco)
        self.assertIn('valore_salvato = self.valori_strategia_gui.get(chiave, "")', blocco)
        self.assertIn('if valore_salvato != ""', blocco)
        self.assertIn('campo.delete(0, "end")', blocco)
        self.assertNotIn('campo.insert(0, self.valori_strategia_gui.get(chiave, ""))  # Reinserisce esattamente il valore precedente.', blocco)

    def test_sorgente_e_destinazione_vuote_preservano_i_placeholder_dopo_navigazione(self):
        blocco = self.gui[self.gui.index("if self.valori_strategia_gui:"):self.gui.index('self.variabile_metodo_strategia.set')]
        self.assertIn('(self.campo_strategia_sorgente, "sorgente")', blocco)
        self.assertIn('(self.campo_strategia_destinazione, "destinazione")', blocco)
        self.assertIn('if valore_salvato != ""', blocco)


if __name__ == "__main__":
    unittest.main()
