"""Regressioni UX introdotte dopo la validazione manuale del candidato 344."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from fdbackup.filtri_backup import FiltroBackup
from fdbackup.gestore_backup_avanzato import GestoreBackupAvanzato, StrategiaBackupAvanzato
from fdbackup.notifiche_windows import mostra_notifica_testo
from fdbackup.politiche_avanzate import GestoreAffidabilita, crea_dashboard


class TestCorrezioniUx345(unittest.TestCase):
    def test_include_estensione_senza_asterisco(self):
        filtro = FiltroBackup(includi=(".txt",))
        self.assertTrue(filtro.accetta("cartella/documento.txt", 10))
        self.assertFalse(filtro.accetta("cartella/foto.png", 10))

    def test_exclude_estensione_senza_asterisco(self):
        filtro = FiltroBackup(escludi=(".log",))
        self.assertFalse(filtro.accetta("cartella/app.log", 10))
        self.assertTrue(filtro.accetta("cartella/documento.txt", 10))

    def test_valutazione_restituisce_motivo_estensione(self):
        filtro = FiltroBackup(estensioni_escluse=(".tmp",))
        self.assertEqual(filtro.valuta("temporaneo.tmp", 3), (False, "estensione"))

    def test_valutazione_restituisce_motivo_dimensione(self):
        filtro = FiltroBackup(dimensione_minima=10, dimensione_massima=100)
        self.assertEqual(filtro.valuta("piccolo.bin", 9), (False, "dimensione_minima"))
        self.assertEqual(filtro.valuta("grande.bin", 101), (False, "dimensione_massima"))

    def test_backup_emette_eventi_inclusi_ed_esclusi(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp); sorgente = radice / "src"; repo = radice / "repo"; sorgente.mkdir()
            (sorgente / "ok.txt").write_text("ok", encoding="utf-8")
            (sorgente / "no.log").write_text("no", encoding="utf-8")
            eventi = []
            gestore = GestoreBackupAvanzato(threading.Event(), lambda evento, dati: eventi.append((evento, dati)))
            risultato = gestore.esegui_strategia(sorgente, repo, StrategiaBackupAvanzato(metodo="completo", filtro=FiltroBackup(escludi=(".log",))))
            self.assertTrue(risultato.successo)
            self.assertTrue(any(e == "file_incluso" and d["file"] == "ok.txt" for e, d in eventi))
            self.assertTrue(any(e == "file_escluso" and d["file"] == "no.log" and d["motivo"] == "pattern_esclusione" for e, d in eventi))

    def test_nuove_versioni_non_creano_manifesto_pubblico(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp); sorgente = radice / "src"; repo = radice / "repo"; sorgente.mkdir()
            (sorgente / "a.txt").write_text("a", encoding="utf-8")
            risultato = GestoreBackupAvanzato().esegui_strategia(sorgente, repo, StrategiaBackupAvanzato(metodo="completo"))
            self.assertTrue(risultato.successo)
            cartella = GestoreBackupAvanzato._trova_cartella_versione(repo, risultato.manifesto.id_backup)
            self.assertIsNotNone(cartella)
            self.assertFalse((cartella / "manifesto.json").exists())
            self.assertTrue((cartella / ".backupcore-manifesto.json").is_file())

    def test_verifica_non_crea_report_se_non_richiesto(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp); sorgente = radice / "src"; repo = radice / "repo"; sorgente.mkdir()
            (sorgente / "a.txt").write_text("a", encoding="utf-8")
            risultato = GestoreBackupAvanzato().esegui_strategia(sorgente, repo, StrategiaBackupAvanzato(metodo="completo"))
            report = GestoreAffidabilita().verifica(repo, risultato.manifesto.id_backup)
            self.assertEqual(report.stato, "verificato")
            self.assertFalse((repo / "_report_verifica").exists())

    def test_dashboard_espone_stato_versioni(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp); sorgente = radice / "src"; repo = radice / "repo"; sorgente.mkdir()
            (sorgente / "a.txt").write_text("a", encoding="utf-8")
            GestoreBackupAvanzato().esegui_strategia(sorgente, repo, StrategiaBackupAvanzato(metodo="completo"))
            dashboard = crea_dashboard(repo)
            self.assertEqual(dashboard["anomalie"], 0)
            self.assertEqual(dashboard["dettagli"][0]["stato"], "verificato")

    def test_notifica_testo_rifiuta_testo_vuoto(self):
        with self.assertRaises(ValueError):
            mostra_notifica_testo("", "messaggio")
        with self.assertRaises(ValueError):
            mostra_notifica_testo("Titolo", "")


if __name__ == "__main__":
    unittest.main()
