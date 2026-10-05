import logging  # Importa il logging standard per registrare configurazioni dei job non valide.
from pathlib import Path  # Importa Path per convertire i percorsi tra modello Python e JSON.

from fdbackup.modelli_backup import JobBackup, PianificazioneBackup, SorgenteBackup  # Importa i modelli persistenti già verificati del progetto.


logger = logging.getLogger(__name__)  # Crea il logger del modulo, collegato gerarchicamente al logger principale "fdbackup".

CHIAVE_JOB_BACKUP = "job_backup"  # Definisce una chiave dedicata senza alterare le altre impostazioni già presenti in config.json.


def serializza_pianificazione_backup(pianificazione: PianificazioneBackup) -> dict:
    """Converte una pianificazione nel dizionario JSON-compatibile associato alla singola sorgente."""
    return {  # Costruisce una struttura semplice e indipendente dalla futura implementazione dello scheduler.
        "abilitata": pianificazione.abilitata,  # Conserva lo stato esplicito della pianificazione.
        "giorni": list(pianificazione.giorni),  # Converte la tupla interna in un array JSON mantenendo l'ordine configurato.
        "ora": pianificazione.ora,  # Conserva l'orario locale nel formato HH:MM oppure la stringa vuota se non configurato.
        "attiva_dal": pianificazione.attiva_dal,  # Conserva il limite che impedisce di recuperare occorrenze antecedenti alla creazione o modifica della regola.
    }


def serializza_sorgente_backup(sorgente: SorgenteBackup) -> dict:
    """Converte una sorgente nel dizionario JSON-compatibile usato dalla configurazione."""
    return {  # Costruisce una struttura composta esclusivamente da tipi supportati nativamente da JSON.
        "id_sorgente": sorgente.id_sorgente,  # Conserva l'identità persistente della sorgente.
        "percorso": str(sorgente.percorso),  # Converte Path in stringa perché JSON non serializza direttamente gli oggetti Path.
        "nome_destinazione": sorgente.nome_destinazione,  # Conserva il nome stabile della sottocartella assegnata alla sorgente.
        "pianificazione": serializza_pianificazione_backup(sorgente.pianificazione),  # Salva la pianificazione specifica della sorgente.
    }


def serializza_job_backup(job: JobBackup) -> dict:
    """Converte un job nel dizionario JSON-compatibile usato dalla configurazione."""
    return {  # Costruisce il documento persistente del singolo job.
        "id_job": job.id_job,  # Conserva l'identità persistente del job.
        "nome": job.nome,  # Conserva il nome leggibile mostrato all'utente.
        "destinazione": str(job.destinazione),  # Converte Path in stringa per la serializzazione JSON.
        "abilitato": job.abilitato,  # Conserva lo stato di attivazione del job.
        "includi_sottocartelle": job.includi_sottocartelle,  # Conserva la scelta relativa all’attraversamento delle sottocartelle.
        "verifica_integrita": job.verifica_integrita,  # Conserva la scelta relativa alla verifica di integrità dopo la copia.
        "sorgenti": [serializza_sorgente_backup(sorgente) for sorgente in job.sorgenti],  # Serializza le sorgenti mantenendo il loro ordine.
    }


def deserializza_pianificazione_backup(dati: dict) -> PianificazioneBackup:
    """Ricostruisce e valida una pianificazione proveniente dal documento JSON."""
    if not isinstance(dati, dict):  # Richiede un oggetto JSON dedicato alla pianificazione.
        raise ValueError("La pianificazione salvata deve essere un oggetto JSON.")  # Rifiuta liste, stringhe e valori scalari.

    abilitata = dati.get("abilitata")  # Recupera lo stato senza convertirlo implicitamente.
    giorni = dati.get("giorni")  # Recupera l'array settimanale persistito.
    ora = dati.get("ora")  # Recupera l'orario testuale persistito.
    attiva_dal = dati.get("attiva_dal", "")  # Mantiene vuoto il limite per i documenti storici creati prima dell’introduzione di questa informazione.

    if not isinstance(abilitata, bool):  # Richiede un vero booleano JSON.
        raise ValueError("Lo stato 'abilitata' della pianificazione salvata non è valido.")  # Rifiuta valori come 0, 1 o stringhe.
    if not isinstance(giorni, list):  # Il formato persistente usa intenzionalmente un array JSON.
        raise ValueError("I giorni della pianificazione salvata devono essere una lista.")  # Rifiuta strutture incompatibili.
    if not isinstance(ora, str):  # Il formato persistente usa una stringa HH:MM o vuota.
        raise ValueError("L'ora della pianificazione salvata non è valida.")  # Rifiuta numeri e valori null.
    if not isinstance(attiva_dal, str):  # Il nuovo limite temporale deve restare una stringa JSON oppure essere assente nei documenti storici.
        raise ValueError("L’istante di attivazione della pianificazione salvata non è valido.")  # Rifiuta tipi incompatibili senza conversioni implicite.

    try:  # Delega al modello la validazione semantica di giorni, duplicati e formato dell'ora.
        return PianificazioneBackup(abilitata=abilitata, giorni=giorni, ora=ora, attiva_dal=attiva_dal)  # Ricostruisce il modello normalizzato includendo il limite temporale quando disponibile.
    except (TypeError, ValueError) as errore:  # Uniforma gli errori del modello al contratto della persistenza.
        raise ValueError(f"La pianificazione salvata non è valida: {errore}") from errore  # Mantiene anche il motivo specifico dell'errore.


