import unittest
from pathlib import Path


class TestPlaceholderStrategie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.testo = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    def test_placeholder_professionali_presenti(self):
        attesi = (
            "Includi: estensioni o pattern, es. .txt;.pdf",
            "Escludi: pattern o percorsi, es. cartella/*",
            "Solo estensioni escluse, es. .tmp;.log",
            "Dimensione minima (byte)",
            "Dimensione massima (byte)",
            "Destinazioni aggiuntive (; separate, locale/SMB)",
        )
        for testo in attesi:
            self.assertIn(f'placeholder_text="{testo}"', self.testo)

    def test_ripristino_gui_non_inserisce_stringa_vuota_nei_campi_professionali(self):
        self.assertIn('if valore_salvato != ""', self.testo)
        self.assertNotIn('campo.delete(0, "end"); campo.insert(0, self.valori_strategia_gui.get(chiave, ""))', self.testo)


if __name__ == "__main__":
    unittest.main()
