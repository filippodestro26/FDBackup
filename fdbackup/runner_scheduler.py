import logging  # Importa il logging standard per registrare decisioni ed errori del processo automatico.
import signal  # Importa i segnali per consentire un arresto ordinato del runner da console o dal sistema.
import threading  # Importa Event per l'attesa interrompibile tra due controlli della pianificazione.
from pathlib import Path  # Importa Path per costruire tutti i percorsi rispetto alla cartella applicativa.

from fdbackup.blocco_operazione import BloccoFile  # Importa il lock interprocesso condiviso con le operazioni manuali della GUI.
from fdbackup.configurazione import carica_configurazione  # Importa il caricamento robusto del config.json esistente.
from fdbackup.cronologia_backup import aggiungi_record, crea_record_operazione  # Importa la cronologia strutturata già mostrata nella Home.
from fdbackup.gestore_backup import GestoreBackup  # Importa il coordinatore multi-job già verificato dal progetto.
from fdbackup.logging_backup import configura_logging  # Importa la configurazione del logging persistente esistente.
from fdbackup.modelli_backup import JobBackup, PianificazioneBackup, SorgenteBackup  # Importa i modelli persistenti reali.
from fdbackup.motore_backup import MotoreBackup  # Importa il motore usato per il backup singolo pianificato.
from fdbackup.notifiche_windows import mostra_notifica_windows  # Importa la notifica Windows isolata che non può modificare l’esito del backup.
from fdbackup.persistenza_job import carica_job_dalla_configurazione, deserializza_pianificazione_backup  # Importa la ricostruzione validata di job e pianificazioni.
from fdbackup.scheduler_backup import acquisisci_occorrenza, carica_stato_scheduler, occorrenza_da_eseguire  # Importa il calcolo deterministico e lo stato anti-duplicazione.
from fdbackup.validazione_backup import ValidatoreBackup  # Importa la validazione globale già usata dal coordinatore prima di qualunque copia.


INTERVALLO_CONTROLLO_SECONDI = 30  # Controlla due volte al minuto senza dipendere dall'esatto secondo di avvio del processo.
IDENTIFICATORE_BACKUP_SINGOLO = "backup_singolo"  # Usa una chiave stabile per la pianificazione singola persistita nella GUI.


