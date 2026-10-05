import os  # Importa il rilevamento della piattaforma per limitare l'integrazione all'ambiente Windows previsto.
import sys  # Importa il percorso dell'interprete Python usato dall'istanza corrente di FDBackup.
from pathlib import Path  # Importa Path per costruire percorsi assoluti e individuare pythonw.exe.

try:  # Tenta di importare l'API del Registro disponibile nella libreria standard soltanto su Windows.
    import winreg  # Importa l'accesso nativo al Registro di Windows senza dipendenze esterne.
except ImportError:  # Consente l'importazione del modulo anche negli ambienti di sviluppo e test non Windows.
    winreg = None  # Mantiene un valore esplicito che le funzioni pubbliche possono riconoscere prima di usare il Registro.


NOME_ATTIVITA = "FDBackup_AvvioAutomatico"  # Identifica la voce di avvio automatico con il nome pubblico corrente.
NOME_ATTIVITA_PRECEDENTE = "BackupCore_AvvioAutomatico"  # Consente di riconoscere e rimuovere la voce creata dalle versioni precedenti.
PERCORSO_CHIAVE_AVVIO = r"Software\Microsoft\Windows\CurrentVersion\Run"  # Usa la chiave Run dell'utente corrente documentata da Microsoft per l'avvio a ogni accesso.
LUNGHEZZA_MASSIMA_COMANDO_RUN = 260  # Rispetta il limite documentato da Microsoft per la riga di comando memorizzata nelle chiavi Run e RunOnce.


def _interprete_senza_console() -> Path:
    """Restituisce pythonw.exe quando disponibile, mantenendo l'interprete corrente negli altri casi."""
    interprete = Path(sys.executable).resolve()  # Normalizza l'interprete realmente usato da FDBackup.

    if os.name == "nt" and interprete.name.lower() in {"python.exe", "python3.exe"}:  # Riconosce l'esecuzione Python standard su Windows.
        candidato = interprete.with_name("pythonw.exe")  # Costruisce il percorso dell'interprete equivalente privo di console.

        if candidato.is_file():  # Verifica che l'installazione corrente includa realmente pythonw.exe.
            return candidato  # Preferisce l'interprete grafico per evitare finestre console all'accesso.

    return interprete  # Mantiene l'eseguibile corrente per ambienti virtuali, build future o test.


def costruisci_comando_avvio(percorso_programma: Path) -> str:
    """Costruisce la riga di comando registrata per l'avvio automatico dell'utente corrente."""
    percorso_programma = Path(percorso_programma).resolve()  # Normalizza il file principale prima di inserirlo nel Registro.
    interprete = _interprete_senza_console()  # Seleziona l'interprete più adatto all'avvio grafico.

    comando_avvio = f'"{interprete}" "{percorso_programma}" --background'  # Quota entrambi i percorsi per supportare correttamente eventuali spazi nei nomi.

    if len(comando_avvio) > LUNGHEZZA_MASSIMA_COMANDO_RUN:  # Verifica il limite specifico imposto da Windows alle command line delle chiavi Run.
        raise OSError(
            f"Impossibile abilitare l'avvio automatico: il comando supera il limite Windows di "
            f"{LUNGHEZZA_MASSIMA_COMANDO_RUN} caratteri."
        )  # Evita di salvare una voce di avvio non conforme.

    return comando_avvio  # Restituisce soltanto una command line già validata.


def _verifica_supporto_windows() -> None:
    """Verifica che il Registro di Windows sia disponibile prima di eseguire operazioni di scrittura."""
    if os.name != "nt" or winreg is None:  # Riconosce piattaforme sulle quali l'integrazione Windows non è utilizzabile.
        raise OSError(
            "L'avvio automatico di FDBackup è disponibile soltanto su Windows."
        )  # Espone un errore previsto e già gestito dalla GUI.