def deserializza_sorgente_backup(dati: dict) -> SorgenteBackup:
    """Ricostruisce una SorgenteBackup da una struttura già decodificata dal JSON."""
    if not isinstance(dati, dict):  # Verifica che la sorgente sia rappresentata da un oggetto JSON.
        raise ValueError("La sorgente salvata deve essere un oggetto JSON.")  # Rifiuta strutture incompatibili.

    id_sorgente = dati.get("id_sorgente")  # Recupera l'identificatore persistente senza generarne uno nuovo.
    percorso = dati.get("percorso")  # Recupera il percorso memorizzato come stringa.
    nome_destinazione = dati.get("nome_destinazione")  # Recupera il nome stabile della sottocartella.
    pianificazione_salvata = dati.get("pianificazione")  # Recupera l'eventuale pianificazione introdotta dopo i primi formati di configurazione.

    if not isinstance(id_sorgente, str) or not id_sorgente.strip():  # Verifica tipo e presenza dell'identificatore.
        raise ValueError("L'identificatore della sorgente salvata non è valido.")  # Evita di perdere l'identità persistente.

    if not isinstance(percorso, str) or not percorso.strip():  # Verifica che il percorso sia una stringa non vuota.
        raise ValueError("Il percorso della sorgente salvata non è valido.")  # Rifiuta percorsi mancanti o di tipo errato.

    if not isinstance(nome_destinazione, str) or not nome_destinazione.strip():  # Verifica il nome logico prima di costruire il modello.
        raise ValueError("Il nome di destinazione della sorgente salvata non è valido.")  # Evita modelli incompleti.

    pianificazione = PianificazioneBackup() if pianificazione_salvata is None else deserializza_pianificazione_backup(pianificazione_salvata)  # Mantiene disabilitate le vecchie sorgenti prive della nuova chiave.

    return SorgenteBackup(  # Ricostruisce il modello usando esplicitamente l'ID originale.
        percorso=Path(percorso),  # Converte la stringa JSON nel tipo Path usato internamente.
        nome_destinazione=nome_destinazione,  # Ripristina il nome stabile della destinazione.
        id_sorgente=id_sorgente,  # Ripristina l'identificatore senza sostituirlo con un nuovo UUID.
        pianificazione=pianificazione,  # Collega la pianificazione ricostruita o il valore retrocompatibile disabilitato.
    )