class RunnerScheduler:
    """Esegue in sequenza le pianificazioni maturate leggendo sempre la configurazione persistente più recente."""

    def __init__(self, cartella_applicazione: Path, notifiche_abilitate: bool = False) -> None:
        """Prepara percorsi, logging, lock ed evento di arresto senza avviare ancora alcun backup."""
        self.cartella_applicazione = Path(cartella_applicazione).resolve()  # Normalizza la radice dell'applicazione indipendentemente dalla directory corrente.
        self.notifiche_abilitate = bool(notifiche_abilitate)  # Mantiene le notifiche disattivate nelle integrazioni programmatiche e le abilita esplicitamente soltanto nel processo runner reale.
        self.file_configurazione = self.cartella_applicazione / "config.json"  # Usa lo stesso file della GUI.
        self.file_cronologia = self.cartella_applicazione / "cronologia.json"  # Usa la stessa cronologia strutturata della Home.
        self.file_stato = self.cartella_applicazione / "stato_scheduler.json"  # Mantiene separato lo stato tecnico anti-duplicazione.
        self.file_lock_scheduler = self.cartella_applicazione / ".scheduler.lock"  # Identifica l'unica istanza ammessa del runner.
        self.file_lock_operazione = self.cartella_applicazione / ".operazione.lock"  # Coordina backup automatici e operazioni manuali.
        self.file_lock_gui = self.cartella_applicazione / ".gui.lock"  # Permette al runner di sapere se almeno la GUI principale è aperta prima di mostrare una notifica.
        self.file_richiesta_arresto = self.cartella_applicazione / ".scheduler.stop"  # Riceve dalla GUI una richiesta esplicita di uscita definitiva valida anche tra processi separati.
        configura_logging(self.cartella_applicazione)  # Collega il runner allo stesso logging rotante dell'applicazione.
        self.logger = logging.getLogger("fdbackup.scheduler")  # Usa un logger figlio coerente con il resto del progetto.
        self.evento_arresto = threading.Event()  # Permette di interrompere l'attesa del ciclo senza thread daemon.
        self.blocco_istanza = BloccoFile(self.file_lock_scheduler)  # Prepara il lock che impedisce due runner contemporanei.

    def richiedi_arresto(self, *_argomenti) -> None:
        """Richiede un arresto cooperativo del ciclo principale e dell'eventuale motore in esecuzione."""
        self.evento_arresto.set()  # Sveglia anche Event.wait() e viene osservato dai motori di backup.

    def _sorveglia_richiesta_arresto_esterna(self) -> None:
        """Osserva il file di stop mentre il runner lavora e propaga rapidamente la richiesta all'evento cooperativo."""
        while not self.evento_arresto.wait(0.5):  # Controlla due volte al secondo senza consumare CPU con un ciclo continuo.
            if self.file_richiesta_arresto.exists():  # Riconosce la richiesta prodotta dalla voce Chiudi FDBackup della tray.
                self.evento_arresto.set()  # Propaga lo stop anche ai motori automatici che condividono questo evento.
                return  # Termina il sorvegliante dopo aver consegnato la richiesta.

    @staticmethod
    def _carica_backup_singolo(configurazione: dict) -> tuple[str, str, PianificazioneBackup] | None:
        """Ricostruisce la configurazione del backup singolo senza dipendere dalla classe grafica."""
        dati = configurazione.get("backup_singolo")  # Recupera la sezione persistita dalla GUI.
        if dati is None:  # Gestisce configurazioni storiche prive della sezione.
            return None  # Non esiste alcun backup singolo pianificabile.
        if not isinstance(dati, dict):  # Richiede la struttura JSON prevista.
            raise ValueError("La sezione 'backup_singolo' deve essere un oggetto JSON.")  # Non corregge silenziosamente dati corrotti.
        sorgente = dati.get("sorgente")  # Recupera il percorso sorgente testuale.
        destinazione = dati.get("destinazione")  # Recupera il percorso destinazione testuale.
        pianificazione_dati = dati.get("pianificazione")  # Recupera la pianificazione serializzata.
        if not isinstance(sorgente, str) or not sorgente.strip():  # Una pianificazione automatica necessita di una sorgente reale configurata.
            return None  # Ignora una sezione vuota compatibile con il primo avvio della GUI.
        if not isinstance(destinazione, str) or not destinazione.strip():  # Una pianificazione automatica necessita anche della destinazione.
            return None  # Non crea un'operazione incompleta.
        pianificazione = PianificazioneBackup() if pianificazione_dati is None else deserializza_pianificazione_backup(pianificazione_dati)  # Riusa la validazione persistente già adottata dalla GUI.
        return sorgente.strip(), destinazione.strip(), pianificazione  # Restituisce dati normalizzati e modello validato.

    @staticmethod
    def _identificatore_sorgente(job: JobBackup, sorgente: SorgenteBackup) -> str:
        """Costruisce una chiave stabile che rimane distinta anche tra job differenti."""
        return f"job:{job.id_job}:sorgente:{sorgente.id_sorgente}"  # Combina le due identità persistenti già presenti nel modello.

    def _registra_cronologia_sicura(self, record) -> None:
        """Tenta di registrare la cronologia senza trasformare un errore diagnostico in una seconda esecuzione del backup."""
        try:  # Isola la persistenza della cronologia dal risultato operativo già concluso.
            aggiungi_record(self.file_cronologia, record)  # Usa la scrittura atomica e il limite a cento record già implementati.
        except (OSError, ValueError, TypeError) as errore:  # Gestisce problemi di file o una cronologia preesistente corrotta.
            self.logger.exception("Impossibile aggiornare la cronologia dello scheduler: %s", errore)  # Conserva il problema nel log persistente.

    def _notifica_se_gui_chiusa(self, record) -> None:
        """Mostra la notifica soltanto quando il lock della GUI risulta libero, senza influire mai sul backup."""
        if not self.notifiche_abilitate:  # I test e gli usi programmatici del runner non devono produrre effetti grafici sul desktop.
            return  # Mantiene deterministiche le integrazioni automatiche.
        blocco_gui = BloccoFile(self.file_lock_gui)  # Usa lo stesso meccanismo interprocesso già collaudato dal progetto.
        if not blocco_gui.acquisisci():  # Un lock occupato indica che la GUI principale è ancora aperta.
            return  # Evita notifiche ridondanti mentre l’utente può già vedere FDBackup.
        try:  # Mantiene il lock soltanto per la verifica e l’invio della notifica.
            mostra_notifica_windows(record)  # Delega al modulo isolato la richiesta al sistema notifiche di Windows.
        finally:  # Garantisce che il controllo della presenza GUI non lasci lock residui.
            blocco_gui.rilascia()  # Rende immediatamente disponibile il lock a una GUI che venga aperta dopo la notifica.

    def _esegui_backup_singolo(self, sorgente: str, destinazione: str) -> None:
        """Esegue un backup singolo pianificato tramite lo stesso MotoreBackup della GUI e registra l'esito reale."""
        motore = MotoreBackup(evento_arresto=self.evento_arresto)  # Crea il motore con lo stesso arresto cooperativo del runner.
        try:  # Protegge il ciclo principale da un errore fatale della singola operazione.
            risultato = motore.esegui(Path(sorgente), Path(destinazione))  # Esegue sorgente e destinazione persistite senza dipendenze grafiche.
            stato = "annullato" if risultato.annullato else ("successo" if risultato.successo else "problemi")  # Traduce l'esito nel vocabolario della cronologia.
            record = crea_record_operazione("backup_singolo", stato, "Backup singolo automatico", risultato.file_copiati, risultato.file_ignorati, risultato.file_falliti, risultato.byte_copiati, tuple(risultato.errori))  # Conserva i contatori reali prodotti dal motore.
            self._registra_cronologia_sicura(record)  # Pubblica l'esito nella Home.
            self._notifica_se_gui_chiusa(record)  # Avvisa tramite Windows soltanto se la GUI non è aperta.
            self.logger.info("Backup singolo automatico terminato | stato=%s | sorgente=%s | destinazione=%s", stato, sorgente, destinazione)  # Registra un riepilogo diagnostico.
        except Exception as errore:  # Mantiene il runner vivo anche davanti a un errore non recuperabile della singola esecuzione.
            self.logger.exception("Backup singolo automatico fallito.")  # Registra traceback e contesto nel log persistente.
            record = crea_record_operazione("backup_singolo", "fallito", "Backup singolo automatico", problemi=(f"{type(errore).__name__}: {errore}",))  # Costruisce un unico record condiviso da cronologia e notifica.
            self._registra_cronologia_sicura(record)  # Rende visibile il fallimento nella cronologia persistente.
            self._notifica_se_gui_chiusa(record)  # Avvisa del fallimento soltanto quando la GUI non è aperta.

    def _esegui_job_pianificato(self, job_originale: JobBackup, sorgenti_dovute: list[SorgenteBackup]) -> None:
        """Esegue soltanto le sorgenti maturate di un job conservandone destinazione, opzioni e identità."""
        job_pianificato = JobBackup(nome=job_originale.nome, destinazione=job_originale.destinazione, sorgenti=list(sorgenti_dovute), abilitato=True, id_job=job_originale.id_job, includi_sottocartelle=job_originale.includi_sottocartelle, verifica_integrita=job_originale.verifica_integrita)  # Crea una vista eseguibile senza modificare il modello caricato dal config.
        coordinatore = GestoreBackup(evento_arresto=self.evento_arresto)  # Riusa il coordinatore già testato per validazione ed esecuzione sequenziale.
        try:  # Isola il singolo job per consentire al runner di proseguire con le scadenze successive.
            risultato = coordinatore.esegui([job_pianificato])  # Esegue esclusivamente le sorgenti la cui occorrenza è stata acquisita.
            file_copiati = sum((rs.risultato_backup.file_copiati if rs.risultato_backup is not None else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti)  # Aggrega i file copiati realmente dal motore.
            file_ignorati = sum((rs.risultato_backup.file_ignorati if rs.risultato_backup is not None else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti)  # Aggrega i file già identici.
            file_falliti = sum((rs.risultato_backup.file_falliti if rs.risultato_backup is not None else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti)  # Aggrega i fallimenti interni dei motori.
            byte_copiati = sum((rs.risultato_backup.byte_copiati if rs.risultato_backup is not None else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti)  # Aggrega i byte copiati con successo.
            problemi = tuple(rs.errore_fatale for rj in risultato.risultati_job for rs in rj.risultati_sorgenti if rs.errore_fatale)  # Conserva gli eventuali errori fatali per sorgente.
            stato = "annullato" if risultato.annullato else ("successo" if risultato.successo else "problemi")  # Traduce l'esito aggregato nel vocabolario della cronologia.
            descrizione = f"Backup automatico: {job_originale.nome}"  # Mantiene riconoscibile il job nella Home.
            record = crea_record_operazione("backup_multiplo", stato, descrizione, file_copiati, file_ignorati, file_falliti, byte_copiati, problemi)  # Costruisce un unico record condiviso da cronologia e notifica.
            self._registra_cronologia_sicura(record)  # Registra i dati reali del coordinatore.
            self._notifica_se_gui_chiusa(record)  # Avvisa tramite Windows soltanto se la GUI non è aperta.
            self.logger.info("Job automatico terminato | job=%s | sorgenti=%d | stato=%s", job_originale.nome, len(sorgenti_dovute), stato)  # Registra il riepilogo nel log persistente.
        except Exception as errore:  # Mantiene attivo il processo scheduler dopo un errore del job corrente.
            self.logger.exception("Job automatico fallito | job=%s", job_originale.nome)  # Registra traceback e identità del job.
            record = crea_record_operazione("backup_multiplo", "fallito", f"Backup automatico: {job_originale.nome}", problemi=(f"{type(errore).__name__}: {errore}",))  # Costruisce un unico record condiviso da cronologia e notifica.
            self._registra_cronologia_sicura(record)  # Pubblica il fallimento nella cronologia strutturata.
            self._notifica_se_gui_chiusa(record)  # Avvisa del fallimento soltanto quando la GUI non è aperta.

    def esegui_controllo(self) -> bool:
        """Esegue un singolo controllo delle scadenze e restituisce True se almeno un'operazione è stata acquisita."""
        configurazione = carica_configurazione(self.file_configurazione)  # Rilegge il config a ogni ciclo per recepire subito modifiche effettuate dalla GUI.
        stato = carica_stato_scheduler(self.file_stato)  # Carica la protezione anti-duplicazione prima di calcolare il lavoro.
        backup_singolo = self._carica_backup_singolo(configurazione)  # Ricostruisce l'eventuale pianificazione singola.
        job = carica_job_dalla_configurazione(configurazione)  # Ricostruisce tutti i job persistenti con le validazioni esistenti.
        ValidatoreBackup.valida_job_multipli(job)  # Rivalida l’intera configurazione corrente prima di acquisire qualsiasi scadenza automatica.
        dovuto_singolo = None  # Prepara l'eventuale occorrenza del backup singolo.
        if backup_singolo is not None:  # Calcola la scadenza soltanto quando esistono percorsi configurati.
            dovuto_singolo = occorrenza_da_eseguire(IDENTIFICATORE_BACKUP_SINGOLO, backup_singolo[2], stato)  # Applica la stessa regola anti-duplicazione delle sorgenti multi-job.
        sorgenti_dovute: list[tuple[JobBackup, SorgenteBackup, object]] = []  # Raccoglie le sorgenti maturate mantenendo il relativo job.
        for singolo_job in job:  # Esamina ogni job persistente nell'ordine configurato.
            if not singolo_job.abilitato:  # Un job disabilitato non deve produrre esecuzioni automatiche.
                continue  # Passa al job successivo senza modificare lo stato.
            for sorgente in singolo_job.sorgenti:  # Valuta indipendentemente la pianificazione di ogni sorgente.
                identificatore = self._identificatore_sorgente(singolo_job, sorgente)  # Costruisce la chiave persistente anti-duplicazione.
                occorrenza = occorrenza_da_eseguire(identificatore, sorgente.pianificazione, stato)  # Calcola l'ultima scadenza non ancora acquisita.
                if occorrenza is not None:  # Conserva soltanto le sorgenti realmente dovute.
                    sorgenti_dovute.append((singolo_job, sorgente, occorrenza))  # Mantiene job, sorgente e chiave temporale insieme.
        if dovuto_singolo is None and not sorgenti_dovute:  # Evita di acquisire il lock operativo quando non esiste lavoro.
            return False  # Comunica che il ciclo non ha avviato nulla.

        blocco_operazione = BloccoFile(self.file_lock_operazione)  # Prepara l'esclusione reciproca con backup e ripristini manuali.
        if not blocco_operazione.acquisisci():  # Non attende se l'utente sta già eseguendo un'operazione dalla GUI.
            self.logger.info("Esecuzione automatica rinviata: un'altra operazione FDBackup è attiva.")  # Spiega nel log perché la scadenza non è stata ancora acquisita.
            return False  # Lascia intatto lo stato così il prossimo ciclo riproverà la stessa occorrenza.

        almeno_una = False  # Tiene traccia delle occorrenze realmente acquisite durante il ciclo.
        try:  # Mantiene il lock operativo per l'intera sequenza di scadenze del ciclo.
            if dovuto_singolo is not None and backup_singolo is not None and not self.evento_arresto.is_set():  # Esegue prima il backup singolo mantenendo un ordine deterministico.
                stato = acquisisci_occorrenza(self.file_stato, stato, IDENTIFICATORE_BACKUP_SINGOLO, dovuto_singolo)  # Marca la scadenza prima della copia per impedire duplicati dopo crash o riavvio.
                almeno_una = True  # Registra l'acquisizione riuscita.
                self._esegui_backup_singolo(backup_singolo[0], backup_singolo[1])  # Delega il lavoro al motore esistente.

            job_ordinati: list[JobBackup] = []  # Conserva l'ordine originale dei job che possiedono almeno una sorgente dovuta.
            for singolo_job, _sorgente, _occorrenza in sorgenti_dovute:  # Analizza la raccolta senza perdere l'ordine di configurazione.
                if all(esistente.id_job != singolo_job.id_job for esistente in job_ordinati):  # Inserisce ogni job una sola volta.
                    job_ordinati.append(singolo_job)  # Mantiene l'ordine della prima sorgente dovuta incontrata.

            for singolo_job in job_ordinati:  # Esegue i job dovuti uno alla volta.
                if self.evento_arresto.is_set():  # Non acquisisce nuove occorrenze dopo una richiesta di arresto.
                    break  # Termina la sequenza lasciando le scadenze non acquisite disponibili al riavvio.
                elementi_job = [(sorgente, occorrenza) for job_corrente, sorgente, occorrenza in sorgenti_dovute if job_corrente.id_job == singolo_job.id_job]  # Seleziona soltanto le sorgenti dovute del job corrente.
                sorgenti_acquisite: list[SorgenteBackup] = []  # Prepara la lista che verrà consegnata al coordinatore.
                for sorgente, occorrenza in elementi_job:  # Acquisisce ogni scadenza prima di iniziare il job.
                    identificatore = self._identificatore_sorgente(singolo_job, sorgente)  # Ricostruisce la chiave stabile della sorgente.
                    stato = acquisisci_occorrenza(self.file_stato, stato, identificatore, occorrenza)  # Persiste immediatamente la protezione anti-duplicazione.
                    sorgenti_acquisite.append(sorgente)  # Aggiunge la sorgente soltanto dopo il salvataggio riuscito dello stato.
                    almeno_una = True  # Registra che il ciclo ha acquisito lavoro reale.
                if sorgenti_acquisite:  # Evita di costruire job vuoti.
                    self._esegui_job_pianificato(singolo_job, sorgenti_acquisite)  # Riusa il coordinatore per il lavoro effettivo.
        finally:  # Garantisce il rilascio anche in presenza di errori di persistenza o configurazione.
            blocco_operazione.rilascia()  # Rende nuovamente disponibili le operazioni manuali o il ciclo successivo.
        return almeno_una  # Comunica al chiamante se il controllo ha acquisito almeno una scadenza.

    def esegui(self) -> int:
        """Mantiene attivo il processo scheduler finché non riceve una richiesta di arresto interna o interprocesso."""
        if not self.blocco_istanza.acquisisci():  # Impedisce che più avvii della GUI creino runner concorrenti.
            return 0  # Un'altra istanza sana è già responsabile delle pianificazioni.
        self.logger.info("Scheduler automatico avviato | intervallo=%ss", INTERVALLO_CONTROLLO_SECONDI)  # Registra l'avvio del servizio applicativo.
        thread_arresto_esterna = threading.Thread(target=self._sorveglia_richiesta_arresto_esterna, name="FDBackupSchedulerStop", daemon=True)  # Crea un sorvegliante leggero che può fermare cooperativamente anche un backup automatico già in corso.
        thread_arresto_esterna.start()  # Avvia il controllo del segnale interprocesso senza rallentare il ciclo delle pianificazioni.
        try:  # Mantiene il lock d'istanza per tutta la vita del processo.
            secondi_trascorsi = INTERVALLO_CONTROLLO_SECONDI  # Forza il primo controllo immediatamente dopo l'acquisizione del lock.
            while not self.evento_arresto.is_set():  # Continua finché non viene richiesto un arresto esplicito.
                if self.file_richiesta_arresto.exists():  # Controlla il segnale interprocesso creato esclusivamente dall'uscita definitiva della GUI.
                    self.evento_arresto.set()  # Propaga la richiesta anche all'eventuale motore che osserva lo stesso evento.
                    break  # Termina il ciclo senza acquisire nuove occorrenze.
                if secondi_trascorsi >= INTERVALLO_CONTROLLO_SECONDI:  # Mantiene invariata la frequenza dei controlli delle pianificazioni.
                    try:  # Isola gli errori di un singolo controllo per mantenere vivo il runner.
                        self.esegui_controllo()  # Rilegge configurazione, calcola scadenze ed esegue quelle maturate.
                    except Exception as errore:  # Cattura errori di configurazione, stato o filesystem senza terminare il servizio.
                        self.logger.exception("Errore durante il controllo dello scheduler: %s", errore)  # Conserva traceback e causa nel log persistente.
                    secondi_trascorsi = 0  # Riparte da zero dopo il controllo periodico appena completato.
                if self.evento_arresto.wait(1):  # Attende al massimo un secondo per rendere rapida la risposta al segnale esterno senza busy-wait.
                    break  # Termina immediatamente quando un segnale interno ha impostato l'evento.
                secondi_trascorsi += 1  # Avanza il contatore usato esclusivamente per mantenere il controllo ogni trenta secondi.
        finally:  # Garantisce il rilascio del lock d'istanza in ogni percorso di uscita.
            self.file_richiesta_arresto.unlink(missing_ok=True)  # Consuma il segnale di uscita per non bloccare un futuro avvio esplicito di FDBackup.
            self.blocco_istanza.rilascia()  # Permette un successivo riavvio del runner.
            self.logger.info("Scheduler automatico arrestato.")  # Registra la conclusione ordinata del processo.
        return 0  # Restituisce un codice di uscita di successo al processo chiamante.


def main() -> int:
    """Avvia il runner dalla cartella principale del progetto quando il modulo viene eseguito con -m."""
    cartella_applicazione = Path(__file__).resolve().parent.parent  # Risale dal package fdbackup alla radice che contiene config.json.
    runner = RunnerScheduler(cartella_applicazione, notifiche_abilitate=True)  # Crea il processo reale abilitando le notifiche desktop, disattivate invece nei test programmatici.
    try:  # Registra i segnali disponibili senza rendere obbligatoria una piattaforma specifica.
        signal.signal(signal.SIGINT, runner.richiedi_arresto)  # Gestisce Ctrl+C quando il runner viene avviato manualmente.
        signal.signal(signal.SIGTERM, runner.richiedi_arresto)  # Gestisce una richiesta di terminazione ordinata quando supportata.
    except (AttributeError, ValueError):  # Tollera ambienti che non consentono la registrazione dei segnali nel contesto corrente.
        pass  # L'evento rimane comunque utilizzabile dai test e dal codice applicativo.
    return runner.esegui()  # Avvia il ciclo continuo e propaga il codice di uscita.


if __name__ == "__main__":  # Permette l'esecuzione diretta con python -m fdbackup.runner_scheduler.
    raise SystemExit(main())  # Converte il risultato del runner nel codice di uscita del processo.