def abilita_avvio_automatico(percorso_programma: Path) -> None:
    """Registra FDBackup nella chiave Run dell'utente corrente per avviarlo a ogni accesso Windows."""
    _verifica_supporto_windows()  # Impedisce l'accesso a costanti e API winreg quando il modulo viene eseguito fuori da Windows.

    comando_avvio = costruisci_comando_avvio(percorso_programma)  # Prepara e valida la command line assoluta da memorizzare.

    try:  # Traduce gli errori del Registro in un messaggio contestualizzato per la GUI.
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            PERCORSO_CHIAVE_AVVIO,
            0,
            winreg.KEY_SET_VALUE,
        ) as chiave_avvio:  # Apre o crea esclusivamente la chiave Run dell'utente corrente con i soli diritti necessari alla scrittura.

            winreg.SetValueEx(
                chiave_avvio,
                NOME_ATTIVITA,
                0,
                winreg.REG_SZ,
                comando_avvio,
            )  # Crea o aggiorna soltanto il valore dedicato a FDBackup senza modificare le altre applicazioni di avvio.
            try:
                winreg.DeleteValue(chiave_avvio, NOME_ATTIVITA_PRECEDENTE)
            except FileNotFoundError:
                pass  # La voce storica può non essere presente nelle installazioni nuove.

    except OSError as errore:  # Intercetta permessi, policy o altri errori restituiti dall'API nativa del Registro.
        raise OSError(
            f"Impossibile abilitare l'avvio automatico: {errore}"
        ) from errore  # Mantiene la causa originale e fornisce alla GUI un messaggio comprensibile.


def disabilita_avvio_automatico() -> None:
    """Rimuove soltanto il valore di FDBackup dalla chiave Run dell'utente corrente in modo idempotente."""
    _verifica_supporto_windows()  # Verifica la disponibilità dell'integrazione Windows prima di aprire il Registro.

    try:  # Gestisce separatamente l'assenza della voce e gli errori reali di accesso.
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            PERCORSO_CHIAVE_AVVIO,
            0,
            winreg.KEY_SET_VALUE,
        ) as chiave_avvio:  # Apre la chiave Run con il solo diritto necessario a eliminare un valore.

            try:  # Isola il caso normale in cui FDBackup è già disabilitato.
                winreg.DeleteValue(
                    chiave_avvio,
                    NOME_ATTIVITA,
                )  # Elimina esclusivamente il valore dedicato a FDBackup.

            except FileNotFoundError:  # Riconosce una voce corrente già assente.
                pass

            try:
                winreg.DeleteValue(chiave_avvio, NOME_ATTIVITA_PRECEDENTE)
            except FileNotFoundError:
                pass  # La disattivazione resta idempotente anche dopo il cambio di nome.

    except FileNotFoundError:  # Riconosce anche il caso limite in cui la chiave Run non esista ancora nel profilo corrente.
        return  # Considera correttamente l'avvio automatico già disabilitato.

    except OSError as errore:  # Intercetta soltanto errori reali di accesso o policy del Registro.
        raise OSError(
            f"Impossibile disabilitare l'avvio automatico: {errore}"
        ) from errore  # Propaga un errore contestualizzato già gestito dalla GUI.


def avvio_automatico_attivo() -> bool:
    """Restituisce True soltanto quando esiste una voce Run valida e non vuota dedicata a FDBackup."""
    if os.name != "nt" or winreg is None:  # Riconosce gli ambienti di sviluppo e test non Windows.
        return False  # Non dichiara attiva una funzionalità che la piattaforma non possiede.

    try:  # Legge esclusivamente la voce di FDBackup senza enumerare o modificare altre startup app.
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            PERCORSO_CHIAVE_AVVIO,
            0,
            winreg.KEY_QUERY_VALUE,
        ) as chiave_avvio:  # Apre la chiave con il solo diritto di interrogazione necessario.

            try:
                comando_avvio, tipo_valore = winreg.QueryValueEx(chiave_avvio, NOME_ATTIVITA)
            except FileNotFoundError:
                comando_avvio, tipo_valore = winreg.QueryValueEx(chiave_avvio, NOME_ATTIVITA_PRECEDENTE)

    except OSError:  # Comprende sia voce assente sia chiave non disponibile, mantenendo sicuro il caricamento della schermata Impostazioni.
        return False  # Mostra il checkbox disattivato quando non è possibile confermare una registrazione valida.

    return (
        tipo_valore == winreg.REG_SZ
        and isinstance(comando_avvio, str)
        and bool(comando_avvio.strip())
    )  # Accetta soltanto una stringa REG_SZ effettivamente utilizzabile come comando di avvio.