def deserializza_job_backup(dati: dict) -> JobBackup:
    """Ricostruisce un JobBackup da una struttura già decodificata dal JSON."""
    if not isinstance(dati, dict):  # Verifica che il job sia rappresentato da un oggetto JSON.
        raise ValueError("Il job salvato deve essere un oggetto JSON.")  # Rifiuta strutture incompatibili.

    id_job = dati.get("id_job")  # Recupera l'identificatore persistente del job.
    nome = dati.get("nome")  # Recupera il nome leggibile del job.
    destinazione = dati.get("destinazione")  # Recupera la destinazione memorizzata come stringa.
    abilitato = dati.get("abilitato")  # Recupera lo stato di attivazione.
    sorgenti_salvate = dati.get("sorgenti")  # Recupera la collezione delle sorgenti.
    includi_sottocartelle = dati.get("includi_sottocartelle", True)  # Mantiene True per i job creati prima dell’introduzione dell’opzione.
    verifica_integrita = dati.get("verifica_integrita", True)  # Mantiene True per i job storici privi della nuova chiave.

    if not isinstance(id_job, str) or not id_job.strip():  # Verifica tipo e presenza dell'identificatore.
        raise ValueError("L'identificatore del job salvato non è valido.")  # Evita identità mancanti o rigenerate accidentalmente.

    if not isinstance(nome, str) or not nome.strip():  # Verifica che il nome del job sia utilizzabile.
        raise ValueError("Il nome del job salvato non è valido.")  # Rifiuta nomi mancanti o di tipo errato.

    if not isinstance(destinazione, str) or not destinazione.strip():  # Verifica che la destinazione sia una stringa non vuota.
        raise ValueError("La destinazione del job salvato non è valida.")  # Rifiuta percorsi mancanti o di tipo errato.

    if not isinstance(abilitato, bool):  # Evita conversioni implicite come bool("false"), che produrrebbero un valore errato.
        raise ValueError("Lo stato 'abilitato' del job salvato non è valido.")  # Richiede il vero tipo booleano del JSON.

    if not isinstance(includi_sottocartelle, bool):  # Richiede un booleano reale quando la nuova opzione è presente nel JSON.
        raise ValueError("L’opzione 'includi_sottocartelle' del job salvato non è valida.")  # Rifiuta stringhe, numeri e altri tipi ambigui.

    if not isinstance(verifica_integrita, bool):  # Richiede un booleano reale per la verifica di integrità persistita.
        raise ValueError("L’opzione 'verifica_integrita' del job salvato non è valida.")  # Evita interpretazioni implicite di valori corrotti.

    if not isinstance(sorgenti_salvate, list):  # Verifica che le sorgenti siano rappresentate da un array JSON.
        raise ValueError("Le sorgenti del job salvato devono essere una lista.")  # Rifiuta strutture incompatibili.

    sorgenti = [deserializza_sorgente_backup(sorgente) for sorgente in sorgenti_salvate]  # Ricostruisce ogni sorgente mantenendo l'ordine salvato.

    return JobBackup(  # Ricostruisce il modello completo usando esplicitamente l'ID originale.
        nome=nome,  # Ripristina il nome leggibile.
        destinazione=Path(destinazione),  # Converte la stringa JSON nel Path interno.
        sorgenti=sorgenti,  # Collega le sorgenti appena ricostruite.
        abilitato=abilitato,  # Ripristina lo stato del job.
        id_job=id_job,  # Ripristina l'identità persistente senza generare un nuovo UUID.
        includi_sottocartelle=includi_sottocartelle,  # Ripristina l’opzione oppure il valore compatibile True per i vecchi job.
        verifica_integrita=verifica_integrita,  # Ripristina l’opzione oppure il valore compatibile True per i vecchi job.
    )


def salva_job_nella_configurazione(configurazione: dict, job: list[JobBackup]) -> dict:
    """Restituisce una nuova configurazione contenente i job serializzati senza perdere le altre impostazioni."""
    nuova_configurazione = dict(configurazione)  # Copia il dizionario per non modificare implicitamente l'oggetto del chiamante.
    nuova_configurazione[CHIAVE_JOB_BACKUP] = [serializza_job_backup(singolo_job) for singolo_job in job]  # Sostituisce soltanto la sezione dedicata ai job.
    return nuova_configurazione  # Restituisce la configurazione pronta per salva_configurazione().


def carica_job_dalla_configurazione(configurazione: dict) -> list[JobBackup]:
    """Ricostruisce tutti i job salvati; una sezione assente rappresenta una configurazione ancora senza job."""
    if not isinstance(configurazione, dict):  # Difende la funzione anche se viene richiamata direttamente con un tipo errato.
        raise TypeError("La configurazione deve essere un dizionario.")  # Mantiene esplicito il contratto della funzione.

    if CHIAVE_JOB_BACKUP not in configurazione:  # Riconosce i config.json precedenti all'introduzione dei job.
        return []  # Mantiene la compatibilità: nessun job salvato equivale a una lista vuota.

    job_salvati = configurazione[CHIAVE_JOB_BACKUP]  # Recupera la sezione dedicata ai job.

    if not isinstance(job_salvati, list):  # Verifica che la sezione abbia la struttura prevista.
        raise ValueError("La sezione dei job di backup deve essere una lista.")  # Non nasconde una configurazione presente ma corrotta.

    try:  # Prova a ricostruire tutti i job prima di restituire un risultato parziale.
        return [deserializza_job_backup(dati_job) for dati_job in job_salvati]  # Mantiene ordine, ID e sorgenti salvati.
    except (TypeError, ValueError) as errore:  # Intercetta esclusivamente errori di struttura o dei modelli.
        logger.error("Configurazione dei job di backup non valida: %s", errore)  # Registra il motivo nel logging persistente.
        raise ValueError(f"Configurazione dei job di backup non valida: {errore}") from errore  # Propaga un errore esplicito senza sostituire silenziosamente i dati.
