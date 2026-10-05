import logging  # Importa il logging standard per registrare eventuali problemi senza interrompere il backup.
import os  # Importa il rilevamento della piattaforma per limitare le notifiche native a Windows.

from fdbackup.cronologia_backup import RecordOperazione  # Importa il modello strutturato già usato dalla cronologia persistente.


logger = logging.getLogger("fdbackup.notifiche")  # Usa un logger figlio coerente con il resto dell'applicazione.


def crea_testo_notifica(record: RecordOperazione) -> tuple[str, str]:
    """Costruisce titolo e corpo sintetici della notifica a partire dall'esito persistito reale."""
    if not isinstance(record, RecordOperazione):  # Impedisce di notificare strutture non validate o dizionari arbitrari.
        raise TypeError("La notifica richiede un RecordOperazione valido.")  # Mantiene un contratto esplicito e testabile.
    etichetta_stato = {"successo": "completato", "problemi": "completato con problemi", "fallito": "fallito", "annullato": "annullato"}[record.stato]  # Traduce lo stato tecnico in un testo leggibile.
    titolo = f"FDBackup • {etichetta_stato}"  # Mantiene sempre riconoscibile l'applicazione nella notifica di Windows.
    corpo = f"{record.descrizione}\nCopiati: {record.file_copiati} • Identici: {record.file_ignorati} • Falliti: {record.file_falliti}"  # Mostra i contatori più utili senza sovraccaricare il banner.
    if record.problemi:  # Aggiunge un'indicazione sintetica quando il record contiene problemi reali.
        corpo += f"\nProblema: {record.problemi[0]}"  # Limita il banner al primo problema; i dettagli completi restano nella cronologia.
    return titolo, corpo  # Restituisce dati puri così la formattazione può essere verificata senza Windows.


def mostra_notifica_windows(record: RecordOperazione) -> bool:
    """Mostra una notifica Windows e restituisce False se la piattaforma o il sottosistema non sono disponibili."""
    if os.name != "nt":  # Evita di importare componenti Windows su Linux/macOS e negli ambienti di test non Windows.
        return False  # La mancata notifica non deve mai modificare l'esito del backup.
    try:  # Isola completamente la funzione cosmetica dal runner automatico.
        from winotify import Notification  # Importa pigramente la libreria pura Python soltanto quando serve davvero su Windows.
        titolo, corpo = crea_testo_notifica(record)  # Costruisce il contenuto esclusivamente dai dati già validati e persistiti.
        notifica = Notification(app_id="FDBackup", title=titolo, msg=corpo)  # Crea una toast destinata al sistema notifiche di Windows.
        notifica.show()  # Affida a Windows posizione, durata e Centro notifiche invece di creare un popup grafico proprietario.
        return True  # Comunica al chiamante che la richiesta di visualizzazione è stata inviata correttamente.
    except Exception as errore:  # Cattura anche problemi del sottosistema notifiche o della libreria opzionale.
        logger.warning("Notifica Windows non disponibile: %s: %s", type(errore).__name__, errore)  # Registra il problema senza produrre un secondo errore operativo.
        return False  # Mantiene il backup riuscito anche se Windows non può mostrare il banner.


def mostra_notifica_testo(titolo: str, messaggio: str) -> bool:
    """Mostra una toast Windows da testo validato, senza alterare l'esito dell'operazione chiamante."""
    if not isinstance(titolo, str) or not titolo.strip() or not isinstance(messaggio, str) or not messaggio.strip():
        raise ValueError("Titolo e messaggio della notifica devono essere stringhe non vuote.")
    if os.name != "nt":
        return False
    try:
        from winotify import Notification
        Notification(app_id="FDBackup", title=titolo.strip(), msg=messaggio.strip()).show()
        return True
    except Exception as errore:
        logger.warning("Notifica Windows non disponibile: %s: %s", type(errore).__name__, errore)
        return False
