import unittest  # Importa il framework standard già usato dalla suite FDBackup.
from pathlib import Path  # Importa Path per costruire un percorso di programma deterministico.
from unittest.mock import MagicMock, call, patch  # Importa i mock necessari a isolare completamente i test dal Registro reale di Windows.

from fdbackup.avvio_automatico import (
    LUNGHEZZA_MASSIMA_COMANDO_RUN,
    NOME_ATTIVITA,
    NOME_ATTIVITA_PRECEDENTE,
    PERCORSO_CHIAVE_AVVIO,
    abilita_avvio_automatico,
    avvio_automatico_attivo,
    costruisci_comando_avvio,
    disabilita_avvio_automatico,
)  # Importa l'API pubblica e le costanti da verificare.


class TestAvvioAutomatico(unittest.TestCase):
    """Verifica l'integrazione con la chiave Run senza modificare il Registro reale del sistema operativo."""

    @staticmethod
    def _winreg_simulato() -> MagicMock:
        """Crea un oggetto winreg simulato con costanti stabili e context manager compatibili con l'implementazione reale."""
        registro = MagicMock()  # Crea il sostituto completo del modulo winreg.
        registro.HKEY_CURRENT_USER = object()  # Simula l'hive per-utente senza dipendere da Windows.
        registro.KEY_SET_VALUE = 0x0002  # Riproduce un valore simbolico sufficiente a verificare gli argomenti delle chiamate.
        registro.KEY_QUERY_VALUE = 0x0001  # Riproduce il diritto di sola interrogazione usato dalla query.
        registro.REG_SZ = 1  # Riproduce il tipo stringa usato per la command line di avvio.

        return registro  # Restituisce il modulo simulato pronto per i singoli test.

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    @patch(
        "fdbackup.avvio_automatico.costruisci_comando_avvio",
        return_value='"pythonw.exe" "C:\\FDBackup\\main.py" --background',
    )
    def test_abilitazione_scrive_solo_valore_run_utente_corrente(
        self,
        costruisci,
    ) -> None:
        """L'abilitazione deve creare o aggiornare soltanto la voce FDBackup sotto HKCU Run."""
        registro = self._winreg_simulato()  # Prepara un Registro completamente simulato.
        chiave = MagicMock()  # Simula l'handle restituito da CreateKeyEx.

        registro.CreateKeyEx.return_value.__enter__.return_value = chiave  # Fa restituire l'handle dal context manager usato dal codice reale.

        with patch(
            "fdbackup.avvio_automatico.winreg",
            registro,
        ):  # Sostituisce winreg soltanto per la durata del test.
            abilita_avvio_automatico(
                Path("main.py")
            )  # Richiede l'abilitazione senza toccare il Registro del computer.

        costruisci.assert_called_once_with(
            Path("main.py")
        )  # Verifica che venga usato il percorso ricevuto dall'API pubblica.

        registro.CreateKeyEx.assert_called_once_with(
            registro.HKEY_CURRENT_USER,
            PERCORSO_CHIAVE_AVVIO,
            0,
            registro.KEY_SET_VALUE,
        )  # Verifica hive, percorso e diritto minimo di scrittura.

        registro.SetValueEx.assert_called_once_with(
            chiave,
            NOME_ATTIVITA,
            0,
            registro.REG_SZ,
            '"pythonw.exe" "C:\\FDBackup\\main.py" --background',
        )  # Verifica nome, tipo e comando registrati.

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    def test_query_restituisce_true_per_voce_reg_sz_valida(self) -> None:
        """La preferenza grafica deve risultare attiva soltanto per una command line REG_SZ non vuota."""
        registro = self._winreg_simulato()  # Prepara il Registro simulato.
        chiave = MagicMock()  # Simula l'handle di sola lettura.

        registro.OpenKey.return_value.__enter__.return_value = chiave  # Collega l'handle al context manager.

        registro.QueryValueEx.return_value = (
            '"pythonw.exe" "C:\\FDBackup\\main.py" --background',
            registro.REG_SZ,
        )  # Simula una voce valida realmente presente.

        with patch(
            "fdbackup.avvio_automatico.winreg",
            registro,
        ):  # Isola la query dal Registro reale.
            self.assertTrue(
                avvio_automatico_attivo()
            )  # Verifica lo stato positivo atteso.

        registro.OpenKey.assert_called_once_with(
            registro.HKEY_CURRENT_USER,
            PERCORSO_CHIAVE_AVVIO,
            0,
            registro.KEY_QUERY_VALUE,
        )  # Verifica l'uso del solo diritto di interrogazione.

        registro.QueryValueEx.assert_called_once_with(
            chiave,
            NOME_ATTIVITA,
        )  # Verifica che venga interrogata soltanto la voce FDBackup.

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    def test_query_restituisce_false_quando_voce_assente(self) -> None:
        """Una voce inesistente deve essere rappresentata come avvio automatico disattivato senza errori GUI."""
        registro = self._winreg_simulato()  # Prepara il Registro simulato.

        registro.OpenKey.side_effect = FileNotFoundError(
            "voce assente"
        )  # Simula l'assenza della chiave o della voce di avvio.

        with patch(
            "fdbackup.avvio_automatico.winreg",
            registro,
        ):  # Isola la lettura dal sistema reale.
            self.assertFalse(
                avvio_automatico_attivo()
            )  # Verifica il fallback neutro previsto.

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    def test_disabilitazione_elimina_solo_valori_fdbackup(self) -> None:
        """La disattivazione deve eliminare la singola voce senza rimuovere la chiave Run o altre applicazioni."""
        registro = self._winreg_simulato()  # Prepara il Registro simulato.
        chiave = MagicMock()  # Simula l'handle aperto in scrittura.

        registro.OpenKey.return_value.__enter__.return_value = chiave  # Collega l'handle al context manager.

        with patch(
            "fdbackup.avvio_automatico.winreg",
            registro,
        ):  # Impedisce qualunque accesso al Registro reale.
            disabilita_avvio_automatico()  # Richiede la disattivazione attraverso l'API pubblica.

        registro.OpenKey.assert_called_once_with(
            registro.HKEY_CURRENT_USER,
            PERCORSO_CHIAVE_AVVIO,
            0,
            registro.KEY_SET_VALUE,
        )  # Verifica il percorso e il diritto minimo richiesto.

        self.assertEqual(
            registro.DeleteValue.call_args_list,
            [
                call(chiave, NOME_ATTIVITA),
                call(chiave, NOME_ATTIVITA_PRECEDENTE),
            ],
        )  # Verifica che vengano eliminate soltanto le due voci appartenenti all'applicazione.

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    def test_disabilitazione_e_idempotente_quando_voce_assente(self) -> None:
        """Disabilitare una configurazione già assente non deve essere trattato come errore."""
        registro = self._winreg_simulato()  # Prepara il Registro simulato.

        registro.OpenKey.side_effect = FileNotFoundError(
            "chiave assente"
        )  # Simula un profilo nel quale la chiave non sia disponibile.

        with patch(
            "fdbackup.avvio_automatico.winreg",
            registro,
        ):  # Isola il test dal sistema reale.
            disabilita_avvio_automatico()  # Verifica che l'operazione termini normalmente.

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    def test_errore_scrittura_viene_esposto_come_oserror_contestualizzato(
        self,
    ) -> None:
        """Un blocco per permessi o policy deve arrivare alla GUI come OSError comprensibile."""
        registro = self._winreg_simulato()  # Prepara il Registro simulato.

        registro.CreateKeyEx.side_effect = PermissionError(
            "Accesso negato"
        )  # Simula una policy Windows che impedisce la scrittura.

        with patch(
            "fdbackup.avvio_automatico.winreg",
            registro,
        ), patch(
            "fdbackup.avvio_automatico.costruisci_comando_avvio",
            return_value='"pythonw.exe" "C:\\FDBackup\\main.py" --background',
        ):  # Isola sia Registro sia costruzione del comando.

            with self.assertRaisesRegex(
                OSError,
                "Impossibile abilitare l'avvio automatico.*Accesso negato",
            ):  # Verifica il messaggio che verrà mostrato dalla GUI.
                abilita_avvio_automatico(
                    Path("main.py")
                )  # Esegue il percorso di errore controllato.

    @patch(
        "fdbackup.avvio_automatico._interprete_senza_console",
        return_value=Path("C:/Python/pythonw.exe"),
    )
    def test_comando_avvio_contiene_background_e_virgolette(
        self,
        _interprete,
    ) -> None:
        """La command line deve preservare percorsi con spazi e avviare FDBackup direttamente nella tray."""
        comando = costruisci_comando_avvio(
            Path("C:/Backup Core/main.py")
        )  # Costruisce un comando usando intenzionalmente un percorso con spazi.

        self.assertTrue(
            comando.startswith(f'"{Path("C:/Python/pythonw.exe")}" ')
        )  # Verifica che l'interprete sia racchiuso tra virgolette senza imporre separatori specifici della piattaforma di test.

        self.assertGreaterEqual(
            comando.count('"'),
            4,
        )  # Verifica che interprete e percorso del programma siano entrambi racchiusi tra virgolette.

        self.assertTrue(
            comando.endswith("--background")
        )  # Verifica che l'avvio automatico non mostri inizialmente la finestra principale.

    @patch("fdbackup.avvio_automatico._interprete_senza_console")
    def test_comando_run_oltre_limite_windows_viene_rifiutato(
        self,
        interprete,
    ) -> None:
        """Una command line oltre 260 caratteri non deve essere registrata come configurazione apparentemente valida."""
        interprete.return_value = Path(
            "C:/" + ("p" * LUNGHEZZA_MASSIMA_COMANDO_RUN) + "/pythonw.exe"
        )  # Forza un interprete abbastanza lungo da superare sicuramente il limite documentato.

        with self.assertRaisesRegex(
            OSError,
            "260 caratteri",
        ):  # Verifica un errore già compatibile con la gestione della GUI.
            costruisci_comando_avvio(
                Path("C:/FDBackup/main.py")
            )  # Tenta di costruire la command line non conforme.

    @patch("fdbackup.avvio_automatico.os.name", "posix")
    def test_fuori_da_windows_query_false_e_scrittura_rifiutata(self) -> None:
        """Il modulo deve restare importabile nei test non Windows senza dichiarare disponibile l'integrazione nativa."""
        self.assertFalse(
            avvio_automatico_attivo()
        )  # Verifica il risultato neutro della sola query.

        with self.assertRaisesRegex(
            OSError,
            "soltanto su Windows",
        ):  # Verifica l'errore esplicito delle operazioni di modifica.
            abilita_avvio_automatico(
                Path("main.py")
            )  # Tenta intenzionalmente una scrittura fuori dalla piattaforma supportata.

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    def test_query_riconosce_voce_storica_dopo_rename(self) -> None:
        """La preferenza resta attiva se Windows contiene ancora la voce creata dalla versione precedente."""
        registro = self._winreg_simulato()
        chiave = MagicMock()
        registro.OpenKey.return_value.__enter__.return_value = chiave
        registro.QueryValueEx.side_effect = [
            FileNotFoundError("voce corrente assente"),
            ('"pythonw.exe" "C:\\FDBackup\\main.py" --background', registro.REG_SZ),
        ]
        with patch("fdbackup.avvio_automatico.winreg", registro):
            self.assertTrue(avvio_automatico_attivo())
        self.assertEqual(
            registro.QueryValueEx.call_args_list,
            [call(chiave, NOME_ATTIVITA), call(chiave, NOME_ATTIVITA_PRECEDENTE)],
        )

    @patch("fdbackup.avvio_automatico.os.name", "nt")
    @patch("fdbackup.avvio_automatico.costruisci_comando_avvio", return_value='"pythonw.exe" "C:\\FDBackup\\main.py" --background')
    def test_abilitazione_rimuove_voce_storica_dopo_rename(self, costruisci) -> None:
        """L'abilitazione col nuovo nome evita un doppio avvio rimuovendo la vecchia voce applicativa."""
        registro = self._winreg_simulato()
        chiave = MagicMock()
        registro.CreateKeyEx.return_value.__enter__.return_value = chiave
        with patch("fdbackup.avvio_automatico.winreg", registro):
            abilita_avvio_automatico(Path("main.py"))
        registro.SetValueEx.assert_called_once_with(
            chiave, NOME_ATTIVITA, 0, registro.REG_SZ, '"pythonw.exe" "C:\\FDBackup\\main.py" --background'
        )
        registro.DeleteValue.assert_called_once_with(chiave, NOME_ATTIVITA_PRECEDENTE)



if __name__ == "__main__":  # Consente l'esecuzione diretta del file durante lo sviluppo.
    unittest.main()  # Avvia unittest quando richiesto come script.