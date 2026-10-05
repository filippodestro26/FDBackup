import logging  # Importa il sistema di logging standard usato per registrare gli eventi diagnostici della GUI.
import os  # Importa le funzioni del sistema operativo usate per aprire il file di log con l’applicazione predefinita.
import queue  # Importa una coda thread-safe per comunicare dal thread di backup alla GUI.
import subprocess  # Importa la gestione dei processi per avviare lo scheduler indipendente dalla GUI.
import sys  # Importa il percorso dell’interprete Python corrente usato per lanciare il runner scheduler.
import threading  # Importa gli strumenti necessari per eseguire il backup senza bloccare la GUI.
from datetime import datetime  # Importa datetime per registrare quando una pianificazione nuova o modificata diventa effettiva.
from pathlib import Path  # Importa Path per gestire i percorsi in modo più sicuro e leggibile.

import customtkinter as ctk  # Importa CustomTkinter per costruire l'interfaccia grafica.
from PIL import Image  # Importa Pillow per caricare e ridimensionare il banner.
from tkinter import filedialog, messagebox  # Importa le finestre native per scegliere cartelle/file e mostrare messaggi.

from fdbackup.blocco_operazione import BloccoFile  # Importa il lock interprocesso che impedisce sovrapposizioni tra operazioni manuali e automatiche.
from fdbackup.avvio_automatico import abilita_avvio_automatico, avvio_automatico_attivo, disabilita_avvio_automatico  # Importa la gestione Windows dell’avvio automatico all’accesso dell’utente.
from fdbackup.configurazione import carica_configurazione, salva_configurazione  # Importa le funzioni separate per leggere e salvare la configurazione.
from fdbackup.cronologia_backup import aggiungi_record, cancella_cronologia, carica_cronologia, crea_record_operazione  # Importa la cronologia strutturata mostrata nella Home e la sua cancellazione isolata.
from fdbackup.gestore_tray import COMANDO_APRI, COMANDO_CHIUDI, GestoreTray  # Importa l’icona Windows e i comandi trasferiti alla GUI tramite coda thread-safe.
from fdbackup.gestore_backup import GestoreBackup as CoordinatoreBackup, RisultatoEsecuzioneBackup  # Importa il coordinatore multi-job con alias per distinguerlo dalla classe GUI.
from fdbackup.gestore_backup_avanzato import GestoreBackupAvanzato, StrategiaBackupAvanzato  # Importa il coordinatore delle strategie versionate senza modificare il motore storico.
from fdbackup.logging_backup import configura_logging  # Importa la funzione che configura il file di log persistente dell'applicazione.
from fdbackup.motore_backup import MotoreBackup, RisultatoBackup  # Importa il motore di backup e il relativo modello di risultato.
from fdbackup.monitoraggio_sistema import formatta_dimensione, rileva_unita_windows  # Importa il monitoraggio delle unità Windows per la dashboard.
from fdbackup.motore_ripristino import MotoreRipristino, RisultatoRipristino  # Importa il motore di ripristino conservativo e il relativo modello di risultato.
from fdbackup.motore_ripristino_avanzato import MotoreRipristinoAvanzato  # Importa il ricostruttore delle catene Full, Incrementali e Differenziali.
from fdbackup.modelli_backup import JobBackup, PianificazioneBackup, SorgenteBackup  # Importa i modelli persistenti reali, inclusa la pianificazione per singola sorgente.
from fdbackup.persistenza_job import carica_job_dalla_configurazione, deserializza_pianificazione_backup, salva_job_nella_configurazione, serializza_pianificazione_backup  # Importa caricamento, serializzazione e validazione persistente dei job e delle pianificazioni.
from fdbackup.persistenza_attivita_avanzata import carica_attivita_avanzate, salva_attivita_avanzate  # Importa la persistenza separata dei registri Strategie, Sincronizza e Ripristino versionato.
from fdbackup.validazione_backup import ValidatoreBackup  # Importa il validatore centrale per non duplicare nella GUI le regole del backend.
from fdbackup.verifica_integrita_avanzata import VerificatoreIntegritaAvanzata  # Importa il verificatore SHA-256 delle versioni senza accoppiare il backend alla GUI.
from fdbackup.filtri_backup import FiltroBackup  # Importa i filtri deterministici applicati prima di hashing e copia.
from fdbackup.notifiche_windows import mostra_notifica_testo  # Importa le notifiche native anche per le strategie manuali.
from fdbackup.politiche_avanzate import (  # Importa le politiche professionali mantenendo la GUI come livello di orchestrazione.
    DestinazioneBackup, GestoreAffidabilita, GestoreDestinazioniMultiple, PoliticaRetention,
    applica_retention_sicura, crea_dashboard, destinazione_disponibile, genera_avvisi,
    pianifica_retention, salva_report_periodico,
)


# ============================================================
# CONFIGURAZIONE APPLICAZIONE
# ============================================================

ctk.set_appearance_mode("dark")  # Imposta il tema scuro dell'interfaccia.
ctk.set_default_color_theme("blue")  # Imposta il tema cromatico blu di CustomTkinter.

CARTELLA_APPLICAZIONE = Path(__file__).resolve().parent  # Individua la cartella che contiene fisicamente il file principale dell'applicazione.
FILE_CONFIGURAZIONE = CARTELLA_APPLICAZIONE / "config.json"
FILE_CRONOLOGIA = CARTELLA_APPLICAZIONE / "cronologia.json"  # Mantiene separati i dati operativi dalla configurazione utente.  # Mantiene il file di configurazione nella cartella dell'applicazione indipendentemente dalla directory di avvio.
FILE_ATTIVITA_AVANZATE = CARTELLA_APPLICAZIONE / "attivita_avanzate.json"  # Mantiene separati e persistenti i registri Attività di Strategie, Sincronizza e Ripristino versionato.
PERCORSO_LOG = configura_logging(CARTELLA_APPLICAZIONE)  # Configura una sola volta il logging persistente nella cartella logs dell'applicazione.
logger = logging.getLogger("fdbackup.gui")  # Usa un logger figlio di "fdbackup" anche quando questo file viene eseguito come programma principale.

# Colori adattivi: CustomTkinter interpreta le tuple come (tema chiaro, tema scuro).
COLORE_SFONDO = ("#F4F7FA", "#08111C")  # Definisce lo sfondo principale per entrambi i temi.
COLORE_SIDEBAR = ("#E7EDF3", "#0B1420")  # Definisce lo sfondo della barra laterale per entrambi i temi.
COLORE_SCHEDA = ("#D7E0E9", "#111D2A")  # Definisce schede più evidenti rispetto allo sfondo nel tema chiaro, mantenendo invariata la variante scura.
COLORE_SCHEDA_ALTERNATIVA = ("#DCE4EC", "#111E2D")  # Definisce schede secondarie leggermente più scure e distinguibili dallo sfondo nel tema chiaro.
COLORE_RIQUADRO = ("#D2DDE7", "#152131")  # Definisce riquadri interni con contrasto visibile anche nel tema chiaro.
COLORE_BORDO = ("#B8C6D3", "#26394D")  # Definisce un bordo leggibile in entrambi i temi.
COLORE_TESTO_SECONDARIO = ("#526577", "#B2BECD")  # Definisce il testo secondario con contrasto adeguato.
COLORE_TESTO_TERZIARIO = ("#647587", "#91A0B4")  # Definisce il testo informativo meno prominente.
COLORE_TESTO_ATTENUATO = ("#6C7D8E", "#73879C")  # Definisce il testo attenuato delle descrizioni.
COLORE_TESTO_STATO = ("#56697B", "#9FB0C3")  # Definisce il testo degli stati operativi.
COLORE_TESTO_INFO = ("#5E7183", "#8FA3B8")  # Definisce il testo informativo del banner e della Home.
COLORE_TESTO_DETTAGLI = ("#43586B", "#B9C7D6")  # Definisce il testo dei dettagli nelle card.
COLORE_BARRA_NORMALE = "#2FA84F"  # Usa il verde quando lo spazio utilizzato è sotto la soglia critica.
COLORE_BARRA_CRITICA = "#C43D4B"  # Usa il rosso quando lo spazio utilizzato raggiunge la soglia critica.
COLORE_MENU_INATTIVO = ("#D2DFEA", "#101B28")  # Mantiene sempre visibili i riquadri delle voci del menu anche nel tema chiaro.
COLORE_MENU_ATTIVO = "#1976B9"  # Usa lo stesso blu dei pulsanti operativi per la voce di menu attiva in modalità Light e Dark.
COLORE_MENU_HOVER = ("#BDD1E1", "#164B70")  # Fornisce un feedback al passaggio del mouse senza perdere contrasto.
COLORE_MENU_TESTO_INATTIVO = ("#17324A", "#E8F1FA")  # Mantiene leggibile il testo delle voci non selezionate in Light e Dark.
COLORE_MENU_TESTO_ATTIVO = ("#FFFFFF", "#FFFFFF")  # Mantiene massimo contrasto sulla voce evidenziata in blu.
COLORE_PULSANTE_SECONDARIO = "#1976B9"  # Usa un blu netto in Light e mantiene il secondario scuro in Dark per rendere sempre riconoscibili i comandi secondari.
COLORE_PULSANTE_SECONDARIO_HOVER = "#155F94"  # Definisce un hover più scuro e chiaramente distinguibile in entrambi i temi.
COLORE_PULSANTE_AVVIA = "#2FA84F"  # Mantiene la stessa tonalità verde del comando Avvia in modalità Light e Dark.
COLORE_PULSANTE_AVVIA_HOVER = "#268B41"  # Mantiene uniforme anche il verde di hover del comando Avvia.
COLORE_PULSANTE_PERICOLO = "#B8323E"  # Usa un rosso unico e chiaramente riconoscibile per eliminazione e arresto in entrambi i temi.
COLORE_PULSANTE_PERICOLO_HOVER = "#942934"  # Definisce un rosso più scuro per il passaggio del mouse sui comandi distruttivi o di arresto.
COLORE_TESTO_PULSANTE = "#FFFFFF"  # Mantiene il testo dei pulsanti colorati leggibile e coerente nei due temi.
COLORE_EDITOR = ("#F1F5F8", "#0D1825")  # Mantiene distinguibile il riquadro dell'editor in entrambi i temi.
COLORE_BORDO_EDITOR = ("#B8C7D4", "#2B4055")  # Mantiene visibile il bordo dell'editor in Light e Dark.
SOGLIA_SPAZIO_CRITICO = 0.90  # Considera critica un'unità dal 90% di spazio utilizzato in su.
INTERVALLO_AGGIORNAMENTO_CRONOLOGIA_MS = 2000  # Controlla ogni due secondi se il runner esterno ha sostituito atomicamente la cronologia.
FILE_RICHIESTA_ARRESTO_SCHEDULER = CARTELLA_APPLICAZIONE / ".scheduler.stop"  # Definisce il segnale interprocesso usato soltanto dall’uscita definitiva di FDBackup.


# ============================================================
# INTERFACCIA GRAFICA
# ============================================================

class GestoreBackup(ctk.CTk):
    """Gestisce la finestra principale e mantiene tutte le operazioni grafiche nel thread della GUI."""

    def __init__(self):
        """Inizializza finestra, stato, coda degli eventi e componenti grafici dell'applicazione."""
        super().__init__()  # Inizializza la finestra principale di CustomTkinter.

        self.title("FDBackup")  # Imposta il titolo visualizzato nella barra della finestra.
        self.geometry("1280x820")  # Imposta una dimensione iniziale più ampia, adatta al nuovo layout professionale.
        self.minsize(1050, 700)  # Impedisce di ridurre la finestra sotto una dimensione che comprometterebbe il layout.
        self.protocol("WM_DELETE_WINDOW", self.gestisci_richiesta_chiusura)  # Intercetta la X della finestra per gestire in sicurezza eventuali operazioni attive.

        self.configurazione = self.carica_configurazione()  # Carica la configurazione salvata dal file JSON.
        self.job_backup = self.carica_job_backup()  # Ricostruisce i job persistenti che verranno mostrati nella nuova area multi-job.
        self.backup_singolo = self.carica_backup_singolo()  # Carica l’eventuale configurazione persistente del backup singolo senza confonderla con i job multi-sorgente.
        self.editor_nuovo_backup = None  # Mantiene il riferimento all’editor incorporato nella schermata principale per impedirne la duplicazione.
        self.righe_sorgenti_nuovo_backup = []  # Conserva i widget delle sorgenti presenti nell’editor del job in creazione o modifica.
        self.id_job_in_modifica = None  # Conserva l’identità del job aperto in modifica; None indica la creazione di un nuovo job.
        self.immagine_banner = None  # Mantiene un riferimento all'immagine del banner per evitarne la rimozione dalla memoria.
        self.thread_backup = None  # Conserverà il thread che esegue il motore di backup.
        self.thread_ripristino = None  # Conserverà il thread che esegue il motore di ripristino.
        self.modalita_operazione = "backup"  # Mantiene la modalità operativa attualmente selezionata nella GUI.
        self.sezione_attiva = "backup"  # Mantiene la sezione reale selezionata nella barra laterale.
        self.operazione_avanzata_in_corso = ""  # Mantiene il lifecycle avanzato indipendente dalla vita dei widget e dal cambio menu.
        self.stato_strategia_testo = "Pronto"  # Conserva lo stato Strategie anche quando la relativa vista viene ricostruita.
        self.stato_sync_testo = "Pronto"  # Conserva lo stato Sincronizza anche quando la relativa vista viene ricostruita.
        self.progresso_strategia = 0.0  # Conserva la frazione determinata dell'ultima strategia visualizzata.
        self.progresso_sync = 0.0  # Conserva la frazione determinata dell'ultima sincronizzazione visualizzata.
        registri_attivita_avanzate = carica_attivita_avanzate(FILE_ATTIVITA_AVANZATE)  # Recupera i registri avanzati persistiti prima di costruire le relative viste.
        self.attivita_strategia = registri_attivita_avanzate["strategie"]  # Ripristina Strategie anche dopo una chiusura definitiva dell’applicazione.
        self.attivita_sync = registri_attivita_avanzate["sincronizza"]  # Ripristina Sincronizza finché l’utente non usa Cancella attività.
        self.attivita_ripristino_versionato = registri_attivita_avanzate["ripristino_versionato"]  # Ripristina il registro del recupero versionato tra sessioni diverse.
        self.attivita_verifica_integrita = registri_attivita_avanzate["verifica_integrita"]  # Ripristina anche la diagnostica delle verifiche di integrità finché l’utente non la cancella.
        self.progresso_ripristino_versionato = 0.0  # Conserva la percentuale del ripristino versionato durante la navigazione.
        self.stato_ripristino_versionato = "Pronto"  # Conserva lo stato leggibile del ripristino versionato.
        self.progresso_verifica_integrita = 0.0  # Conserva la percentuale della verifica anche durante la navigazione.
        self.stato_verifica_integrita = "Pronto"  # Conserva lo stato leggibile dell’ultima verifica di integrità.
        self.etichette_banner_globali = []  # Registra le etichette banner vive per aggiornare tutte le sezioni senza duplicare lo stato.
        self.valori_strategia_gui = {}  # Conserva i parametri Strategie quando il pannello viene distrutto durante la navigazione.
        self.valori_ripristino_versionato_gui = {}  # Conserva separatamente i parametri del ripristino versionato, ora ospitato nella sezione Ripristino.
        self.valori_verifica_integrita_gui = {}  # Conserva radice e versione selezionata quando la pagina di verifica viene ricostruita.
        self.valori_sync_gui = {}  # Conserva i parametri Sincronizza quando il pannello viene distrutto durante la navigazione.
        self.valori_modalita_operativa = {"backup": {}, "ripristino": {}}  # Conserva separatamente campi e stato delle due viste storiche durante la navigazione.
        self.chiusura_in_corso = False  # Indica se l’utente ha confermato la chiusura mentre un worker è ancora attivo.
        self.evento_arresto = threading.Event()  # Crea l'evento thread-safe condiviso dal pulsante Stop.
        self.blocco_operazione_manuale = BloccoFile(CARTELLA_APPLICAZIONE / ".operazione.lock")  # Prepara il lock condiviso con lo scheduler per impedire copie o ripristini concorrenti.
        self.blocco_presenza_gui = BloccoFile(CARTELLA_APPLICAZIONE / ".gui.lock")  # Segnala al runner automatico che la GUI è aperta così evita notifiche Windows ridondanti.
        self.blocco_presenza_gui.acquisisci()  # Mantiene il lock per l’intera vita della finestra; una seconda GUI non compromette comunque il runner.
        self.firme_cronologia_visualizzate = set()  # Tiene traccia dei record persistenti già riportati nello specchietto Attività.
        self.firma_file_cronologia = None  # Conserva metadati del file per evitare letture JSON inutili quando nulla è cambiato.
        self.coda_eventi = queue.Queue()  # Crea la coda thread-safe usata per trasferire eventi dal worker alla GUI.
        self.coda_comandi_tray = queue.Queue()  # Crea una coda separata per trasferire le azioni dell’icona al thread Tk.
        self.gestore_tray = GestoreTray(self.coda_comandi_tray)  # Prepara una sola icona associata all’intera vita dell’applicazione.
        self.tray_disponibile = self.gestore_tray.avvia()  # Avvia l’icona prima che la finestra possa essere nascosta dall’utente.

        self.grid_columnconfigure(1, weight=1)  # Permette alla colonna principale di espandersi con la finestra.
        self.grid_rowconfigure(0, weight=1)  # Permette alla riga principale di espandersi con la finestra.

        self.crea_barra_laterale()  # Costruisce la barra laterale.
        self.crea_interfaccia_principale()  # Costruisce il contenuto principale.
        self.applica_tema_salvato()  # Applica l’eventuale preferenza globale di aspetto persistita.
        self.after(100, self.processa_eventi)  # Avvia il controllo periodico degli eventi prodotti dal thread di backup.
        self.after(100, self.processa_comandi_tray)  # Avvia il polling Tk dei comandi prodotti dal thread dell’icona Windows.
        self.avvia_scheduler_indipendente()  # Avvia in background il runner automatico; il lock interno impedisce istanze duplicate.
        self.carica_attivita_persistente()  # Popola subito Attività con la cronologia delle sessioni precedenti, compresi i backup eseguiti a GUI chiusa.
        self.after(INTERVALLO_AGGIORNAMENTO_CRONOLOGIA_MS, self.controlla_cronologia_esterna)  # Avvia il refresh leggero della cronologia prodotta dal runner separato.

    def avvia_scheduler_indipendente(self) -> None:
        """Avvia una sola istanza dello scheduler in un processo separato che può continuare anche dopo la chiusura della GUI."""
        try:  # Protegge l’avvio della GUI da eventuali problemi nella creazione del processo secondario.
            FILE_RICHIESTA_ARRESTO_SCHEDULER.unlink(missing_ok=True)  # Elimina un eventuale segnale residuo prima di avviare esplicitamente un nuovo runner.
            argomenti = [sys.executable, "-m", "fdbackup.runner_scheduler"]  # Riusa esattamente l’interprete corrente e l’avvio modulare raccomandato da Python.
            opzioni = {"cwd": str(CARTELLA_APPLICAZIONE), "close_fds": True}  # Imposta la radice corretta e impedisce l’eredità non necessaria di handle.
            if os.name == "nt":  # Applica su Windows i flag che rendono il runner indipendente e senza finestra console.
                opzioni["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW  # Separa il runner dalla console della GUI mantenendolo invisibile.
            else:  # Mantiene un comportamento equivalente negli ambienti POSIX usati per test e sviluppo.
                opzioni["start_new_session"] = True  # Crea una sessione separata senza usare preexec_fn.
            subprocess.Popen(argomenti, **opzioni)  # Avvia il runner senza attenderne la conclusione; il suo lock d’istanza elimina i duplicati.
        except OSError as errore:  # Gestisce esclusivamente errori di creazione del processo o dell’interprete.
            logger.exception("Impossibile avviare lo scheduler automatico: %s", errore)  # Registra il problema senza impedire l’uso manuale dell’applicazione.

    def acquisisci_blocco_operazione_manuale(self) -> bool:
        """Acquisisce il lock condiviso prima di un backup o ripristino manuale e informa l’utente se lo scheduler sta lavorando."""
        if self.blocco_operazione_manuale.acquisisci():  # Tenta l’acquisizione senza bloccare il thread grafico.
            return True  # Consente l’avvio dell’operazione manuale quando nessun altro processo sta lavorando.
        messagebox.showwarning("Operazione in corso", "FDBackup sta già eseguendo un'operazione automatica o manuale. Attendi il completamento e riprova.", parent=self)  # Evita accessi concorrenti agli stessi dati.
        return False  # Impedisce la creazione del worker concorrente.

    def rilascia_blocco_operazione_manuale(self) -> None:
        """Rilascia in modo idempotente il lock condiviso al termine di qualunque operazione manuale."""
        self.blocco_operazione_manuale.rilascia()  # Delega al lock interprocesso la chiusura sicura del descrittore.

    # ========================================================
    # CONFIGURAZIONE
    # ========================================================

    def carica_configurazione(self) -> dict:
        """Carica la configurazione dell'applicazione utilizzando il modulo dedicato."""
        return carica_configurazione(FILE_CONFIGURAZIONE)  # Delega al modulo dedicato la lettura e la validazione del file JSON.

    def carica_job_backup(self) -> list:
        """Carica i job persistenti senza impedire l'avvio della GUI se la relativa sezione è corrotta."""
        try:  # Prova a ricostruire tutti i job attraverso il modulo di persistenza già verificato.
            return carica_job_dalla_configurazione(self.configurazione)  # Restituisce la lista mantenendo ordine, ID e stato abilitato.

        except (TypeError, ValueError) as errore:  # Gestisce esclusivamente una struttura persistita non valida.
            logger.error("Impossibile caricare i job di backup dalla configurazione: %s", errore)  # Registra il problema nel log persistente.
            return []  # Mantiene avviabile la GUI senza inventare o correggere automaticamente job corrotti.

    def salva_configurazione(self) -> None:
        """Salva la configurazione corrente utilizzando il modulo dedicato."""
        try:  # Prova a delegare al modulo dedicato il salvataggio della configurazione.
            salva_configurazione(FILE_CONFIGURAZIONE, self.configurazione)  # Scrive la configurazione corrente nel file JSON dell'applicazione.
        except OSError as errore:  # Intercetta eventuali problemi di accesso o scrittura segnalati dal modulo dedicato.
            messagebox.showerror("Errore configurazione", f"Impossibile salvare la configurazione:\n{errore}")  # Mostra all'utente l'errore senza terminare l'applicazione.

    def carica_backup_singolo(self) -> dict:
        """Carica e valida la configurazione persistente del backup singolo mantenendo compatibili i file precedenti."""
        dati_salvati = self.configurazione.get("backup_singolo")  # Recupera la sezione dedicata senza alterare le altre chiavi del documento JSON.
        if dati_salvati is None:  # Riconosce una configurazione precedente priva del backup singolo persistente.
            return {"sorgente": "", "destinazione": "", "pianificazione": PianificazioneBackup()}  # Restituisce un valore neutro e retrocompatibile.
        if not isinstance(dati_salvati, dict):  # Verifica che la sezione abbia la struttura JSON prevista.
            logger.error("La configurazione del backup singolo non è un oggetto JSON valido.")  # Registra il problema senza impedire l'avvio della GUI.
            return {"sorgente": "", "destinazione": "", "pianificazione": PianificazioneBackup()}  # Evita di utilizzare dati corrotti.
        sorgente = dati_salvati.get("sorgente", "")  # Recupera il percorso sorgente persistito.
        destinazione = dati_salvati.get("destinazione", "")  # Recupera il percorso destinazione persistito.
        pianificazione_salvata = dati_salvati.get("pianificazione")  # Recupera l'eventuale pianificazione del backup singolo.
        if not isinstance(sorgente, str) or not isinstance(destinazione, str):  # Impedisce che valori JSON di tipo errato raggiungano i widget.
            logger.error("I percorsi del backup singolo salvato non sono validi.")  # Registra la configurazione incompatibile.
            return {"sorgente": "", "destinazione": "", "pianificazione": PianificazioneBackup()}  # Ripristina uno stato sicuro.
        try:  # Riusa la stessa validazione persistente adottata per le sorgenti dei job.
            pianificazione = PianificazioneBackup() if pianificazione_salvata is None else deserializza_pianificazione_backup(pianificazione_salvata)  # Ricostruisce il modello oppure usa il default disabilitato.
        except ValueError as errore:  # Gestisce una pianificazione corrotta senza bloccare l'intera applicazione.
            logger.error("Pianificazione del backup singolo non valida: %s", errore)  # Conserva il motivo nel log diagnostico.
            pianificazione = PianificazioneBackup()  # Disabilita soltanto la pianificazione non valida.
        return {"sorgente": sorgente.strip(), "destinazione": destinazione.strip(), "pianificazione": pianificazione}  # Restituisce la configurazione normalizzata pronta per la GUI.

    # ========================================================
    # SIDEBAR
    # ========================================================

    def crea_barra_laterale(self) -> None:
        """Crea la barra laterale ispirata al mockup professionale di FDBackup."""
        self.barra_laterale = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=COLORE_SIDEBAR)  # Crea una sidebar scura e compatta.
        self.barra_laterale.grid(row=0, column=0, sticky="ns")  # Estende la sidebar per tutta l'altezza della finestra.
        self.barra_laterale.grid_propagate(False)  # Mantiene stabile la larghezza della barra laterale.

        self.logo_sidebar = ctk.CTkLabel(self.barra_laterale, text="↻", font=ctk.CTkFont(size=52, weight="bold"), text_color="#169BFF")  # Crea un simbolo grafico semplice che richiama il backup.
        self.logo_sidebar.pack(pady=(28, 0))  # Posiziona il simbolo nella parte superiore della sidebar.

        self.nome_sidebar = ctk.CTkLabel(self.barra_laterale, text="FDBackup", font=ctk.CTkFont(size=24, weight="bold"))  # Mostra il nome del programma in evidenza.
        self.nome_sidebar.pack(pady=(0, 28))  # Separa il nome dai pulsanti di navigazione.

        self.pulsanti_navigazione = {}  # Conserva i pulsanti della sidebar per aggiornare visivamente la sezione attiva.
        voci_navigazione = (("⌂", "Home"), ("▣", "Backup"), ("◆", "Strategie"), ("⇄", "Sincronizza"), ("↶", "Ripristino"), ("⚙", "Impostazioni"), ("ⓘ", "Informazioni"))  # Definisce le voci della navigazione.
        for icona, testo_pulsante in voci_navigazione:  # Crea in sequenza tutte le voci della sidebar.
            comando = lambda sezione=testo_pulsante.lower(): self.mostra_sezione(sezione)  # Collega ogni voce a una sezione reale dell’applicazione.

            colore = COLORE_MENU_ATTIVO if testo_pulsante == "Backup" else COLORE_MENU_INATTIVO  # Evidenzia Backup come modalità iniziale.
            pulsante = ctk.CTkButton(self.barra_laterale, text=f"{icona}   {testo_pulsante}", anchor="w", height=48, corner_radius=10, fg_color=colore, hover_color=COLORE_MENU_HOVER, text_color=COLORE_MENU_TESTO_ATTIVO if testo_pulsante == "Backup" else COLORE_MENU_TESTO_INATTIVO, font=ctk.CTkFont(size=15), command=comando)  # Costruisce il pulsante di navigazione mantenendo testo e riquadro leggibili in entrambi i temi.
            pulsante.pack(fill="x", padx=12, pady=5)  # Posiziona il pulsante mantenendo margini uniformi.
            self.pulsanti_navigazione[testo_pulsante] = pulsante  # Memorizza il pulsante per modificarne il colore quando cambia modalità.

        self.etichetta_slogan = ctk.CTkLabel(self.barra_laterale, text="I tuoi dati, sempre al sicuro", text_color=("#111111", "#8BA9C7"), font=ctk.CTkFont(size=12))  # Mostra lo slogan nella parte bassa della sidebar.
        self.etichetta_slogan.pack(side="bottom", pady=(0, 12))  # Posiziona lo slogan sopra la versione.

        self.etichetta_versione = ctk.CTkLabel(self.barra_laterale, text="v0.1.0", text_color="#62758A", font=ctk.CTkFont(size=11))  # Mostra la versione attuale del prototipo.
        self.etichetta_versione.pack(side="bottom", pady=(0, 8))  # Posiziona la versione sul fondo della sidebar.

    def crea_interfaccia_principale(self) -> None:
        """Crea il nuovo layout principale mantenendo invariata la logica reale del backup."""
        self.contenuto_principale = ctk.CTkScrollableFrame(self, fg_color=COLORE_SFONDO, corner_radius=0)  # Crea un'area principale scura e scorrevole per finestre più piccole.
        self.contenuto_principale.grid(row=0, column=1, sticky="nsew")  # Occupa tutto lo spazio disponibile accanto alla sidebar.

        self.intestazione_operativa = ctk.CTkFrame(self.contenuto_principale, fg_color="transparent")  # Conserva la fascia del titolo per poterla ordinare coerentemente tra Backup e Ripristino tradizionale.
        self.intestazione_operativa.pack(fill="x", padx=18, pady=(16, 6))  # Posiziona inizialmente l'intestazione sopra il banner nella vista Backup.

        self.etichetta_titolo = ctk.CTkLabel(self.intestazione_operativa, text="Backup", font=ctk.CTkFont(size=22, weight="bold"))  # Crea il titolo della modalità attualmente selezionata.
        self.etichetta_titolo.pack(side="left")  # Posiziona il titolo nella parte sinistra dell'intestazione.

        self.pulsante_torna_tipi_ripristino = ctk.CTkButton(self.contenuto_principale, text="← Torna ai tipi di ripristino", command=lambda: self.mostra_sezione("ripristino"), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE)  # Offre al ripristino tradizionale lo stesso ritorno al centro Ripristino già disponibile nella pagina versionata.

        self.riquadro_banner = ctk.CTkFrame(self.contenuto_principale, height=250, corner_radius=16, fg_color=COLORE_RIQUADRO, border_width=1, border_color="#64778B")  # Crea l'area rettangolare dedicata al banner.
        self.riquadro_banner.pack(fill="x", padx=18, pady=(6, 12))  # Estende il riquadro lungo la larghezza disponibile.
        self.riquadro_banner.pack_propagate(False)  # Mantiene fissa l'altezza del riquadro anche senza immagine.

        self.etichetta_banner = ctk.CTkLabel(self.riquadro_banner, text="")  # Crea l'etichetta che ospiterà l'immagine scelta.
        self.etichetta_banner.pack(expand=True)  # Centra l'immagine nel riquadro banner.
        self.etichette_banner_globali.append(self.etichetta_banner)  # Registra anche il banner della vista Backup/Ripristino tra le viste sincronizzate.

        self.contenitore_segnaposto_banner = ctk.CTkFrame(self.riquadro_banner, fg_color="transparent")  # Crea il contenitore delle indicazioni mostrate quando manca il banner.
        self.contenitore_segnaposto_banner.place(relx=0.5, rely=0.5, anchor="center")  # Centra le indicazioni nel riquadro vuoto.
        ctk.CTkLabel(self.contenitore_segnaposto_banner, text="▧", font=ctk.CTkFont(size=46), text_color=COLORE_TESTO_TERZIARIO).pack()  # Mostra un semplice simbolo che richiama un'immagine.
        ctk.CTkLabel(self.contenitore_segnaposto_banner, text="Carica qui il tuo banner", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(2, 2))  # Spiega la funzione dell'area vuota.
        ctk.CTkLabel(self.contenitore_segnaposto_banner, text='Gestisci il banner dalla Home', text_color=COLORE_TESTO_SECONDARIO, font=ctk.CTkFont(size=13)).pack()  # Indica come scegliere il file.
        ctk.CTkLabel(self.contenitore_segnaposto_banner, text="Dimensioni consigliate: 1200 × 300 px (rapporto 4:1)", text_color="#9EADBF", font=ctk.CTkFont(size=12)).pack(pady=(5, 0))  # Comunica le dimensioni consigliate.
        ctk.CTkLabel(self.contenitore_segnaposto_banner, text="Formati supportati: PNG, JPG, JPEG", text_color="#7F91A5", font=ctk.CTkFont(size=12)).pack()  # Comunica i formati selezionabili.

        self.etichetta_info_banner = ctk.CTkLabel(self.contenuto_principale, text="", text_color=COLORE_TESTO_INFO, font=ctk.CTkFont(size=11))  # Mostra dimensioni e peso del banner caricato.
        self.etichetta_info_banner.pack(fill="x", padx=24, pady=(0, 4))  # Posiziona le informazioni immediatamente sotto il banner.

        if "banner" in self.configurazione:  # Controlla se esiste un banner salvato nella configurazione.
            self.carica_banner(self.configurazione["banner"])  # Ripristina il banner salvato all'avvio.

        self.scheda_job = ctk.CTkFrame(self.contenuto_principale, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea la prima area visiva dedicata ai job persistenti.
        self.scheda_job.pack(fill="x", padx=18, pady=8)  # Posiziona l'elenco dei job sopra la configurazione manuale già esistente.

        intestazione_job = ctk.CTkFrame(self.scheda_job, fg_color="transparent")  # Crea l'intestazione della nuova area multi-job.
        intestazione_job.pack(fill="x", padx=18, pady=(16, 8))  # Mantiene margini coerenti con le altre schede.

        ctk.CTkLabel(intestazione_job, text="Backup multi-sorgente", font=ctk.CTkFont(size=17, weight="bold")).pack(side="left")  # Introduce l'elenco dei job salvati.
        self.pulsante_nuovo_backup = ctk.CTkButton(intestazione_job, text="+  Backup multi-sorgente", width=150, height=38, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.apri_editor_nuovo_backup)  # Apre l’editor controllato per creare un nuovo JobBackup.
        self.pulsante_nuovo_backup.pack(side="right")  # Posiziona il comando futuro nella parte destra dell'intestazione.

        self.etichetta_fase_job = ctk.CTkLabel(self.scheda_job, text="Copia più cartelle sorgente in un’unica destinazione, mantenendole separate in sottocartelle.", text_color=COLORE_TESTO_ATTENUATO, font=ctk.CTkFont(size=11), anchor="w")  # Dichiara con precisione ciò che è già operativo e ciò che non lo è ancora.
        self.etichetta_fase_job.pack(fill="x", padx=18, pady=(0, 10))  # Posiziona la nota sotto l'intestazione.

        self.contenitore_job = ctk.CTkFrame(self.scheda_job, fg_color="transparent")  # Contiene dinamicamente una scheda per ogni job persistito.
        self.contenitore_job.pack(fill="x", padx=18, pady=(0, 16))  # Riserva lo spazio necessario all'elenco.
        self.aggiorna_elenco_job()  # Costruisce immediatamente la rappresentazione grafica dei job caricati.

        self.scheda_configurazione = ctk.CTkFrame(self.contenuto_principale, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea la scheda dei percorsi di backup.
        self.scheda_configurazione.pack(fill="x", padx=18, pady=8)  # Posiziona la scheda sotto il banner.
        ctk.CTkLabel(self.scheda_configurazione, text="Sorgente e destinazione", font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w", padx=18, pady=(16, 10))  # Mostra il titolo della scheda.

        riga_sorgente = ctk.CTkFrame(self.scheda_configurazione, fg_color="transparent")  # Crea la riga dedicata alla sorgente.
        riga_sorgente.pack(fill="x", padx=18, pady=6)  # Posiziona la riga della sorgente.
        self.etichetta_sorgente = ctk.CTkLabel(riga_sorgente, text="▰  Cartella sorgente", width=180, anchor="w", font=ctk.CTkFont(size=14))  # Crea l'etichetta del percorso sorgente modificabile in base alla modalità.
        self.etichetta_sorgente.pack(side="left")  # Posiziona l'etichetta della sorgente nella riga.
        self.campo_sorgente = ctk.CTkEntry(riga_sorgente, placeholder_text="Nessuna cartella selezionata", height=42)  # Crea il campo che contiene la sorgente.
        self.campo_sorgente.pack(side="left", fill="x", expand=True, padx=10)  # Estende il campo nella riga.
        ctk.CTkButton(riga_sorgente, text="Sfoglia...", width=120, height=42, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self.scegli_cartella(self.campo_sorgente)).pack(side="right")  # Apre la scelta della sorgente.

        riga_destinazione = ctk.CTkFrame(self.scheda_configurazione, fg_color="transparent")  # Crea la riga dedicata alla destinazione.
        riga_destinazione.pack(fill="x", padx=18, pady=(6, 16))  # Posiziona la riga della destinazione.
        self.etichetta_destinazione = ctk.CTkLabel(riga_destinazione, text="▰  Cartella destinazione", width=180, anchor="w", font=ctk.CTkFont(size=14))  # Crea l'etichetta della destinazione modificabile in base alla modalità.
        self.etichetta_destinazione.pack(side="left")  # Posiziona l'etichetta della destinazione nella riga.
        self.campo_destinazione = ctk.CTkEntry(riga_destinazione, placeholder_text="Nessuna cartella selezionata", height=42)  # Crea il campo che contiene la destinazione.
        self.campo_destinazione.pack(side="left", fill="x", expand=True, padx=10)  # Estende il campo nella riga.
        ctk.CTkButton(riga_destinazione, text="Sfoglia...", width=120, height=42, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self.scegli_cartella(self.campo_destinazione)).pack(side="right")  # Apre la scelta della destinazione.

        pianificazione_salvata_singola = self.backup_singolo["pianificazione"]  # Recupera il modello già validato durante l'avvio dell'applicazione.
        self.scheda_pianificazione_singola = ctk.CTkFrame(self.scheda_configurazione, corner_radius=10, fg_color=COLORE_RIQUADRO)  # Crea un riquadro dedicato alla pianificazione del percorso singolo.
        self.scheda_pianificazione_singola.pack(fill="x", padx=18, pady=(0, 16))  # Mantiene la pianificazione visivamente collegata a sorgente e destinazione.
        self.variabile_pianificazione_singola = ctk.BooleanVar(value=pianificazione_salvata_singola.abilitata)  # Collega la checkbox allo stato persistito della pianificazione singola.
        self.variabili_giorni_singoli = [ctk.BooleanVar(value=indice in pianificazione_salvata_singola.giorni) for indice in range(7)]  # Precarica i sette giorni con la convenzione 0=lunedì ... 6=domenica.
        self.controlli_pianificazione_singola = []  # Conserva i widget da abilitare o disabilitare insieme alla pianificazione.
        ctk.CTkCheckBox(self.scheda_pianificazione_singola, text="Pianifica automaticamente questo backup singolo", variable=self.variabile_pianificazione_singola, command=self.aggiorna_stato_pianificazione_backup_singolo).pack(anchor="w", padx=14, pady=(12, 6))  # Permette di attivare la pianificazione senza avviare ancora lo scheduler.
        riga_pianificazione_singola = ctk.CTkFrame(self.scheda_pianificazione_singola, fg_color="transparent")  # Raggruppa giorni, ora e comando di salvataggio.
        riga_pianificazione_singola.pack(fill="x", padx=14, pady=(0, 12))  # Posiziona i controlli temporali sotto la checkbox principale.
        nomi_giorni_singoli = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")  # Mantiene le stesse abbreviazioni usate nei job multi-sorgente.
        for indice, nome_giorno in enumerate(nomi_giorni_singoli):  # Crea una checkbox indipendente per ogni giorno della settimana.
            controllo_giorno = ctk.CTkCheckBox(riga_pianificazione_singola, text=nome_giorno, variable=self.variabili_giorni_singoli[indice], width=64)  # Collega il giorno visibile al relativo indice numerico.
            controllo_giorno.pack(side="left", padx=(0, 4))  # Mantiene i giorni su una riga compatta.
            self.controlli_pianificazione_singola.append(controllo_giorno)  # Memorizza il widget per governarne lo stato.
        ctk.CTkLabel(riga_pianificazione_singola, text="Ora:", text_color=COLORE_TESTO_SECONDARIO).pack(side="left", padx=(10, 5))  # Introduce il campo orario.
        self.campo_ora_pianificazione_singola = ctk.CTkEntry(riga_pianificazione_singola, width=90, height=34, justify="center")  # Riusa la stessa esperienza HH:MM del multi-sorgente.
        self.campo_ora_pianificazione_singola.insert(0, pianificazione_salvata_singola.ora if pianificazione_salvata_singola.ora else "__:__")  # Mostra l'orario persistito oppure la maschera vuota.
        self.campo_ora_pianificazione_singola.bind("<KeyPress>", lambda evento: self.gestisci_tasto_campo_ora(evento, self.campo_ora_pianificazione_singola))  # Mantiene fisso ':' e limita l'input a 00:00-23:59.
        self.campo_ora_pianificazione_singola.bind("<FocusIn>", lambda evento: self.posiziona_cursore_campo_ora(self.campo_ora_pianificazione_singola))  # Porta il cursore sulla prima cifra ancora libera.
        self.campo_ora_pianificazione_singola.pack(side="left")  # Posiziona il campo dopo i giorni.
        self.controlli_pianificazione_singola.append(self.campo_ora_pianificazione_singola)  # Include l'orario nei controlli governati dalla checkbox.
        ctk.CTkButton(riga_pianificazione_singola, text="Salva pianificazione", width=150, height=34, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.salva_backup_singolo).pack(side="right")  # Salva insieme percorsi e pianificazione necessari a una futura esecuzione automatica.
        self.campo_sorgente.insert(0, self.backup_singolo["sorgente"])  # Ripristina la sorgente singola salvata, se presente.
        self.campo_destinazione.insert(0, self.backup_singolo["destinazione"])  # Ripristina la destinazione singola salvata, se presente.
        self.aggiorna_stato_pianificazione_backup_singolo()  # Applica subito lo stato corretto a giorni e ora.

        self.scheda_opzioni = ctk.CTkFrame(self.contenuto_principale, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea la scheda delle funzioni pianificate.
        self.scheda_opzioni.pack(fill="x", padx=18, pady=8)  # Posiziona la scheda delle opzioni.
        self.etichetta_opzioni = ctk.CTkLabel(self.scheda_opzioni, text="Opzioni di backup", font=ctk.CTkFont(size=17, weight="bold"))  # Crea il titolo della scheda opzioni.
        self.etichetta_opzioni.pack(anchor="w", padx=18, pady=(14, 4))  # Posiziona il titolo della scheda opzioni.
        self.etichetta_descrizione_opzioni = ctk.CTkLabel(self.scheda_opzioni, text="Le opzioni configurabili vengono salvate separatamente per ogni job.", text_color=COLORE_TESTO_ATTENUATO, font=ctk.CTkFont(size=11))  # Spiega che le scelte operative appartengono ai singoli job persistenti.
        self.etichetta_descrizione_opzioni.pack(anchor="w", padx=18, pady=(0, 8))  # Posiziona la descrizione sotto il titolo.
        self.etichetta_stato_sottocartelle = ctk.CTkLabel(self.scheda_opzioni, text="• Includi sottocartelle — configurabile per ogni job", text_color=COLORE_TESTO_SECONDARIO, anchor="w")  # Informa che la ricorsione è una proprietà reale del singolo job.
        self.etichetta_stato_sottocartelle.pack(fill="x", padx=20, pady=3)  # Posiziona l'indicatore informativo nella scheda.
        self.etichetta_stato_integrita = ctk.CTkLabel(self.scheda_opzioni, text="• Verifica integrità dopo la copia — configurabile per ogni job", text_color=COLORE_TESTO_SECONDARIO, anchor="w")  # Informa che la verifica post-copia è una proprietà reale del singolo job.
        self.etichetta_stato_integrita.pack(fill="x", padx=20, pady=3)  # Posiziona l'indicatore informativo nella scheda.
        self.etichetta_stato_struttura = ctk.CTkLabel(self.scheda_opzioni, text="✓ Struttura delle cartelle mantenuta", text_color=("#187A32", "#5FD17A"), anchor="w")  # Dichiara il comportamento garantito dal motore quando vengono incluse le sottocartelle.
        self.etichetta_stato_struttura.pack(fill="x", padx=20, pady=3)  # Posiziona l'indicatore del comportamento garantito.
        self.etichetta_stato_logging = ctk.CTkLabel(self.scheda_opzioni, text="✓ Logging persistente attivo", text_color=("#187A32", "#5FD17A"), anchor="w")  # Dichiara che il logging applicativo è globale e sempre configurato.
        self.etichetta_stato_logging.pack(fill="x", padx=20, pady=(3, 12))  # Posiziona l'indicatore del logging e chiude visivamente la scheda.

        contenitore_pulsanti = ctk.CTkFrame(self.contenuto_principale, fg_color="transparent")  # Crea la fascia dei comandi principali.
        contenitore_pulsanti.pack(fill="x", padx=18, pady=(8, 4))  # Posiziona i comandi sotto le opzioni.
        self.pulsante_avvia = ctk.CTkButton(contenitore_pulsanti, text="▶   Avvia backup", width=250, height=54, corner_radius=14, fg_color=COLORE_PULSANTE_AVVIA, hover_color=COLORE_PULSANTE_AVVIA_HOVER, text_color=COLORE_TESTO_PULSANTE, font=ctk.CTkFont(size=16, weight="bold"), command=self.avvia_operazione)  # Crea il pulsante principale che avvia la modalità selezionata.
        self.pulsante_avvia.pack(side="left")  # Posiziona Avvia sulla sinistra come nel mockup.
        self.pulsante_stop = ctk.CTkButton(contenitore_pulsanti, text="■   Stop", width=180, height=54, corner_radius=14, fg_color=COLORE_PULSANTE_PERICOLO, hover_color=COLORE_PULSANTE_PERICOLO_HOVER, text_color=COLORE_TESTO_PULSANTE, text_color_disabled="#F2D9DC", command=self.ferma_operazione, state="disabled")  # Crea il pulsante Stop condiviso tra backup e ripristino.
        self.pulsante_stop.pack(side="right")  # Posiziona Stop sulla destra.

        self.etichetta_stato = ctk.CTkLabel(self.contenuto_principale, text="Pronto", anchor="w", text_color=COLORE_TESTO_STATO)  # Crea l'indicatore dello stato corrente.
        self.etichetta_stato.pack(fill="x", padx=22, pady=(8, 2))  # Posiziona lo stato sopra la barra di avanzamento.
        self.barra_avanzamento = ctk.CTkProgressBar(self.contenuto_principale, mode="indeterminate", height=8)  # Crea la barra animata per il backup in corso.
        self.barra_avanzamento.pack(fill="x", padx=22, pady=(0, 8))  # Posiziona la barra sotto lo stato.
        self.barra_avanzamento.set(0)  # Imposta la barra nello stato iniziale.

        intestazione_attivita = ctk.CTkFrame(self.contenuto_principale, fg_color="transparent")  # Raggruppa il titolo Attività e il comando di cancellazione della cronologia sulla stessa riga.
        intestazione_attivita.pack(fill="x", padx=22, pady=(8, 4))  # Mantiene l’intestazione allineata al riquadro delle attività.
        ctk.CTkLabel(intestazione_attivita, text="Attività", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")  # Introduce l'area delle attività reali del motore.
        ctk.CTkButton(intestazione_attivita, text="Cancella cronologia", width=150, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, command=self.cancella_cronologia_utente).pack(side="right")  # Sposta la cancellazione accanto ad Attività senza modificare la logica persistente.
        self.casella_log = ctk.CTkTextbox(self.contenuto_principale, height=150, corner_radius=12, fg_color=COLORE_RIQUADRO, border_width=1, border_color=COLORE_BORDO, text_color=("#1E2F3F", "#E8F1FA"))  # Crea il log visuale con uno sfondo e un bordo sempre distinguibili dal contenitore principale.
        self.casella_log.pack(fill="both", expand=True, padx=18, pady=(0, 18))  # Estende il log nella parte finale della schermata.
        self.casella_log.configure(state="disabled")  # Impedisce la modifica manuale del contenuto del log.
        self.casella_log.bind("<MouseWheel>", self.gestisci_scroll_attivita, add="+")  # Intercetta la rotellina sopra Attività per impedire che lo stesso evento faccia scorrere anche la pagina principale.
        self.casella_log.bind("<Button-4>", self.gestisci_scroll_attivita, add="+")  # Gestisce anche lo scroll verso l'alto negli ambienti X11 senza alterare il comportamento Windows.
        self.casella_log.bind("<Button-5>", self.gestisci_scroll_attivita, add="+")  # Gestisce anche lo scroll verso il basso negli ambienti X11 senza alterare il comportamento Windows.

    def gestisci_scroll_attivita(self, evento) -> str:
        """Fa scorrere soltanto il riquadro Attività quando la rotellina viene usata al suo interno."""
        if sys.platform.startswith("win"):  # Applica la convenzione delta usata da Tk su Windows, ambiente principale di FDBackup.
            direzione = -1 if evento.delta > 0 else 1  # Converte il segno della rotellina in una singola unità verticale coerente con tkinter.Text.
            self.casella_log.yview_scroll(direzione, "units")  # Sposta esclusivamente il contenuto del riquadro Attività di una unità.
        elif sys.platform == "darwin":  # Mantiene un comportamento sensato anche sui sistemi macOS usati eventualmente per sviluppo.
            direzione = -1 if evento.delta > 0 else 1  # Normalizza il delta macOS evitando di trasferire valori grezzi troppo grandi al textbox.
            self.casella_log.yview_scroll(direzione, "units")  # Sposta esclusivamente il contenuto del riquadro Attività.
        else:  # Gestisce gli eventi Button-4 e Button-5 prodotti normalmente da X11/Linux.
            direzione = -1 if getattr(evento, "num", None) == 4 else 1  # Traduce Button-4 in salita e Button-5 in discesa.
            self.casella_log.yview_scroll(direzione, "units")  # Sposta esclusivamente il contenuto del riquadro Attività.
        return "break"  # Interrompe la propagazione così il CTkScrollableFrame esterno non riceve la stessa rotazione della rotellina.

    def operazione_in_corso(self) -> bool:
        """Restituisce True quando un backup o un ripristino sta ancora usando la configurazione corrente."""
        backup_attivo = self.thread_backup is not None and self.thread_backup.is_alive()  # Controlla se il worker di backup è ancora attivo.
        ripristino_attivo = self.thread_ripristino is not None and self.thread_ripristino.is_alive()  # Controlla se il worker di ripristino è ancora attivo.
        return backup_attivo or ripristino_attivo  # Impedisce modifiche alla configurazione mentre un worker potrebbe leggerla.

    def apri_editor_nuovo_backup(self) -> None:
        """Apre l'editor inline in modalità creazione di un nuovo backup multi-sorgente."""
        self.apri_editor_backup()  # Riutilizza lo stesso editor usato anche per la modifica, senza duplicare la logica grafica.

    def apri_editor_modifica_backup(self, job: JobBackup) -> None:
        """Apre l'editor inline precaricando un job esistente e conservandone le identità persistenti."""
        self.apri_editor_backup(job)  # Passa il job reale all'editor affinché nome, percorsi, stato e ID possano essere preservati.

    def apri_editor_backup(self, job: JobBackup | None = None) -> None:
        """Costruisce l'editor inline per creare un nuovo job oppure modificare un job esistente."""
        if self.operazione_in_corso():  # Evita che la configurazione venga modificata mentre un worker la sta utilizzando.
            messagebox.showwarning("Operazione in corso", "Attendi il termine del backup o del ripristino prima di modificare la configurazione.", parent=self)  # Spiega il motivo del blocco.
            return  # Mantiene invariati configurazione e interfaccia.

        if self.editor_nuovo_backup is not None and self.editor_nuovo_backup.winfo_exists():  # Controlla se esiste già un editor aperto.
            if job is not None and self.id_job_in_modifica != job.id_job:  # Rileva il tentativo di modificare un job diverso mentre l'editor è occupato.
                messagebox.showwarning("Editor già aperto", "Chiudi o salva l'editor corrente prima di modificare un altro backup.", parent=self)  # Evita di perdere modifiche non salvate.
            self.campo_nome_nuovo_backup.focus_set()  # Riporta il cursore sul primo campo disponibile.
            return  # Non crea un secondo editor concorrente.

        self.id_job_in_modifica = job.id_job if job is not None else None  # Memorizza l'ID soltanto quando stiamo modificando un job esistente.
        self.righe_sorgenti_nuovo_backup = []  # Riparte da una collezione di righe coerente con il job aperto.
        self.editor_nuovo_backup = ctk.CTkFrame(self.scheda_job, corner_radius=14, fg_color=COLORE_EDITOR, border_width=1, border_color=COLORE_BORDO_EDITOR)  # Crea l'editor direttamente nella sezione multi-sorgente.
        self.editor_nuovo_backup.pack(fill="x", padx=18, pady=(0, 12), before=self.contenitore_job)  # Inserisce l'editor sopra l'elenco dei job salvati.

        contenitore = self.editor_nuovo_backup  # Usa il frame incorporato come contenitore principale dell'editor.
        testo_editor = "Modifica il backup mantenendo la sua identità persistente." if job is not None else "Definisci un job con una destinazione e una o più cartelle sorgente."  # Adatta la descrizione alla modalità corrente.
        ctk.CTkLabel(contenitore, text=testo_editor, text_color=COLORE_TESTO_INFO).pack(anchor="w", padx=24, pady=(12, 18))  # Spiega sinteticamente lo scopo dell'editor.

        scheda_generale = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA)  # Raggruppa nome e destinazione del job.
        scheda_generale.pack(fill="x", padx=24, pady=6)  # Posiziona la scheda generale con margini uniformi.
        ctk.CTkLabel(scheda_generale, text="Nome backup", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x", padx=16, pady=(14, 5))  # Introduce il nome leggibile del job.
        self.campo_nome_nuovo_backup = ctk.CTkEntry(scheda_generale, placeholder_text="Es. Documenti personali", height=40)  # Permette di inserire o modificare il nome del job.
        self.campo_nome_nuovo_backup.pack(fill="x", padx=16, pady=(0, 12))  # Estende il campo lungo la scheda.

        ctk.CTkLabel(scheda_generale, text="Destinazione principale", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x", padx=16, pady=(0, 5))  # Introduce la radice di destinazione.
        riga_destinazione = ctk.CTkFrame(scheda_generale, fg_color="transparent")  # Contiene campo e pulsante di scelta della destinazione.
        riga_destinazione.pack(fill="x", padx=16, pady=(0, 16))  # Posiziona la riga di destinazione.
        self.campo_destinazione_nuovo_backup = ctk.CTkEntry(riga_destinazione, placeholder_text="Seleziona la cartella che conterrà il backup", height=40)  # Conserva il percorso principale del job.
        self.campo_destinazione_nuovo_backup.pack(side="left", fill="x", expand=True, padx=(0, 8))  # Lascia spazio al pulsante Sfoglia.
        ctk.CTkButton(riga_destinazione, text="Sfoglia...", width=110, height=40, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.scegli_destinazione_nuovo_backup).pack(side="right")  # Apre la scelta nativa della destinazione.

        scheda_sorgenti = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA)  # Raggruppa tutte le sorgenti del job.
        scheda_sorgenti.pack(fill="x", padx=24, pady=8)  # Posiziona la scheda sotto i dati generali.
        intestazione_sorgenti = ctk.CTkFrame(scheda_sorgenti, fg_color="transparent")  # Crea la riga di titolo e comando di aggiunta.
        intestazione_sorgenti.pack(fill="x", padx=16, pady=(14, 8))  # Posiziona l'intestazione della sezione sorgenti.
        ctk.CTkLabel(intestazione_sorgenti, text="Sorgenti", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")  # Mostra il titolo della sezione.
        ctk.CTkButton(intestazione_sorgenti, text="+  Aggiungi sorgente", width=150, height=34, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.aggiungi_riga_sorgente_nuovo_backup).pack(side="right")  # Permette di aggiungere dinamicamente una nuova sorgente.
        self.contenitore_sorgenti_nuovo_backup = ctk.CTkFrame(scheda_sorgenti, fg_color="transparent")  # Ospita le righe sorgente create dinamicamente.
        self.contenitore_sorgenti_nuovo_backup.pack(fill="x", padx=16, pady=(0, 14))  # Mantiene un margine interno uniforme.

        scheda_opzioni_job = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA)  # Raggruppa le opzioni realmente applicate dal motore al job corrente.
        scheda_opzioni_job.pack(fill="x", padx=24, pady=8)  # Posiziona le opzioni sotto l'elenco delle sorgenti.
        ctk.CTkLabel(scheda_opzioni_job, text="Opzioni del backup", font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(fill="x", padx=16, pady=(14, 6))  # Introduce le proprietà operative persistenti del job.
        self.variabile_includi_sottocartelle = ctk.BooleanVar(value=job.includi_sottocartelle if job is not None else True)  # Precarica il valore persistito oppure il default compatibile con il comportamento storico.
        self.variabile_verifica_integrita = ctk.BooleanVar(value=job.verifica_integrita if job is not None else True)  # Precarica il valore persistito oppure il default che mantiene la verifica post-copia.
        ctk.CTkCheckBox(scheda_opzioni_job, text="Includi sottocartelle", variable=self.variabile_includi_sottocartelle).pack(anchor="w", padx=18, pady=5)  # Permette di decidere se il motore deve attraversare le directory figlie.
        ctk.CTkCheckBox(scheda_opzioni_job, text="Verifica integrità dopo la copia", variable=self.variabile_verifica_integrita).pack(anchor="w", padx=18, pady=5)  # Permette di abilitare o disabilitare la verifica SHA-256 post-copia.
        ctk.CTkLabel(scheda_opzioni_job, text="La struttura delle cartelle viene mantenuta automaticamente; il logging persistente resta sempre attivo.", text_color=COLORE_TESTO_ATTENUATO, anchor="w").pack(fill="x", padx=18, pady=(4, 14))  # Chiarisce i due comportamenti globali che non sono opzioni disattivabili del job.

        if job is None:  # In creazione serve subito una prima riga vuota.
            self.aggiungi_riga_sorgente_nuovo_backup()  # Crea la sorgente minima richiesta da un nuovo job abilitato.
        else:  # In modifica ricostruisce esattamente le sorgenti persistite.
            self.campo_nome_nuovo_backup.insert(0, job.nome)  # Precarica il nome leggibile corrente.
            self.campo_destinazione_nuovo_backup.insert(0, str(job.destinazione))  # Precarica la destinazione principale corrente.
            for sorgente in job.sorgenti:  # Mantiene l'ordine persistito delle sorgenti esistenti.
                self.aggiungi_riga_sorgente_nuovo_backup(sorgente)  # Precarica percorso, nome logico e ID della sorgente.
            if not job.sorgenti:  # Gestisce anche un eventuale job disabilitato persistito senza sorgenti.
                self.aggiungi_riga_sorgente_nuovo_backup()  # Offre una riga vuota per consentire di renderlo nuovamente configurabile.

        comandi = ctk.CTkFrame(contenitore, fg_color="transparent")  # Crea la fascia finale dei comandi dell'editor.
        comandi.pack(fill="x", padx=24, pady=(12, 24))  # Separa i comandi dai campi.
        ctk.CTkButton(comandi, text="Annulla", width=130, height=42, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, command=self.chiudi_editor_nuovo_backup).pack(side="left")  # Chiude senza modificare dati persistenti.
        testo_salvataggio = "Salva modifiche" if job is not None else "Salva backup"  # Distingue chiaramente creazione e modifica.
        ctk.CTkButton(comandi, text=testo_salvataggio, width=170, height=42, fg_color=COLORE_PULSANTE_AVVIA, hover_color=COLORE_PULSANTE_AVVIA_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.salva_nuovo_backup).pack(side="right")  # Avvia costruzione, validazione e persistenza del candidato.

        self.pulsante_nuovo_backup.configure(state="disabled")  # Impedisce di aprire un secondo editor contemporaneamente.
        self.campo_nome_nuovo_backup.focus_set()  # Porta il cursore sul primo campo utile.

    def chiudi_editor_nuovo_backup(self) -> None:
        """Rimuove l'editor incorporato senza modificare i dati persistenti."""
        if self.editor_nuovo_backup is not None and self.editor_nuovo_backup.winfo_exists():  # Controlla se l'editor è ancora visibile.
            self.editor_nuovo_backup.destroy()  # Rimuove soltanto il modulo temporaneo dalla schermata principale.
        self.editor_nuovo_backup = None  # Elimina il riferimento al modulo ormai chiuso.
        self.id_job_in_modifica = None  # Dimentica l'eventuale identità del job in modifica.
        self.pulsante_nuovo_backup.configure(state="normal")  # Riabilita il comando per creare un altro job.
        self.righe_sorgenti_nuovo_backup = []  # Elimina i riferimenti alle righe non più utilizzabili.

    def scegli_destinazione_nuovo_backup(self) -> None:
        """Seleziona la destinazione principale del job attualmente aperto nell'editor."""
        percorso = filedialog.askdirectory(parent=self, title="Seleziona la destinazione del backup")  # Apre il dialogo nativo sopra la finestra principale.
        if percorso:  # Considera valida soltanto una selezione effettiva.
            self.campo_destinazione_nuovo_backup.delete(0, "end")  # Rimuove l'eventuale percorso precedente.
            self.campo_destinazione_nuovo_backup.insert(0, percorso)  # Inserisce il percorso scelto nel campo del job.

    def aggiungi_riga_sorgente_nuovo_backup(self, sorgente: SorgenteBackup | None = None) -> None:
        """Aggiunge una sorgente all'editor includendo la relativa pianificazione settimanale persistente."""
        riga = ctk.CTkFrame(self.contenitore_sorgenti_nuovo_backup, corner_radius=10, fg_color=COLORE_RIQUADRO)  # Crea un contenitore autonomo per tutti i dati della singola sorgente.
        riga.pack(fill="x", pady=5)  # Inserisce la sorgente sotto quelle già presenti mantenendo l'ordine persistito.

        riga_percorsi = ctk.CTkFrame(riga, fg_color="transparent")  # Separa i campi filesystem dai controlli della pianificazione.
        riga_percorsi.pack(fill="x", padx=10, pady=(10, 5))  # Posiziona i campi principali nella parte superiore della scheda sorgente.
        campo_percorso = ctk.CTkEntry(riga_percorsi, placeholder_text="Cartella sorgente", height=38)  # Conserva il percorso reale della sorgente.
        campo_percorso.pack(side="left", fill="x", expand=True, padx=(0, 6))  # Lascia al percorso la maggior parte dello spazio disponibile.
        campo_nome_destinazione = ctk.CTkEntry(riga_percorsi, placeholder_text="Nome nella destinazione", width=190, height=38)  # Conserva il nome stabile della sottocartella associata.
        campo_nome_destinazione.pack(side="left", padx=6)  # Posiziona il nome logico accanto al percorso.

        pianificazione_iniziale = sorgente.pianificazione if sorgente is not None else PianificazioneBackup()  # Riusa la pianificazione persistita oppure il default disabilitato del modello.
        variabile_pianificazione = ctk.BooleanVar(value=pianificazione_iniziale.abilitata)  # Collega lo stato della pianificazione alla checkbox della sorgente.
        variabili_giorni = [ctk.BooleanVar(value=indice in pianificazione_iniziale.giorni) for indice in range(7)]  # Precarica i sette giorni usando la convenzione 0=lunedì ... 6=domenica.
        campo_ora = ctk.CTkEntry(riga, width=90, height=34, justify="center")  # Crea il campo orario mascherato mantenendo sempre visibile il separatore tra ore e minuti.
        testo_ora_iniziale = pianificazione_iniziale.ora if pianificazione_iniziale.ora else "__:__"  # Usa l'orario persistito oppure la maschera vuota quando la sorgente non ha ancora un orario.
        campo_ora.insert(0, testo_ora_iniziale)  # Mostra subito la struttura HH:MM senza affidarsi a un placeholder che scomparirebbe durante la digitazione.
        campo_ora.bind("<KeyPress>", lambda evento, campo=campo_ora: self.gestisci_tasto_campo_ora(evento, campo))  # Intercetta la tastiera per mantenere la maschera, saltare i due punti e impedire valori impossibili.
        campo_ora.bind("<FocusIn>", lambda evento, campo=campo_ora: self.posiziona_cursore_campo_ora(campo))  # Porta il cursore sul primo spazio libero quando l'utente entra nel campo.

        dati_riga = {"contenitore": riga, "percorso": campo_percorso, "nome_destinazione": campo_nome_destinazione, "id_sorgente": sorgente.id_sorgente if sorgente is not None else None, "pianificazione_abilitata": variabile_pianificazione, "giorni_pianificazione": variabili_giorni, "ora_pianificazione": campo_ora, "controlli_pianificazione": []}  # Conserva widget, identità e valori temporanei necessari al salvataggio.
        self.righe_sorgenti_nuovo_backup.append(dati_riga)  # Registra la riga nell'ordine visualizzato e persistito.
        ctk.CTkButton(riga_percorsi, text="Sfoglia...", width=90, height=38, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda dati=dati_riga: self.scegli_sorgente_nuovo_backup(dati)).pack(side="left", padx=6)  # Collega la scelta cartella alla sorgente corretta.
        ctk.CTkButton(riga_percorsi, text="Rimuovi", width=82, height=38, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, command=lambda dati=dati_riga: self.rimuovi_riga_sorgente_nuovo_backup(dati)).pack(side="left", padx=(6, 0))  # Permette di eliminare la singola sorgente dall'editor.

        riga_attivazione = ctk.CTkFrame(riga, fg_color="transparent")  # Crea la riga che abilita o disabilita la pianificazione della sorgente.
        riga_attivazione.pack(fill="x", padx=12, pady=(4, 2))  # Mantiene la pianificazione visivamente associata alla sorgente.
        ctk.CTkCheckBox(riga_attivazione, text="Pianifica automaticamente questa sorgente", variable=variabile_pianificazione, command=lambda dati=dati_riga: self.aggiorna_stato_pianificazione_sorgente(dati)).pack(side="left")  # Attiva i controlli temporali senza avviare alcuno scheduler.

        riga_pianificazione = ctk.CTkFrame(riga, fg_color="transparent")  # Raggruppa giorni della settimana e ora della singola sorgente.
        riga_pianificazione.pack(fill="x", padx=12, pady=(2, 10))  # Posiziona i controlli temporali sotto la checkbox di attivazione.
        nomi_giorni = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")  # Traduce nella GUI la convenzione numerica interna del modello.
        for indice, nome_giorno in enumerate(nomi_giorni):  # Crea un controllo indipendente per ciascun giorno della settimana.
            controllo_giorno = ctk.CTkCheckBox(riga_pianificazione, text=nome_giorno, variable=variabili_giorni[indice], width=64)  # Collega il giorno visualizzato al relativo indice 0-6.
            controllo_giorno.pack(side="left", padx=(0, 4))  # Mantiene i sette giorni su una riga compatta.
            dati_riga["controlli_pianificazione"].append(controllo_giorno)  # Memorizza il widget per abilitarlo o disabilitarlo insieme alla pianificazione.
        ctk.CTkLabel(riga_pianificazione, text="Ora:", text_color=COLORE_TESTO_SECONDARIO).pack(side="left", padx=(10, 5))  # Introduce chiaramente il campo dell'orario.
        campo_ora.pack(side="left")  # Posiziona il campo HH:MM dopo i giorni.
        dati_riga["controlli_pianificazione"].append(campo_ora)  # Include il campo ora nei controlli governati dalla checkbox principale.

        if sorgente is not None:  # Precarica i valori quando la riga rappresenta una sorgente persistita.
            campo_percorso.insert(0, str(sorgente.percorso))  # Ripristina il percorso corrente della sorgente.
            campo_nome_destinazione.insert(0, sorgente.nome_destinazione)  # Ripristina il nome logico corrente senza alterarne l'ID.

        self.aggiorna_stato_pianificazione_sorgente(dati_riga)  # Applica immediatamente lo stato corretto ai controlli giorni/ora.

    def posiziona_cursore_campo_ora(self, campo_ora: ctk.CTkEntry) -> None:
        """Posiziona il cursore sul primo carattere orario ancora da compilare, saltando sempre i due punti."""
        testo_corrente = campo_ora.get()  # Legge la maschera oraria attualmente visualizzata.
        posizioni_cifre = (0, 1, 3, 4)  # Definisce le sole quattro posizioni modificabili della maschera HH:MM.
        posizione_libera = next((posizione for posizione in posizioni_cifre if posizione < len(testo_corrente) and testo_corrente[posizione] == "_"), 5)  # Cerca la prima cifra non ancora inserita oppure usa la fine del campo.
        campo_ora.icursor(posizione_libera)  # Sposta il cursore nella posizione utile senza modificare il testo.

    def gestisci_tasto_campo_ora(self, evento, campo_ora: ctk.CTkEntry) -> str | None:
        """Gestisce la digitazione HH:MM mantenendo la maschera e accettando soltanto ore 00-23 e minuti 00-59."""
        tasti_navigazione = {"Tab", "ISO_Left_Tab", "Return", "Escape"}  # Elenca i tasti che devono conservare il normale comportamento di navigazione della GUI.
        if evento.keysym in tasti_navigazione:  # Riconosce i tasti che non modificano direttamente l'orario.
            return None  # Lascia a Tkinter la gestione standard del cambio focus o della conferma.

        testo_corrente = campo_ora.get()  # Recupera il contenuto visualizzato prima di elaborare il nuovo tasto.
        if len(testo_corrente) != 5 or testo_corrente[2] != ":":  # Protegge la logica da eventuali contenuti anomali introdotti esternamente.
            campo_ora.delete(0, "end")  # Elimina il contenuto non conforme alla maschera prevista.
            campo_ora.insert(0, "__:__")  # Ripristina una maschera oraria valida e riconoscibile.
            testo_corrente = "__:__"  # Allinea anche la copia locale al valore appena ripristinato.

        if evento.keysym in {"Left", "Right", "Home", "End"}:  # Gestisce esplicitamente la navigazione interna per non lasciare il cursore sui due punti.
            posizione_corrente = campo_ora.index("insert")  # Legge la posizione corrente del cursore nell'entry.
            if evento.keysym == "Left":  # Sposta il cursore verso la cifra precedente.
                nuova_posizione = max(0, posizione_corrente - 1)  # Calcola la posizione precedente senza uscire dal campo.
                nuova_posizione = 1 if nuova_posizione == 2 else nuova_posizione  # Salta il separatore centrale andando direttamente alla seconda cifra delle ore.
            elif evento.keysym == "Right":  # Sposta il cursore verso la cifra successiva.
                nuova_posizione = min(5, posizione_corrente + 1)  # Calcola la posizione successiva senza superare la fine del campo.
                nuova_posizione = 3 if nuova_posizione == 2 else nuova_posizione  # Salta il separatore centrale andando direttamente alla prima cifra dei minuti.
            elif evento.keysym == "Home":  # Porta il cursore all'inizio dell'orario.
                nuova_posizione = 0  # Seleziona la prima cifra delle ore come destinazione.
            else:  # Gestisce il tasto End.
                nuova_posizione = 5  # Porta il cursore dopo l'ultima cifra dei minuti.
            campo_ora.icursor(nuova_posizione)  # Applica lo spostamento calcolato.
            return "break"  # Impedisce al binding standard di eseguire un secondo spostamento.

        if evento.keysym in {"BackSpace", "Delete"}:  # Gestisce la cancellazione senza rimuovere mai il carattere ':'.
            posizione_corrente = campo_ora.index("insert")  # Legge il punto in cui si trova il cursore prima della cancellazione.
            if evento.keysym == "BackSpace":  # Cerca la cifra immediatamente precedente al cursore.
                posizione_da_cancellare = posizione_corrente - 1  # Parte dal carattere che precede il cursore.
                if posizione_da_cancellare == 2:  # Rileva il separatore fisso tra ore e minuti.
                    posizione_da_cancellare = 1  # Salta i due punti e torna alla seconda cifra delle ore.
            else:  # Gestisce il tasto Delete sulla posizione corrente.
                posizione_da_cancellare = posizione_corrente  # Parte esattamente dal carattere sotto il cursore.
                if posizione_da_cancellare == 2:  # Rileva il separatore fisso tra ore e minuti.
                    posizione_da_cancellare = 3  # Salta i due punti e passa alla prima cifra dei minuti.
            if posizione_da_cancellare in (0, 1, 3, 4):  # Consente la cancellazione soltanto nelle quattro posizioni numeriche.
                caratteri = list(testo_corrente)  # Converte la stringa in una lista modificabile di caratteri.
                caratteri[posizione_da_cancellare] = "_"  # Sostituisce la cifra cancellata con il segnaposto visivo.
                campo_ora.delete(0, "end")  # Rimuove temporaneamente la vecchia rappresentazione.
                campo_ora.insert(0, "".join(caratteri))  # Ridisegna l'orario mantenendo intatto il separatore centrale.
                campo_ora.icursor(posizione_da_cancellare)  # Riporta il cursore sulla posizione appena liberata.
            return "break"  # Blocca la cancellazione standard che potrebbe eliminare i due punti.

        if not evento.char.isdigit():  # Rifiuta lettere, simboli, spazi e altri caratteri non numerici.
            return "break"  # Impedisce l'inserimento di caratteri incompatibili con HH:MM.

        posizione_corrente = campo_ora.index("insert")  # Individua la posizione in cui l'utente sta digitando la cifra.
        if posizione_corrente >= 5:  # Gestisce il caso in cui il cursore sia già dopo l'ultima cifra.
            return "break"  # Non permette di superare le quattro cifre previste dalla maschera.
        if posizione_corrente == 2:  # Rileva il tentativo di digitare sul separatore.
            posizione_corrente = 3  # Sposta automaticamente l'inserimento sulla prima cifra dei minuti.

        cifra = evento.char  # Conserva la singola cifra digitata per applicare i limiti specifici della posizione.
        if posizione_corrente == 0 and int(cifra) > 2:  # La prima cifra delle ore può essere soltanto 0, 1 oppure 2.
            return "break"  # Rifiuta immediatamente ore che non potranno rientrare nell'intervallo 00-23.
        if posizione_corrente == 1 and testo_corrente[0] == "2" and int(cifra) > 3:  # Con un 2 iniziale limita la seconda cifra delle ore a 0-3.
            return "break"  # Impedisce valori da 24 a 29.
        if posizione_corrente == 3 and int(cifra) > 5:  # La prima cifra dei minuti può essere soltanto 0-5.
            return "break"  # Impedisce minuti da 60 a 99.

        caratteri = list(testo_corrente)  # Converte la maschera corrente in una struttura modificabile.
        caratteri[posizione_corrente] = cifra  # Scrive la cifra nella posizione valida scelta dall'utente.
        campo_ora.delete(0, "end")  # Elimina la rappresentazione precedente prima di ridisegnare la maschera.
        campo_ora.insert(0, "".join(caratteri))  # Mostra il nuovo valore lasciando sempre visibili i due punti.
        posizione_successiva = posizione_corrente + 1  # Calcola il punto in cui proseguire dopo la cifra appena inserita.
        if posizione_successiva == 2:  # Rileva il passaggio dalla seconda cifra delle ore al separatore.
            posizione_successiva = 3  # Salta automaticamente ':' e porta il cursore alla prima cifra dei minuti.
        campo_ora.icursor(min(posizione_successiva, 5))  # Posiziona il cursore sulla cifra successiva oppure alla fine del campo.
        return "break"  # Impedisce al comportamento standard dell'Entry di inserire nuovamente la stessa cifra.

    def leggi_ora_pianificazione(self, campo_ora: ctk.CTkEntry) -> str:
        """Converte la maschera vuota in stringa vuota e lascia al modello la validazione finale di valori incompleti."""
        testo_ora = campo_ora.get().strip()  # Legge il valore visualizzato nel campo orario mascherato.
        return "" if testo_ora == "__:__" else testo_ora  # Mantiene compatibile il default non configurato con PianificazioneBackup.

    def aggiorna_stato_pianificazione_sorgente(self, dati_riga: dict) -> None:
        """Abilita o disabilita i campi temporali in base alla checkbox della singola sorgente."""
        stato = "normal" if dati_riga["pianificazione_abilitata"].get() else "disabled"  # Traduce il booleano della GUI nello stato previsto dai widget CustomTkinter.
        for controllo in dati_riga["controlli_pianificazione"]:  # Applica lo stesso stato a giorni e campo ora della sorgente.
            controllo.configure(state=stato)  # Impedisce modifiche accidentali quando la pianificazione è disattivata.

    def scegli_sorgente_nuovo_backup(self, dati_riga: dict) -> None:
        """Seleziona una cartella sorgente e propone un nome di destinazione soltanto se il campo è vuoto."""
        percorso = filedialog.askdirectory(parent=self, title="Seleziona una cartella sorgente", mustexist=True)  # Limita la selezione a directory esistenti, coerentemente con il validatore.
        if not percorso:  # Riconosce l'annullamento del dialogo.
            return  # Mantiene intatti gli eventuali valori già inseriti.
        campo_percorso = dati_riga["percorso"]  # Recupera il campo percorso della riga selezionata.
        campo_percorso.delete(0, "end")  # Rimuove l'eventuale percorso precedente.
        campo_percorso.insert(0, percorso)  # Inserisce la cartella scelta.
        campo_nome = dati_riga["nome_destinazione"]  # Recupera il campo della sottocartella stabile.
        if not campo_nome.get().strip():  # Non sovrascrive un nome personalizzato o persistito.
            nome_proposto = self.genera_nome_destinazione_univoco(Path(percorso).name or "Sorgente", dati_riga)  # Deriva un nome leggibile dall'ultima componente del percorso.
            campo_nome.insert(0, nome_proposto)  # Inserisce la proposta modificabile dall'utente.

    def genera_nome_destinazione_univoco(self, nome_base: str, riga_corrente: dict) -> str:
        """Propone un nome distinto rispetto alle altre righe dell'editor senza sostituire la validazione finale."""
        nomi_usati = {dati["nome_destinazione"].get().strip().casefold() for dati in self.righe_sorgenti_nuovo_backup if dati is not riga_corrente and dati["nome_destinazione"].get().strip()}  # Raccoglie i nomi già usati ignorando differenze di maiuscole.
        candidato = nome_base.strip() or "Sorgente"  # Usa il nome della cartella oppure un valore leggibile di ripiego.
        if candidato.casefold() not in nomi_usati:  # Verifica se il nome semplice è disponibile.
            return candidato  # Restituisce il nome naturale senza suffissi inutili.
        indice = 2  # Inizia dal suffisso _2 per il primo duplicato.
        while f"{candidato}_{indice}".casefold() in nomi_usati:  # Continua finché il candidato collide con un nome esistente.
            indice += 1  # Passa al suffisso successivo.
        return f"{candidato}_{indice}"  # Restituisce il primo nome numerato disponibile.

    def rimuovi_riga_sorgente_nuovo_backup(self, dati_riga: dict) -> None:
        """Rimuove una sorgente dall'editor mantenendo sempre almeno una riga visibile."""
        if len(self.righe_sorgenti_nuovo_backup) <= 1:  # Impedisce di lasciare l'editor senza alcuna sorgente.
            messagebox.showwarning("Sorgente richiesta", "Un backup deve contenere almeno una sorgente.", parent=self)  # Spiega perché l'ultima riga non viene eliminata.
            return  # Mantiene la sorgente minima richiesta dall'editor.
        dati_riga["contenitore"].destroy()  # Elimina dalla GUI la riga scelta.
        self.righe_sorgenti_nuovo_backup.remove(dati_riga)  # Elimina la stessa riga anche dalla struttura dati temporanea.

    def trova_job_per_id(self, id_job: str) -> JobBackup | None:
        """Restituisce il job con l'identità richiesta senza usare nome o percorso come chiave."""
        return next((job for job in self.job_backup if job.id_job == id_job), None)  # Cerca esclusivamente tramite l'identità persistente del modello.

    def persisti_lista_job(self, job_candidati: list[JobBackup]) -> dict:
        """Valida e salva una lista candidata senza pubblicarla in memoria prima del successo su disco."""
        ValidatoreBackup.valida_job_multipli(job_candidati)  # Applica tutte le regole locali e globali prima della scrittura.
        nuova_configurazione = salva_job_nella_configurazione(self.configurazione, job_candidati)  # Crea una nuova configurazione preservando le chiavi non relative ai job.
        salva_configurazione(FILE_CONFIGURAZIONE, nuova_configurazione)  # Esegue il salvataggio atomico già usato dal progetto.
        return nuova_configurazione  # Restituisce il documento da pubblicare in memoria soltanto dopo il successo.

    def salva_nuovo_backup(self) -> None:
        """Crea o modifica un job, preservando gli ID esistenti e pubblicando lo stato solo dopo il salvataggio riuscito."""
        nome_job = self.campo_nome_nuovo_backup.get().strip()  # Legge il nome visibile del job.
        destinazione = self.campo_destinazione_nuovo_backup.get().strip()  # Legge la radice di destinazione scelta.
        if not nome_job:  # Blocca un job senza nome.
            messagebox.showerror("Dati mancanti", "Inserisci un nome per il backup.", parent=self)  # Indica il campo da completare.
            return  # Lascia aperto l'editor.
        if not destinazione:  # Verifica che sia indicata una destinazione.
            messagebox.showerror("Dati mancanti", "Seleziona la destinazione del backup.", parent=self)  # Indica il dato mancante.
            return  # Non modifica alcuna configurazione.

        job_originale = self.trova_job_per_id(self.id_job_in_modifica) if self.id_job_in_modifica is not None else None  # Recupera il job originale soltanto in modalità modifica.
        if self.id_job_in_modifica is not None and job_originale is None:  # Rileva una configurazione cambiata in modo inatteso mentre l'editor era aperto.
            messagebox.showerror("Backup non trovato", "Il backup da modificare non è più presente nella configurazione.", parent=self)  # Evita di trasformare accidentalmente la modifica in una nuova creazione.
            return  # Mantiene aperto l'editor per non perdere i dati digitati.

        sorgenti = []  # Prepara la collezione candidata delle sorgenti.
        try:  # Converte i dati grafici in modelli e applica la validazione centrale.
            for indice, dati_riga in enumerate(self.righe_sorgenti_nuovo_backup, start=1):  # Mantiene lo stesso ordine mostrato nell'editor.
                percorso_sorgente = dati_riga["percorso"].get().strip()  # Legge il percorso della sorgente corrente.
                nome_destinazione = dati_riga["nome_destinazione"].get().strip()  # Legge il nome stabile della sottocartella.
                if not percorso_sorgente:  # Individua una riga incompleta.
                    raise ValueError(f"Seleziona la cartella della sorgente {indice}.")  # Produce un messaggio riferito alla riga corretta.
                if not nome_destinazione:  # Individua un nome logico mancante.
                    raise ValueError(f"Inserisci il nome di destinazione della sorgente {indice}.")  # Evita nomi impliciti durante la persistenza.
                pianificazione_abilitata = dati_riga["pianificazione_abilitata"].get()  # Legge lo stato della pianificazione appartenente esclusivamente alla sorgente corrente.
                giorni_pianificati = tuple(indice_giorno for indice_giorno, variabile_giorno in enumerate(dati_riga["giorni_pianificazione"]) if variabile_giorno.get())  # Converte le checkbox selezionate negli indici 0=lunedì ... 6=domenica.
                ora_pianificata = self.leggi_ora_pianificazione(dati_riga["ora_pianificazione"])  # Converte la maschera vuota nel valore non configurato e lascia al modello la validazione definitiva.
                id_sorgente = dati_riga.get("id_sorgente")  # Recupera l'ID soltanto se la riga deriva da una sorgente già persistita.
                sorgente_originale = next((sorgente for sorgente in job_originale.sorgenti if sorgente.id_sorgente == id_sorgente), None) if job_originale is not None and id_sorgente is not None else None  # Recupera la pianificazione precedente della stessa identità, se esiste.
                pianificazione_precedente = sorgente_originale.pianificazione if sorgente_originale is not None else None  # Isola il modello temporale precedente senza basarsi su percorso o nome modificabili.
                pianificazione_invariata = pianificazione_precedente is not None and pianificazione_precedente.abilitata == pianificazione_abilitata and pianificazione_precedente.giorni == giorni_pianificati and pianificazione_precedente.ora == ora_pianificata  # Stabilisce se la regola temporale è realmente rimasta identica.
                attiva_dal = pianificazione_precedente.attiva_dal if pianificazione_invariata else (datetime.now().astimezone().replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S") if pianificazione_abilitata else "")  # Conserva il limite precedente solo per una regola invariata; una regola nuova o modificata parte dall’istante del salvataggio.
                pianificazione = PianificazioneBackup(abilitata=pianificazione_abilitata, giorni=giorni_pianificati, ora=ora_pianificata, attiva_dal=attiva_dal)  # Costruisce il modello temporale validato includendo il limite che impedisce recuperi anteriori alla configurazione.
                if id_sorgente is None:  # Una sorgente realmente nuova deve ricevere una nuova identità.
                    sorgenti.append(SorgenteBackup(Path(percorso_sorgente), nome_destinazione, pianificazione=pianificazione))  # Lascia al modello la generazione del nuovo UUID associando la pianificazione configurata.
                else:  # Una sorgente esistente deve mantenere la stessa identità anche se cambiano percorso, nome o pianificazione.
                    sorgenti.append(SorgenteBackup(Path(percorso_sorgente), nome_destinazione, id_sorgente=id_sorgente, pianificazione=pianificazione))  # Ricostruisce la sorgente conservando l'ID e applicando la pianificazione scelta.

            if job_originale is None:  # Gestisce la creazione di un nuovo job.
                job_candidato = JobBackup(nome_job, Path(destinazione), sorgenti, abilitato=True, includi_sottocartelle=self.variabile_includi_sottocartelle.get(), verifica_integrita=self.variabile_verifica_integrita.get())  # Crea il nuovo job salvando anche le due opzioni operative selezionate nell'editor.
                job_candidati = [*self.job_backup, job_candidato]  # Aggiunge il candidato senza mutare la lista corrente.
            else:  # Gestisce la modifica di un job esistente.
                job_candidato = JobBackup(nome_job, Path(destinazione), sorgenti, abilitato=job_originale.abilitato, id_job=job_originale.id_job, includi_sottocartelle=self.variabile_includi_sottocartelle.get(), verifica_integrita=self.variabile_verifica_integrita.get())  # Conserva identità e stato del job applicando le opzioni scelte nell'editor.
                job_candidati = [job_candidato if job.id_job == job_originale.id_job else job for job in self.job_backup]  # Sostituisce soltanto il job corretto mantenendo ordine e altri oggetti invariati.

            nuova_configurazione = self.persisti_lista_job(job_candidati)  # Valida l'intera configurazione e la salva atomicamente prima di pubblicarla.
        except (TypeError, ValueError) as errore:  # Gestisce dati incompleti, modelli invalidi e conflitti globali.
            messagebox.showerror("Backup non valido", str(errore), parent=self)  # Mostra la regola violata lasciando aperto l'editor.
            return  # Garantisce che nessuno stato candidato venga pubblicato.
        except OSError as errore:  # Gestisce problemi reali durante il salvataggio atomico.
            logger.error("Impossibile salvare il job di backup: %s", errore)  # Registra il problema nel log persistente.
            messagebox.showerror("Errore configurazione", f"Impossibile salvare il backup:\n{errore}", parent=self)  # Comunica il fallimento senza perdere l'editor.
            return  # Mantiene invariati configurazione e job in memoria.

        era_modifica = job_originale is not None  # Conserva la modalità prima che la chiusura dell'editor azzeri il relativo ID.
        self.configurazione = nuova_configurazione  # Pubblica la configurazione in memoria soltanto dopo il salvataggio riuscito.
        self.job_backup = job_candidati  # Pubblica la nuova lista di job soltanto dopo validazione e persistenza.
        self.aggiorna_elenco_job()  # Ridisegna immediatamente le schede con i dati aggiornati.
        azione = "modificato" if era_modifica else "salvato"  # Costruisce un messaggio coerente con l'operazione effettuata.
        self.aggiungi_log(f"Job {azione}: {job_candidato.nome} | Sorgenti: {len(job_candidato.sorgenti)}")  # Registra la modifica nell'area attività.
        logger.info("Job di backup %s | id=%s | nome=%s | sorgenti=%d", azione, job_candidato.id_job, job_candidato.nome, len(job_candidato.sorgenti))  # Registra nel file di log l'identità persistente.
        self.chiudi_editor_nuovo_backup()  # Chiude l'editor soltanto dopo il completamento effettivo del salvataggio.
        titolo = "Backup modificato" if era_modifica else "Backup salvato"  # Distingue il messaggio finale.
        messagebox.showinfo(titolo, f"Il backup '{job_candidato.nome}' è stato {azione} correttamente.", parent=self)  # Conferma il successo all'utente.

    def cambia_stato_job(self, job: JobBackup) -> None:
        """Abilita o disabilita un job persistendo il nuovo stato senza alterarne identità e contenuto."""
        if self.operazione_in_corso():  # Blocca la modifica mentre un worker utilizza la configurazione.
            messagebox.showwarning("Operazione in corso", "Attendi il termine del backup o del ripristino prima di cambiare lo stato del backup.", parent=self)  # Spiega il blocco.
            return  # Non modifica il modello corrente.
        if self.editor_nuovo_backup is not None and self.editor_nuovo_backup.winfo_exists():  # Evita che un toggle esterno renda incoerente un editor aperto.
            messagebox.showwarning("Editor aperto", "Salva o annulla le modifiche aperte prima di cambiare lo stato di un backup.", parent=self)  # Protegge le modifiche non ancora persistite.
            return  # Mantiene invariato lo stato.

        job_candidato = JobBackup(job.nome, job.destinazione, job.sorgenti, abilitato=not job.abilitato, id_job=job.id_job, includi_sottocartelle=job.includi_sottocartelle, verifica_integrita=job.verifica_integrita)  # Ricostruisce il job cambiando esclusivamente lo stato e preservando entrambe le opzioni operative.
        job_candidati = [job_candidato if elemento.id_job == job.id_job else elemento for elemento in self.job_backup]  # Sostituisce soltanto il job selezionato.
        try:  # Valida e persiste il nuovo insieme prima di aggiornare la GUI.
            nuova_configurazione = self.persisti_lista_job(job_candidati)  # Riutilizza il percorso transazionale comune.
        except (TypeError, ValueError) as errore:  # Un'abilitazione può rendere attivi conflitti filesystem prima ignorati.
            messagebox.showerror("Impossibile cambiare stato", str(errore), parent=self)  # Mostra la regola che impedisce il cambio.
            return  # Mantiene lo stato precedente.
        except OSError as errore:  # Gestisce un fallimento della scrittura atomica.
            logger.error("Impossibile cambiare lo stato del job '%s': %s", job.id_job, errore)  # Registra il problema nel file di log.
            messagebox.showerror("Errore configurazione", f"Impossibile salvare il nuovo stato:\n{errore}", parent=self)  # Comunica il problema all'utente.
            return  # Non pubblica il candidato in memoria.

        self.configurazione = nuova_configurazione  # Aggiorna la configurazione soltanto dopo il successo su disco.
        self.job_backup = job_candidati  # Aggiorna la lista corrente con il nuovo stato.
        self.aggiorna_elenco_job()  # Ridisegna etichetta e pulsante dello stato.
        nuovo_stato = "abilitato" if job_candidato.abilitato else "disabilitato"  # Traduce il booleano in un testo leggibile.
        self.aggiungi_log(f"Job {nuovo_stato}: {job_candidato.nome}")  # Registra l'azione nell'area attività.
        logger.info("Job di backup %s | id=%s | nome=%s", nuovo_stato, job_candidato.id_job, job_candidato.nome)  # Registra anche l'identità nel log persistente.

    def elimina_job(self, job: JobBackup) -> None:
        """Elimina soltanto la configurazione del job, senza cancellare file o cartelle di backup."""
        if self.operazione_in_corso():  # Blocca l'eliminazione mentre un worker utilizza la configurazione.
            messagebox.showwarning("Operazione in corso", "Attendi il termine del backup o del ripristino prima di eliminare un backup configurato.", parent=self)  # Spiega il blocco.
            return  # Non modifica alcun dato.
        if self.editor_nuovo_backup is not None and self.editor_nuovo_backup.winfo_exists():  # Evita di eliminare dati mentre un editor contiene modifiche non salvate.
            messagebox.showwarning("Editor aperto", "Salva o annulla le modifiche aperte prima di eliminare un backup.", parent=self)  # Protegge lo stato temporaneo dell'editor.
            return  # Mantiene invariata la configurazione.

        confermato = messagebox.askyesno("Elimina backup", f"Vuoi eliminare la configurazione del backup '{job.nome}'?\n\nI file già presenti nella destinazione NON verranno cancellati.", parent=self)  # Richiede una conferma esplicita e chiarisce che i dati fisici restano intatti.
        if not confermato:  # Gestisce la risposta negativa o la chiusura del dialogo.
            return  # Non modifica nulla.

        job_candidati = [elemento for elemento in self.job_backup if elemento.id_job != job.id_job]  # Rimuove esclusivamente il job con l'identità selezionata.
        try:  # Persiste la lista risultante prima di aggiornare la GUI.
            nuova_configurazione = self.persisti_lista_job(job_candidati)  # Mantiene tutte le altre impostazioni e gli altri job.
        except (TypeError, ValueError) as errore:  # Gestisce un'eventuale incoerenza residua della configurazione.
            messagebox.showerror("Impossibile eliminare il backup", str(errore), parent=self)  # Mostra il problema senza modificare lo stato corrente.
            return  # Non pubblica la lista candidata.
        except OSError as errore:  # Gestisce un fallimento della scrittura atomica.
            logger.error("Impossibile eliminare il job '%s': %s", job.id_job, errore)  # Registra il problema nel log persistente.
            messagebox.showerror("Errore configurazione", f"Impossibile salvare l'eliminazione:\n{errore}", parent=self)  # Comunica il problema all'utente.
            return  # Mantiene il job nella GUI perché il file non è stato aggiornato.

        self.configurazione = nuova_configurazione  # Pubblica la configurazione senza il job soltanto dopo il successo su disco.
        self.job_backup = job_candidati  # Aggiorna la lista in memoria.
        self.aggiorna_elenco_job()  # Rimuove la scheda corrispondente dall'interfaccia.
        self.aggiungi_log(f"Job eliminato dalla configurazione: {job.nome}")  # Registra l'azione senza suggerire la cancellazione dei dati.
        logger.info("Job di backup eliminato dalla configurazione | id=%s | nome=%s", job.id_job, job.nome)  # Registra l'identità eliminata nel log persistente.
        messagebox.showinfo("Backup eliminato", f"La configurazione di '{job.nome}' è stata eliminata.\nI file di backup esistenti non sono stati cancellati.", parent=self)  # Conferma il comportamento conservativo.

    def aggiorna_elenco_job(self) -> None:
        """Ricostruisce l'elenco grafico dei job persistenti senza modificarne i dati."""
        for componente in self.contenitore_job.winfo_children():  # Scorre esclusivamente i widget creati dentro l'elenco dei job.
            componente.destroy()  # Elimina la rappresentazione precedente prima di ridisegnare l'elenco.
        if not self.job_backup:  # Controlla se la configurazione non contiene alcun job.
            ctk.CTkLabel(self.contenitore_job, text="Nessun backup configurato.", text_color=COLORE_TESTO_STATO, anchor="w", font=ctk.CTkFont(size=13)).pack(fill="x", pady=10)  # Mostra uno stato vuoto comprensibile.
            return  # Evita di costruire schede quando non esistono job persistenti.
        for job in self.job_backup:  # Mantiene nella GUI lo stesso ordine persistito nel file di configurazione.
            self.crea_scheda_job(job)  # Delega la rappresentazione del singolo job.

    def crea_scheda_job(self, job: JobBackup) -> None:
        """Crea una scheda interattiva per modificare, abilitare/disabilitare o eliminare un job salvato."""
        scheda = ctk.CTkFrame(self.contenitore_job, corner_radius=12, fg_color=COLORE_RIQUADRO, border_width=1, border_color="#26384B")  # Separa visivamente il job dagli altri elementi.
        scheda.pack(fill="x", pady=5)  # Estende la scheda lungo la larghezza disponibile.
        riga_superiore = ctk.CTkFrame(scheda, fg_color="transparent")  # Crea la riga con nome, stato e comandi del job.
        riga_superiore.pack(fill="x", padx=14, pady=(12, 4))  # Posiziona la riga principale con margini interni.
        ctk.CTkLabel(riga_superiore, text=job.nome, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(side="left")  # Mostra il nome persistente del job.

        ctk.CTkButton(riga_superiore, text="Elimina", width=82, height=30, fg_color=COLORE_PULSANTE_PERICOLO, hover_color=COLORE_PULSANTE_PERICOLO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda job_corrente=job: self.elimina_job(job_corrente)).pack(side="right", padx=(6, 0))  # Elimina soltanto la configurazione dopo conferma.
        ctk.CTkButton(riga_superiore, text="Modifica", width=82, height=30, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, command=lambda job_corrente=job: self.apri_editor_modifica_backup(job_corrente)).pack(side="right", padx=(6, 0))  # Apre lo stesso editor inline con i dati esistenti.
        testo_toggle = "Disabilita" if job.abilitato else "Abilita"  # Mostra l'azione disponibile invece dello stato già noto.
        ctk.CTkButton(riga_superiore, text=testo_toggle, width=92, height=30, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, command=lambda job_corrente=job: self.cambia_stato_job(job_corrente)).pack(side="right", padx=(6, 0))  # Persiste il cambio di stato mantenendo l'identità del job.
        testo_stato = "Abilitato" if job.abilitato else "Disabilitato"  # Traduce il booleano persistito in un testo leggibile.
        colore_stato = "#5FD17A" if job.abilitato else COLORE_TESTO_TERZIARIO  # Distingue visivamente lo stato corrente.
        ctk.CTkLabel(riga_superiore, text=testo_stato, text_color=colore_stato, font=ctk.CTkFont(size=12, weight="bold")).pack(side="right", padx=(8, 4))  # Mantiene visibile lo stato oltre al comando di toggle.

        ctk.CTkLabel(scheda, text=f"Destinazione: {job.destinazione}", text_color=COLORE_TESTO_SECONDARIO, anchor="w").pack(fill="x", padx=14, pady=2)  # Mostra la radice di destinazione persistita.
        ctk.CTkLabel(scheda, text=f"Sorgenti: {len(job.sorgenti)}", text_color=COLORE_TESTO_INFO, anchor="w").pack(fill="x", padx=14, pady=(2, 4))  # Comunica quante sorgenti appartengono al job.
        testo_sottocartelle = "Sì" if job.includi_sottocartelle else "No"  # Traduce l'opzione ricorsiva in un valore immediatamente leggibile.
        testo_integrita = "Sì" if job.verifica_integrita else "No"  # Traduce l'opzione di verifica post-copia in un valore immediatamente leggibile.
        ctk.CTkLabel(scheda, text=f"Opzioni: sottocartelle {testo_sottocartelle}  |  verifica integrità {testo_integrita}", text_color=COLORE_TESTO_INFO, anchor="w").pack(fill="x", padx=14, pady=(0, 5))  # Mostra le opzioni effettivamente persistite senza richiedere l'apertura dell'editor.
        nomi_giorni = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")  # Fornisce le abbreviazioni usate per rendere leggibile la pianificazione nelle schede riepilogative.
        for sorgente in job.sorgenti:  # Elenca le sorgenti mantenendo l'ordine salvato.
            testo_sorgente = f"• {sorgente.nome_destinazione}  ←  {sorgente.percorso}"  # Costruisce una descrizione compatta della mappatura sorgente-sottocartella.
            ctk.CTkLabel(scheda, text=testo_sorgente, text_color=COLORE_TESTO_STATO, anchor="w").pack(fill="x", padx=24, pady=1)  # Mostra la sorgente senza esporre gli identificatori tecnici.
            if sorgente.pianificazione.abilitata:  # Mostra i dettagli temporali soltanto quando la pianificazione della sorgente è attiva.
                giorni_testo = ", ".join(nomi_giorni[indice] for indice in sorgente.pianificazione.giorni)  # Traduce gli indici persistiti in abbreviazioni italiane.
                testo_pianificazione = f"  Pianificazione: {giorni_testo} alle {sorgente.pianificazione.ora}"  # Costruisce un riepilogo compatto di giorni e ora.
            else:  # Distingue chiaramente una sorgente priva di esecuzione automatica.
                testo_pianificazione = "  Pianificazione: disattivata"  # Evita di mostrare giorni o orari non operativi.
            ctk.CTkLabel(scheda, text=testo_pianificazione, text_color=COLORE_TESTO_ATTENUATO, anchor="w").pack(fill="x", padx=36, pady=(0, 2))  # Visualizza lo stato persistito sotto la sorgente corrispondente.
        ctk.CTkLabel(scheda, text="").pack(pady=2)  # Mantiene un piccolo margine inferiore uniforme.


    def aggiorna_stato_pianificazione_backup_singolo(self) -> None:
        """Abilita o disabilita giorni e ora della pianificazione associata al backup singolo."""
        stato = "normal" if self.variabile_pianificazione_singola.get() else "disabled"  # Traduce il booleano della GUI nello stato previsto dai widget.
        for controllo in self.controlli_pianificazione_singola:  # Attraversa tutti i controlli temporali del backup singolo.
            controllo.configure(state=stato)  # Impedisce modifiche accidentali quando la pianificazione è disattivata.

    def salva_backup_singolo(self) -> None:
        """Valida e persiste sorgente, destinazione e pianificazione del backup singolo."""
        sorgente = self.campo_sorgente.get().strip()  # Legge la sorgente necessaria anche a un futuro scheduler.
        destinazione = self.campo_destinazione.get().strip()  # Legge la destinazione associata in modo stabile alla sorgente singola.
        if not sorgente or not destinazione:  # Richiede entrambi i percorsi perché una pianificazione incompleta non sarebbe eseguibile.
            messagebox.showerror("Dati mancanti", "Seleziona sorgente e destinazione prima di salvare la pianificazione.", parent=self)  # Indica chiaramente cosa manca.
            return  # Non modifica la configurazione persistente.
        try:  # Costruisce il modello reale per riutilizzare la validazione già coperta dai test backend.
            giorni = tuple(indice for indice, variabile in enumerate(self.variabili_giorni_singoli) if variabile.get())  # Converte le checkbox selezionate negli indici 0-6 del modello.
            ora = self.leggi_ora_pianificazione(self.campo_ora_pianificazione_singola)  # Converte la maschera vuota nel valore neutro previsto dal modello.
            pianificazione_precedente = self.backup_singolo["pianificazione"]  # Recupera la regola già validata per distinguere un semplice salvataggio da una modifica temporale reale.
            pianificazione_abilitata = self.variabile_pianificazione_singola.get()  # Legge una sola volta lo stato richiesto dalla checkbox.
            pianificazione_invariata = pianificazione_precedente.abilitata == pianificazione_abilitata and pianificazione_precedente.giorni == giorni and pianificazione_precedente.ora == ora  # Confronta esclusivamente i dati che definiscono il calendario della regola.
            attiva_dal = pianificazione_precedente.attiva_dal if pianificazione_invariata else (datetime.now().astimezone().replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S") if pianificazione_abilitata else "")  # Una regola nuova o modificata diventa valida dal salvataggio, mentre una regola invariata conserva la propria origine temporale.
            pianificazione = PianificazioneBackup(abilitata=pianificazione_abilitata, giorni=giorni, ora=ora, attiva_dal=attiva_dal)  # Delega al modello i controlli semantici finali includendo il limite anti-recupero retroattivo.
            MotoreBackup(threading.Event()).valida_percorsi(Path(sorgente), Path(destinazione))  # Verifica anche la coppia di percorsi prima di renderla persistente.
        except (TypeError, ValueError) as errore:  # Gestisce sia gli errori temporali sia quelli relativi ai percorsi.
            messagebox.showerror("Configurazione non valida", str(errore), parent=self)  # Mostra il motivo reale senza duplicare la validazione.
            return  # Mantiene intatta la configurazione precedente.
        nuova_configurazione = dict(self.configurazione)  # Prepara una copia per pubblicare lo stato soltanto dopo il successo su disco.
        nuova_configurazione["backup_singolo"] = {"sorgente": sorgente, "destinazione": destinazione, "pianificazione": serializza_pianificazione_backup(pianificazione)}  # Usa lo stesso formato persistente della pianificazione multi-sorgente.
        try:  # Tenta il salvataggio prima di aggiornare lo stato vivo della GUI.
            salva_configurazione(FILE_CONFIGURAZIONE, nuova_configurazione)  # Scrive il documento JSON tramite il modulo di configurazione esistente.
        except OSError as errore:  # Intercetta problemi filesystem senza perdere la configurazione precedente in memoria.
            messagebox.showerror("Errore configurazione", f"Impossibile salvare il backup singolo:\n{errore}", parent=self)  # Comunica il fallimento all'utente.
            return  # Non pubblica uno stato che non è stato realmente scritto.
        self.configurazione = nuova_configurazione  # Pubblica la nuova configurazione soltanto dopo il salvataggio riuscito.
        self.backup_singolo = {"sorgente": sorgente, "destinazione": destinazione, "pianificazione": pianificazione}  # Mantiene allineato lo stato validato in memoria.
        messagebox.showinfo("Backup singolo", "Sorgente, destinazione e pianificazione sono state salvate.", parent=self)  # Conferma esplicitamente la persistenza.

    # ========================================================
    # HOME, IMPOSTAZIONI E INFORMAZIONI
    # ========================================================

    def applica_tema_salvato(self) -> None:
        """Applica una preferenza globale valida senza impedire l'avvio con configurazioni precedenti."""
        tema = self.configurazione.get("tema_interfaccia", "dark")  # Recupera il tema persistito oppure mantiene il tema storico scuro.
        if tema not in {"dark", "light", "system"}:  # Rifiuta valori corrotti senza modificare il file automaticamente.
            tema = "dark"  # Usa il comportamento storico come fallback prevedibile.
        ctk.set_appearance_mode(tema)  # Delega a CustomTkinter l'applicazione del tema globale.

    def _salva_stato_pannello_avanzato(self) -> None:
        """Conserva i campi delle viste avanzate prima che la navigazione distrugga i relativi widget."""
        if self.sezione_attiva == "strategie" and hasattr(self, "campo_strategia_sorgente") and self.campo_strategia_sorgente.winfo_exists():  # Legge soltanto una vista Strategie ancora viva.
            self.valori_strategia_gui = {"sorgente": self.campo_strategia_sorgente.get(), "destinazione": self.campo_strategia_destinazione.get(), "metodo": self.variabile_metodo_strategia.get(), "full_ogni": self.campo_full_ogni.get(), "catene": self.campo_catene_mantenere.get(), "sottocartelle": self.variabile_strategia_sottocartelle.get(), "verifica": self.variabile_verifica_post_backup.get(), "recuperabilita": self.variabile_test_recuperabilita.get(), "includi": self.campo_filtro_includi.get(), "escludi": self.campo_filtro_escludi.get(), "estensioni": self.campo_estensioni_escluse.get(), "minimo": self.campo_dimensione_minima.get(), "massimo": self.campo_dimensione_massima.get(), "nascosti": self.variabile_escludi_nascosti.get(), "sola_lettura": self.variabile_escludi_sola_lettura.get(), "reparse": self.variabile_politica_reparse.get(), "destinazioni_extra": self.campo_destinazioni_aggiuntive.get(), "destinazioni_obbligatorie": self.variabile_destinazioni_obbligatorie.get(), "ret_g": self.campo_retention_giorni.get(), "ret_s": self.campo_retention_settimane.get(), "ret_m": self.campo_retention_mesi.get(), "ret_a": self.campo_retention_anni.get()}  # Conserva anche le opzioni professionali durante la navigazione.
        if self.sezione_attiva == "ripristino_versionato" and hasattr(self, "campo_versioni_ripristino") and self.campo_versioni_ripristino.winfo_exists():  # Salva il recupero versionato indipendentemente dalle Strategie.
            self.valori_ripristino_versionato_gui = {"versioni": self.campo_versioni_ripristino.get(), "destinazione_ripristino": self.campo_destinazione_ripristino_avanzato.get(), "sovrascrivi": self.variabile_sovrascrivi_ripristino_avanzato.get(), "selezione": self.campo_selezione_ripristino.get()}  # Conserva i parametri utente della pagina dedicata.
        if self.sezione_attiva == "verifica_integrita" and hasattr(self, "campo_versioni_verifica") and self.campo_versioni_verifica.winfo_exists():  # Conserva la radice del repository e la selezione leggibile prima di distruggere la pagina.
            self.valori_verifica_integrita_gui = {"versioni": self.campo_versioni_verifica.get(), "versione": self.variabile_versione_verifica.get()}  # Mantiene i parametri necessari a ricostruire la verifica senza toccare il repository.
        if self.sezione_attiva == "sincronizza" and hasattr(self, "campo_sync_sorgente") and self.campo_sync_sorgente.winfo_exists():  # Legge soltanto una vista Sincronizza ancora viva.
            self.valori_sync_gui = {"sorgente": self.campo_sync_sorgente.get(), "destinazione": self.campo_sync_destinazione.get(), "metodo": self.variabile_metodo_sync.get(), "sottocartelle": self.variabile_sync_sottocartelle.get()}  # Conserva i parametri necessari a ricostruire il pannello.

    def mostra_sezione(self, sezione: str) -> None:
        """Mostra una sezione reale evitando sovrapposizioni o pannelli invisibili durante la navigazione."""
        if sezione not in {"home", "backup", "strategie", "sincronizza", "ripristino", "ripristino_tradizionale", "ripristino_versionato", "verifica_integrita", "impostazioni", "informazioni"}:  # Accetta soltanto sezioni implementate.
            return  # Ignora richieste non riconosciute.

        self._salva_stato_pannello_avanzato()  # Conserva campi e opzioni prima di distruggere l'eventuale pannello avanzato.
        self.sezione_attiva = sezione  # Memorizza la sezione selezionata prima di aggiornare i widget.
        for nome, pulsante in self.pulsanti_navigazione.items():  # Aggiorna l'evidenziazione della sidebar.
            pulsante.configure(fg_color=COLORE_MENU_ATTIVO if (nome.lower() == sezione or (nome == "Ripristino" and sezione in {"ripristino_tradizionale", "ripristino_versionato", "verifica_integrita"})) else COLORE_MENU_INATTIVO, text_color=COLORE_MENU_TESTO_ATTIVO if (nome.lower() == sezione or (nome == "Ripristino" and sezione in {"ripristino_tradizionale", "ripristino_versionato", "verifica_integrita"})) else COLORE_MENU_TESTO_INATTIVO)  # Evidenzia una sola voce e mantiene sempre leggibile il testo del menu.

        pannello_precedente = getattr(self, "pannello_sezione", None)  # Recupera l'eventuale vista informativa attualmente presente.
        if pannello_precedente is not None:  # Gestisce in modo esplicito il pannello precedente.
            pannello_precedente.grid_remove()  # Lo rimuove subito dal layout per impedire che copra la vista operativa.
            pannello_precedente.destroy()  # Distrugge i widget ormai inutili soltanto dopo averli rimossi dalla griglia.
            self.pannello_sezione = None  # Mantiene un riferimento esplicito e sicuro invece di cancellare l'attributo.

        if sezione in {"backup", "ripristino_tradizionale"}:  # Riutilizza la stessa vista operativa persistente per Backup e Ripristino tradizionale.
            modalita_operativa = "backup" if sezione == "backup" else "ripristino"  # Traduce la sezione grafica nella modalità del motore storico.
            self.contenuto_principale.grid(row=0, column=1, sticky="nsew")  # Ripristina sempre tutti i parametri della griglia.
            self.contenuto_principale.tkraise()  # Porta esplicitamente la vista operativa davanti a eventuali widget residui.
            self.cambia_modalita(modalita_operativa, forza=sezione == "ripristino_tradizionale")  # Configura i campi e forza il tradizionale per evitare stato grafico obsoleto.
            self.after_idle(self._riporta_vista_operativa_in_alto)  # Riporta la vista persistente all'inizio dopo che Tk ha ricalcolato la regione scorrevole.
            return  # Conclude la navigazione operativa.

        self.contenuto_principale.grid_remove()  # Nasconde l'interfaccia operativa senza distruggerne stato e widget.
        self.pannello_sezione = ctk.CTkScrollableFrame(self, fg_color=COLORE_SFONDO, corner_radius=0)  # Crea la vista informativa richiesta.
        self.pannello_sezione.grid(row=0, column=1, sticky="nsew")  # Occupa la stessa area del contenuto principale.
        self.pannello_sezione.tkraise()  # Garantisce che la nuova sezione sia quella effettivamente visibile.
        self._crea_banner_globale_sola_lettura(self.pannello_sezione)  # Mostra lo stesso banner aziendale in ogni sezione non operativa.
        if sezione == "home":  # Costruisce la dashboard richiesta.
            self.crea_home(self.pannello_sezione)  # Popola la Home con dischi e cronologia.
        elif sezione == "strategie":  # Costruisce il nuovo pannello isolato per i backup versionati.
            self.crea_strategie_backup(self.pannello_sezione)  # Espone Full, Incrementale, Differenziale e ripristino senza alterare il flusso storico.
        elif sezione == "sincronizza":  # Costruisce il pannello dedicato alle logiche di sincronizzazione.
            self.crea_sincronizzazione(self.pannello_sezione)  # Espone Update e Mirror mantenendoli distinti dai backup versionati.
        elif sezione == "ripristino":  # Mostra un unico punto di ingresso per i due motori di ripristino.
            self.crea_centro_ripristino(self.pannello_sezione)  # Lascia scegliere tra recupero tradizionale e recupero di una versione.
        elif sezione == "ripristino_versionato":  # Costruisce la pagina dedicata alle catene Full/Incrementali/Differenziali.
            self.crea_ripristino_versionato(self.pannello_sezione)  # Separa visivamente il recupero versionato dalle Strategie.
        elif sezione == "verifica_integrita":  # Costruisce la pagina di controllo SHA-256 e recuperabilità del repository versionato.
            self.crea_verifica_integrita(self.pannello_sezione)  # Mantiene la verifica separata dal ripristino perché non scrive nella destinazione.
        elif sezione == "impostazioni":  # Costruisce le impostazioni globali.
            self.crea_impostazioni(self.pannello_sezione)  # Mostra soltanto preferenze realmente globali.
        else:  # Rimane la sezione Informazioni.
            self.crea_informazioni(self.pannello_sezione)  # Mostra stato e limiti del progetto.

    def _riporta_vista_operativa_in_alto(self) -> None:
        """Riporta in alto il pannello storico Backup/Ripristino quando torna visibile dopo la navigazione."""
        tela = getattr(self.contenuto_principale, "_parent_canvas", None)  # Recupera la Canvas usata internamente dal CTkScrollableFrame senza assumere che esista sempre.
        if tela is not None and tela.winfo_exists():  # Interviene soltanto sulla tela ancora viva della vista operativa.
            tela.yview_moveto(0.0)  # Posiziona la frazione iniziale del documento in alto, evitando una riapertura apparentemente vuota.

    def _crea_banner_globale_sola_lettura(self, contenitore) -> None:
        """Mostra il banner aziendale nella sezione indicata senza esporre comandi di modifica fuori dalla Home."""
        riquadro = ctk.CTkFrame(contenitore, height=190, corner_radius=16, fg_color=COLORE_RIQUADRO, border_width=1, border_color=COLORE_BORDO)  # Crea una fascia coerente in tutte le sezioni.
        riquadro.pack(fill="x", padx=18, pady=(14, 8))  # Mantiene il banner visibile prima dei contenuti specifici della pagina.
        riquadro.pack_propagate(False)  # Impedisce al contenuto di comprimere l'area aziendale.
        etichetta = ctk.CTkLabel(riquadro, text="Banner non configurato • gestiscilo dalla Home", text_color=COLORE_TESTO_TERZIARIO)  # Mostra uno stato neutro quando non esiste un'immagine.
        etichetta.pack(expand=True)  # Centra immagine o messaggio nel riquadro.
        self.etichette_banner_globali.append(etichetta)  # Registra il widget per gli aggiornamenti globali successivi.
        if self.immagine_banner is not None:  # Riusa immediatamente l'immagine già caricata all'avvio o dalla Home.
            etichetta.configure(image=self.immagine_banner, text="")  # Mostra lo stesso banner senza duplicare file o configurazione.

    def gestisci_scroll_testo_locale(self, evento, casella) -> str:
        """Fa scorrere soltanto il textbox sotto il puntatore e blocca la propagazione alla pagina esterna."""
        if sys.platform.startswith("win"):  # Normalizza il delta prodotto da Windows.
            direzione = -1 if evento.delta > 0 else 1  # Traduce la rotazione in una singola unità leggibile.
        elif sys.platform == "darwin":  # Gestisce il delta di macOS senza trasferire valori grezzi.
            direzione = -1 if evento.delta > 0 else 1  # Mantiene lo stesso verso visivo.
        else:  # Gestisce gli eventi X11 Button-4 e Button-5.
            direzione = -1 if getattr(evento, "num", None) == 4 else 1  # Traduce i pulsanti virtuali in direzione.
        inizio_visibile, fine_visibile = casella.yview()  # Legge la porzione realmente visibile del registro prima di intercettare la rotellina.
        if inizio_visibile <= 0.0 and fine_visibile >= 1.0:  # Se tutto il contenuto è già visibile, non esiste nulla da scorrere localmente.
            return None  # Lascia propagare l'evento al CTkScrollableFrame esterno come richiesto.
        casella.yview_scroll(direzione, "units")  # Scorre il registro soltanto quando possiede contenuto eccedente l'area visibile.
        return "break"  # Blocca la propagazione esclusivamente quando Attività ha realmente assorbito lo scroll.

    def _salva_attivita_avanzate(self) -> None:
        """Persiste i registri avanzati senza mescolarli con la cronologia operativa storica."""
        registri = {"strategie": self.attivita_strategia, "sincronizza": self.attivita_sync, "ripristino_versionato": self.attivita_ripristino_versionato, "verifica_integrita": self.attivita_verifica_integrita}  # Raccoglie lo stato autorevole mantenuto dalla GUI.
        salva_attivita_avanzate(FILE_ATTIVITA_AVANZATE, registri)  # Pubblica atomicamente i registri così la chiusura definitiva non li azzera.

    def _aggiungi_attivita_ripristino_versionato(self, testo: str) -> None:
        """Aggiunge e persiste una riga del ripristino versionato applicando lo stesso limite degli altri monitor."""
        self.attivita_ripristino_versionato.append(testo)  # Accoda l'evento al registro indipendente dal widget grafico.
        if len(self.attivita_ripristino_versionato) > 500:  # Impedisce una crescita illimitata tra molte sessioni dell'applicazione.
            del self.attivita_ripristino_versionato[:-500]  # Mantiene soltanto gli eventi più recenti coerentemente con gli altri monitor.
        self._salva_attivita_avanzate()  # Rende immediatamente persistente la nuova riga senza attendere la chiusura del programma.

    def _aggiungi_attivita_verifica_integrita(self, testo: str) -> None:
        """Aggiunge e persiste una riga della verifica di integrità senza dipendere dalla vita dei widget."""
        self.attivita_verifica_integrita.append(testo)  # Accoda la diagnostica al modello persistente della verifica.
        if len(self.attivita_verifica_integrita) > 500:  # Applica lo stesso limite degli altri registri avanzati.
            del self.attivita_verifica_integrita[:-500]  # Mantiene soltanto le righe più recenti.
        self._salva_attivita_avanzate()  # Pubblica subito il nuovo stato per resistere a navigazione e riavvio.

    def cancella_attivita_avanzata(self, sezione: str) -> None:
        """Cancella soltanto il registro Attività scelto su richiesta esplicita dell'utente."""
        if sezione == "strategie":  # Seleziona il registro delle strategie versionate.
            self.attivita_strategia.clear()  # Rimuove lo storico della sessione Strategie.
            nome_widget = "casella_attivita_strategia"  # Identifica il textbox eventualmente visibile.
        elif sezione == "sincronizza":  # Seleziona il registro Update/Mirror.
            self.attivita_sync.clear()  # Rimuove lo storico della sessione Sincronizza.
            nome_widget = "casella_attivita_sync"  # Identifica il textbox eventualmente visibile.
        elif sezione == "ripristino_versionato":  # Gestisce il monitor del ripristino versionato.
            self.attivita_ripristino_versionato.clear()  # Rimuove lo storico del solo ripristino versionato.
            nome_widget = "casella_attivita_ripristino_versionato"  # Identifica il textbox eventualmente visibile.
        else:  # Gestisce il monitor dedicato alla verifica di integrità.
            self.attivita_verifica_integrita.clear()  # Rimuove soltanto la diagnostica delle verifiche.
            nome_widget = "casella_attivita_verifica_integrita"  # Identifica il textbox eventualmente visibile.
        self._salva_attivita_avanzate()  # Persiste immediatamente la cancellazione esplicita così resta valida anche al riavvio.
        casella = getattr(self, nome_widget, None)  # Recupera il widget senza assumere che la relativa pagina sia aperta.
        if casella is not None and casella.winfo_exists():  # Aggiorna la vista soltanto se il widget è ancora vivo.
            casella.configure(state="normal")  # Abilita temporaneamente la modifica programmatica.
            casella.delete("1.0", "end")  # Cancella il testo soltanto dopo la richiesta esplicita.
            casella.configure(state="disabled")  # Ripristina la sola lettura.

    def _scegli_cartella_in_campo(self, campo) -> None:
        """Seleziona una cartella e la inserisce nel campo indicato senza avviare operazioni."""
        percorso = filedialog.askdirectory(parent=self)  # Usa il selettore nativo già adottato dal resto della GUI.
        if percorso:  # Modifica il campo soltanto quando l'utente conferma una cartella reale.
            campo.delete(0, "end")  # Rimuove il valore precedente per evitare concatenazioni accidentali.
            campo.insert(0, percorso)  # Inserisce il percorso scelto in forma testuale.

    def crea_strategie_backup(self, contenitore) -> None:
        """Costruisce la sezione isolata per Full, Incrementale, Differenziale e ripristino delle versioni."""
        ctk.CTkLabel(contenitore, text="Strategie di backup", font=ctk.CTkFont(size=26, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 4))  # Introduce la nuova area senza sostituire il Backup storico.
        ctk.CTkLabel(contenitore, text="Backup versionati con catene verificabili. Il primo Incrementale o Differenziale crea automaticamente un Full di base.", text_color=COLORE_TESTO_TERZIARIO, anchor="w", wraplength=900, justify="left").pack(fill="x", padx=18, pady=(0, 12))  # Spiega la semantica reale del coordinatore.
        scheda = ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea una scheda separata dal flusso storico.
        scheda.pack(fill="x", padx=18, pady=8)  # Mantiene gli stessi margini visivi delle altre sezioni.
        self.campo_strategia_sorgente = ctk.CTkEntry(scheda, placeholder_text="Cartella sorgente")  # Raccoglie la sorgente del set versionato.
        self.campo_strategia_sorgente.pack(fill="x", padx=18, pady=(18, 6))  # Estende il campo per percorsi lunghi.
        ctk.CTkButton(scheda, text="Scegli sorgente", fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self._scegli_cartella_in_campo(self.campo_strategia_sorgente)).pack(anchor="e", padx=18, pady=(0, 8))  # Collega il selettore nativo.
        self.campo_strategia_destinazione = ctk.CTkEntry(scheda, placeholder_text="Cartella che conterrà le versioni FDBackup")  # Raccoglie la radice delle versioni.
        self.campo_strategia_destinazione.pack(fill="x", padx=18, pady=6)  # Mantiene leggibile la destinazione.
        ctk.CTkButton(scheda, text="Scegli destinazione", fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self._scegli_cartella_in_campo(self.campo_strategia_destinazione)).pack(anchor="e", padx=18, pady=(0, 10))  # Collega il selettore della destinazione.
        riga = ctk.CTkFrame(scheda, fg_color="transparent")  # Raggruppa le opzioni numeriche e il metodo.
        riga.pack(fill="x", padx=18, pady=6)  # Mantiene le opzioni sulla stessa fascia.
        ctk.CTkLabel(riga, text="Metodo").pack(side="left", padx=(0, 6))  # Etichetta il selettore del metodo.
        self.variabile_metodo_strategia = ctk.StringVar(value="Incrementale")  # Seleziona l'incrementale come strategia efficiente predefinita.
        ctk.CTkOptionMenu(riga, variable=self.variabile_metodo_strategia, values=["Completo", "Incrementale", "Differenziale"]).pack(side="left", padx=(0, 18))  # Limita la scelta ai metodi realmente implementati.
        ctk.CTkLabel(riga, text="Nuovo Full dopo").pack(side="left", padx=(0, 6))  # Introduce la rotazione automatica.
        self.campo_full_ogni = ctk.CTkEntry(riga, width=70)  # Raccoglie il numero massimo di versioni successive.
        self.campo_full_ogni.insert(0, "7")  # Usa il valore già adottato dal modello di strategia.
        self.campo_full_ogni.pack(side="left", padx=(0, 18))  # Posiziona la soglia accanto alla descrizione.
        ctk.CTkLabel(riga, text="Catene da mantenere").pack(side="left", padx=(0, 6))  # Introduce la retention per catene complete.
        self.campo_catene_mantenere = ctk.CTkEntry(riga, width=70)  # Raccoglie il numero di catene recuperabili.
        self.campo_catene_mantenere.insert(0, "3")  # Usa il default conservativo del coordinatore.
        self.campo_catene_mantenere.pack(side="left")  # Completa la riga delle opzioni.
        self.variabile_strategia_sottocartelle = ctk.BooleanVar(value=True)  # Mantiene ricorsiva la scansione per impostazione predefinita.
        ctk.CTkCheckBox(scheda, text="Includi sottocartelle", variable=self.variabile_strategia_sottocartelle).pack(anchor="w", padx=18, pady=(8, 4))  # Espone la stessa scelta supportata dal motore.

        pannello_professionale = ctk.CTkFrame(scheda, fg_color=COLORE_RIQUADRO, corner_radius=12)  # Raggruppa le opzioni 31-60 senza confonderle con i parametri base.
        pannello_professionale.pack(fill="x", padx=18, pady=(8, 6))
        ctk.CTkLabel(pannello_professionale, text="Affidabilità, filtri e gestione professionale", font=ctk.CTkFont(size=16, weight="bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 6))
        riga_affidabilita = ctk.CTkFrame(pannello_professionale, fg_color="transparent")
        riga_affidabilita.pack(fill="x", padx=14, pady=4)
        self.variabile_verifica_post_backup = ctk.BooleanVar(value=True)
        self.variabile_test_recuperabilita = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(riga_affidabilita, text="Verifica SHA-256 automatica dopo il backup", variable=self.variabile_verifica_post_backup).pack(side="left", padx=(0, 18))
        ctk.CTkCheckBox(riga_affidabilita, text="Test automatico di recuperabilità", variable=self.variabile_test_recuperabilita).pack(side="left")

        riga_filtri = ctk.CTkFrame(pannello_professionale, fg_color="transparent")
        riga_filtri.pack(fill="x", padx=14, pady=4)
        self.campo_filtro_includi = ctk.CTkEntry(riga_filtri, placeholder_text="Includi: estensioni o pattern, es. .txt;.pdf", width=260)
        self.campo_filtro_includi.pack(side="left", padx=(0, 6))
        self.campo_filtro_escludi = ctk.CTkEntry(riga_filtri, placeholder_text="Escludi: pattern o percorsi, es. cartella/*", width=270)
        self.campo_filtro_escludi.pack(side="left", padx=6)
        self.campo_estensioni_escluse = ctk.CTkEntry(riga_filtri, placeholder_text="Solo estensioni escluse, es. .tmp;.log", width=245)
        self.campo_estensioni_escluse.pack(side="left", padx=6)

        riga_filtri_due = ctk.CTkFrame(pannello_professionale, fg_color="transparent")
        riga_filtri_due.pack(fill="x", padx=14, pady=4)
        self.campo_dimensione_minima = ctk.CTkEntry(riga_filtri_due, placeholder_text="Dimensione minima (byte)", width=110)
        self.campo_dimensione_minima.pack(side="left", padx=(0, 6))
        self.campo_dimensione_massima = ctk.CTkEntry(riga_filtri_due, placeholder_text="Dimensione massima (byte)", width=110)
        self.campo_dimensione_massima.pack(side="left", padx=6)
        self.variabile_escludi_nascosti = ctk.BooleanVar(value=False)
        self.variabile_escludi_sola_lettura = ctk.BooleanVar(value=False)
        self.variabile_politica_reparse = ctk.StringVar(value="Ignora")
        ctk.CTkCheckBox(riga_filtri_due, text="Escludi nascosti", variable=self.variabile_escludi_nascosti).pack(side="left", padx=8)
        ctk.CTkCheckBox(riga_filtri_due, text="Escludi sola lettura", variable=self.variabile_escludi_sola_lettura).pack(side="left", padx=8)
        ctk.CTkLabel(riga_filtri_due, text="Reparse:").pack(side="left", padx=(10, 4))
        ctk.CTkOptionMenu(riga_filtri_due, variable=self.variabile_politica_reparse, values=["Ignora", "Segui"], width=100).pack(side="left")

        riga_destinazioni = ctk.CTkFrame(pannello_professionale, fg_color="transparent")
        riga_destinazioni.pack(fill="x", padx=14, pady=4)
        self.campo_destinazioni_aggiuntive = ctk.CTkEntry(riga_destinazioni, placeholder_text="Destinazioni aggiuntive (; separate, locale/SMB)")
        self.campo_destinazioni_aggiuntive.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.variabile_destinazioni_obbligatorie = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(riga_destinazioni, text="Obbligatorie", variable=self.variabile_destinazioni_obbligatorie).pack(side="left")

        riga_retention = ctk.CTkFrame(pannello_professionale, fg_color="transparent")
        riga_retention.pack(fill="x", padx=14, pady=(6, 4))
        ctk.CTkLabel(riga_retention, text="Retention", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 12))

        for etichetta, attributo, valore in (
            ("Giornalieri", "campo_retention_giorni", "7"),
            ("Settimanali", "campo_retention_settimane", "4"),
            ("Mensili", "campo_retention_mesi", "12"),
            ("Annuali", "campo_retention_anni", "3"),
        ):
            ctk.CTkLabel(riga_retention, text=etichetta).pack(side="left", padx=(4, 4))
            campo_retention = ctk.CTkEntry(riga_retention, width=55)
            campo_retention.insert(0, valore)
            campo_retention.pack(side="left", padx=(0, 8))
            setattr(self, attributo, campo_retention)

        riga_azioni_professionali = ctk.CTkFrame(pannello_professionale, fg_color="transparent")
        riga_azioni_professionali.pack(fill="x", padx=14, pady=(2, 12))
        ctk.CTkButton(riga_azioni_professionali, text="Anteprima retention", width=140, command=self.anteprima_retention_strategia).pack(side="left", padx=(0, 4))
        ctk.CTkButton(riga_azioni_professionali, text="Dashboard", width=105, command=self.mostra_dashboard_strategia).pack(side="left", padx=4)
        ctk.CTkButton(riga_azioni_professionali, text="Salva report", width=105, command=self.salva_report_strategia).pack(side="left", padx=4)

        self.etichetta_stato_strategia = ctk.CTkLabel(scheda, text=self.stato_strategia_testo, text_color=COLORE_TESTO_STATO, anchor="w")  # Mostra lo stato senza riutilizzare widget della vista storica nascosta.
        self.etichetta_stato_strategia.pack(fill="x", padx=18, pady=(6, 4))  # Mantiene visibile l'esito corrente.
        riga_comandi_strategia = ctk.CTkFrame(scheda, fg_color="transparent")  # Isola i comandi dal monitor per evitare vuoti o separazioni causati dal pack laterale.
        riga_comandi_strategia.pack(fill="x", padx=18, pady=(4, 8))  # Dedica una riga completa alle azioni.
        self.pulsante_avvia_strategia = ctk.CTkButton(riga_comandi_strategia, text="▶ Avvia strategia", fg_color=COLORE_PULSANTE_AVVIA, hover_color=COLORE_PULSANTE_AVVIA_HOVER, text_color=COLORE_TESTO_PULSANTE, text_color_disabled="#FFFFFF", command=self.avvia_strategia_backup)  # Avvia il coordinatore avanzato tramite worker.
        self.pulsante_avvia_strategia.pack(side="right", padx=(6, 0))  # Mantiene il comando principale nella riga dedicata.
        ctk.CTkButton(riga_comandi_strategia, text="■ Stop", width=90, fg_color=COLORE_PULSANTE_PERICOLO, hover_color=COLORE_PULSANTE_PERICOLO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.richiedi_stop_avanzato).pack(side="right", padx=6)  # Espone lo Stop cooperativo senza interferire col monitor.
        self._crea_monitor_avanzato(scheda, "strategie", integrato=True)  # Mantiene Avanzamento e Attività nello stesso rettangolo della strategia.

        if self.valori_strategia_gui:  # Ripristina i parametri precedenti dopo un cambio menu senza influenzare il worker già avviato.
            for campo, chiave in ((self.campo_strategia_sorgente, "sorgente"), (self.campo_strategia_destinazione, "destinazione")):  # I campi con placeholder non devono essere svuotati programmaticamente quando il valore salvato è vuoto.
                valore_salvato = self.valori_strategia_gui.get(chiave, "")
                if valore_salvato != "":
                    campo.delete(0, "end")
                    campo.insert(0, valore_salvato)
            for campo, chiave in ((self.campo_full_ogni, "full_ogni"), (self.campo_catene_mantenere, "catene")):  # I campi numerici hanno un valore predefinito reale e vanno sempre riallineati allo stato salvato.
                campo.delete(0, "end")
                campo.insert(0, self.valori_strategia_gui.get(chiave, ""))
            self.variabile_metodo_strategia.set(self.valori_strategia_gui.get("metodo", "Incrementale"))  # Ripristina il metodo scelto.
            self.variabile_strategia_sottocartelle.set(bool(self.valori_strategia_gui.get("sottocartelle", True)))  # Ripristina la ricorsione.
            self.variabile_verifica_post_backup.set(bool(self.valori_strategia_gui.get("verifica", True)))
            self.variabile_test_recuperabilita.set(bool(self.valori_strategia_gui.get("recuperabilita", False)))
            for campo, chiave in ((self.campo_filtro_includi, "includi"), (self.campo_filtro_escludi, "escludi"), (self.campo_estensioni_escluse, "estensioni"), (self.campo_dimensione_minima, "minimo"), (self.campo_dimensione_massima, "massimo"), (self.campo_destinazioni_aggiuntive, "destinazioni_extra")):
                valore_salvato = self.valori_strategia_gui.get(chiave, "")
                if valore_salvato != "":  # Lascia intatto il CTkEntry appena creato quando il valore è vuoto: il placeholder resta nello stato gestito da CustomTkinter.
                    campo.delete(0, "end")
                    campo.insert(0, valore_salvato)
            for campo, chiave in ((self.campo_retention_giorni, "ret_g"), (self.campo_retention_settimane, "ret_s"), (self.campo_retention_mesi, "ret_m"), (self.campo_retention_anni, "ret_a")):
                campo.delete(0, "end")
                campo.insert(0, self.valori_strategia_gui.get(chiave, ""))
            self.variabile_escludi_nascosti.set(bool(self.valori_strategia_gui.get("nascosti", False)))
            self.variabile_escludi_sola_lettura.set(bool(self.valori_strategia_gui.get("sola_lettura", False)))
            self.variabile_politica_reparse.set(self.valori_strategia_gui.get("reparse", "Ignora"))
            self.variabile_destinazioni_obbligatorie.set(bool(self.valori_strategia_gui.get("destinazioni_obbligatorie", False)))
        if self.operazione_avanzata_in_corso == "strategie":  # Rende coerente il comando quando si torna alla vista durante un worker.
            self.pulsante_avvia_strategia.configure(state="disabled", text="⏳ Strategia in corso...")  # Impedisce un secondo avvio concorrente e conserva il feedback.

    def crea_centro_ripristino(self, contenitore) -> None:
        """Presenta in un unico menu i due tipi di ripristino realmente disponibili."""
        ctk.CTkLabel(contenitore, text="Ripristino", font=ctk.CTkFont(size=26, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 4))  # Introduce il centro di recupero senza mescolarlo alle Strategie.
        ctk.CTkLabel(contenitore, text="Scegli il tipo di recupero: backup tradizionale oppure una versione appartenente a una catena Full/Incrementale/Differenziale.", text_color=COLORE_TESTO_TERZIARIO, anchor="w", wraplength=900, justify="left").pack(fill="x", padx=18, pady=(0, 12))  # Spiega la differenza prima della scelta.
        scheda_tradizionale = ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea la scelta del motore conservativo storico.
        scheda_tradizionale.pack(fill="x", padx=18, pady=8)  # Mantiene la scelta come card autonoma.
        ctk.CTkLabel(scheda_tradizionale, text="Ripristino backup tradizionale", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 4))  # Identifica il primo motore.
        ctk.CTkLabel(scheda_tradizionale, text="Recupera una cartella di backup tradizionale con politica conservativa sui file già presenti.", text_color=COLORE_TESTO_TERZIARIO, anchor="w").pack(fill="x", padx=18, pady=(0, 10))  # Descrive il comportamento reale.
        ctk.CTkButton(scheda_tradizionale, text="Apri ripristino tradizionale", command=self.apri_ripristino_tradizionale, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 16))  # Apre la vista storica soltanto dopo la scelta.
        scheda_versione = ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea la scelta del ricostruttore di catene.
        scheda_versione.pack(fill="x", padx=18, pady=8)  # Separa chiaramente i due significati.
        ctk.CTkLabel(scheda_versione, text="Ripristino di una versione", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 4))  # Identifica il recupero avanzato.
        ctk.CTkLabel(scheda_versione, text="Ricostruisce una versione selezionata applicando correttamente la sua catena e le eliminazioni registrate.", text_color=COLORE_TESTO_TERZIARIO, anchor="w").pack(fill="x", padx=18, pady=(0, 10))  # Descrive la semantica verificata.
        ctk.CTkButton(scheda_versione, text="Apri ripristino di una versione", command=lambda: self.mostra_sezione("ripristino_versionato"), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 16))  # Apre la pagina versionata separata dalle Strategie.

        scheda_verifica = ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea un accesso separato alla verifica perché il controllo non esegue alcun ripristino.
        scheda_verifica.pack(fill="x", padx=18, pady=8)  # Mantiene la stessa gerarchia visiva delle due modalità di recupero.
        ctk.CTkLabel(scheda_verifica, text="Verifica integrità delle versioni", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 4))  # Identifica chiaramente il controllo SHA-256.
        ctk.CTkLabel(scheda_verifica, text="Controlla catena, disponibilità dei payload, dimensioni e SHA-256 senza modificare i file del backup.", text_color=COLORE_TESTO_TERZIARIO, anchor="w", wraplength=900, justify="left").pack(fill="x", padx=18, pady=(0, 10))  # Spiega l’effetto non distruttivo del comando.
        ctk.CTkButton(scheda_verifica, text="Apri verifica integrità", command=lambda: self.mostra_sezione("verifica_integrita"), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 16))  # Apre la pagina dedicata senza avviare automaticamente scansioni.

    def apri_ripristino_tradizionale(self) -> None:
        """Apre il ripristino tradizionale tramite lo stesso gestore centrale usato dalle altre sezioni."""
        self.mostra_sezione("ripristino_tradizionale")  # Evita un secondo percorso di gestione dei pannelli e riusa la navigazione che rende correttamente visibile la vista operativa.

    def crea_verifica_integrita(self, contenitore) -> None:
        """Costruisce la pagina di verifica manuale delle versioni con progresso e diagnostica persistente."""
        ctk.CTkLabel(contenitore, text="Verifica integrità", font=ctk.CTkFont(size=26, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 4))  # Titola la pagina in modo distinto dal ripristino.
        ctk.CTkButton(contenitore, text="← Torna ai tipi di ripristino", command=lambda: self.mostra_sezione("ripristino"), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="w", padx=18, pady=(0, 10))  # Mantiene la navigazione coerente con il ripristino versionato.
        scheda = ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Riunisce configurazione, progresso e diagnostica in una sola card.
        scheda.pack(fill="both", expand=True, padx=18, pady=8)  # Usa lo spazio disponibile senza creare pannelli sovrapposti.
        self.campo_versioni_verifica = ctk.CTkEntry(scheda, placeholder_text="Radice delle versioni")  # Raccoglie il repository versionato da controllare.
        self.campo_versioni_verifica.pack(fill="x", padx=18, pady=(18, 6))  # Mantiene leggibili anche percorsi lunghi.
        self.campo_versioni_verifica.insert(0, self.valori_verifica_integrita_gui.get("versioni", ""))  # Ripristina il percorso dopo la navigazione.
        ctk.CTkButton(scheda, text="Scegli versioni", command=lambda: self._scegli_cartella_in_campo(self.campo_versioni_verifica), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 6))  # Seleziona la radice senza eseguire controlli impliciti.
        self.mappa_versioni_verifica = {}  # Associa etichette leggibili agli ID persistenti dei manifesti.
        self.variabile_versione_verifica = ctk.StringVar(value=self.valori_verifica_integrita_gui.get("versione", "Nessuna versione caricata"))  # Conserva la selezione visiva quando possibile.
        self.menu_versioni_verifica = ctk.CTkOptionMenu(scheda, variable=self.variabile_versione_verifica, values=["Nessuna versione caricata"])  # Mostra soltanto versioni caricate e validate.
        self.menu_versioni_verifica.pack(fill="x", padx=18, pady=6)  # Dedica una riga alla versione da verificare.
        ctk.CTkButton(scheda, text="Aggiorna versioni", command=self.carica_versioni_verifica_gui, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 6))  # Scansiona i manifesti senza avviare la verifica.
        riga_comandi = ctk.CTkFrame(scheda, fg_color="transparent")  # Raggruppa avvio e Stop in una riga stabile.
        riga_comandi.pack(fill="x", padx=18, pady=(4, 8))  # Separa i comandi dalla selezione.
        self.pulsante_avvia_verifica_integrita = ctk.CTkButton(riga_comandi, text="✓ Verifica integrità", command=self.avvia_verifica_integrita, fg_color=COLORE_PULSANTE_AVVIA, hover_color=COLORE_PULSANTE_AVVIA_HOVER, text_color=COLORE_TESTO_PULSANTE, text_color_disabled="#FFFFFF")  # Avvia il worker soltanto dopo una selezione valida.
        self.pulsante_avvia_verifica_integrita.pack(side="right", padx=(6, 0))  # Evidenzia l’azione principale.
        ctk.CTkButton(riga_comandi, text="■ Stop", width=90, command=self.richiedi_stop_avanzato, fg_color=COLORE_PULSANTE_PERICOLO, hover_color=COLORE_PULSANTE_PERICOLO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(side="right", padx=6)  # Riusa lo Stop cooperativo condiviso dalle operazioni avanzate.
        ctk.CTkLabel(scheda, text="Avanzamento", font=ctk.CTkFont(size=17, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(14, 4))  # Introduce il progresso determinato.
        riga_progresso = ctk.CTkFrame(scheda, fg_color="transparent")  # Allinea barra e percentuale.
        riga_progresso.pack(fill="x", padx=18, pady=(0, 8))  # Mantiene margini coerenti con le altre pagine.
        self.barra_verifica_integrita = ctk.CTkProgressBar(riga_progresso, mode="determinate", height=12)  # Usa la modalità determinata documentata da CustomTkinter.
        self.barra_verifica_integrita.pack(side="left", fill="x", expand=True, padx=(0, 12))  # Lascia spazio alla percentuale numerica.
        self.barra_verifica_integrita.set(self.progresso_verifica_integrita)  # Ripristina il progresso conservato durante la navigazione.
        self.percentuale_verifica_integrita = ctk.CTkLabel(riga_progresso, text=f"{int(self.progresso_verifica_integrita * 100)}%", width=52, anchor="e")  # Mostra la stessa informazione in forma numerica.
        self.percentuale_verifica_integrita.pack(side="right")  # Mantiene stabile la larghezza della barra.
        self.etichetta_stato_verifica_integrita = ctk.CTkLabel(scheda, text=self.stato_verifica_integrita, text_color=COLORE_TESTO_STATO, anchor="w")  # Mostra lo stato corrente o finale.
        self.etichetta_stato_verifica_integrita.pack(fill="x", padx=18, pady=(0, 6))  # Posiziona lo stato vicino al progresso.
        riga_attivita = ctk.CTkFrame(scheda, fg_color="transparent")  # Raggruppa titolo e cancellazione del report.
        riga_attivita.pack(fill="x", padx=18, pady=(2, 6))  # Mantiene il comando vicino alla diagnostica.
        ctk.CTkLabel(riga_attivita, text="Attività", font=ctk.CTkFont(size=16, weight="bold"), anchor="w").pack(side="left", fill="x", expand=True)  # Introduce il report persistente.
        ctk.CTkButton(riga_attivita, text="Cancella attività", width=130, command=lambda: self.cancella_attivita_avanzata("verifica_integrita"), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(side="right")  # Cancella soltanto su richiesta esplicita.
        self.casella_attivita_verifica_integrita = ctk.CTkTextbox(scheda, height=170, corner_radius=12, fg_color=COLORE_RIQUADRO, border_width=1, border_color=COLORE_BORDO, text_color=("#1E2F3F", "#E8F1FA"))  # Visualizza esito e anomalie senza renderle modificabili.
        self.casella_attivita_verifica_integrita.pack(fill="both", expand=True, padx=18, pady=(0, 18))  # Offre spazio ai percorsi diagnostici.
        if self.attivita_verifica_integrita:  # Ricostruisce il report quando si torna nella pagina o si riavvia FDBackup.
            self.casella_attivita_verifica_integrita.insert("end", "\n".join(self.attivita_verifica_integrita) + "\n")  # Ripubblica il modello persistente nel widget.
            self.casella_attivita_verifica_integrita.see("end")  # Mantiene visibile l’esito più recente.
        self.casella_attivita_verifica_integrita.configure(state="disabled")  # Impedisce modifiche manuali del report.
        self.casella_attivita_verifica_integrita.bind("<MouseWheel>", lambda evento: self.gestisci_scroll_testo_locale(evento, self.casella_attivita_verifica_integrita))  # Applica la stessa politica di scroll degli altri monitor.
        if self.operazione_avanzata_in_corso == "verifica_integrita":  # Ricostruisce correttamente la pagina mentre il worker continua.
            self.pulsante_avvia_verifica_integrita.configure(state="disabled", text="Verifica in corso...")  # Impedisce un secondo avvio concorrente.

    def carica_versioni_verifica_gui(self) -> None:
        """Carica le versioni valide disponibili per la verifica senza modificare il repository."""
        radice_testo = self.campo_versioni_verifica.get().strip()  # Legge la radice indicata dall’utente.
        if not radice_testo:  # Richiede un percorso esplicito.
            messagebox.showerror("Verifica integrità", "Seleziona la radice delle versioni.", parent=self)  # Indica il dato mancante.
            return  # Non tenta scansioni implicite.
        try:  # Riusa l’indice validato del motore di ripristino per non duplicare la semantica delle catene.
            radice = Path(radice_testo).expanduser().resolve(strict=True)  # Normalizza il percorso e richiede che esista realmente.
            if not radice.is_dir():  # Evita di interpretare un file come repository.
                raise ValueError("La radice delle versioni deve essere una cartella.")  # Produce una diagnosi coerente con il motore di ripristino.
            if (radice / ".backupcore-manifesto.json").is_file() or (radice / "manifesto.json").is_file():  # Accetta metadati interni nuovi e repository storici.
                radice = radice.parent  # Risale alla radice comune che contiene tutte le versioni della catena.
                self.campo_versioni_verifica.delete(0, "end")  # Allinea il campo al percorso realmente usato.
                self.campo_versioni_verifica.insert(0, str(radice))  # Rende visibile e ripetibile la normalizzazione applicata.
            indice = MotoreRipristinoAvanzato._carica_indice(radice)  # Carica soltanto manifesti strutturalmente validi.
            radice_testo = str(radice)  # Conserva il percorso normalizzato per il successivo avvio della verifica.
        except (OSError, ValueError, TypeError) as errore:  # Gestisce radice assente, manifesti corrotti o dati incompatibili.
            messagebox.showerror("Verifica integrità", str(errore), parent=self)  # Mostra la causa reale senza dichiarare versioni utilizzabili.
            return  # Mantiene la selezione precedente finché il caricamento non riesce.
        etichette = []  # Prepara le descrizioni leggibili ordinate cronologicamente.
        self.mappa_versioni_verifica = {}  # Sostituisce la mappa soltanto con l’indice appena validato.
        for id_backup, (manifesto, cartella) in sorted(indice.items(), key=lambda elemento: elemento[1][0].creato_il, reverse=True):  # Mostra prima le versioni più recenti.
            etichetta = f"{cartella.name} • {manifesto.tipo_backup}"  # Combina nome leggibile della cartella e metodo senza esporre l’UUID completo.
            etichette.append(etichetta)  # Aggiunge la voce al menu.
            self.mappa_versioni_verifica[etichetta] = id_backup  # Conserva l’identità persistente usata dal backend.
        if not etichette:  # Gestisce un repository esistente ma privo di versioni valide.
            self.menu_versioni_verifica.configure(values=["Nessuna versione disponibile"])  # Mantiene il menu in uno stato esplicito.
            self.variabile_versione_verifica.set("Nessuna versione disponibile")  # Allinea il valore visualizzato.
            return  # Non inventa versioni.
        self.menu_versioni_verifica.configure(values=etichette)  # Pubblica l’elenco validato nel menu.
        precedente = self.valori_verifica_integrita_gui.get("versione", "")  # Recupera l’eventuale selezione precedente.
        self.variabile_versione_verifica.set(precedente if precedente in self.mappa_versioni_verifica else etichette[0])  # Conserva la selezione se ancora valida, altrimenti usa la più recente.
        self.valori_verifica_integrita_gui = {"versioni": radice_testo, "versione": self.variabile_versione_verifica.get()}  # Conserva i valori per la navigazione successiva.

    def avvia_verifica_integrita(self) -> None:
        """Valida la selezione, acquisisce il lock condiviso e avvia la verifica SHA-256 fuori dal thread Tk."""
        if self.ottieni_thread_attivo() is not None or self.operazione_avanzata_in_corso:  # Impedisce sovrapposizioni con backup, sync o ripristini.
            messagebox.showwarning("Operazione in corso", "Attendi il completamento dell'operazione corrente prima di avviare la verifica.", parent=self)  # Evita risultati falsati da repository modificati durante il controllo.
            return  # Non crea un secondo worker.
        radice_testo = self.campo_versioni_verifica.get().strip()  # Legge il repository da controllare.
        etichetta = self.variabile_versione_verifica.get()  # Legge la versione scelta nel menu.
        id_backup = self.mappa_versioni_verifica.get(etichetta)  # Traduce l’etichetta nell’identità persistente.
        if not radice_testo or not id_backup:  # Richiede sia repository sia versione realmente caricata.
            messagebox.showerror("Verifica integrità", "Seleziona la radice, premi Aggiorna versioni e scegli una versione valida.", parent=self)  # Fornisce una correzione precisa.
            return  # Non avvia una verifica ambigua.
        if not self.acquisisci_blocco_operazione_manuale():  # Coordina la lettura con scheduler e altre operazioni che possono modificare il repository.
            return  # Mantiene intatti stato e selezione se il lock non è disponibile.
        self.evento_arresto.clear()  # Elimina richieste Stop appartenenti a operazioni precedenti.
        self.operazione_avanzata_in_corso = "verifica_integrita"  # Mantiene il lifecycle anche se l’utente cambia pagina.
        self.progresso_verifica_integrita = 0.0  # Azzera il progresso per il nuovo controllo.
        self.stato_verifica_integrita = "Preparazione verifica..."  # Espone una fase iniziale prima del primo evento del backend.
        self._aggiungi_attivita_verifica_integrita(f"[VERIFICA] {etichetta}")  # Registra quale versione è stata richiesta.
        if self.sezione_attiva == "verifica_integrita" and self.pulsante_avvia_verifica_integrita.winfo_exists():  # Aggiorna soltanto widget ancora vivi.
            self.pulsante_avvia_verifica_integrita.configure(state="disabled", text="Verifica in corso...")  # Fornisce feedback immediato al click.
            self.barra_verifica_integrita.set(0.0)  # Allinea la barra al nuovo ciclo.
            self.percentuale_verifica_integrita.configure(text="0%")  # Allinea il valore numerico.
            self.etichetta_stato_verifica_integrita.configure(text=self.stato_verifica_integrita)  # Mostra la fase iniziale.
        self.thread_backup = threading.Thread(target=self._worker_verifica_integrita, args=(Path(radice_testo), id_backup), daemon=True)  # Riusa il riferimento worker globale per la gestione sicura della chiusura.
        self.thread_backup.start()  # Avvia l’I/O fuori dal thread principale Tk.

    def _worker_verifica_integrita(self, radice_versioni: Path, id_backup: str) -> None:
        """Esegue il verificatore nel worker e inoltra esclusivamente dati puri alla coda Tk."""
        try:  # Converte eventuali eccezioni impreviste in un evento gestibile dalla GUI.
            verificatore = VerificatoreIntegritaAvanzata(self.evento_arresto, funzione_avanzamento=lambda evento, dati: self.coda_eventi.put(("evento_verifica_integrita", {"evento": evento, "dati": dati})))  # Collega il backend alla coda senza accessi Tk dal thread secondario.
            risultato = verificatore.verifica_versione(radice_versioni, id_backup)  # Esegue catena, presenza, dimensioni e SHA-256.
            self.coda_eventi.put(("verifica_integrita_completata", {"risultato": risultato}))  # Consegna il report finale al thread Tk.
        except Exception as errore:  # Protegge il lifecycle GUI anche da errori non previsti dal contratto pubblico.
            self.coda_eventi.put(("errore_fatale_verifica_integrita", {"errore": f"{type(errore).__name__}: {errore}"}))  # Trasferisce una diagnostica completa senza toccare widget.

    def gestisci_verifica_integrita_completata(self, risultato) -> None:
        """Finalizza lock, stato, attività e popup della verifica nel thread Tk."""
        self.rilascia_blocco_operazione_manuale()  # Rende nuovamente disponibile il repository alle altre operazioni.
        self.operazione_avanzata_in_corso = ""  # Chiude il lifecycle soltanto dopo aver ricevuto il risultato.
        if risultato.annullato:  # Distingue uno Stop da un controllo realmente concluso.
            self.stato_verifica_integrita = "Verifica annullata"  # Non promuove una verifica incompleta a valida.
            self._aggiungi_attivita_verifica_integrita("[FINE] Verifica annullata prima del completamento.")  # Registra esplicitamente l’incompletezza.
        elif risultato.integro:  # Gestisce soltanto il successo pieno e verificato.
            self.progresso_verifica_integrita = 1.0  # Porta al 100% una verifica conclusa senza anomalie.
            self.stato_verifica_integrita = "Integro e recuperabile"  # Usa una formulazione coerente con ciò che il verificatore ha realmente controllato.
            self._aggiungi_attivita_verifica_integrita(f"[OK] {risultato.file_verificati} file, {risultato.byte_verificati:,} byte, {risultato.versioni_catena} versioni nella catena.")  # Registra i contatori verificati.
        else:  # Gestisce corruzione, payload mancanti o catene non valide.
            self.stato_verifica_integrita = "Problemi di integrità"  # Evita di dichiarare recuperabile una versione anomala.
            for errore in risultato.errori:  # Pubblica ogni anomalia separatamente per una diagnosi precisa.
                self._aggiungi_attivita_verifica_integrita(f"[ERRORE] {errore}")  # Conserva il dettaglio fino a cancellazione esplicita.
            self._aggiungi_attivita_verifica_integrita(f"[FINE] Anomalie rilevate: {len(risultato.errori)}.")  # Chiude il report con un contatore sintetico.
        if self.sezione_attiva == "verifica_integrita" and hasattr(self, "pulsante_avvia_verifica_integrita") and self.pulsante_avvia_verifica_integrita.winfo_exists():  # Aggiorna soltanto la pagina ancora viva.
            self.pulsante_avvia_verifica_integrita.configure(state="normal", text="✓ Verifica integrità")  # Riabilita un nuovo controllo.
            self.barra_verifica_integrita.set(max(0.0, min(1.0, self.progresso_verifica_integrita)))  # Allinea la barra allo stato finale.
            self.percentuale_verifica_integrita.configure(text=f"{int(self.progresso_verifica_integrita * 100)}%")  # Allinea la percentuale.
            self.etichetta_stato_verifica_integrita.configure(text=self.stato_verifica_integrita)  # Mostra l’esito finale.
            self._sincronizza_attivita_verifica_integrita_visibile()  # Pubblica il report persistente aggiornato.
        riepilogo = f"File verificati: {risultato.file_verificati}\nByte verificati: {risultato.byte_verificati:,}\nVersioni nella catena: {risultato.versioni_catena}\nAnomalie: {len(risultato.errori)}"  # Costruisce un riepilogo soltanto dai dati del backend.
        if risultato.integro:  # Mostra un successo soltanto per un controllo completo e senza anomalie.
            messagebox.showinfo("Verifica integrità", "Versione integra e recuperabile.\n\n" + riepilogo, parent=self)  # Comunica il risultato positivo verificato.
        elif risultato.annullato:  # Uno Stop non è né successo né corruzione.
            messagebox.showwarning("Verifica integrità", "Verifica annullata. Il controllo è incompleto.\n\n" + riepilogo, parent=self)  # Evita falsi positivi.
        else:  # Qualunque anomalia richiede un avviso.
            messagebox.showwarning("Verifica integrità", "Sono stati rilevati problemi. Consulta Attività per i dettagli.\n\n" + riepilogo, parent=self)  # Rimanda alla diagnostica persistente.

    def _sincronizza_attivita_verifica_integrita_visibile(self) -> None:
        """Riallinea il textbox della verifica al modello persistente soltanto quando il widget esiste."""
        casella = getattr(self, "casella_attivita_verifica_integrita", None)  # Recupera il widget senza assumere che la pagina sia aperta.
        if casella is None or not casella.winfo_exists():  # Evita accessi a widget distrutti dalla navigazione.
            return  # Il modello resta comunque persistito e verrà ricostruito alla riapertura.
        casella.configure(state="normal")  # Abilita temporaneamente l’aggiornamento programmatico.
        casella.delete("1.0", "end")  # Rimuove la rappresentazione precedente.
        if self.attivita_verifica_integrita:  # Evita una riga vuota artificiale quando non esistono eventi.
            casella.insert("end", "\n".join(self.attivita_verifica_integrita[-500:]) + "\n")  # Mostra la stessa finestra persistita su disco.
            casella.see("end")  # Mantiene visibile l’esito più recente.
        casella.configure(state="disabled")  # Ripristina la sola lettura.

    def crea_ripristino_versionato(self, contenitore) -> None:
        """Costruisce il ripristino versionato come pagina autonoma sotto il menu Ripristino."""
        ctk.CTkLabel(contenitore, text="Ripristino di una versione", font=ctk.CTkFont(size=26, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 4))  # Titola chiaramente la pagina separata dalle Strategie.
        ctk.CTkButton(contenitore, text="← Torna ai tipi di ripristino", command=lambda: self.mostra_sezione("ripristino"), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="w", padx=18, pady=(0, 10))  # Consente di cambiare tipo senza usare la sidebar.
        scheda = ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Riunisce configurazione, avanzamento e attività in un unico rettangolo.
        scheda.pack(fill="both", expand=True, padx=18, pady=8)  # Evita la separazione visiva contestata nel test manuale.
        self.campo_versioni_ripristino = ctk.CTkEntry(scheda, placeholder_text="Radice delle versioni")  # Raccoglie la radice prodotta dal backup avanzato.
        self.campo_versioni_ripristino.pack(fill="x", padx=18, pady=(18, 6))  # Mostra il percorso completo.
        ctk.CTkButton(scheda, text="Scegli versioni", command=lambda: self._scegli_cartella_in_campo(self.campo_versioni_ripristino), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 6))  # Seleziona la radice.
        self.mappa_versioni_ripristino = {}  # Associa le etichette leggibili agli ID persistenti.
        self.variabile_versione_ripristino = ctk.StringVar(value="Nessuna versione caricata")  # Mantiene uno stato neutro prima della scansione.
        self.menu_versioni_ripristino = ctk.CTkOptionMenu(scheda, variable=self.variabile_versione_ripristino, values=["Nessuna versione caricata"])  # Mostra soltanto manifesti validi.
        self.menu_versioni_ripristino.pack(fill="x", padx=18, pady=6)  # Mantiene leggibile la versione.
        ctk.CTkButton(scheda, text="Aggiorna versioni", command=self.carica_versioni_ripristino_gui, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 6))  # Aggiorna l'elenco senza modificare dati.
        self.campo_destinazione_ripristino_avanzato = ctk.CTkEntry(scheda, placeholder_text="Destinazione del ripristino")  # Raccoglie la destinazione.
        self.campo_destinazione_ripristino_avanzato.pack(fill="x", padx=18, pady=6)  # Mantiene il percorso visibile.
        ctk.CTkButton(scheda, text="Scegli destinazione", command=lambda: self._scegli_cartella_in_campo(self.campo_destinazione_ripristino_avanzato), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(anchor="e", padx=18, pady=(0, 6))  # Seleziona la cartella di recupero.
        self.campo_selezione_ripristino = ctk.CTkEntry(scheda, placeholder_text="Ripristino selettivo: percorsi relativi separati da ; (vuoto = intera versione)")  # Consente di limitare il recupero a file o cartelle dello snapshot.
        self.campo_selezione_ripristino.pack(fill="x", padx=18, pady=6)  # Mantiene visibili anche selezioni multiple.
        self.variabile_sovrascrivi_ripristino_avanzato = ctk.BooleanVar(value=False)  # Mantiene il default conservativo.
        ctk.CTkCheckBox(scheda, text="Sovrascrivi file già presenti", variable=self.variabile_sovrascrivi_ripristino_avanzato).pack(anchor="w", padx=18, pady=6)  # Espone l'opzione potenzialmente distruttiva.
        riga_comandi_ripristino = ctk.CTkFrame(scheda, fg_color="transparent")  # Isola le azioni dal monitor del ripristino.
        riga_comandi_ripristino.pack(fill="x", padx=18, pady=(4, 8))  # Dedica una riga completa ai comandi.
        self.pulsante_ripristina_versione = ctk.CTkButton(riga_comandi_ripristino, text="↶ Ripristina versione", command=self.avvia_ripristino_avanzato, fg_color=COLORE_PULSANTE_AVVIA, hover_color=COLORE_PULSANTE_AVVIA_HOVER, text_color=COLORE_TESTO_PULSANTE, text_color_disabled="#FFFFFF")  # Fornisce feedback coerente con gli altri avvii.
        self.pulsante_ripristina_versione.pack(side="right", padx=(6, 0))  # Posiziona il comando principale nella riga dedicata.
        ctk.CTkButton(riga_comandi_ripristino, text="■ Stop", width=90, command=self.richiedi_stop_avanzato, fg_color=COLORE_PULSANTE_PERICOLO, hover_color=COLORE_PULSANTE_PERICOLO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(side="right", padx=6)  # Espone lo stop cooperativo senza separare il monitor.
        ctk.CTkLabel(scheda, text="Avanzamento", font=ctk.CTkFont(size=17, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(14, 4))  # Integra il monitor nella stessa card.
        riga_progresso = ctk.CTkFrame(scheda, fg_color="transparent")  # Allinea barra e percentuale.
        riga_progresso.pack(fill="x", padx=18, pady=(0, 8))  # Mantiene margini coerenti.
        self.barra_ripristino_versionato = ctk.CTkProgressBar(riga_progresso, mode="determinate", height=12)  # Visualizza il progresso reale del motore.
        self.barra_ripristino_versionato.pack(side="left", fill="x", expand=True, padx=(0, 12))  # Lascia spazio alla percentuale.
        self.barra_ripristino_versionato.set(self.progresso_ripristino_versionato)  # Ripristina il valore dopo la navigazione.
        self.percentuale_ripristino_versionato = ctk.CTkLabel(riga_progresso, text=f"{int(self.progresso_ripristino_versionato * 100)}%", width=52, anchor="e")  # Mostra la percentuale.
        self.percentuale_ripristino_versionato.pack(side="right")  # Mantiene stabile la barra.
        self.etichetta_stato_ripristino_versionato = ctk.CTkLabel(scheda, text=self.stato_ripristino_versionato, text_color=COLORE_TESTO_STATO, anchor="w")  # Conserva lo stato.
        self.etichetta_stato_ripristino_versionato.pack(fill="x", padx=18, pady=(0, 6))  # Posiziona lo stato vicino alla barra.
        riga_attivita = ctk.CTkFrame(scheda, fg_color="transparent")  # Raggruppa titolo e cancellazione.
        riga_attivita.pack(fill="x", padx=18, pady=(2, 6))  # Mantiene il comando vicino al registro.
        ctk.CTkLabel(riga_attivita, text="Attività", font=ctk.CTkFont(size=16, weight="bold"), anchor="w").pack(side="left", fill="x", expand=True)  # Introduce il registro.
        ctk.CTkButton(riga_attivita, text="Cancella attività", width=130, command=lambda: self.cancella_attivita_avanzata("ripristino_versionato"), fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE).pack(side="right")  # Cancella solo su richiesta.
        self.casella_attivita_ripristino_versionato = ctk.CTkTextbox(scheda, height=150, corner_radius=12, fg_color=COLORE_RIQUADRO, border_width=1, border_color=COLORE_BORDO, text_color=("#1E2F3F", "#E8F1FA"))  # Crea il registro persistente.
        self.casella_attivita_ripristino_versionato.pack(fill="both", expand=True, padx=18, pady=(0, 18))  # Offre spazio ai percorsi.
        if self.attivita_ripristino_versionato:  # Ricostruisce il registro quando si torna nella pagina.
            self.casella_attivita_ripristino_versionato.insert("end", "\n".join(self.attivita_ripristino_versionato) + "\n")  # Mantiene gli eventi.
            self.casella_attivita_ripristino_versionato.see("end")  # Porta in vista l'ultimo evento.
        self.casella_attivita_ripristino_versionato.configure(state="disabled")  # Impedisce modifiche manuali.
        self.casella_attivita_ripristino_versionato.bind("<MouseWheel>", lambda evento: self.gestisci_scroll_testo_locale(evento, self.casella_attivita_ripristino_versionato), add="+")  # Applica lo scroll intelligente.
        if self.valori_ripristino_versionato_gui:  # Ripristina i parametri dopo la navigazione.
            self.campo_versioni_ripristino.insert(0, self.valori_ripristino_versionato_gui.get("versioni", ""))  # Ripristina la radice versioni.
            self.campo_destinazione_ripristino_avanzato.insert(0, self.valori_ripristino_versionato_gui.get("destinazione_ripristino", ""))  # Ripristina la destinazione.
            self.variabile_sovrascrivi_ripristino_avanzato.set(bool(self.valori_ripristino_versionato_gui.get("sovrascrivi", False)))  # Ripristina la politica.
            self.campo_selezione_ripristino.insert(0, self.valori_ripristino_versionato_gui.get("selezione", ""))  # Ripristina l’eventuale selezione file/cartelle.
        if self.operazione_avanzata_in_corso == "ripristino_versionato":  # Mantiene il feedback durante la navigazione.
            self.pulsante_ripristina_versione.configure(state="disabled", text="⏳ Ripristino in corso...")  # Impedisce un secondo avvio concorrente.

    def crea_sincronizzazione(self, contenitore) -> None:
        """Costruisce la sezione Update/Mirror mantenendo visibile il rischio delle eliminazioni Mirror."""
        ctk.CTkLabel(contenitore, text="Sincronizzazione", font=ctk.CTkFont(size=26, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 4))  # Introduce la sezione distinta dai backup versionati.
        ctk.CTkLabel(contenitore, text="Update copia nuovi/modificati senza eliminare gli extra in destinazione. Mirror rende la destinazione equivalente alla sorgente e può eliminare file.", text_color=COLORE_TESTO_TERZIARIO, anchor="w", wraplength=900, justify="left").pack(fill="x", padx=18, pady=(0, 12))  # Espone la differenza operativa prima dell'esecuzione.
        scheda = ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Crea il pannello operativo isolato.
        scheda.pack(fill="x", padx=18, pady=8)  # Mantiene lo stile della GUI esistente.
        self.campo_sync_sorgente = ctk.CTkEntry(scheda, placeholder_text="Cartella sorgente")  # Raccoglie la sorgente della sincronizzazione.
        self.campo_sync_sorgente.pack(fill="x", padx=18, pady=(18, 6))  # Estende il campo per percorsi lunghi.
        ctk.CTkButton(scheda, text="Scegli sorgente", fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self._scegli_cartella_in_campo(self.campo_sync_sorgente)).pack(anchor="e", padx=18, pady=(0, 8))  # Collega il selettore nativo.
        self.campo_sync_destinazione = ctk.CTkEntry(scheda, placeholder_text="Cartella destinazione")  # Raccoglie la destinazione della sincronizzazione.
        self.campo_sync_destinazione.pack(fill="x", padx=18, pady=6)  # Mantiene visibile il percorso.
        ctk.CTkButton(scheda, text="Scegli destinazione", fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self._scegli_cartella_in_campo(self.campo_sync_destinazione)).pack(anchor="e", padx=18, pady=(0, 8))  # Collega il selettore della destinazione.
        self.variabile_metodo_sync = ctk.StringVar(value="Update")  # Seleziona la modalità non distruttiva come default.
        ctk.CTkOptionMenu(scheda, variable=self.variabile_metodo_sync, values=["Update", "Mirror"]).pack(anchor="w", padx=18, pady=6)  # Limita la scelta alle modalità implementate realmente.
        self.variabile_sync_sottocartelle = ctk.BooleanVar(value=True)  # Mantiene la scansione ricorsiva come comportamento ordinario.
        ctk.CTkCheckBox(scheda, text="Includi sottocartelle", variable=self.variabile_sync_sottocartelle).pack(anchor="w", padx=18, pady=6)  # Espone la scelta supportata dal motore.
        self.etichetta_stato_sync = ctk.CTkLabel(scheda, text=self.stato_sync_testo, text_color=COLORE_TESTO_STATO, anchor="w")  # Mostra lo stato corrente della sincronizzazione.
        self.etichetta_stato_sync.pack(fill="x", padx=18, pady=(6, 4))  # Mantiene il feedback vicino ai controlli.
        riga_comandi_sync = ctk.CTkFrame(scheda, fg_color="transparent")  # Isola i comandi dal monitor integrato.
        riga_comandi_sync.pack(fill="x", padx=18, pady=(4, 8))  # Dedica una riga completa alle azioni.
        self.pulsante_avvia_sync = ctk.CTkButton(riga_comandi_sync, text="⇄ Avvia sincronizzazione", fg_color=COLORE_PULSANTE_AVVIA, hover_color=COLORE_PULSANTE_AVVIA_HOVER, text_color=COLORE_TESTO_PULSANTE, text_color_disabled="#FFFFFF", command=self.avvia_sincronizzazione)  # Avvia Update o Mirror tramite worker isolato.
        self.pulsante_avvia_sync.pack(side="right", padx=(6, 0))  # Posiziona il comando principale nella riga dedicata.
        ctk.CTkButton(riga_comandi_sync, text="■ Stop", width=90, fg_color=COLORE_PULSANTE_PERICOLO, hover_color=COLORE_PULSANTE_PERICOLO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.richiedi_stop_avanzato).pack(side="right", padx=6)  # Espone l'arresto cooperativo senza separare il monitor.
        self._crea_monitor_avanzato(scheda, "sincronizza", integrato=True)  # Aggiunge percentuale e Attività persistenti anche alla sincronizzazione.

        if self.valori_sync_gui:  # Ripristina i parametri Sincronizza dopo la ricostruzione della vista.
            for campo, chiave in ((self.campo_sync_sorgente, "sorgente"), (self.campo_sync_destinazione, "destinazione")):  # Elenca i due percorsi della sincronizzazione.
                campo.delete(0, "end")  # Rimuove il valore ricostruito.
                campo.insert(0, self.valori_sync_gui.get(chiave, ""))  # Ripristina il percorso precedente.
            self.variabile_metodo_sync.set(self.valori_sync_gui.get("metodo", "Update"))  # Ripristina Update o Mirror.
            self.variabile_sync_sottocartelle.set(bool(self.valori_sync_gui.get("sottocartelle", True)))  # Ripristina la profondità di scansione.
        if self.operazione_avanzata_in_corso == "sincronizza":  # Rende coerente il comando quando si torna alla vista durante un worker.
            self.pulsante_avvia_sync.configure(state="disabled", text="⏳ Sincronizzazione in corso...")  # Impedisce un secondo avvio concorrente e conferma visivamente il click.

    def _crea_monitor_avanzato(self, contenitore, sezione: str, integrato: bool = False) -> None:
        """Crea barra determinata, percentuale e riquadro Attività ricostruibili dopo ogni cambio menu."""
        scheda_monitor = contenitore if integrato else ctk.CTkFrame(contenitore, corner_radius=16, fg_color=COLORE_SCHEDA)  # Riusa la card operativa quando il monitor deve far parte dello stesso rettangolo.
        if not integrato:  # Impacchetta un nuovo frame soltanto per eventuali utilizzi realmente separati.
            scheda_monitor.pack(fill="both", expand=True, padx=18, pady=8)  # Occupa lo spazio disponibile senza creare separazioni inutili nelle card integrate.
        ctk.CTkLabel(scheda_monitor, text="Avanzamento", font=ctk.CTkFont(size=17, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(14, 4))  # Introduce la progressione numerica.
        riga_progresso = ctk.CTkFrame(scheda_monitor, fg_color="transparent")  # Allinea barra e percentuale sulla stessa fascia.
        riga_progresso.pack(fill="x", padx=18, pady=(0, 10))  # Mantiene margini coerenti con le altre schede.
        barra = ctk.CTkProgressBar(riga_progresso, mode="determinate", height=12)  # Usa una barra determinata perché il motore comunica byte totali e trasferiti.
        barra.pack(side="left", fill="x", expand=True, padx=(0, 12))  # Lascia spazio alla percentuale testuale.
        progresso = self.progresso_strategia if sezione == "strategie" else self.progresso_sync  # Recupera il valore persistente della sezione.
        barra.set(progresso)  # Ripristina la posizione anche dopo aver visitato un altro menu.
        etichetta_percentuale = ctk.CTkLabel(riga_progresso, text=f"{int(progresso * 100)}%", width=52, anchor="e")  # Mostra una percentuale immediatamente leggibile.
        etichetta_percentuale.pack(side="right")  # Mantiene stabile la larghezza della barra.
        riga_attivita = ctk.CTkFrame(scheda_monitor, fg_color="transparent")  # Raggruppa titolo e cancellazione del registro senza perdere spazio verticale.
        riga_attivita.pack(fill="x", padx=18, pady=(2, 6))  # Mantiene il comando vicino al contenuto che controlla.
        ctk.CTkLabel(riga_attivita, text="Attività", font=ctk.CTkFont(size=16, weight="bold"), anchor="w").pack(side="left", fill="x", expand=True)  # Introduce il registro della sezione.
        ctk.CTkButton(riga_attivita, text="Cancella attività", width=130, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self.cancella_attivita_avanzata(sezione)).pack(side="right")  # Lascia all'utente la decisione di svuotare il registro.
        casella = ctk.CTkTextbox(scheda_monitor, height=170, corner_radius=12, fg_color=COLORE_RIQUADRO, border_width=1, border_color=COLORE_BORDO, text_color=("#1E2F3F", "#E8F1FA"))  # Crea un log visuale coerente con quello storico.
        casella.pack(fill="both", expand=True, padx=18, pady=(0, 18))  # Consente di leggere molte righe anche in finestra ridotta.
        casella.bind("<MouseWheel>", lambda evento: self.gestisci_scroll_testo_locale(evento, casella), add="+")  # Fa scorrere soltanto Attività quando il puntatore è nel textbox.
        casella.bind("<Button-4>", lambda evento: self.gestisci_scroll_testo_locale(evento, casella), add="+")  # Supporta lo scroll locale anche su X11/Linux.
        casella.bind("<Button-5>", lambda evento: self.gestisci_scroll_testo_locale(evento, casella), add="+")  # Supporta il verso opposto dello scroll X11/Linux.
        righe = self.attivita_strategia if sezione == "strategie" else self.attivita_sync  # Recupera i messaggi persistiti nello stato della finestra.
        if righe:  # Evita inserimenti inutili quando la sessione non contiene ancora eventi.
            casella.insert("end", "\n".join(righe) + "\n")  # Ricostruisce il testo nello stesso ordine in cui gli eventi sono avvenuti.
            casella.see("end")  # Mostra subito l'attività più recente.
        casella.configure(state="disabled")  # Impedisce modifiche manuali del registro visuale.
        if sezione == "strategie":  # Conserva riferimenti soltanto alla vista Strategie attualmente viva.
            self.barra_strategia = barra  # Permette agli eventi Tk di aggiornare la barra visibile.
            self.percentuale_strategia = etichetta_percentuale  # Permette agli eventi Tk di aggiornare il testo percentuale.
            self.casella_attivita_strategia = casella  # Permette di aggiungere righe senza ricostruire la vista.
        else:  # Gestisce i riferimenti equivalenti della sincronizzazione.
            self.barra_sync = barra  # Conserva la barra Sincronizza attualmente visibile.
            self.percentuale_sync = etichetta_percentuale  # Conserva la percentuale Sincronizza attualmente visibile.
            self.casella_attivita_sync = casella  # Conserva il log Sincronizza attualmente visibile.

    def _aggiungi_attivita_avanzata(self, sezione: str, testo: str) -> None:
        """Aggiunge un messaggio allo stato persistente e, se visibile, al relativo CTkTextbox."""
        righe = self.attivita_strategia if sezione == "strategie" else self.attivita_sync  # Seleziona il registro indipendente dalla vista.
        righe.append(testo)  # Conserva il messaggio anche se l'utente sta guardando un altro menu.
        if len(righe) > 500:  # Limita la memoria della sessione senza perdere gli eventi più recenti.
            del righe[:-500]  # Mantiene soltanto le ultime cinquecento righe.
        self._salva_attivita_avanzate()  # Salva ogni nuovo evento così Strategie e Sincronizza sopravvivono alla chiusura definitiva.
        nome_widget = "casella_attivita_strategia" if sezione == "strategie" else "casella_attivita_sync"  # Risolve il widget della sezione senza duplicare logica.
        casella = getattr(self, nome_widget, None)  # Recupera il widget soltanto se la vista è stata costruita.
        if casella is not None and casella.winfo_exists() and self.sezione_attiva == sezione:  # Aggiorna esclusivamente un widget vivo nel thread Tk.
            casella.configure(state="normal")  # Abilita temporaneamente l'inserimento programmatico.
            casella.insert("end", testo + "\n")  # Aggiunge la nuova attività in coda.
            casella.see("end")  # Mantiene visibile l'evento più recente.
            casella.configure(state="disabled")  # Ripristina immediatamente la sola lettura.

    def _aggiorna_progresso_avanzato(self, sezione: str, frazione: float, stato: str | None = None) -> None:
        """Aggiorna stato persistente e widget visibili limitando sempre il progresso tra zero e uno."""
        frazione = max(0.0, min(1.0, float(frazione)))  # Difende la GUI da valori fuori intervallo prodotti da errori di conteggio.
        if sezione == "strategie":  # Aggiorna il modello visuale della strategia.
            self.progresso_strategia = frazione  # Conserva la frazione oltre la vita del pannello.
            if stato is not None:  # Modifica il testo soltanto quando il chiamante fornisce un nuovo stato.
                self.stato_strategia_testo = stato  # Conserva lo stato leggibile.
        else:  # Aggiorna il modello visuale della sincronizzazione.
            self.progresso_sync = frazione  # Conserva la frazione oltre la vita del pannello.
            if stato is not None:  # Modifica il testo soltanto quando richiesto.
                self.stato_sync_testo = stato  # Conserva lo stato leggibile.
        if self.sezione_attiva != sezione:  # Non tenta di toccare widget distrutti quando l'utente naviga altrove.
            return  # Lo stato persistente verrà applicato alla prossima costruzione della vista.
        barra = getattr(self, "barra_strategia" if sezione == "strategie" else "barra_sync", None)  # Recupera la barra attualmente visibile.
        percentuale = getattr(self, "percentuale_strategia" if sezione == "strategie" else "percentuale_sync", None)  # Recupera l'etichetta numerica.
        etichetta = getattr(self, "etichetta_stato_strategia" if sezione == "strategie" else "etichetta_stato_sync", None)  # Recupera lo stato testuale.
        if barra is not None and barra.winfo_exists():  # Verifica che la barra appartenga ancora alla vista viva.
            barra.set(frazione)  # Aggiorna graficamente l'avanzamento.
        if percentuale is not None and percentuale.winfo_exists():  # Verifica che l'etichetta percentuale sia viva.
            percentuale.configure(text=f"{int(frazione * 100)}%")  # Mostra una percentuale intera stabile.
        if stato is not None and etichetta is not None and etichetta.winfo_exists():  # Aggiorna lo stato soltanto quando necessario.
            etichetta.configure(text=stato)  # Riflette nella vista il testo persistito.

    def richiedi_stop_avanzato(self) -> None:
        """Richiede l'arresto cooperativo dell'operazione avanzata corrente senza terminare forzatamente il thread."""
        if self.ottieni_thread_attivo() is None:  # Evita di impostare uno Stop persistente quando non esiste alcun worker.
            return  # Mantiene neutro l'evento per la prossima operazione.
        self.evento_arresto.set()  # Usa lo stesso evento osservato dai motori storici e avanzati tra le unità di lavoro.
        if self.sezione_attiva == "strategie" and hasattr(self, "etichetta_stato_strategia") and self.etichetta_stato_strategia.winfo_exists():  # Aggiorna il pannello versionato quando visibile.
            self.etichetta_stato_strategia.configure(text="Arresto richiesto...")  # Comunica che lo Stop è cooperativo e non immediato.
        if self.sezione_attiva == "sincronizza" and hasattr(self, "etichetta_stato_sync") and self.etichetta_stato_sync.winfo_exists():  # Aggiorna il pannello di sincronizzazione quando visibile.
            self.etichetta_stato_sync.configure(text="Arresto richiesto...")  # Comunica che il worker terminerà in un punto sicuro.

    def _politica_retention_gui(self) -> PoliticaRetention:
        """Costruisce la retention GFS dai valori visibili nella sezione Strategie."""
        return PoliticaRetention(int(self.campo_retention_giorni.get()), int(self.campo_retention_settimane.get()), int(self.campo_retention_mesi.get()), int(self.campo_retention_anni.get()))

    def anteprima_retention_strategia(self) -> None:
        """Mostra l'anteprima non distruttiva e permette l'applicazione soltanto dopo conferma esplicita."""
        try:
            radice = Path(self.campo_strategia_destinazione.get().strip())
            if not self.campo_strategia_destinazione.get().strip():
                raise ValueError("Seleziona prima il repository delle versioni.")
            conservare, eliminare = pianifica_retention(radice, self._politica_retention_gui())
            testo = f"Versioni da conservare: {len(conservare)}\nVersioni eliminabili: {len(eliminare)}"
            if not eliminare:
                messagebox.showinfo("Anteprima retention", testo + "\n\nNessuna eliminazione necessaria.", parent=self); return
            if messagebox.askyesno("Anteprima retention", testo + "\n\nApplicare ora la retention alle catene selezionate?", parent=self):
                eliminate = applica_retention_sicura(radice, self._politica_retention_gui(), conferma=True)
                self._aggiungi_attivita_avanzata("strategie", f"[RETENTION] Eliminate {len(eliminate)} versioni appartenenti a catene scadute.")
        except (OSError, ValueError) as errore:
            messagebox.showerror("Retention", str(errore), parent=self)

    def mostra_dashboard_strategia(self) -> None:
        """Mostra statistiche reali del repository selezionato senza modificarlo."""
        try:
            radice = Path(self.campo_strategia_destinazione.get().strip())
            if not self.campo_strategia_destinazione.get().strip(): raise ValueError("Seleziona prima il repository delle versioni.")
            dati = crea_dashboard(radice); tipi = dati["tipi"]
            dettagli = dati.get("dettagli", [])
            righe_stato = [f"{voce['creato_il']} • {str(voce['tipo']).title()} • {str(voce['stato']).upper()}" for voce in dettagli[-8:]]
            testo_stati = "\n".join(righe_stato) if righe_stato else "Nessuna versione."
            messagebox.showinfo("Dashboard repository", f"Versioni: {dati['versioni']}\nFull: {tipi['completo']}\nIncrementali: {tipi['incrementale']}\nDifferenziali: {tipi['differenziale']}\nAnomalie: {dati.get('anomalie', 0)}\nUltimo backup: {dati['ultimo_backup'] or 'nessuno'}\n\nStato versioni recenti:\n{testo_stati}", parent=self)
        except (OSError, ValueError) as errore:
            messagebox.showerror("Dashboard", str(errore), parent=self)

    def salva_report_strategia(self) -> None:
        """Salva un report JSON del repository nel percorso scelto dall'utente."""
        try:
            radice_testo = self.campo_strategia_destinazione.get().strip()
            if not radice_testo: raise ValueError("Seleziona prima il repository delle versioni.")
            percorso = filedialog.asksaveasfilename(parent=self, title="Salva report FDBackup", defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not percorso: return
            salva_report_periodico(Path(percorso), [Path(radice_testo)])
            messagebox.showinfo("Report", "Report salvato correttamente.", parent=self)
        except (OSError, ValueError) as errore:
            messagebox.showerror("Report", str(errore), parent=self)

    def avvia_strategia_backup(self) -> None:
        """Valida i parametri della sezione Strategie e avvia il coordinatore avanzato in un worker."""
        if self.ottieni_thread_attivo() is not None or self.operazione_avanzata_in_corso:  # Impedisce sovrapposizioni anche nella finestra tra fine worker e finalizzazione Tk.
            messagebox.showwarning("Strategie", "È già in corso un'operazione.", parent=self)  # Informa senza creare un secondo worker.
            return  # Mantiene intatta l'operazione attiva.
        try:  # Converte e valida tutti i parametri prima di acquisire il lock globale.
            sorgente = Path(self.campo_strategia_sorgente.get().strip())  # Converte la sorgente in Path senza correggerla silenziosamente.
            destinazione = Path(self.campo_strategia_destinazione.get().strip())  # Converte la radice delle versioni in Path.
            metodo = self.variabile_metodo_strategia.get().strip().lower()  # Normalizza la voce visualizzata secondo il contratto del backend.
            separa = lambda testo: tuple(voce.strip() for voce in testo.split(";") if voce.strip())
            minimo_testo = self.campo_dimensione_minima.get().strip()
            massimo_testo = self.campo_dimensione_massima.get().strip()
            filtro = FiltroBackup(includi=separa(self.campo_filtro_includi.get()), escludi=separa(self.campo_filtro_escludi.get()), estensioni_escluse=separa(self.campo_estensioni_escluse.get()), dimensione_minima=int(minimo_testo) if minimo_testo else 0, dimensione_massima=int(massimo_testo) if massimo_testo else None, escludi_nascosti=self.variabile_escludi_nascosti.get(), escludi_sola_lettura=self.variabile_escludi_sola_lettura.get(), politica_reparse=self.variabile_politica_reparse.get().strip().lower())
            strategia = StrategiaBackupAvanzato(metodo=metodo, full_ogni=int(self.campo_full_ogni.get().strip()), catene_da_mantenere=int(self.campo_catene_mantenere.get().strip()), includi_sottocartelle=self.variabile_strategia_sottocartelle.get(), filtro=filtro)  # Delega al modello avanzato anche i filtri professionali.
            if not self.campo_strategia_sorgente.get().strip() or not self.campo_strategia_destinazione.get().strip():  # Rifiuta Path('.') derivati da campi vuoti.
                raise ValueError("Sorgente e destinazione sono obbligatorie.")  # Mantiene esplicito il requisito dei percorsi.
        except (TypeError, ValueError) as errore:  # Gestisce input numerici o strategici non validi.
            messagebox.showerror("Strategia non valida", str(errore), parent=self)  # Mostra il motivo senza avviare il worker.
            return  # Lascia modificabili i campi.
        if not self.acquisisci_blocco_operazione_manuale():  # Condivide lo stesso lock interprocesso del Backup storico e dello scheduler.
            return  # Non avvia l'operazione quando il lock appartiene a un altro processo.
        self.evento_arresto.clear()  # Elimina richieste Stop residue prima del nuovo worker.
        self.operazione_avanzata_in_corso = "strategie"  # Mantiene attiva l'operazione fino alla finalizzazione GUI, anche se il worker termina prima del polling.
        self._aggiorna_progresso_avanzato("strategie", 0.0, "Analisi della sorgente...")  # Mostra la fase preliminare prima che siano noti i byte da copiare.
        self.statistiche_filtri_strategia = {"inclusi": 0, "esclusi": 0, "cartelle_escluse": 0}
        self._aggiungi_attivita_avanzata("strategie", "[AVVIO] Analisi della sorgente e preparazione della strategia.")  # Fornisce feedback immediato all'utente.
        self.pulsante_avvia_strategia.configure(state="disabled", text="⏳ Strategia in corso...")  # Impedisce doppi click e conferma immediatamente la pressione.
        opzioni_professionali = {"verifica": self.variabile_verifica_post_backup.get(), "recuperabilita": self.variabile_test_recuperabilita.get(), "destinazioni": [Path(x.strip()) for x in self.campo_destinazioni_aggiuntive.get().split(";") if x.strip()], "destinazioni_obbligatorie": self.variabile_destinazioni_obbligatorie.get()}
        self.thread_backup = threading.Thread(target=self._worker_strategia_backup, args=(sorgente, destinazione, strategia, opzioni_professionali), daemon=True, name="ThreadStrategiaBackup")  # Riusa il riferimento del backup per le protezioni di chiusura già esistenti.
        self.thread_backup.start()  # Avvia il coordinatore fuori dal thread Tk.

    def _worker_strategia_backup(self, sorgente: Path, destinazione: Path, strategia: StrategiaBackupAvanzato, opzioni_professionali: dict | None = None) -> None:
        """Esegue la strategia avanzata e trasferisce il risultato alla GUI esclusivamente tramite coda."""
        try:  # Isola qualunque errore non previsto dal thread grafico.
            gestore = GestoreBackupAvanzato(evento_arresto=self.evento_arresto, callback=lambda evento, dati: self.coda_eventi.put(("evento_avanzato", {"sezione": "strategie", "evento": evento, "dati": dati})))  # Inoltra progresso e attività alla coda thread-safe senza toccare Tk.
            disponibile, dettaglio_destinazione = destinazione_disponibile(destinazione)
            if not disponibile:
                raise OSError(f"Destinazione non disponibile: {dettaglio_destinazione}")
            risultato = gestore.esegui_strategia(sorgente, destinazione, strategia)  # Esegue la strategia già coperta dai test backend.
            opzioni_professionali = opzioni_professionali or {}
            manifesto = getattr(risultato, "manifesto", None)
            if getattr(risultato, "successo", False) and manifesto is not None:
                report = None
                affidabilita = GestoreAffidabilita()
                if opzioni_professionali.get("verifica", True):
                    report = affidabilita.verifica(destinazione, manifesto.id_backup)
                    self.coda_eventi.put(("attivita_professionale", {"testo": f"[VERIFICA POST-BACKUP] Stato: {report.stato}; file: {report.file_verificati}; errori: {len(report.errori)}."}))
                if opzioni_professionali.get("recuperabilita", False) and (report is None or report.stato == "verificato"):
                    import tempfile
                    with tempfile.TemporaryDirectory(prefix="fdbackup-recuperabilita-") as temporanea:
                        recuperabilita = affidabilita.test_recuperabilita(destinazione, manifesto.id_backup, Path(temporanea))
                    self.coda_eventi.put(("attivita_professionale", {"testo": f"[RECUPERABILITÀ] Stato: {recuperabilita.stato}; errori: {len(recuperabilita.errori)}."}))
                destinazioni_extra = opzioni_professionali.get("destinazioni", [])
                if destinazioni_extra:
                    cartella_versione = gestore._trova_cartella_versione(destinazione, manifesto.id_backup)
                    if cartella_versione is None:
                        raise FileNotFoundError("La versione appena pubblicata non è stata trovata per la replica.")
                    voci = [DestinazioneBackup(Path(x), bool(opzioni_professionali.get("destinazioni_obbligatorie", False))) for x in destinazioni_extra]
                    repliche = GestoreDestinazioniMultiple().replica(cartella_versione, voci)
                    for percorso, stato in repliche.items():
                        self.coda_eventi.put(("attivita_professionale", {"testo": f"[DESTINAZIONE AGGIUNTIVA] {percorso}: {stato}"}))
                for avviso in genera_avvisi(destinazione, 0, report):
                    self.coda_eventi.put(("attivita_professionale", {"testo": f"[AVVISO {avviso.codice}] {avviso.messaggio}"}))
            if getattr(risultato, "successo", False):
                stato_integrita = report.stato if 'report' in locals() and report is not None else "non verificato"
                titolo_notifica = "FDBackup • backup completato" if stato_integrita in {"verificato", "non verificato"} else "FDBackup • verifica non superata"
                mostra_notifica_testo(titolo_notifica, f"Strategia {risultato.tipo_backup}: {risultato.file_copiati} file copiati. Integrità: {stato_integrita}.")
            self.coda_eventi.put(("strategia_completata", {"risultato": risultato}))  # Consegna l'esito senza toccare widget Tk dal worker.
        except Exception as errore:  # Mantiene la GUI viva anche davanti a un errore fatale del backend.
            testo_errore = f"{type(errore).__name__}: {errore}"
            mostra_notifica_testo("FDBackup • backup fallito", testo_errore)
            self.coda_eventi.put(("errore_fatale_strategia", {"errore": testo_errore}))  # Trasferisce una diagnostica esplicita al thread GUI.

    def avvia_sincronizzazione(self) -> None:
        """Valida Update/Mirror e avvia la sincronizzazione usando il lock operativo condiviso."""
        if self.ottieni_thread_attivo() is not None or self.operazione_avanzata_in_corso:  # Impedisce una seconda operazione anche prima che Tk finalizzi la precedente.
            messagebox.showwarning("Sincronizzazione", "È già in corso un'operazione.", parent=self)  # Informa l'utente senza modificare lo stato.
            return  # Mantiene il worker corrente.
        sorgente_testo = self.campo_sync_sorgente.get().strip()  # Legge la sorgente una sola volta.
        destinazione_testo = self.campo_sync_destinazione.get().strip()  # Legge la destinazione una sola volta.
        if not sorgente_testo or not destinazione_testo:  # Evita che Path('.') venga interpretato come input valido.
            messagebox.showerror("Sincronizzazione", "Sorgente e destinazione sono obbligatorie.", parent=self)  # Richiede una configurazione esplicita.
            return  # Non acquisisce il lock per input incompleti.
        metodo = self.variabile_metodo_sync.get().strip().lower()  # Normalizza Update/Mirror secondo l'API del coordinatore.
        if metodo == "mirror":  # Richiede una conferma aggiuntiva soltanto per la modalità che può eliminare file.
            conferma = messagebox.askyesno("Conferma Mirror", "Mirror può eliminare dalla destinazione file e cartelle non presenti nella sorgente. Vuoi continuare?", parent=self)  # Espone il rischio prima dell'operazione distruttiva.
            if not conferma:  # Rispetta il rifiuto senza effetti sul filesystem.
                return  # Termina prima dell'acquisizione del lock.
        if not self.acquisisci_blocco_operazione_manuale():  # Condivide l'esclusione reciproca con scheduler e motori storici.
            return  # Non crea il worker se un'altra operazione possiede il lock.
        self.evento_arresto.clear()  # Prepara un evento Stop pulito.
        self.operazione_avanzata_in_corso = "sincronizza"  # Mantiene il lifecycle indipendente dal pannello visualizzato.
        self._aggiorna_progresso_avanzato("sincronizza", 0.0, "Analisi della sorgente...")  # Mostra la fase preliminare prima della copia.
        self._aggiungi_attivita_avanzata("sincronizza", f"[AVVIO] Sincronizzazione {metodo.title()} in preparazione.")  # Mostra la modalità effettivamente richiesta.
        self.pulsante_avvia_sync.configure(state="disabled", text="⏳ Sincronizzazione in corso...")  # Impedisce avvii duplicati e conferma immediatamente la pressione.
        self.thread_backup = threading.Thread(target=self._worker_sincronizzazione, args=(metodo, Path(sorgente_testo), Path(destinazione_testo), self.variabile_sync_sottocartelle.get()), daemon=True, name="ThreadSincronizzazione")  # Riusa le protezioni lifecycle del backup esistente.
        self.thread_backup.start()  # Avvia il motore senza bloccare Tk.

    def _worker_sincronizzazione(self, metodo: str, sorgente: Path, destinazione: Path, includi_sottocartelle: bool) -> None:
        """Esegue Update/Mirror e inoltra alla GUI soltanto un evento thread-safe."""
        try:  # Protegge il worker da errori di validazione o filesystem.
            gestore = GestoreBackupAvanzato(evento_arresto=self.evento_arresto, callback=lambda evento, dati: self.coda_eventi.put(("evento_avanzato", {"sezione": "sincronizza", "evento": evento, "dati": dati})))  # Inoltra progresso e attività alla coda thread-safe senza toccare Tk.
            risultato = gestore.esegui_sincronizzazione(metodo, sorgente, destinazione, includi_sottocartelle)  # Esegue esclusivamente la modalità richiesta.
            self.coda_eventi.put(("sincronizzazione_completata", {"risultato": risultato}))  # Trasferisce l'esito nel thread Tk.
        except Exception as errore:  # Converte gli errori fatali in un evento gestibile dalla GUI.
            self.coda_eventi.put(("errore_fatale_sincronizzazione", {"errore": f"{type(errore).__name__}: {errore}"}))  # Conserva tipo e messaggio dell'eccezione.

    def _sincronizza_attivita_ripristino_versionato_visibile(self) -> None:
        """Ridisegna il registro versionato quando la relativa pagina è attualmente visibile."""
        casella = getattr(self, "casella_attivita_ripristino_versionato", None)  # Recupera il textbox senza dipendere dalla pagina corrente.
        if casella is None or not casella.winfo_exists():  # Non tocca widget distrutti durante la navigazione.
            return  # Il registro in memoria verrà ricostruito alla prossima apertura.
        casella.configure(state="normal")  # Abilita temporaneamente l'aggiornamento programmatico.
        casella.delete("1.0", "end")  # Evita duplicazioni quando il registro viene sincronizzato più volte.
        if self.attivita_ripristino_versionato:  # Scrive soltanto quando esistono eventi da mostrare.
            casella.insert("end", "\n".join(self.attivita_ripristino_versionato) + "\n")  # Ricostruisce il testo dalla fonte persistente in memoria.
            casella.see("end")  # Porta in vista l'ultimo evento aggiunto.
        casella.configure(state="disabled")  # Ripristina la sola lettura richiesta dal pannello Attività.

    def carica_versioni_ripristino_gui(self) -> None:
        """Carica i manifesti validi e presenta le versioni disponibili senza richiedere ID manuali."""
        radice_testo = self.campo_versioni_ripristino.get().strip()  # Legge la radice indicata dall'utente senza modificarla.
        if not radice_testo:  # Richiede una radice esplicita prima della scansione.
            messagebox.showerror("Versioni", "Seleziona prima la radice delle versioni.", parent=self)  # Evita una scansione involontaria della directory corrente.
            return  # Mantiene il menu nello stato precedente.
        try:  # Isola errori di percorso e manifesti non validi dalla GUI.
            radice = Path(radice_testo).expanduser().resolve(strict=True)  # Richiede una cartella realmente esistente prima di cercare le versioni.
            if not radice.is_dir():  # Evita di trattare un file come contenitore delle versioni.
                raise ValueError("La radice delle versioni deve essere una cartella.")  # Fornisce un errore leggibile invece di un menu vuoto.
            if (radice / ".backupcore-manifesto.json").is_file() or (radice / "manifesto.json").is_file():  # Accetta metadati interni nuovi e repository storici.
                radice = radice.parent  # Risale alla radice comune attesa dal motore di ripristino.
                self.campo_versioni_ripristino.delete(0, "end")  # Allinea il campo al percorso effettivamente utilizzato.
                self.campo_versioni_ripristino.insert(0, str(radice))  # Mostra la radice corretta per rendere ripetibile il ripristino.
            gestore = GestoreBackupAvanzato()  # Riusa il lettore di manifesti già validato dal coordinatore.
            manifesti = gestore.elenca_manifesti(radice)  # Carica soltanto versioni con manifesto valido direttamente sotto la radice.
        except (OSError, ValueError) as errore:  # Gestisce percorsi non accessibili o incompatibili.
            messagebox.showerror("Versioni", str(errore), parent=self)  # Mostra il motivo senza alterare i dati.
            return  # Conserva il menu precedente.
        self.mappa_versioni_ripristino = {}  # Ricostruisce la mappa da zero per evitare riferimenti a versioni eliminate.
        etichette = []  # Prepara l'ordine visuale restituito dal coordinatore.
        for manifesto in reversed(manifesti):  # Mostra prima le versioni più recenti per facilitare il recupero ordinario.
            etichetta = f"{manifesto.creato_il} • {manifesto.tipo_backup.upper()} • {manifesto.id_backup[:8]}"  # Combina data, metodo e prefisso ID in una voce leggibile.
            self.mappa_versioni_ripristino[etichetta] = manifesto.id_backup  # Conserva internamente l'identità completa necessaria al ripristino.
            etichette.append(etichetta)  # Aggiunge la voce al menu nell'ordine desiderato.
        if not etichette:  # Gestisce una radice valida ma ancora priva di versioni pubblicate.
            etichette = ["Nessuna versione disponibile"]  # Comunica esplicitamente l'assenza di backup recuperabili.
        self.menu_versioni_ripristino.configure(values=etichette)  # Aggiorna le sole scelte effettivamente disponibili.
        self.variabile_versione_ripristino.set(etichette[0])  # Seleziona la versione più recente oppure il messaggio neutro.
        if manifesti:  # Fornisce un riscontro esplicito quando la scansione ha trovato versioni valide.
            self.stato_ripristino_versionato = f"Versioni disponibili: {len(manifesti)}"  # Conserva il conteggio anche durante la navigazione.
            self.etichetta_stato_ripristino_versionato.configure(text=self.stato_ripristino_versionato)  # Aggiorna subito lo stato visibile.
            self._aggiungi_attivita_ripristino_versionato(f"[VERSIONI] Caricate {len(manifesti)} versioni valide da {radice}.")  # Registra l'esito senza cancellare lo storico.
            self._sincronizza_attivita_ripristino_versionato_visibile()  # Rende immediatamente visibile il nuovo evento nel textbox corrente.
        else:  # Una radice esistente ma senza manifesti validi richiede un feedback esplicito.
            self.stato_ripristino_versionato = "Nessuna versione valida trovata"  # Evita il precedente silenzio del comando Aggiorna versioni.
            self.etichetta_stato_ripristino_versionato.configure(text=self.stato_ripristino_versionato)  # Mostra il risultato della scansione.
            messagebox.showwarning("Versioni", "Nella cartella selezionata non sono state trovate versioni FDBackup valide. Seleziona la cartella che contiene le directory COMPLETO/INCREMENTALE/DIFFERENZIALE.", parent=self)  # Indica esattamente quale livello di cartella è atteso.

    def avvia_ripristino_avanzato(self) -> None:
        """Avvia il ripristino deterministico della versione indicata senza modificare il Ripristino storico."""
        if self.ottieni_thread_attivo() is not None:  # Impedisce sovrapposizioni con backup o sincronizzazioni.
            messagebox.showwarning("Ripristino versionato", "È già in corso un'operazione.", parent=self)  # Informa l'utente.
            return  # Non crea un secondo worker.
        radice = self.campo_versioni_ripristino.get().strip()  # Legge la radice delle versioni.
        etichetta_versione = self.variabile_versione_ripristino.get().strip()  # Legge la voce selezionata nel menu delle versioni validate.
        id_backup = self.mappa_versioni_ripristino.get(etichetta_versione, "")  # Risolve internamente l'ID completo senza input manuale.
        destinazione = self.campo_destinazione_ripristino_avanzato.get().strip()  # Legge la destinazione di recupero.
        if not radice or not id_backup or not destinazione:  # Richiede tutti gli elementi necessari alla ricostruzione deterministica.
            messagebox.showerror("Ripristino versionato", "Radice versioni, versione selezionata e destinazione sono obbligatorie. Usa 'Aggiorna versioni' dopo aver scelto la radice.", parent=self)  # Spiega come ottenere una selezione valida.
            return  # Non acquisisce il lock con input incompleto.
        selezione_testo = self.campo_selezione_ripristino.get().strip()  # Legge l’eventuale selezione di file/cartelle relativa allo snapshot.
        selezione = [elemento.strip().replace("\\", "/") for elemento in selezione_testo.split(";") if elemento.strip()] or None  # Normalizza separatori e rimuove elementi vuoti lasciando al backend la validazione di sicurezza.
        if not self.acquisisci_blocco_operazione_manuale():  # Condivide il lock con ogni altra operazione FDBackup.
            return  # Non avvia il worker se lo scheduler sta lavorando.
        self.evento_arresto.clear()  # Elimina eventuali Stop precedenti.
        self.operazione_avanzata_in_corso = "ripristino_versionato"  # Mantiene il lifecycle del recupero indipendente dalla pagina visibile.
        self.progresso_ripristino_versionato = 0.0  # Azzera soltanto la barra della nuova esecuzione, non il registro Attività.
        self.stato_ripristino_versionato = "Preparazione ripristino..."  # Fornisce feedback immediato prima della scansione della catena.
        self._aggiungi_attivita_ripristino_versionato("[AVVIO] Preparazione del ripristino versionato.")  # Conserva l’avvio senza cancellare le operazioni precedenti.
        self.pulsante_ripristina_versione.configure(state="disabled", text="⏳ Ripristino in corso...")  # Impedisce richieste duplicate e conferma immediatamente la pressione.
        self.thread_ripristino = threading.Thread(target=self._worker_ripristino_avanzato, args=(Path(radice), id_backup, Path(destinazione), self.variabile_sovrascrivi_ripristino_avanzato.get(), selezione), daemon=True, name="ThreadRipristinoAvanzato")  # Riusa il riferimento lifecycle del ripristino storico.
        self.thread_ripristino.start()  # Avvia il motore fuori da Tk.

    def _worker_ripristino_avanzato(self, radice: Path, id_backup: str, destinazione: Path, sovrascrivi: bool, selezione: list[str] | None = None) -> None:
        """Ricostruisce la catena selezionata e trasferisce il risultato alla GUI tramite coda."""
        try:  # Isola gli errori di catena, manifesto o filesystem.
            motore = MotoreRipristinoAvanzato(self.evento_arresto, funzione_avanzamento=lambda evento, dati: self.coda_eventi.put(("evento_ripristino_avanzato", {"evento": evento, "dati": dati})))  # Crea il motore con Stop e progresso thread-safe.
            risultato = motore.ripristina(radice, id_backup, destinazione, sovrascrivi=sovrascrivi, selezione=selezione)  # Ricostruisce l’intera versione o soltanto i percorsi richiesti.
            self.coda_eventi.put(("ripristino_avanzato_completato", {"risultato": risultato}))  # Inoltra l'esito senza toccare Tk.
        except Exception as errore:  # Converte un errore fatale in evento GUI.
            self.coda_eventi.put(("errore_fatale_ripristino_avanzato", {"errore": f"{type(errore).__name__}: {errore}"}))  # Conserva una diagnostica completa.

    def _concludi_operazione_avanzata(self, titolo: str, tipo_record: str, risultato, descrizione: str) -> None:
        """Ripristina lock e controlli dopo un backup avanzato o una sincronizzazione e registra la cronologia."""
        self.rilascia_blocco_operazione_manuale()  # Rende disponibile il lock condiviso al termine del worker.
        sezione = "strategie" if tipo_record == "backup_versionato" else "sincronizza"  # Associa il risultato al monitor corretto senza dipendere dalla vista attuale.
        self.operazione_avanzata_in_corso = ""  # Chiude il lifecycle soltanto nel thread Tk dopo aver ricevuto l'esito.
        self._aggiorna_progresso_avanzato(sezione, 1.0 if risultato.successo else (self.progresso_strategia if sezione == "strategie" else self.progresso_sync), "Completato" if risultato.successo else ("Annullato" if risultato.annullato else "Completato con problemi"))  # Conserva percentuale e stato finale.
        eliminazioni_visualizzate = len(risultato.manifesto.eliminati) if sezione == "strategie" and risultato.manifesto is not None else risultato.file_eliminati  # Per i backup versionati conta i tombstone del manifesto; per Mirror mantiene le cancellazioni fisiche.
        self._aggiungi_attivita_avanzata(sezione, f"[FINE] File copiati: {risultato.file_copiati}; {'eliminazioni registrate' if sezione == 'strategie' else 'file eliminati'}: {eliminazioni_visualizzate}; errori: {len(risultato.errori)}.")  # Registra il riepilogo con la semantica corretta per ciascuna strategia.
        stato_record = "annullato" if risultato.annullato else ("successo" if risultato.successo else "problemi")  # Traduce l'esito nel vocabolario persistente.
        problemi = tuple(risultato.errori)  # Congela gli errori per il record strutturato.
        self.registra_cronologia(crea_record_operazione(tipo_record, stato_record, descrizione, risultato.file_copiati, 0, len(risultato.errori), risultato.byte_copiati, problemi))  # Conserva contatori e diagnostica nella cronologia esistente.
        etichetta_eliminazioni = "Eliminazioni registrate" if sezione == "strategie" else "File eliminati"  # Distingue le tombstone versionate dalle cancellazioni fisiche Mirror.
        riepilogo = f"{titolo}\n\nFile copiati: {risultato.file_copiati}\n{etichetta_eliminazioni}: {eliminazioni_visualizzate}\nByte copiati: {risultato.byte_copiati:,}\nErrori: {len(risultato.errori)}"  # Costruisce un riepilogo basato esclusivamente sui contatori reali.
        if self.sezione_attiva == "strategie" and hasattr(self, "pulsante_avvia_strategia") and self.pulsante_avvia_strategia.winfo_exists():  # Aggiorna soltanto widget ancora appartenenti alla vista attiva.
            self.pulsante_avvia_strategia.configure(state="normal", text="▶ Avvia strategia")  # Riabilita il comando dopo il worker e ripristina l’etichetta.
            self.etichetta_stato_strategia.configure(text="Completato" if risultato.successo else "Completato con problemi")  # Mostra l'esito sintetico.
        if self.sezione_attiva == "sincronizza" and hasattr(self, "pulsante_avvia_sync") and self.pulsante_avvia_sync.winfo_exists():  # Aggiorna la vista sincronizzazione quando ancora presente.
            self.pulsante_avvia_sync.configure(state="normal", text="▶ Avvia sincronizzazione")  # Riabilita il comando principale e ripristina l’etichetta.
            self.etichetta_stato_sync.configure(text="Completato" if risultato.successo else "Completato con problemi")  # Mostra l'esito sintetico.
        if risultato.successo:  # Usa un popup informativo soltanto per un successo pieno.
            messagebox.showinfo(titolo, riepilogo, parent=self)  # Mostra il riepilogo nel thread Tk.
        else:  # Annullamento ed errori richiedono un avviso prudente.
            messagebox.showwarning(titolo, riepilogo, parent=self)  # Non dichiara successo quando l'operazione è incompleta.

    def gestisci_ripristino_avanzato_completato(self, risultato) -> None:
        """Registra e presenta l'esito del ripristino versionato nel thread della GUI."""
        self.rilascia_blocco_operazione_manuale()  # Rilascia il lock operativo condiviso.
        self.operazione_avanzata_in_corso = ""  # Chiude il lifecycle del ripristino nel thread Tk.
        self.progresso_ripristino_versionato = 1.0 if risultato.successo else self.progresso_ripristino_versionato  # Porta a 100% soltanto un esito completo.
        self.stato_ripristino_versionato = "Completato" if risultato.successo else ("Annullato" if risultato.annullato else "Completato con problemi")  # Conserva l’esito durante la navigazione.
        self._aggiungi_attivita_ripristino_versionato(f"[FINE] Ripristinati: {risultato.file_ripristinati}; ignorati: {risultato.file_ignorati}; errori: {len(risultato.errori)}.")  # Mantiene il riepilogo finché l’utente non lo cancella.
        stato_record = "annullato" if risultato.annullato else ("successo" if risultato.successo else "problemi")  # Traduce lo stato del motore.
        self.registra_cronologia(crea_record_operazione("ripristino_versionato", stato_record, "Ripristino versione", risultato.file_ripristinati, risultato.file_ignorati, len(risultato.errori), risultato.byte_ripristinati, tuple(risultato.errori)))  # Integra il nuovo ripristino nella cronologia storica.
        if self.sezione_attiva == "ripristino_versionato" and hasattr(self, "pulsante_ripristina_versione") and self.pulsante_ripristina_versione.winfo_exists():  # Verifica che il pannello esista ancora.
            self.pulsante_ripristina_versione.configure(state="normal", text="↶ Ripristina versione")  # Riabilita il comando di ripristino e ripristina l’etichetta.
            self.barra_ripristino_versionato.set(self.progresso_ripristino_versionato)  # Allinea la barra al valore finale.
            self.percentuale_ripristino_versionato.configure(text=f"{int(self.progresso_ripristino_versionato * 100)}%")  # Allinea la percentuale finale.
            self.etichetta_stato_ripristino_versionato.configure(text=self.stato_ripristino_versionato)  # Mostra l’esito finale.
        riepilogo = f"Ripristino versionato\n\nFile ripristinati: {risultato.file_ripristinati}\nFile ignorati: {risultato.file_ignorati}\nByte ripristinati: {risultato.byte_ripristinati:,}\nErrori: {len(risultato.errori)}"  # Usa soltanto dati prodotti dal motore.
        if risultato.successo:  # Distingue il successo pieno dagli esiti incompleti.
            messagebox.showinfo("Ripristino versionato", riepilogo, parent=self)  # Mostra il riepilogo positivo.
        else:  # Errori o annullamento richiedono un avviso.
            messagebox.showwarning("Ripristino versionato", riepilogo, parent=self)  # Evita di mascherare problemi.

    def gestisci_errore_operazione_avanzata(self, titolo: str, errore: str) -> None:
        """Rilascia il lock e presenta un errore fatale proveniente da un worker avanzato."""
        self.rilascia_blocco_operazione_manuale()  # Garantisce che un errore non lasci il lock operativo occupato.
        sezione = self.operazione_avanzata_in_corso or ("strategie" if "Strategia" in titolo else "sincronizza")  # Recupera il monitor che possiede l'operazione fallita.
        self.operazione_avanzata_in_corso = ""  # Chiude il lifecycle anche quando il backend solleva un'eccezione.
        if sezione in {"strategie", "sincronizza"}:  # Aggiorna soltanto monitor avanzati riconosciuti.
            self._aggiorna_progresso_avanzato(sezione, self.progresso_strategia if sezione == "strategie" else self.progresso_sync, "Errore")  # Mantiene la percentuale raggiunta e segnala il fallimento.
            self._aggiungi_attivita_avanzata(sezione, f"[ERRORE] {errore}")  # Conserva la diagnostica anche dopo un cambio menu.
        if sezione == "ripristino_versionato":  # Gestisce separatamente il monitor del recupero di catena.
            self.progresso_ripristino_versionato = 0.0  # Un errore fatale precedente all'avvio non deve lasciare visibile il 100% di un'operazione precedente.
            self.stato_ripristino_versionato = "Errore"  # Conserva lo stato anche se la pagina non è visibile.
            self._aggiungi_attivita_ripristino_versionato(f"[ERRORE] {errore}")  # Conserva la diagnostica fino a cancellazione esplicita.
            if self.sezione_attiva == "ripristino_versionato" and hasattr(self, "pulsante_ripristina_versione") and self.pulsante_ripristina_versione.winfo_exists():  # Aggiorna soltanto widget vivi.
                self.pulsante_ripristina_versione.configure(state="normal", text="↶ Ripristina versione")  # Riabilita il comando dopo l'errore.
                self.barra_ripristino_versionato.set(0.0)  # Riallinea visivamente la barra allo stato di errore.
                self.percentuale_ripristino_versionato.configure(text="0%")  # Evita la combinazione incoerente Errore + 100%.
                self.etichetta_stato_ripristino_versionato.configure(text="Errore")  # Mostra l'esito senza perdere la pagina.
        self.registra_cronologia(crea_record_operazione("operazione_avanzata", "fallito", titolo, problemi=(errore,)))  # Conserva il fallimento nella cronologia.
        messagebox.showerror(titolo, errore, parent=self)  # Mostra la diagnostica nel thread GUI.

    def aggiorna_home(self) -> None:
        """Aggiorna la Home dopo la conclusione del callback del pulsante, senza distruggere la vista che lo sta eseguendo."""
        if self.sezione_attiva != "home":  # Evita aggiornamenti tardivi se l'utente ha già cambiato sezione.
            return  # Non modifica una vista che non è più attiva.
        pannello = getattr(self, "pannello_sezione", None)  # Recupera la Home attualmente visibile.
        if pannello is None or not pannello.winfo_exists():  # Verifica che il contenitore sia ancora valido.
            return  # Evita operazioni su widget già distrutti.
        for widget in pannello.winfo_children():  # Scorre soltanto i contenuti interni della Home.
            widget.destroy()  # Elimina i dati visuali precedenti senza distruggere il contenitore attivo.
        self._crea_banner_globale_sola_lettura(pannello)  # Ricrea anche il banner globale eliminato dal refresh della Home.
        self.crea_home(pannello)  # Ricostruisce i dati aggiornati nello stesso pannello stabile.

    def crea_home(self, contenitore) -> None:
        """Costruisce la dashboard con unità Windows, selezione rapida e cronologia strutturata."""
        comandi_home = ctk.CTkFrame(contenitore, fg_color="transparent")  # Crea una sola riga compatta per i comandi della Home senza aggiungere un titolo ridondante sotto il banner.
        comandi_home.pack(fill="x", padx=18, pady=(10, 8))  # Mantiene la riga allineata al contenuto e lascia libero lo spazio a sinistra.
        ctk.CTkButton(comandi_home, text="↻ Aggiorna", width=110, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=lambda: self.after_idle(self.aggiorna_home)).pack(side="right", padx=(8, 0))  # Mantiene Aggiorna compatto sul margine destro.
        ctk.CTkButton(comandi_home, text="Rimuovi banner", width=130, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.rimuovi_banner).pack(side="right", padx=(8, 0))  # Mantiene il comando di rimozione separato senza espanderlo.
        ctk.CTkButton(comandi_home, text="Scegli banner", width=120, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.cambia_banner).pack(side="right")  # Mantiene il comando di scelta compatto e allineato agli altri due.
        ctk.CTkLabel(contenitore, text="Dischi e unità disponibili", font=ctk.CTkFont(size=20, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(8, 4))  # Introduce la sezione dischi.
        ctk.CTkLabel(contenitore, text="Le unità vengono lette direttamente da Windows. Sorgente e destinazione si configurano nella sezione Backup.", text_color=COLORE_TESTO_TERZIARIO, anchor="w").pack(fill="x", padx=18, pady=(0, 10))  # Chiarisce l'effetto dei pulsanti.
        try:  # Isola anche un eventuale errore globale di enumerazione delle unità.
            unita = rileva_unita_windows()  # Recupera lettere e spazio tramite la libreria standard.
        except OSError as errore:  # Gestisce piattaforma non supportata o errore di Windows.
            unita = []  # Mantiene la dashboard utilizzabile per la cronologia.
            ctk.CTkLabel(contenitore, text=f"Unità non disponibili: {errore}", text_color="#F0A04B", anchor="w").pack(fill="x", padx=18, pady=8)  # Mostra il problema senza crash.
        for informazioni in unita:  # Crea una scheda indipendente per ogni lettera restituita da Windows.
            scheda = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA_ALTERNATIVA, border_width=1, border_color=COLORE_BORDO)  # Crea la card dell'unità.
            scheda.pack(fill="x", padx=18, pady=6)  # Dispone verticalmente le unità per una lettura simile a Esplora file.
            riga = ctk.CTkFrame(scheda, fg_color="transparent")  # Crea la riga con nome e azioni.
            riga.pack(fill="x", padx=14, pady=(12, 6))  # Mantiene margini interni uniformi.
            ctk.CTkLabel(riga, text=f"▰  Unità {informazioni.percorso}", font=ctk.CTkFont(size=17, weight="bold")).pack(side="left")  # Mostra la radice senza inventare etichette volume.
            if informazioni.accessibile:  # Mostra statistiche soltanto quando disk_usage è riuscito.
                ctk.CTkLabel(scheda, text=f"Usato {formatta_dimensione(informazioni.usato)} di {formatta_dimensione(informazioni.totale)}   •   Libero {formatta_dimensione(informazioni.libero)}", text_color=COLORE_TESTO_DETTAGLI, anchor="w").pack(fill="x", padx=14)  # Mostra misure binarie coerenti.
                colore_barra = COLORE_BARRA_CRITICA if informazioni.frazione_utilizzata >= SOGLIA_SPAZIO_CRITICO else COLORE_BARRA_NORMALE  # Usa il rosso soltanto dal 90% di utilizzo in su.
                barra = ctk.CTkProgressBar(scheda, height=12, progress_color=colore_barra)  # Crea la barra con stato cromatico esplicito e testabile.
                barra.pack(fill="x", padx=14, pady=(7, 14))  # Estende la barra lungo la card.
                barra.set(informazioni.frazione_utilizzata)  # Imposta una frazione già limitata tra zero e uno.
            else:  # Gestisce supporti assenti, reti scollegate o permessi insufficienti.
                ctk.CTkLabel(scheda, text=f"Non accessibile • {informazioni.errore}", text_color="#F0A04B", anchor="w").pack(fill="x", padx=14, pady=(0, 14))  # Mantiene visibile il motivo diagnostico.
        riga_cronologia = ctk.CTkFrame(contenitore, fg_color="transparent")  # Raggruppa il titolo della cronologia e il comando di cancellazione senza alterare le card.
        riga_cronologia.pack(fill="x", padx=18, pady=(22, 6))  # Mantiene la stessa spaziatura verticale usata in precedenza dal titolo.
        ctk.CTkLabel(riga_cronologia, text="Attività recenti", font=ctk.CTkFont(size=20, weight="bold"), anchor="w").pack(side="left", fill="x", expand=True)  # Introduce la cronologia persistente.
        ctk.CTkButton(riga_cronologia, text="Cancella attività", width=130, fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.cancella_cronologia_utente).pack(side="right")  # Offre anche dalla Home il controllo esplicito sulla cronologia persistente.
        try:  # Protegge la Home da un eventuale file cronologia corrotto.
            cronologia = carica_cronologia(FILE_CRONOLOGIA)  # Legge i record strutturati senza analizzare il log testuale.
        except ValueError as errore:  # Riconosce esplicitamente la corruzione.
            cronologia = []  # Evita di inventare dati storici.
            ctk.CTkLabel(contenitore, text=f"Cronologia non leggibile: {errore}", text_color="#F0A04B", anchor="w").pack(fill="x", padx=18, pady=6)  # Informa l'utente del problema.
        if not cronologia:  # Gestisce un'applicazione senza esecuzioni registrate.
            ctk.CTkLabel(contenitore, text="Nessuna operazione registrata. I nuovi backup e ripristini compariranno qui.", text_color=COLORE_TESTO_TERZIARIO, anchor="w").pack(fill="x", padx=18, pady=(2, 18))  # Mostra uno stato vuoto esplicito.
        for record in reversed(cronologia[-10:]):  # Mostra prima gli ultimi dieci eventi per non sovraccaricare la dashboard.
            scheda = ctk.CTkFrame(contenitore, corner_radius=12, fg_color=COLORE_SCHEDA_ALTERNATIVA)  # Crea la card del record.
            scheda.pack(fill="x", padx=18, pady=5)  # Dispone la cronologia verticalmente.
            simbolo = "✓" if record.stato == "successo" else "■" if record.stato == "annullato" else "!"  # Usa un indicatore semplice senza dipendenze grafiche.
            ctk.CTkLabel(scheda, text=f"{simbolo}  {record.descrizione}", font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(fill="x", padx=14, pady=(10, 2))  # Mostra esito e descrizione.
            ctk.CTkLabel(scheda, text=f"{record.timestamp.replace('T', ' ')}  •  Stato: {record.stato}  •  Copiati: {record.file_copiati}  •  Identici: {record.file_ignorati}  •  Falliti: {record.file_falliti}  •  Dati: {formatta_dimensione(record.byte_copiati)}", text_color=COLORE_TESTO_DETTAGLI, anchor="w").pack(fill="x", padx=14, pady=(0, 4))  # Mostra i contatori principali.
            if record.problemi:  # Mostra un'anteprima dei problemi quando presenti.
                ctk.CTkLabel(scheda, text="Problemi: " + " | ".join(record.problemi[:3]), text_color="#F0A04B", anchor="w", justify="left", wraplength=850).pack(fill="x", padx=14, pady=(0, 10))  # Limita la card ai primi tre messaggi.
            else:  # Mantiene una spaziatura coerente anche senza errori.
                ctk.CTkLabel(scheda, text="Nessun problema registrato", text_color="#6FAE83", anchor="w").pack(fill="x", padx=14, pady=(0, 10))  # Conferma l'assenza di problemi.

    def usa_unita_backup(self, percorso: str, come_sorgente: bool) -> None:
        """Precompila il backup singolo con l'unità scelta e porta l'utente alla sezione Backup."""
        self.mostra_sezione("backup")  # Rende visibili i campi operativi senza avviare alcun worker.
        campo = self.campo_sorgente if come_sorgente else self.campo_destinazione  # Seleziona il campo richiesto dal pulsante.
        campo.delete(0, "end")  # Rimuove il valore precedente.
        campo.insert(0, percorso)  # Inserisce la radice dell'unità scelta.
        self.etichetta_stato.configure(text="Unità selezionata: scegli l'altro percorso e avvia quando sei pronto")  # Conferma che è avvenuta soltanto una selezione.

    def crea_impostazioni(self, contenitore) -> None:
        """Mostra esclusivamente impostazioni globali dell'applicazione."""
        ctk.CTkLabel(contenitore, text="Impostazioni", font=ctk.CTkFont(size=26, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 4))  # Mostra il titolo.
        ctk.CTkLabel(contenitore, text="Preferenze globali dell'interfaccia. Le opzioni dei backup restano associate ai singoli job.", text_color=COLORE_TESTO_TERZIARIO, anchor="w").pack(fill="x", padx=18, pady=(0, 14))  # Separa correttamente impostazioni globali e job.
        scheda_tema = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA_ALTERNATIVA)  # Crea la scheda del tema.
        scheda_tema.pack(fill="x", padx=18, pady=6)  # Posiziona la scheda.
        ctk.CTkLabel(scheda_tema, text="Aspetto", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 6))  # Introduce la preferenza.
        tema_corrente = self.configurazione.get("tema_interfaccia", "dark")  # Recupera il valore persistito.
        self.variabile_tema = ctk.StringVar(value=tema_corrente if tema_corrente in {"dark", "light", "system"} else "dark")  # Crea una variabile valida per il menu.
        ctk.CTkOptionMenu(scheda_tema, values=["dark", "light", "system"], variable=self.variabile_tema, command=self.salva_tema_interfaccia).pack(anchor="w", padx=14, pady=(0, 14))  # Permette di cambiare e salvare subito il tema.
        scheda_avvio = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA_ALTERNATIVA)  # Crea la scheda dedicata all'integrazione con l'accesso Windows.
        scheda_avvio.pack(fill="x", padx=18, pady=6)  # Posiziona la preferenza separatamente dalle opzioni puramente grafiche.
        ctk.CTkLabel(scheda_avvio, text="Avvio con Windows", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 4))  # Introduce la preferenza di esecuzione automatica.
        ctk.CTkLabel(scheda_avvio, text="FDBackup verrà avviato all’accesso di Windows e resterà disponibile anche nell’area di notifica.", text_color=COLORE_TESTO_TERZIARIO, anchor="w").pack(fill="x", padx=14, pady=(0, 6))  # Spiega l'effetto senza suggerire un servizio di sistema inesistente.
        stato_avvio = avvio_automatico_attivo()  # Legge lo stato reale dell'attività Windows invece di fidarsi soltanto del file JSON.
        self.variabile_avvio_automatico = ctk.BooleanVar(value=stato_avvio)  # Collega il controllo grafico allo stato effettivamente rilevato.
        ctk.CTkCheckBox(scheda_avvio, text="Avvia FDBackup con Windows", variable=self.variabile_avvio_automatico, command=self.cambia_avvio_automatico).pack(anchor="w", padx=14, pady=(4, 14))  # Permette di creare o rimuovere l'attività ONLOGON.
        scheda_utilita = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA_ALTERNATIVA)  # Crea la scheda delle utilità globali.
        scheda_utilita.pack(fill="x", padx=18, pady=6)  # Posiziona la scheda.
        ctk.CTkLabel(scheda_utilita, text="Diagnostica", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 8))  # Introduce i comandi globali.
        riga = ctk.CTkFrame(scheda_utilita, fg_color="transparent")  # Raggruppa i pulsanti.
        riga.pack(fill="x", padx=14, pady=(0, 14))  # Posiziona i comandi.
        ctk.CTkButton(riga, text="Apri file di log", fg_color=COLORE_PULSANTE_SECONDARIO, hover_color=COLORE_PULSANTE_SECONDARIO_HOVER, text_color=COLORE_TESTO_PULSANTE, command=self.apri_file_log).pack(side="left", padx=6)  # Usa lo stesso stile primario di Cambia banner per rendere evidente l’accesso alla diagnostica persistente.

    def cambia_avvio_automatico(self) -> None:
        """Applica la preferenza di avvio Windows e salva la configurazione soltanto dopo un'operazione riuscita."""
        richiesto = bool(self.variabile_avvio_automatico.get())  # Legge il nuovo stato scelto dall'utente nel controllo grafico.
        try:  # Protegge la GUI da errori di Task Scheduler, permessi o percorsi non validi.
            if richiesto:  # Distingue la creazione dalla rimozione dell'attività Windows.
                abilita_avvio_automatico(Path(__file__).resolve())  # Registra il file principale corrente con un percorso assoluto stabile.
            else:  # Gestisce la scelta esplicita di non avviare FDBackup al login.
                disabilita_avvio_automatico()  # Rimuove soltanto l'attività dedicata a FDBackup.
        except OSError as errore:  # Intercetta esclusivamente problemi previsti dell'integrazione Windows.
            self.variabile_avvio_automatico.set(not richiesto)  # Ripristina il controllo allo stato precedente perché la modifica non è stata applicata.
            messagebox.showerror("Avvio con Windows", str(errore), parent=self)  # Comunica il motivo senza alterare altre impostazioni.
            return  # Evita di persistere nel JSON uno stato diverso da quello reale.
        self.configurazione["avvio_automatico_windows"] = richiesto  # Conserva anche la preferenza per finalità diagnostiche e future migrazioni.
        self.salva_configurazione()  # Riusa la scrittura atomica già verificata del progetto.

    def cancella_cronologia_utente(self) -> None:
        """Cancella soltanto cronologia.json dopo conferma e riallinea immediatamente le viste della GUI."""
        conferma = messagebox.askyesno("Cancella cronologia", "Vuoi cancellare tutta la cronologia delle operazioni?\n\nConfigurazione, pianificazioni, stato dello scheduler, log e file di backup non verranno modificati.", parent=self)  # Chiede una conferma esplicita descrivendo con precisione l'ambito della cancellazione.
        if not conferma:  # Riconosce l'annullamento dell'utente.
            return  # Mantiene intatti file e interfaccia.
        try:  # Isola eventuali problemi di accesso al solo file della cronologia.
            cancella_cronologia(FILE_CRONOLOGIA)  # Delega al modulo dedicato l'eliminazione esclusiva di cronologia.json.
        except OSError as errore:  # Gestisce file bloccato, permessi o altri errori filesystem.
            messagebox.showerror("Cancella cronologia", f"Impossibile cancellare la cronologia:\n{errore}", parent=self)  # Informa l'utente senza modificare lo stato visualizzato.
            return  # Interrompe l'aggiornamento perché la cancellazione non è riuscita.
        self.firme_cronologia_visualizzate.clear()  # Dimentica le firme dei record che non esistono più sul disco.
        self.firma_file_cronologia = self._firma_file_cronologia_corrente()  # Allinea il polling alla nuova assenza del file.
        self.casella_log.configure(state="normal")  # Abilita temporaneamente il widget Attività per rimuovere lo storico già mostrato.
        self.casella_log.delete("1.0", "end")  # Elimina dalla vista i record storici e i messaggi della sessione già visualizzati.
        self.casella_log.configure(state="disabled")  # Ripristina immediatamente la modalità di sola lettura.
        self.aggiungi_log("Cronologia cancellata.")  # Conferma nella vista Attività l'azione appena completata senza ripersistirla.
        if self.sezione_attiva == "home":  # Verifica se la dashboard con le card storiche è attualmente visibile.
            self.aggiorna_home()  # Ricostruisce la Home mostrando subito lo stato vuoto della cronologia.

    def salva_tema_interfaccia(self, tema: str) -> None:
        """Applica e persiste il tema globale scelto dall'utente."""
        if tema not in {"dark", "light", "system"}:  # Difende la configurazione anche da chiamate non provenienti dal menu.
            return  # Ignora valori non supportati.
        ctk.set_appearance_mode(tema)  # Applica immediatamente il tema; i colori adattivi scelgono automaticamente la variante corretta.
        self.update_idletasks()  # Chiede a Tk di completare il ridisegno dei widget già esistenti prima di proseguire.
        self.configurazione["tema_interfaccia"] = tema  # Aggiorna soltanto la chiave globale dedicata.
        self.salva_configurazione()  # Riusa il salvataggio atomico già presente nel progetto.

    def apri_file_log(self) -> None:
        """Apre il log persistente con l'applicazione predefinita di Windows."""
        try:  # Protegge la GUI da errori di shell o file non disponibile.
            os.startfile(PERCORSO_LOG)  # Chiede a Windows di aprire il file con il programma associato.
        except (AttributeError, OSError) as errore:  # Gestisce piattaforma non Windows o problemi di apertura.
            messagebox.showerror("Log", f"Impossibile aprire il file di log:\n{errore}")  # Mostra il motivo senza terminare l'applicazione.

    def crea_informazioni(self, contenitore) -> None:
        """Mostra informazioni tecniche e limiti reali della versione di sviluppo."""
        ctk.CTkLabel(contenitore, text="Informazioni", font=ctk.CTkFont(size=26, weight="bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 6))  # Mostra il titolo.
        scheda = ctk.CTkFrame(contenitore, corner_radius=14, fg_color=COLORE_SCHEDA_ALTERNATIVA)  # Crea una card leggibile.
        scheda.pack(fill="x", padx=18, pady=6)  # Posiziona la card.
        testo = ("FDBackup • versione di sviluppo 0.1.0\n\n"
                 "Applicazione desktop Python per backup di file e cartelle, strategie versionate e ripristino conservativo.\n\n"
                 "Funzioni presenti: backup singolo, multi-sorgente e multi-job; Full versionato; Incrementale; Differenziale; rotazione automatica del Full; retention per catene; ripristino delle versioni; Update; Mirror con conferma esplicita; SHA-256; Stop cooperativo; logging persistente; scheduler storico; avvio automatico Windows; dashboard dischi; cronologia strutturata e aggiornamento live delle attività.\n\n"
                 "Limiti attuali: le nuove strategie versionate e la sincronizzazione sono disponibili manualmente ma non sono ancora collegate allo scheduler automatico; shutil.copy2 non conserva tutti i metadati NTFS come ACL, proprietario e Alternate Data Streams; non sono ancora presenti VSS nativo, imaging di disco/partizione, cifratura o compressione degli archivi.")  # Descrive soltanto capacità e limiti realmente presenti in questo checkpoint.
        ctk.CTkLabel(scheda, text=testo, justify="left", anchor="w", wraplength=850, font=ctk.CTkFont(size=14)).pack(fill="x", padx=18, pady=18)  # Mostra il testo con ritorno a capo responsivo.

    def registra_cronologia(self, record) -> None:
        """Persistisce un record operativo senza trasformare un problema di cronologia in un fallimento del backup."""
        try:  # Isola completamente la telemetria locale dal risultato dell'operazione principale.
            aggiungi_record(FILE_CRONOLOGIA, record)  # Aggiunge il record con scrittura atomica e limite massimo.
        except (OSError, TypeError, ValueError) as errore:  # Gestisce file non scrivibile o cronologia già corrotta.
            logger.error("Impossibile aggiornare la cronologia delle operazioni: %s", errore)  # Conserva il problema nel log diagnostico.

    def cambia_modalita(self, modalita: str, forza: bool = False) -> None:
        """Aggiorna la GUI per lavorare in modalità backup oppure ripristino senza avviare operazioni."""
        if modalita not in ("backup", "ripristino"):  # Accetta soltanto le due modalità realmente implementate.
            return  # Ignora richieste provenienti da sezioni ancora puramente visive.
        if modalita == self.modalita_operazione and not forza:  # Riconosce il ritorno ordinario alla stessa vista dopo Home, Strategie o altri menu.
            return  # Conserva campi, stato, barra e Attività senza azzerare la sessione operativa.

        modalita_precedente = self.modalita_operazione  # Memorizza la vista che sta per essere nascosta.
        self.valori_modalita_operativa[modalita_precedente] = {"sorgente": self.campo_sorgente.get(), "destinazione": self.campo_destinazione.get(), "stato": self.etichetta_stato.cget("text")}  # Salva campi e stato prima di riutilizzare gli stessi widget.
        self.modalita_operazione = modalita  # Memorizza la modalità selezionata.
        for nome_pulsante, pulsante in self.pulsanti_navigazione.items():  # Aggiorna l'evidenziazione dei pulsanti della sidebar.
            attivo = (modalita == "backup" and nome_pulsante == "Backup") or (modalita == "ripristino" and nome_pulsante == "Ripristino")  # Determina quale voce deve risultare attiva.
            pulsante.configure(fg_color=COLORE_MENU_ATTIVO if attivo else COLORE_MENU_INATTIVO)  # Applica il colore attivo soltanto alla modalità corrente.

        self.campo_sorgente.delete(0, "end")  # Svuota la sorgente per evitare di riutilizzare accidentalmente un percorso con significato diverso.
        self.campo_destinazione.delete(0, "end")  # Svuota la destinazione per evitare operazioni involontarie dopo il cambio modalità.
        stato_salvato = self.valori_modalita_operativa.get(modalita, {})  # Recupera l'eventuale sessione precedente della vista richiesta.
        self.etichetta_stato.configure(text=stato_salvato.get("stato", "Pronto"))  # Ripristina lo stato della vista invece di azzerarlo durante la navigazione.

        if modalita == "backup":  # Configura testi e comandi visivi per il backup.
            self.intestazione_operativa.pack_forget()  # Rimuove temporaneamente il titolo per ripristinare l'ordine originale della vista Backup.
            self.intestazione_operativa.pack(fill="x", padx=18, pady=(16, 6), before=self.riquadro_banner)  # Mantiene Backup con titolo sopra il banner senza alterarne il layout già verificato.
            self.pulsante_torna_tipi_ripristino.pack_forget()  # Il ritorno ai tipi di ripristino non appartiene alla schermata Backup.
            self.scheda_job.pack(fill="x", padx=18, pady=8, before=self.scheda_configurazione)  # Rende visibile l’elenco multi-job soltanto nella modalità backup.
            self.etichetta_titolo.configure(text="Backup")  # Mostra il titolo della modalità backup.
            self.etichetta_sorgente.configure(text="▰  Cartella sorgente")  # Descrive la cartella da proteggere.
            self.etichetta_destinazione.configure(text="▰  Cartella destinazione")  # Descrive la cartella che riceverà il backup.
            self.etichetta_opzioni.configure(text="Opzioni di backup")  # Mantiene il titolo coerente con il backup.
            self.etichetta_descrizione_opzioni.configure(text="Le opzioni configurabili vengono salvate separatamente per ogni job.")  # Spiega che le opzioni operative appartengono ai job persistenti.
            self.scheda_pianificazione_singola.pack(fill="x", padx=18, pady=(0, 16))  # Rende disponibile la pianificazione del backup singolo nella modalità corretta.
            self.campo_sorgente.insert(0, stato_salvato.get("sorgente", self.backup_singolo["sorgente"]))  # Ripristina prima la sessione corrente e usa la configurazione persistita soltanto al primo accesso.
            self.campo_destinazione.insert(0, stato_salvato.get("destinazione", self.backup_singolo["destinazione"]))  # Conserva la destinazione anche dopo aver visitato Ripristino.
            self.pulsante_avvia.configure(text="▶   Avvia backup")  # Aggiorna il comando principale per il backup.
        else:  # Configura testi e comandi visivi per il ripristino.
            self.intestazione_operativa.pack_forget()  # Rimuove il titolo dalla posizione precedente al banner.
            self.intestazione_operativa.pack(fill="x", padx=18, pady=(10, 4), after=self.etichetta_info_banner)  # Nel tradizionale colloca il titolo sotto il banner, come nella pagina di ripristino versionato.
            self.pulsante_torna_tipi_ripristino.pack_forget()  # Evita duplicazioni di geometria quando si rientra più volte nel ripristino tradizionale.
            self.pulsante_torna_tipi_ripristino.pack(anchor="w", padx=18, pady=(0, 10), after=self.intestazione_operativa)  # Colloca il ritorno subito sotto il titolo e quindi sotto il banner, replicando l'ordine del ripristino versionato.  # Mostra nel tradizionale il pulsante compatto con lo stesso allineamento e le stesse dimensioni naturali usate nel ripristino versionato.
            self.scheda_job.pack_forget()  # Nasconde i job di backup quando la schermata assume il significato di ripristino.
            self.etichetta_titolo.configure(text="Ripristino")  # Mostra chiaramente che l'utente sta lavorando nel ripristino.
            self.etichetta_sorgente.configure(text="▰  Cartella di backup")  # Identifica la sorgente come backup da cui recuperare i dati.
            self.etichetta_destinazione.configure(text="▰  Destinazione ripristino")  # Identifica la cartella nella quale recuperare i dati.
            self.etichetta_opzioni.configure(text="Politica di ripristino")  # Introduce il comportamento conservativo del motore.
            self.etichetta_descrizione_opzioni.configure(text="Ripristino conservativo: i file differenti già presenti non vengono sovrascritti.")  # Esplicita la protezione fondamentale del motore.
            self.scheda_pianificazione_singola.pack_forget()  # Nasconde i controlli di pianificazione perché non appartengono al flusso di ripristino.
            self.campo_sorgente.insert(0, stato_salvato.get("sorgente", ""))  # Ripristina la cartella di backup storica scelta in precedenza.
            self.campo_destinazione.insert(0, stato_salvato.get("destinazione", ""))  # Ripristina la destinazione storica scelta in precedenza.
            self.pulsante_avvia.configure(text="↶   Avvia ripristino")  # Aggiorna il comando principale per il ripristino.

    def avvia_operazione(self) -> None:
        """Avvia il worker corrispondente alla modalità attualmente selezionata."""
        if self.modalita_operazione == "ripristino":  # Controlla se l'utente ha selezionato il ripristino.
            self.avvia_thread_ripristino()  # Delega l'avvio alla procedura specifica del ripristino.
        else:  # Usa il backup come modalità predefinita.
            percorso_singolo_presente = bool(self.campo_sorgente.get().strip() or self.campo_destinazione.get().strip())  # Riconosce l'intenzione esplicita di usare la sezione Sorgente e destinazione.
            if percorso_singolo_presente:  # Dà priorità al backup singolo quando l'utente ha compilato almeno uno dei due campi dedicati.
                self.avvia_thread_backup()  # Avvia soltanto la coppia sorgente-destinazione mostrata nella sezione singola.
            elif self.job_backup:  # Usa i job persistenti quando la sezione singola è vuota.
                self.avvia_thread_backup_multiplo()  # Avvia sequenzialmente tutti i job abilitati tramite il coordinatore.
            else:  # Mantiene il comportamento di errore del backup singolo quando non esiste alcuna configurazione disponibile.
                self.avvia_thread_backup()  # Delega alla validazione già esistente dei campi mancanti.

    def ferma_operazione(self) -> None:
        """Richiede l'arresto cooperativo del worker attualmente in esecuzione."""
        if self.thread_ripristino is not None and self.thread_ripristino.is_alive():  # Controlla prima se è attivo un ripristino.
            self.ferma_ripristino()  # Inoltra lo Stop al ripristino.
        elif self.thread_backup is not None and self.thread_backup.is_alive():  # Controlla altrimenti se è attivo un backup.
            self.ferma_backup()  # Inoltra lo Stop al backup.

    def aggiungi_log(self, testo: str) -> None:
        """Aggiunge una riga alla casella delle attività mantenendola non modificabile dall'utente."""
        self.casella_log.configure(state="normal")  # Abilita temporaneamente la modifica del widget.
        self.casella_log.insert("end", testo + "\n")  # Inserisce il nuovo messaggio alla fine del log.
        self.casella_log.see("end")  # Scorre automaticamente fino all'ultima riga.
        self.casella_log.configure(state="disabled")  # Ripristina la modalità di sola lettura.

    @staticmethod
    def _firma_record_cronologia(record) -> tuple:
        """Costruisce una firma immutabile sufficiente a riconoscere un record già mostrato nella sessione corrente."""
        return (record.timestamp, record.tipo, record.stato, record.descrizione, record.file_copiati, record.file_ignorati, record.file_falliti, record.byte_copiati, record.problemi)  # Include tutti i dati persistiti per evitare collisioni tra operazioni dello stesso secondo.

    @staticmethod
    def _formatta_record_attivita(record) -> str:
        """Trasforma un record persistente in un riepilogo completo e leggibile per lo specchietto Attività."""
        timestamp = record.timestamp.replace("T", " ")  # Rende il timestamp ISO più leggibile senza perdere data, ora e fuso.
        problemi = "Nessuno" if not record.problemi else " | ".join(record.problemi)  # Mantiene tutti i problemi disponibili nel record, non soltanto un'anteprima.
        return (f"[{timestamp}] {record.descrizione} • Stato: {record.stato}\n"
                f"  File copiati: {record.file_copiati} • File identici: {record.file_ignorati} • File falliti: {record.file_falliti} • Dati copiati: {formatta_dimensione(record.byte_copiati)}\n"
                f"  Problemi: {problemi}")  # Restituisce tre righe compatte ma complete per ogni operazione conclusa.

    def _firma_file_cronologia_corrente(self):
        """Restituisce una firma economica del file cronologia oppure None quando il file non esiste ancora."""
        try:  # Legge soltanto metadati, senza aprire il JSON a ogni polling.
            statistiche = FILE_CRONOLOGIA.stat()  # Recupera stato del file sostituito atomicamente dal writer.
            return statistiche.st_mtime_ns, statistiche.st_size  # Combina timestamp ad alta risoluzione e dimensione per rilevare le modifiche.
        except FileNotFoundError:  # Gestisce normalmente il primo avvio senza cronologia.
            return None  # Rappresenta l'assenza del file senza generare errori grafici.
        except OSError as errore:  # Isola problemi temporanei del filesystem dal ciclo grafico.
            logger.warning("Impossibile leggere i metadati della cronologia: %s", errore)  # Conserva la diagnostica nel log persistente.
            return self.firma_file_cronologia  # Mantiene la firma precedente per riprovare al controllo successivo.

    def carica_attivita_persistente(self) -> None:
        """Carica nello specchietto Attività tutta la cronologia persistita disponibile, fino al limite strutturale di cento record."""
        try:  # Protegge l'avvio della GUI da un file cronologia corrotto o temporaneamente illeggibile.
            cronologia = carica_cronologia(FILE_CRONOLOGIA)  # Riusa il parser validato e non analizza mai il log testuale.
        except ValueError as errore:  # Riconosce esplicitamente una cronologia non valida.
            self.aggiungi_log(f"[CRONOLOGIA] Impossibile leggere lo storico: {errore}")  # Rende il problema visibile senza inventare record.
            self.firma_file_cronologia = self._firma_file_cronologia_corrente()  # Evita di ripetere lo stesso messaggio a ogni polling finché il file non cambia.
            return  # Mantiene la GUI pienamente utilizzabile.
        for record in cronologia:  # Mantiene l'ordine cronologico dal più vecchio al più recente.
            firma = self._firma_record_cronologia(record)  # Costruisce l'identità completa del record.
            if firma in self.firme_cronologia_visualizzate:  # Evita duplicati durante i refresh successivi.
                continue  # Passa direttamente al record successivo.
            self.aggiungi_log(self._formatta_record_attivita(record))  # Mostra tutte le informazioni persistite dell'operazione.
            self.firme_cronologia_visualizzate.add(firma)  # Marca il record soltanto dopo averlo inserito nella GUI.
        self.firma_file_cronologia = self._firma_file_cronologia_corrente()  # Memorizza la versione appena letta del file.

    def controlla_cronologia_esterna(self) -> None:
        """Rileva senza bloccare la GUI i nuovi record scritti dal runner e aggiorna Attività e Home."""
        if self.chiusura_in_corso or not self.winfo_exists():  # Evita di pianificare nuovo lavoro mentre la finestra sta terminando.
            return  # Interrompe definitivamente il polling durante la chiusura.
        firma_corrente = self._firma_file_cronologia_corrente()  # Controlla prima soltanto i metadati del file.
        if firma_corrente != self.firma_file_cronologia:  # Rilegge il JSON esclusivamente quando il file è cambiato.
            self.carica_attivita_persistente()  # Aggiunge allo specchietto soltanto i record non ancora visualizzati.
            if self.sezione_attiva == "home":  # Aggiorna anche le card della Home quando sono effettivamente visibili.
                self.after_idle(self.aggiorna_home)  # Ricostruisce la Home fuori dal callback corrente per evitare distruzioni durante l'evento.
        self.after(INTERVALLO_AGGIORNAMENTO_CRONOLOGIA_MS, self.controlla_cronologia_esterna)  # Pianifica il controllo successivo nel thread Tk.

    def scegli_cartella(self, campo: ctk.CTkEntry) -> None:
        """Apre la finestra di scelta directory e inserisce il percorso nel campo indicato."""
        percorso = filedialog.askdirectory()  # Mostra la finestra nativa per scegliere una directory.

        if percorso:  # Verifica che l'utente non abbia annullato la selezione.
            campo.delete(0, "end")  # Rimuove l'eventuale percorso precedente.
            campo.insert(0, percorso)  # Inserisce il nuovo percorso selezionato.

    # ========================================================
    # BACKUP THREAD
    # ========================================================

    def invia_evento(self, evento: str, dati: dict) -> None:
        """Inserisce nella coda thread-safe un evento prodotto dal motore di backup."""
        self.coda_eventi.put((evento, dati))  # Accoda l'evento senza modificare direttamente la GUI dal worker.

    def avvia_thread_backup_multiplo(self) -> None:
        """Avvia in un thread separato tutti i job persistenti abilitati usando il coordinatore multi-job."""
        if self.thread_backup is not None and self.thread_backup.is_alive():  # Impedisce una seconda esecuzione mentre il worker è già attivo.
            return  # Mantiene una sola operazione di backup alla volta.

        if not any(job.abilitato for job in self.job_backup):  # Controlla che almeno un job sia realmente eseguibile.
            messagebox.showwarning("Backup", "Non ci sono job di backup abilitati da eseguire.")  # Spiega perché non viene avviato alcun worker.
            return  # Lascia invariato lo stato della GUI.

        try:  # Esegue la stessa validazione globale del coordinatore prima di creare il thread.
            ValidatoreBackup.valida_job_multipli(self.job_backup)  # Blocca l'intera esecuzione se la configurazione corrente non è più valida.
        except (TypeError, ValueError) as errore:  # Gestisce sorgenti rimosse, destinazioni diventate file o altri conflitti sopravvenuti.
            messagebox.showerror("Configurazione non valida", str(errore))  # Mostra il messaggio prodotto dal validatore centrale.
            return  # Non modifica lo stato della GUI e non avvia copie parziali.

        if not self.acquisisci_blocco_operazione_manuale():  # Coordina il backup multi-job con l'eventuale scheduler automatico già attivo.
            return  # Rinuncia all'avvio senza modificare lo stato della GUI.

        self.evento_arresto.clear()  # Elimina un eventuale Stop rimasto dall'esecuzione precedente.
        self.pulsante_avvia.configure(state="disabled")  # Impedisce avvii concorrenti.
        self.pulsante_stop.configure(state="normal")  # Abilita lo Stop cooperativo condiviso dal coordinatore.
        self.etichetta_stato.configure(text="Backup multi-job in esecuzione...")  # Comunica il tipo di operazione corrente.
        self.barra_avanzamento.start()  # Avvia l'indicatore indeterminato.
        self.aggiungi_log("=== BACKUP MULTI-JOB AVVIATO ===")  # Separa nel log grafico la nuova esecuzione.

        self.thread_backup = threading.Thread(
            target=self.esegui_backup_multiplo_worker,
            daemon=False,
            name="ThreadBackupMultiplo",
        )  # Crea un worker non daemon, compatibile con la chiusura sicura già presente.
        self.thread_backup.start()  # Avvia il coordinatore senza bloccare il thread grafico.

    def esegui_backup_multiplo_worker(self) -> None:
        """Esegue il coordinatore fuori dal thread grafico e trasferisce tutti gli eventi tramite la coda."""
        coordinatore = CoordinatoreBackup(
            evento_arresto=self.evento_arresto,
            funzione_avanzamento=self.invia_evento_backup_multiplo,
        )  # Riutilizza lo stesso Event dello Stop e una callback che non tocca direttamente i widget.

        try:  # Protegge il worker da errori di validazione o altri errori non recuperabili.
            risultato = coordinatore.esegui(self.job_backup)  # Esegue i job abilitati in ordine sequenziale.
            self.coda_eventi.put(("backup_multiplo_completato", {"risultato": risultato}))  # Consegna alla GUI l'esito aggregato.
        except Exception as errore:  # Mantiene un'ultima barriera anche contro errori imprevisti nel worker.
            logger.exception("Errore fatale non gestito nel thread di backup multi-job.")  # Registra traceback e contesto nel log persistente.
            self.coda_eventi.put(
                (
                    "errore_fatale_backup_multiplo",
                    {"errore": f"{type(errore).__name__}: {errore}"},
                )
            )  # Invia l'errore alla GUI senza accedere ai widget dal thread secondario.

    def invia_evento_backup_multiplo(self, evento: str, dati: dict) -> None:
        """Inserisce nella coda thread-safe un evento prodotto dal coordinatore multi-job."""
        self.coda_eventi.put(("evento_backup_multiplo", {"evento": evento, "dati": dati}))  # Conserva nome evento e payload del coordinatore.

    def gestisci_evento_backup_multiplo(self, evento: str, dati: dict) -> None:
        """Traduce gli eventi del coordinatore in stato e messaggi dell'area Attività."""
        if evento == "inizio_esecuzione":  # Gestisce l'avvio globale dopo la validazione.
            self.aggiungi_log(f"Job abilitati: {dati['numero_job']}")  # Mostra quanti job verranno eseguiti.

        elif evento == "inizio_job":  # Gestisce l'avvio del singolo job.
            self.etichetta_stato.configure(text=f"Backup: {dati['nome_job']}")  # Mostra il job attualmente in esecuzione.
            self.aggiungi_log(f"[JOB] Avvio: {dati['nome_job']}")  # Registra il passaggio al job corrente.

        elif evento == "inizio_sorgente":  # Gestisce l'avvio della singola sorgente.
            self.aggiungi_log(f"[SORGENTE] {dati['sorgente']} → {dati['destinazione']}")  # Mostra la mappatura reale sorgente-destinazione.

        elif evento == "errore_fatale_sorgente":  # Gestisce un errore circoscritto a una sorgente.
            self.aggiungi_log(f"[ERRORE SORGENTE] {dati['nome_job']}: {dati['errore']}")  # Registra il problema senza interrompere artificialmente i job successivi.

        elif evento == "fine_job":  # Gestisce la conclusione di un job avviato.
            risultato_job = dati["risultato"]  # Recupera l'esito aggregato del job.
            stato_job = "OK" if risultato_job.successo else ("ANNULLATO" if risultato_job.annullato else "CON SEGNALAZIONI")  # Traduce l'esito in un testo sintetico.
            self.aggiungi_log(f"[JOB] Fine: {dati['nome_job']} — {stato_job}")  # Registra il risultato prima del job successivo.

        elif evento == "evento_motore":  # Gestisce gli eventi dettagliati inoltrati dal MotoreBackup.
            evento_motore = dati["evento_motore"]  # Recupera il tipo dell'evento originario.
            dati_motore = dati["dati_motore"]  # Recupera il payload originario del motore.

            if evento_motore == "file":  # Gestisce l'inizio dell'elaborazione di un file della sorgente corrente.
                self.etichetta_stato.configure(text=f"Elaborazione: {dati_motore['file']}")  # Mostra il percorso relativo comunicato realmente dal motore.
            elif evento_motore == "copiato":  # Gestisce un file copiato e verificato correttamente.
                self.aggiungi_log(f"[COPIATO] {dati_motore['file']}")  # Usa la chiave 'file' prevista dal contratto reale di MotoreBackup.
            elif evento_motore == "ignorato":  # Gestisce un file già identico nella destinazione.
                self.aggiungi_log(f"[GIÀ IDENTICO] {dati_motore['file']}")  # Usa la stessa chiave 'file' prodotta dal motore per i file ignorati.
            elif evento_motore == "cartella_creata":  # Gestisce una sottocartella creata dal motore.
                self.aggiungi_log(f"[CARTELLA CREATA] {dati_motore['cartella']}")  # Usa la chiave 'cartella' prevista dall'evento del motore.
            elif evento_motore == "cartella_esistente":  # Gestisce una sottocartella già presente nella destinazione.
                self.aggiungi_log(f"[CARTELLA ESISTENTE] {dati_motore['cartella']}")  # Registra la cartella senza trattarla come errore.
            elif evento_motore == "errore_cartella":  # Gestisce un errore recuperabile durante la preparazione di una cartella.
                self.aggiungi_log(f"[ERRORE CARTELLA] {dati_motore['errore']}")  # Riporta il messaggio diagnostico completo prodotto dal motore.
            elif evento_motore == "errore":  # Gestisce un errore recuperabile relativo a un singolo file.
                self.aggiungi_log(f"[ERRORE] {dati_motore['errore']}")  # Riporta il messaggio diagnostico originale del motore.
            elif evento_motore in ("inizio", "fine"):  # Riconosce gli eventi di delimitazione già rappresentati dagli eventi del coordinatore.
                pass  # Evita log duplicati senza alterare il flusso degli eventi o il risultato finale.

    def gestisci_completamento_backup_multiplo(self, risultato: RisultatoEsecuzioneBackup) -> None:
        """Ripristina i controlli e mostra un riepilogo che distingue esito delle sorgenti e stato globale dell'esecuzione."""
        self.rilascia_blocco_operazione_manuale()  # Rende disponibile il lock condiviso appena il worker manuale ha concluso.
        self.barra_avanzamento.stop()  # Ferma l'indicatore animato perché il coordinatore ha concluso l'esecuzione.
        self.barra_avanzamento.set(0)  # Riporta la barra allo stato iniziale dopo la conclusione del worker.
        self.pulsante_avvia.configure(state="normal")  # Permette all'utente di avviare una nuova operazione.
        self.pulsante_stop.configure(state="disabled")  # Disabilita Stop perché non esiste più un worker da arrestare.

        numero_job_avviati = len(risultato.risultati_job)  # Conta esclusivamente i job che il coordinatore ha effettivamente avviato.
        numero_sorgenti_avviate = risultato.sorgenti_eseguite  # Usa il contratto del coordinatore per contare le sorgenti effettivamente avviate.

        sorgenti_completate = sum(
            1
            for risultato_job in risultato.risultati_job
            for risultato_sorgente in risultato_job.risultati_sorgenti
            if risultato_sorgente.successo
        )  # Conta le sorgenti che hanno prodotto un risultato pienamente riuscito, anche se uno Stop globale è arrivato subito dopo.

        sorgenti_annullate = sum(
            1
            for risultato_job in risultato.risultati_job
            for risultato_sorgente in risultato_job.risultati_sorgenti
            if risultato_sorgente.annullato
        )  # Conta soltanto le sorgenti nelle quali il MotoreBackup ha realmente registrato un annullamento cooperativo.

        sorgenti_con_errori = sum(
            1
            for risultato_job in risultato.risultati_job
            for risultato_sorgente in risultato_job.risultati_sorgenti
            if not risultato_sorgente.successo and not risultato_sorgente.annullato
        )  # Separa gli errori reali dagli annullamenti, evitando di riunirli nella voce ambigua "segnalazioni".

        if risultato.annullato:  # Controlla per primo lo stato globale perché uno Stop può impedire l'avvio delle sorgenti successive.
            stato = "Backup multi-job annullato"  # Comunica chiaramente che l'esecuzione pianificata non è stata completata integralmente.
            stato_esecuzione = "ANNULLATA"  # Prepara una voce esplicita da mostrare sia nel log sia nel popup finale.
        elif risultato.successo:  # Verifica il successo pieno soltanto quando l'esecuzione non è stata annullata.
            stato = "Backup multi-job completato"  # Comunica che tutti i job e tutte le sorgenti avviate sono riusciti.
            stato_esecuzione = "COMPLETATA"  # Rende immediatamente leggibile lo stato globale nel riepilogo.
        else:  # Gestisce l'esecuzione terminata senza Stop ma con almeno un errore o risultato non riuscito.
            stato = "Backup multi-job completato con errori"  # Evita il termine generico "segnalazioni" e descrive il caso reale.
            stato_esecuzione = "COMPLETATA CON ERRORI"  # Distingue chiaramente questo caso dall'annullamento richiesto dall'utente.

        self.etichetta_stato.configure(text=stato)  # Aggiorna l'indicatore principale con lo stato globale appena determinato.
        totale_copiati = sum((rs.risultato_backup.file_copiati if rs.risultato_backup else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti)  # Aggrega i file copiati realmente prodotti dai motori.
        totale_ignorati = sum((rs.risultato_backup.file_ignorati if rs.risultato_backup else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti)  # Aggrega i file già identici.
        totale_falliti = sum((rs.risultato_backup.file_falliti if rs.risultato_backup else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti) + sorgenti_con_errori  # Aggrega errori file e sorgenti fatalmente fallite.
        totale_byte = sum((rs.risultato_backup.byte_copiati if rs.risultato_backup else 0) for rj in risultato.risultati_job for rs in rj.risultati_sorgenti)  # Aggrega i byte copiati.
        problemi = tuple(rs.errore_fatale for rj in risultato.risultati_job for rs in rj.risultati_sorgenti if rs.errore_fatale)  # Conserva gli errori fatali delle sorgenti.
        stato_record = "annullato" if risultato.annullato else "successo" if risultato.successo else "problemi"  # Normalizza lo stato per la Home.
        self.registra_cronologia(crea_record_operazione("backup_multiplo", stato_record, f"Backup multi-job ({numero_job_avviati} job, {numero_sorgenti_avviate} sorgenti)", totale_copiati, totale_ignorati, totale_falliti, totale_byte, problemi))  # Salva l'esito strutturato.
        self.aggiungi_log("=== BACKUP MULTI-JOB TERMINATO ===")  # Separa visivamente il riepilogo finale dagli eventi delle singole sorgenti.
        self.aggiungi_log(f"Job avviati: {numero_job_avviati}")  # Mostra quanti job sono realmente partiti prima di un eventuale Stop.
        self.aggiungi_log(f"Sorgenti avviate: {numero_sorgenti_avviate}")  # Mostra quante sorgenti sono state effettivamente consegnate al motore.
        self.aggiungi_log(f"Sorgenti completate con successo: {sorgenti_completate}")  # Mostra le sorgenti concluse senza errori o annullamento interno.
        self.aggiungi_log(f"Sorgenti annullate: {sorgenti_annullate}")  # Mostra separatamente le sorgenti nelle quali il motore ha osservato lo Stop.
        self.aggiungi_log(f"Sorgenti con errori: {sorgenti_con_errori}")  # Mostra separatamente le sorgenti fallite per problemi reali.
        self.aggiungi_log(f"Esecuzione: {stato_esecuzione}")  # Evidenzia lo stato globale, necessario quando lo Stop arriva tra due sorgenti.

        riepilogo = (
            f"{stato}\n\n"
            f"Job avviati: {numero_job_avviati}\n"
            f"Sorgenti avviate: {numero_sorgenti_avviate}\n"
            f"Sorgenti completate con successo: {sorgenti_completate}\n"
            f"Sorgenti annullate: {sorgenti_annullate}\n"
            f"Sorgenti con errori: {sorgenti_con_errori}\n"
            f"Esecuzione: {stato_esecuzione}"
        )  # Costruisce un riepilogo coerente con i modelli del coordinatore e con lo stato globale dell'esecuzione.

        if risultato.successo:  # Usa il contratto del coordinatore per riservare il popup informativo al successo pieno.
            messagebox.showinfo("Backup", riepilogo)  # Mostra il riepilogo positivo quando tutta l'esecuzione è riuscita.
        else:  # Comprende sia l'annullamento richiesto dall'utente sia un'esecuzione terminata con errori.
            messagebox.showwarning("Backup", riepilogo)  # Usa un avviso prudente senza trasformare uno Stop volontario in un errore fatale.


    def gestisci_errore_fatale_backup_multiplo(self, errore: str) -> None:
        """Ripristina la GUI dopo un errore fatale del worker multi-job."""
        self.rilascia_blocco_operazione_manuale()  # Rende disponibile il lock condiviso appena il worker manuale ha concluso.
        self.barra_avanzamento.stop()  # Ferma l'indicatore di attività.
        self.barra_avanzamento.set(0)  # Riporta la barra allo stato iniziale.
        self.pulsante_avvia.configure(state="normal")  # Consente di correggere la configurazione e riprovare.
        self.pulsante_stop.configure(state="disabled")  # Disabilita Stop perché il worker non è più attivo.
        self.etichetta_stato.configure(text="Backup multi-job fallito")  # Comunica chiaramente il fallimento.
        self.registra_cronologia(crea_record_operazione("backup_multiplo", "fallito", "Backup multi-job", problemi=(errore,)))  # Conserva l'errore fatale nella cronologia strutturata.
        self.aggiungi_log(f"[ERRORE FATALE MULTI-JOB] {errore}")  # Registra il problema nell'area attività.
        messagebox.showerror("Backup multi-job fallito", errore)  # Mostra il messaggio diagnostico nel thread della GUI.

    def avvia_thread_backup(self) -> None:
        """Valida i campi della GUI e avvia il motore di backup in un thread separato."""
        if self.thread_backup is not None and self.thread_backup.is_alive():  # Controlla che non sia già in esecuzione un backup.
            return  # Ignora una seconda richiesta di avvio mentre il worker è attivo.

        sorgente = self.campo_sorgente.get().strip()  # Legge e ripulisce il percorso sorgente inserito nella GUI.
        destinazione = self.campo_destinazione.get().strip()  # Legge e ripulisce il percorso destinazione inserito nella GUI.

        if not sorgente or not destinazione:  # Verifica che entrambi i percorsi siano stati specificati.
            messagebox.showerror("Errore", "Seleziona sorgente e destinazione.")  # Informa l'utente della configurazione incompleta.
            return  # Non avvia il worker con percorsi mancanti.

        try:  # Esegue una prima validazione nel thread della GUI prima di avviare il worker.
            motore_verifica = MotoreBackup(threading.Event())  # Crea un motore temporaneo usato soltanto per la validazione.
            motore_verifica.valida_percorsi(Path(sorgente), Path(destinazione))  # Verifica i percorsi scelti.
        except ValueError as errore:  # Gestisce le configurazioni di percorso non valide.
            messagebox.showerror("Configurazione non valida", str(errore))  # Mostra all'utente il motivo del rifiuto.
            return  # Impedisce l'avvio del backup.

        if not self.acquisisci_blocco_operazione_manuale():  # Coordina il backup singolo con l'eventuale scheduler automatico già attivo.
            return  # Rinuncia all'avvio senza modificare lo stato della GUI.

        self.evento_arresto.clear()  # Elimina eventuali richieste di arresto rimaste da un backup precedente.
        self.pulsante_avvia.configure(state="disabled", text="⏳ Backup in corso...")  # Disabilita Avvia e conferma immediatamente la pressione.
        self.pulsante_stop.configure(state="normal")  # Abilita il pulsante Stop.
        self.etichetta_stato.configure(text="Backup in esecuzione...")  # Aggiorna lo stato visualizzato.
        self.barra_avanzamento.start()  # Avvia l'animazione della barra di avanzamento.
        self.aggiungi_log("=== BACKUP AVVIATO ===")  # Registra nel log l'inizio della nuova operazione.

        self.thread_backup = threading.Thread(
            target=self.esegui_backup_worker,
            args=(Path(sorgente), Path(destinazione)),
            daemon=False,
            name="ThreadBackup",
        )  # Crea il thread che eseguirà il motore senza bloccare l'interfaccia.
        self.thread_backup.start()  # Avvia effettivamente il thread di backup.

    def esegui_backup_worker(self, sorgente: Path, destinazione: Path) -> None:
        """Esegue il motore nel thread secondario e invia alla GUI soltanto eventi thread-safe."""
        motore = MotoreBackup(
            evento_arresto=self.evento_arresto,
            funzione_avanzamento=self.invia_evento,
        )  # Crea il motore collegato all'evento Stop e alla coda della GUI.

        try:  # Protegge il thread da errori non gestiti dal normale flusso del motore.
            risultato = motore.esegui(sorgente, destinazione)  # Esegue il backup e raccoglie il risultato.
            self.coda_eventi.put(("backup_completato", {"risultato": risultato}))  # Comunica alla GUI il completamento del backup distinguendolo dal ripristino.
        except Exception as errore:  # Costituisce l'ultima barriera contro un arresto silenzioso del thread.
            logger.exception("Errore fatale non gestito nel thread di backup.")  # Registra nel file di log il messaggio e il traceback completo dell'eccezione imprevista.
            self.coda_eventi.put(
                (
                    "errore_fatale_backup",
                    {"errore": f"{type(errore).__name__}: {errore}"},
                )
            )  # Invia alla GUI l'errore fatale senza chiamare widget dal thread secondario.

    def ferma_backup(self) -> None:
        """Richiede al motore di interrompersi in modo cooperativo appena raggiunge un punto di controllo."""
        if self.thread_backup is None or not self.thread_backup.is_alive():  # Verifica che esista realmente un backup attivo.
            return  # Non esegue alcuna azione se non c'è un worker in esecuzione.

        self.evento_arresto.set()  # Imposta il flag thread-safe che il motore controlla durante la scansione.
        self.etichetta_stato.configure(text="Arresto richiesto...")  # Informa l'utente che la richiesta è stata registrata.
        self.pulsante_stop.configure(state="disabled")  # Evita richieste Stop ripetute.
        self.aggiungi_log("Richiesto arresto del backup...")  # Registra la richiesta nel log.

    def avvia_thread_ripristino(self) -> None:
        """Valida i percorsi e avvia il motore di ripristino in un thread separato."""
        if self.thread_ripristino is not None and self.thread_ripristino.is_alive():  # Evita l'avvio di due ripristini concorrenti.
            return  # Ignora una seconda richiesta mentre il worker è attivo.

        if self.thread_backup is not None and self.thread_backup.is_alive():  # Impedisce di avviare un ripristino mentre il backup sta lavorando.
            return  # Mantiene una sola operazione filesystem attiva dalla GUI.

        sorgente = self.campo_sorgente.get().strip()  # Legge la cartella di backup scelta dall'utente.
        destinazione = self.campo_destinazione.get().strip()  # Legge la destinazione scelta per il ripristino.

        if not sorgente or not destinazione:  # Verifica che entrambi i percorsi siano stati specificati.
            messagebox.showerror("Errore", "Seleziona la cartella di backup e la destinazione del ripristino.")  # Informa l'utente della configurazione incompleta.
            return  # Non avvia il worker con percorsi mancanti.

        try:  # Valida i percorsi nel thread della GUI prima di creare il worker.
            motore_verifica = MotoreRipristino(threading.Event())  # Crea un motore temporaneo utilizzato soltanto per la validazione.
            motore_verifica.valida_percorsi(Path(sorgente), Path(destinazione))  # Applica esattamente le regole del motore reale.
        except ValueError as errore:  # Gestisce una configurazione rifiutata dal motore.
            messagebox.showerror("Configurazione non valida", str(errore))  # Mostra il motivo preciso senza avviare il thread.
            return  # Interrompe l'avvio del ripristino.

        if not self.acquisisci_blocco_operazione_manuale():  # Coordina il ripristino con l'eventuale scheduler automatico già attivo.
            return  # Rinuncia all'avvio senza modificare lo stato della GUI.

        self.evento_arresto.clear()  # Elimina eventuali richieste Stop rimaste dall'operazione precedente.
        self.pulsante_avvia.configure(state="disabled", text="⏳ Ripristino in corso...")  # Impedisce un’altra operazione e conferma immediatamente la pressione.
        self.pulsante_stop.configure(state="normal")  # Abilita il comando di arresto cooperativo.
        self.etichetta_stato.configure(text="Ripristino in esecuzione...")  # Comunica lo stato corrente all'utente.
        self.barra_avanzamento.start()  # Avvia l'indicatore indeterminato mentre il motore lavora.
        self.aggiungi_log("=== RIPRISTINO AVVIATO ===")  # Registra l'inizio dell'operazione nell'area attività.

        self.thread_ripristino = threading.Thread(
            target=self.esegui_ripristino_worker,
            args=(Path(sorgente), Path(destinazione)),
            daemon=False,
            name="ThreadRipristino",
        )  # Crea il worker senza eseguire direttamente operazioni sui widget.
        self.thread_ripristino.start()  # Avvia effettivamente il ripristino nel thread secondario.

    def esegui_ripristino_worker(self, sorgente: Path, destinazione: Path) -> None:
        """Esegue il motore di ripristino e comunica con la GUI esclusivamente attraverso la coda."""
        motore = MotoreRipristino(
            evento_arresto=self.evento_arresto,
            funzione_avanzamento=self.invia_evento,
        )  # Collega il motore allo stesso Event di Stop e alla callback thread-safe.

        try:  # Protegge il worker da eccezioni impreviste non classificate dal motore.
            risultato = motore.esegui(sorgente, destinazione)  # Esegue il ripristino conservativo e raccoglie il risultato finale.
            self.coda_eventi.put(("ripristino_completato", {"risultato": risultato}))  # Comunica alla GUI il risultato completo del ripristino.
        except Exception as errore:  # Costituisce l'ultima barriera contro la terminazione silenziosa del worker.
            logger.exception("Errore fatale non gestito nel thread di ripristino.")  # Registra messaggio e traceback nel log persistente.
            self.coda_eventi.put(("errore_fatale_ripristino", {"errore": f"{type(errore).__name__}: {errore}"}))  # Invia alla GUI l'errore senza toccare widget dal thread secondario.

    def ferma_ripristino(self) -> None:
        """Richiede al motore di ripristino un arresto cooperativo."""
        if self.thread_ripristino is None or not self.thread_ripristino.is_alive():  # Verifica che esista un ripristino realmente attivo.
            return  # Non esegue azioni quando non esiste un worker da fermare.

        self.evento_arresto.set()  # Imposta il flag che il motore controlla tra una fase e l'altra.
        self.etichetta_stato.configure(text="Arresto ripristino richiesto...")  # Informa l'utente che la richiesta è stata registrata.
        self.pulsante_stop.configure(state="disabled")  # Evita richieste Stop ripetute.
        self.aggiungi_log("Richiesto arresto del ripristino...")  # Registra la richiesta nell'area attività.

    # ========================================================
    # EVENTI WORKER -> GUI
    # ========================================================

    def processa_eventi(self) -> None:
        """Consuma gli eventi del worker nel thread della GUI e aggiorna i widget in sicurezza."""
        try:  # Prova a consumare tutti gli eventi attualmente disponibili.
            while True:  # Continua finché la coda contiene eventi.
                evento, dati = self.coda_eventi.get_nowait()  # Estrae un evento senza bloccare la GUI.

                if self.chiusura_in_corso:  # Controlla se l’utente ha già confermato la chiusura controllata dell’applicazione.
                    continue  # Drena la coda senza mostrare popup o aggiornamenti grafici mentre il worker termina.

                if evento == "file":  # Gestisce l'evento che indica il file attualmente in elaborazione.
                    self.etichetta_stato.configure(text=f"Elaborazione: {dati['file']}")  # Mostra il file corrente.

                elif evento == "copiato":  # Gestisce un file copiato e verificato correttamente.
                    self.aggiungi_log(f"[COPIATO] {dati['file']}")  # Registra il file copiato.

                elif evento == "ignorato":  # Gestisce un file già identico nella destinazione.
                    self.aggiungi_log(f"[IDENTICO] {dati['file']}")  # Registra il file che non richiedeva copia.

                elif evento == "cartella_creata":  # Gestisce una sottocartella appena creata nella destinazione.
                    self.aggiungi_log(f"[CARTELLA CREATA] {dati['cartella']}")  # Registra la nuova directory.

                elif evento == "errore_cartella":  # Gestisce un errore avvenuto durante la preparazione di una directory.
                    self.aggiungi_log(f"[ERRORE CARTELLA] {dati['errore']}")  # Registra il problema della directory.

                elif evento == "errore":  # Gestisce un errore relativo a un singolo file.
                    self.aggiungi_log(f"[ERRORE] {dati['errore']}")  # Registra il problema del file.

                elif evento == "file_ripristinato":  # Gestisce un file copiato e verificato dal motore di ripristino.
                    self.aggiungi_log(f"[RIPRISTINATO] {dati['percorso']}")  # Registra il file recuperato correttamente.

                elif evento == "file_identico":  # Gestisce un file già corretto nella destinazione del ripristino.
                    self.aggiungi_log(f"[GIÀ IDENTICO] {dati['percorso']}")  # Registra il file che non richiedeva alcuna scrittura.

                elif evento == "file_conflitto":  # Gestisce un file differente che il ripristino conservativo non sovrascrive.
                    self.aggiungi_log(f"[CONFLITTO FILE] {dati['percorso']}")  # Evidenzia il conflitto senza dichiararlo copiato.

                elif evento == "cartella_conflitto":  # Gestisce un conflitto nel quale era attesa una directory.
                    self.aggiungi_log(f"[CONFLITTO CARTELLA] {dati['errore']}")  # Registra il messaggio diagnostico completo.

                elif evento == "errore_file":  # Gestisce un errore previsto relativo a un file durante il ripristino.
                    self.aggiungi_log(f"[ERRORE RIPRISTINO] {dati['errore']}")  # Registra il problema senza bloccare il thread grafico.

                elif evento == "evento_backup_multiplo":  # Gestisce un evento del coordinatore nel thread della GUI.
                    self.gestisci_evento_backup_multiplo(dati["evento"], dati["dati"])  # Aggiorna stato e log senza violare la separazione tra thread.

                elif evento == "backup_multiplo_completato":  # Gestisce la conclusione normale del coordinatore.
                    self.gestisci_completamento_backup_multiplo(dati["risultato"])  # Ripristina i controlli e mostra il riepilogo aggregato.

                elif evento == "errore_fatale_backup_multiplo":  # Gestisce un errore non recuperabile del worker multi-job.
                    self.gestisci_errore_fatale_backup_multiplo(dati["errore"])  # Ripristina la GUI e mostra l'errore.

                elif evento == "backup_completato":  # Gestisce la conclusione del worker di backup.
                    self.gestisci_completamento(dati["risultato"])  # Aggiorna la GUI usando il risultato finale del backup.

                elif evento == "ripristino_completato":  # Gestisce la conclusione del worker di ripristino.
                    self.gestisci_completamento_ripristino(dati["risultato"])  # Aggiorna la GUI usando il risultato finale del ripristino.

                elif evento == "evento_avanzato":  # Gestisce progresso e attività prodotti dai motori avanzati senza accessi Tk dal worker.
                    sezione = dati["sezione"]  # Identifica il monitor Strategie o Sincronizza destinatario.
                    evento_motore = dati["evento"]  # Recupera il tipo di avanzamento emesso dal motore.
                    dettagli = dati["dati"]  # Recupera i dati numerici o il percorso associato.
                    if evento_motore == "file_incluso" and sezione == "strategie":
                        self.statistiche_filtri_strategia["inclusi"] += 1
                        self._aggiungi_attivita_avanzata(sezione, f"[INCLUSO] {dettagli.get('file', '')}")
                    elif evento_motore == "file_escluso" and sezione == "strategie":
                        self.statistiche_filtri_strategia["esclusi"] += 1
                        motivo = str(dettagli.get("motivo", "filtro")).replace("_", " ").upper()
                        self._aggiungi_attivita_avanzata(sezione, f"[ESCLUSO - {motivo}] {dettagli.get('file', '')}")
                    elif evento_motore == "cartella_esclusa" and sezione == "strategie":
                        self.statistiche_filtri_strategia["cartelle_escluse"] += 1
                        motivo = str(dettagli.get("motivo", "filtro")).replace("_", " ").upper()
                        self._aggiungi_attivita_avanzata(sezione, f"[CARTELLA ESCLUSA - {motivo}] {dettagli.get('cartella', '')}")
                    elif evento_motore == "inizio_copia":  # Passa dalla fase di analisi alla fase determinata di trasferimento.
                        totale = dettagli.get("totale_byte", 0)  # Legge il totale realmente selezionato dal motore.
                        self._aggiorna_progresso_avanzato(sezione, 1.0 if totale == 0 else 0.0, "Copia in corso..." if totale else "Nessun file da copiare")  # Gestisce correttamente anche operazioni senza payload.
                        if sezione == "strategie":
                            statistiche = getattr(self, "statistiche_filtri_strategia", {"inclusi": 0, "esclusi": 0, "cartelle_escluse": 0})
                            self._aggiungi_attivita_avanzata(sezione, f"[ANALISI] File inclusi: {statistiche['inclusi']}; file esclusi: {statistiche['esclusi']}; cartelle escluse: {statistiche['cartelle_escluse']}.")
                        self._aggiungi_attivita_avanzata(sezione, f"[COPIA] {dettagli.get('totale_file', 0)} file selezionati, {totale:,} byte.")  # Registra il volume reale del lavoro.
                    elif evento_motore == "avanzamento_copia":  # Aggiorna la percentuale durante i blocchi di un file grande.
                        totale = dettagli.get("totale_byte", 0)  # Recupera il denominatore comunicato dal motore.
                        frazione = dettagli.get("byte_elaborati", 0) / totale if totale else 1.0  # Evita divisioni per zero.
                        self._aggiorna_progresso_avanzato(sezione, frazione, f"Copia: {dettagli.get('file', '')}")  # Aggiorna barra, percentuale e file corrente.
                    elif evento_motore == "file_copiato":  # Registra il completamento atomico di un payload.
                        self._aggiungi_attivita_avanzata(sezione, f"[COPIATO] {dettagli.get('file', '')}")  # Mantiene un log leggibile equivalente a Backup/Ripristino.
                    elif evento_motore == "file_eliminato":  # Evidenzia separatamente le eliminazioni Mirror.
                        self._aggiungi_attivita_avanzata(sezione, f"[ELIMINATO] {dettagli.get('file', '')}")  # Rende visibile ogni modifica distruttiva.

                elif evento == "attivita_professionale":
                    self._aggiungi_attivita_avanzata("strategie", dati["testo"])

                elif evento == "strategia_completata":  # Gestisce la conclusione di Full, Incrementale o Differenziale.
                    self._concludi_operazione_avanzata("Strategia di backup", "backup_versionato", dati["risultato"], f"Backup {dati['risultato'].tipo_backup}")  # Registra e presenta l'esito reale.

                elif evento == "sincronizzazione_completata":  # Gestisce la conclusione di Update o Mirror.
                    self._concludi_operazione_avanzata("Sincronizzazione", "sincronizzazione", dati["risultato"], f"Sincronizzazione {dati['risultato'].tipo_backup}")  # Integra l'esito nella cronologia esistente.

                elif evento == "evento_verifica_integrita":  # Gestisce il progresso del verificatore nel thread Tk.
                    evento_verifica = dati["evento"]  # Recupera il tipo di notifica del backend.
                    dettagli_verifica = dati["dati"]  # Recupera contatori e percorso corrente.
                    if evento_verifica == "inizio_verifica":  # Inizializza il denominatore prima del primo hash.
                        totale = dettagli_verifica.get("totale_byte", 0)  # Legge i byte logici da verificare.
                        self.progresso_verifica_integrita = 1.0 if totale == 0 else 0.0  # Gestisce correttamente anche snapshot vuoti.
                        self.stato_verifica_integrita = "Verifica in corso..." if totale else "Verifica struttura..."  # Distingue hash dei payload e controllo strutturale.
                        self._aggiungi_attivita_verifica_integrita(f"[ANALISI] {dettagli_verifica.get('totale_file', 0)} file, {totale:,} byte, {dettagli_verifica.get('versioni_catena', 0)} versioni.")  # Registra il lavoro previsto.
                    elif evento_verifica == "avanzamento_verifica":  # Aggiorna la percentuale dopo ogni payload verificato.
                        totale = dettagli_verifica.get("totale_byte", 0)  # Recupera il denominatore stabile.
                        self.progresso_verifica_integrita = dettagli_verifica.get("byte_elaborati", 0) / totale if totale else 1.0  # Calcola una frazione determinata limitabile a 0..1.
                        self.stato_verifica_integrita = f"Verifica: {dettagli_verifica.get('file', '')}"  # Mostra il file appena controllato.
                    if self.sezione_attiva == "verifica_integrita" and hasattr(self, "barra_verifica_integrita") and self.barra_verifica_integrita.winfo_exists():  # Aggiorna soltanto widget vivi.
                        self.barra_verifica_integrita.set(max(0.0, min(1.0, self.progresso_verifica_integrita)))  # Rispetta l’intervallo 0..1 richiesto dal widget.
                        self.percentuale_verifica_integrita.configure(text=f"{int(self.progresso_verifica_integrita * 100)}%")  # Aggiorna la percentuale numerica.
                        self.etichetta_stato_verifica_integrita.configure(text=self.stato_verifica_integrita)  # Aggiorna lo stato corrente.
                        self._sincronizza_attivita_verifica_integrita_visibile()  # Mantiene il report coerente con il modello persistente.

                elif evento == "verifica_integrita_completata":  # Gestisce il report finale prodotto dal verificatore.
                    self.gestisci_verifica_integrita_completata(dati["risultato"])  # Finalizza lock, stato e diagnostica nel thread Tk.

                elif evento == "errore_fatale_verifica_integrita":  # Gestisce un errore imprevisto del worker di verifica.
                    self.rilascia_blocco_operazione_manuale()  # Evita di lasciare occupato il lock dopo un errore fatale.
                    self.operazione_avanzata_in_corso = ""  # Chiude il lifecycle dell’operazione fallita.
                    self.stato_verifica_integrita = "Errore"  # Conserva lo stato anche se l’utente ha cambiato pagina.
                    self._aggiungi_attivita_verifica_integrita(f"[ERRORE] {dati['errore']}")  # Persiste la diagnostica completa.
                    if self.sezione_attiva == "verifica_integrita" and hasattr(self, "pulsante_avvia_verifica_integrita") and self.pulsante_avvia_verifica_integrita.winfo_exists():  # Aggiorna soltanto la pagina viva.
                        self.pulsante_avvia_verifica_integrita.configure(state="normal", text="✓ Verifica integrità")  # Riabilita un nuovo tentativo.
                        self.etichetta_stato_verifica_integrita.configure(text="Errore")  # Mostra l’esito fallito.
                        self._sincronizza_attivita_verifica_integrita_visibile()  # Pubblica la diagnostica nel textbox.
                    messagebox.showerror("Verifica integrità", dati["errore"], parent=self)  # Comunica l’errore senza mascherarlo.

                elif evento == "evento_ripristino_avanzato":  # Gestisce il progresso determinato del ripristino versionato.
                    evento_ripristino = dati["evento"]  # Recupera il tipo di notifica emessa dal motore.
                    dettagli_ripristino = dati["dati"]  # Recupera contatori e percorso del file corrente.
                    if evento_ripristino == "inizio_ripristino":  # Inizializza il denominatore della barra.
                        totale = dettagli_ripristino.get("totale_byte", 0)  # Legge i byte logici della versione finale.
                        self.progresso_ripristino_versionato = 1.0 if totale == 0 else 0.0  # Gestisce anche una versione senza file.
                        self.stato_ripristino_versionato = "Ripristino in corso..." if totale else "Nessun file da ripristinare"  # Aggiorna lo stato persistente.
                        self._aggiungi_attivita_ripristino_versionato(f"[RIPRISTINO] {dettagli_ripristino.get('totale_file', 0)} file, {totale:,} byte.")  # Registra il volume reale del recupero.
                    elif evento_ripristino == "avanzamento_ripristino":  # Aggiorna la barra dopo ogni file gestito e verificato.
                        totale = dettagli_ripristino.get("totale_byte", 0)  # Recupera il denominatore stabile.
                        self.progresso_ripristino_versionato = dettagli_ripristino.get("byte_elaborati", 0) / totale if totale else 1.0  # Calcola la frazione determinata.
                        self.stato_ripristino_versionato = f"Ripristino: {dettagli_ripristino.get('file', '')}"  # Mostra il file corrente.
                        self._aggiungi_attivita_ripristino_versionato(f"[GESTITO] {dettagli_ripristino.get('file', '')}")  # Conserva il dettaglio fino a cancellazione esplicita.
                    if self.sezione_attiva == "ripristino_versionato" and hasattr(self, "barra_ripristino_versionato") and self.barra_ripristino_versionato.winfo_exists():  # Aggiorna soltanto widget vivi.
                        self.barra_ripristino_versionato.set(max(0.0, min(1.0, self.progresso_ripristino_versionato)))  # Limita la barra all'intervallo valido.
                        self.percentuale_ripristino_versionato.configure(text=f"{int(self.progresso_ripristino_versionato * 100)}%")  # Aggiorna la percentuale numerica.
                        self.etichetta_stato_ripristino_versionato.configure(text=self.stato_ripristino_versionato)  # Aggiorna il file/stato corrente.
                        self.casella_attivita_ripristino_versionato.configure(state="normal")  # Abilita temporaneamente l'inserimento.
                        self.casella_attivita_ripristino_versionato.delete("1.0", "end")  # Riallinea il widget al modello persistente.
                        self.casella_attivita_ripristino_versionato.insert("end", "\n".join(self.attivita_ripristino_versionato[-500:]) + "\n")  # Mostra le ultime righe senza crescita illimitata.
                        self.casella_attivita_ripristino_versionato.see("end")  # Mantiene visibile l'evento più recente.
                        self.casella_attivita_ripristino_versionato.configure(state="disabled")  # Ripristina la sola lettura.

                elif evento == "ripristino_avanzato_completato":  # Gestisce la ricostruzione di una versione avanzata.
                    self.gestisci_ripristino_avanzato_completato(dati["risultato"])  # Ripristina controlli, lock e cronologia.

                elif evento == "errore_fatale_strategia":  # Gestisce un errore fatale del coordinatore versionato.
                    self.gestisci_errore_operazione_avanzata("Strategia di backup fallita", dati["errore"])  # Rilascia il lock e mostra la diagnostica.

                elif evento == "errore_fatale_sincronizzazione":  # Gestisce un errore fatale Update/Mirror.
                    self.gestisci_errore_operazione_avanzata("Sincronizzazione fallita", dati["errore"])  # Rilascia il lock e mostra la diagnostica.

                elif evento == "errore_fatale_ripristino_avanzato":  # Gestisce un errore fatale della ricostruzione di catena.
                    self.gestisci_errore_operazione_avanzata("Ripristino versionato fallito", dati["errore"])  # Rilascia il lock e mostra la diagnostica.

                elif evento == "errore_fatale_backup":  # Gestisce un errore non recuperabile del worker di backup.
                    self.gestisci_errore_fatale(dati["errore"])  # Ripristina la GUI e mostra l'errore del backup.

                elif evento == "errore_fatale_ripristino":  # Gestisce un errore non recuperabile del worker di ripristino.
                    self.gestisci_errore_fatale_ripristino(dati["errore"])  # Ripristina la GUI e mostra l'errore del ripristino.

        except queue.Empty:  # Riconosce che tutti gli eventi disponibili sono stati elaborati.
            pass  # Non esegue altre operazioni quando la coda è vuota.

        self.after(100, self.processa_eventi)  # Pianifica il prossimo controllo della coda dopo 100 millisecondi.

    def gestisci_completamento(self, risultato: RisultatoBackup) -> None:
        """Ripristina i controlli della GUI e mostra il riepilogo dell'operazione conclusa."""
        self.rilascia_blocco_operazione_manuale()  # Rende disponibile il lock condiviso appena il worker manuale ha concluso.
        self.barra_avanzamento.stop()  # Ferma l'animazione della barra.
        self.barra_avanzamento.set(0)  # Riporta la barra allo stato iniziale.
        self.pulsante_avvia.configure(state="normal")  # Riabilita l'avvio di un nuovo backup.
        self.pulsante_stop.configure(state="disabled")  # Disabilita Stop perché il worker ha terminato.

        if risultato.annullato:  # Verifica se la conclusione è dovuta a una richiesta dell'utente.
            stato = "Backup annullato"  # Imposta lo stato appropriato per un backup interrotto.
        elif risultato.file_falliti or risultato.cartelle_fallite:  # Verifica se almeno un file o una cartella ha prodotto un errore.
            stato = "Backup completato con errori"  # Distingue un completamento parziale da un successo completo.
        else:  # Gestisce il caso senza errori e senza annullamento.
            stato = "Backup completato"  # Imposta lo stato di successo.

        self.etichetta_stato.configure(text=stato)  # Mostra lo stato finale nella finestra.
        stato_record = "annullato" if risultato.annullato else "problemi" if (risultato.file_falliti or risultato.cartelle_fallite) else "successo"  # Normalizza l'esito del backup singolo.
        self.registra_cronologia(crea_record_operazione("backup_singolo", stato_record, "Backup singolo", risultato.file_copiati, risultato.file_ignorati, risultato.file_falliti, risultato.byte_copiati, tuple(risultato.errori)))  # Registra contatori e problemi reali.

        riepilogo = (
            f"{stato}\n\n"
            f"File trovati: {risultato.file_trovati}\n"
            f"File copiati: {risultato.file_copiati}\n"
            f"File già identici: {risultato.file_ignorati}\n"
            f"File falliti: {risultato.file_falliti}\n"
            f"Cartelle trovate: {risultato.cartelle_trovate}\n"
            f"Cartelle create: {risultato.cartelle_create}\n"
            f"Cartelle già esistenti: {risultato.cartelle_esistenti}\n"
            f"Cartelle fallite: {risultato.cartelle_fallite}\n"
            f"Byte copiati: {risultato.byte_copiati:,}"
        )  # Costruisce il riepilogo dettagliato mostrato all'utente.

        self.aggiungi_log("=== BACKUP TERMINATO ===")  # Registra la fine dell'operazione nel log.
        self.aggiungi_log(f"Copiati: {risultato.file_copiati}")  # Registra il numero di file copiati.
        self.aggiungi_log(f"Identici: {risultato.file_ignorati}")  # Registra il numero di file già identici.
        self.aggiungi_log(f"Falliti: {risultato.file_falliti}")  # Registra il numero di file falliti.
        self.aggiungi_log(f"Cartelle trovate: {risultato.cartelle_trovate}")  # Registra il numero di sottocartelle individuate.
        self.aggiungi_log(f"Cartelle create: {risultato.cartelle_create}")  # Registra il numero di sottocartelle create.
        self.aggiungi_log(f"Cartelle fallite: {risultato.cartelle_fallite}")  # Registra il numero di sottocartelle non preparate.

        if risultato.annullato:  # Sceglie il tipo di finestra in caso di annullamento.
            messagebox.showwarning("Backup", riepilogo)  # Mostra un avviso con il riepilogo parziale.
        elif risultato.file_falliti or risultato.cartelle_fallite:  # Sceglie il tipo di finestra quando esistono errori.
            messagebox.showwarning("Backup completato con errori", riepilogo)  # Mostra un avviso anziché dichiarare un successo pieno.
        else:  # Gestisce il completamento senza problemi.
            messagebox.showinfo("Backup", riepilogo)  # Mostra il riepilogo del backup riuscito.

    def gestisci_completamento_ripristino(self, risultato: RisultatoRipristino) -> None:
        """Ripristina i controlli della GUI e mostra il riepilogo finale del ripristino."""
        self.rilascia_blocco_operazione_manuale()  # Rende disponibile il lock condiviso appena il worker manuale ha concluso.
        self.barra_avanzamento.stop()  # Ferma l'animazione dell'indicatore di attività.
        self.barra_avanzamento.set(0)  # Riporta la barra allo stato iniziale.
        self.pulsante_avvia.configure(state="normal")  # Consente di avviare una nuova operazione.
        self.pulsante_stop.configure(state="disabled")  # Disabilita Stop perché il worker ha terminato.

        if risultato.annullato:  # Controlla se l'utente ha richiesto l'arresto.
            stato = "Ripristino annullato"  # Distingue l'interruzione da un completamento.
        elif risultato.file_falliti or risultato.cartelle_fallite:  # Controlla la presenza di errori filesystem.
            stato = "Ripristino completato con errori"  # Segnala un completamento parziale.
        elif risultato.file_conflitto or risultato.cartelle_conflitto:  # Controlla i conflitti lasciati intenzionalmente intatti.
            stato = "Ripristino completato con conflitti"  # Distingue i conflitti dagli errori tecnici.
        else:  # Gestisce il caso completamente riuscito.
            stato = "Ripristino completato"  # Comunica il successo dell'operazione.

        self.etichetta_stato.configure(text=stato)  # Mostra lo stato finale nell'interfaccia.
        stato_record = "annullato" if risultato.annullato else "successo" if risultato.successo else "problemi"  # Normalizza l'esito del ripristino.
        self.registra_cronologia(crea_record_operazione("ripristino", stato_record, "Ripristino", risultato.file_ripristinati, risultato.file_identici, risultato.file_falliti, risultato.byte_ripristinati, tuple(risultato.errori)))  # Registra il ripristino senza confonderlo con un backup.

        riepilogo = (
            f"{stato}\n\n"
            f"File trovati: {risultato.file_trovati}\n"
            f"File ripristinati: {risultato.file_ripristinati}\n"
            f"File già identici: {risultato.file_identici}\n"
            f"Conflitti file: {risultato.file_conflitto}\n"
            f"File falliti: {risultato.file_falliti}\n"
            f"Cartelle trovate: {risultato.cartelle_trovate}\n"
            f"Cartelle create: {risultato.cartelle_create}\n"
            f"Cartelle già esistenti: {risultato.cartelle_esistenti}\n"
            f"Conflitti cartelle: {risultato.cartelle_conflitto}\n"
            f"Cartelle fallite: {risultato.cartelle_fallite}\n"
            f"Byte ripristinati: {risultato.byte_ripristinati:,}"
        )  # Costruisce il riepilogo completo usando esclusivamente i contatori del motore.

        self.aggiungi_log("=== RIPRISTINO TERMINATO ===")  # Registra la fine dell'operazione nell'area attività.
        self.aggiungi_log(f"Ripristinati: {risultato.file_ripristinati}")  # Registra il numero di file recuperati.
        self.aggiungi_log(f"Identici: {risultato.file_identici}")  # Registra i file già corretti.
        self.aggiungi_log(f"Conflitti file: {risultato.file_conflitto}")  # Registra i file lasciati intatti per conflitto.
        self.aggiungi_log(f"Falliti: {risultato.file_falliti}")  # Registra i file non elaborati per errore.
        self.aggiungi_log(f"Cartelle create: {risultato.cartelle_create}")  # Registra le sottocartelle create.
        self.aggiungi_log(f"Conflitti cartelle: {risultato.cartelle_conflitto}")  # Registra i conflitti relativi alle directory.

        if risultato.annullato:  # Sceglie un avviso per un'operazione interrotta.
            messagebox.showwarning("Ripristino", riepilogo)  # Mostra il riepilogo parziale dell'operazione annullata.
        elif not risultato.successo:  # Comprende sia errori sia conflitti secondo il contratto di RisultatoRipristino.
            messagebox.showwarning("Ripristino completato con segnalazioni", riepilogo)  # Evita di presentare come successo pieno un risultato con problemi.
        else:  # Gestisce un ripristino senza errori, conflitti o annullamento.
            messagebox.showinfo("Ripristino", riepilogo)  # Mostra il riepilogo del ripristino riuscito.

    def gestisci_errore_fatale_ripristino(self, errore: str) -> None:
        """Ripristina la GUI dopo un errore fatale del worker di ripristino."""
        self.rilascia_blocco_operazione_manuale()  # Rende disponibile il lock condiviso appena il worker manuale ha concluso.
        self.barra_avanzamento.stop()  # Ferma la barra di avanzamento.
        self.barra_avanzamento.set(0)  # Riporta la barra allo stato iniziale.
        self.pulsante_avvia.configure(state="normal")  # Consente un nuovo tentativo.
        self.pulsante_stop.configure(state="disabled")  # Disabilita Stop perché il worker è terminato.
        self.etichetta_stato.configure(text="Ripristino fallito")  # Mostra chiaramente il tipo di operazione fallita.
        self.registra_cronologia(crea_record_operazione("ripristino", "fallito", "Ripristino", problemi=(errore,)))  # Conserva l'errore fatale nella cronologia strutturata.
        self.aggiungi_log(f"[ERRORE FATALE RIPRISTINO] {errore}")  # Registra il problema nell'area attività.
        messagebox.showerror("Ripristino fallito", errore)  # Mostra l'errore all'utente nel thread della GUI.

    def gestisci_errore_fatale(self, errore: str) -> None:
        """Ripristina la GUI dopo un errore fatale e mostra il relativo messaggio."""
        self.rilascia_blocco_operazione_manuale()  # Rende disponibile il lock condiviso appena il worker manuale ha concluso.
        self.barra_avanzamento.stop()  # Ferma la barra di avanzamento.
        self.barra_avanzamento.set(0)  # Riporta la barra allo stato iniziale.
        self.pulsante_avvia.configure(state="normal")  # Consente un nuovo tentativo.
        self.pulsante_stop.configure(state="disabled")  # Disabilita Stop perché il worker non è più operativo.
        self.etichetta_stato.configure(text="Backup fallito")  # Mostra lo stato di errore.
        self.registra_cronologia(crea_record_operazione("backup_singolo", "fallito", "Backup singolo", problemi=(errore,)))  # Conserva l'errore fatale nella cronologia strutturata.
        self.aggiungi_log(f"[ERRORE FATALE] {errore}")  # Registra il problema nell'area attività.
        messagebox.showerror("Backup fallito", errore)  # Mostra l'errore all'utente.

    # ========================================================
    # CHIUSURA SICURA
    # ========================================================

    def ottieni_thread_attivo(self) -> threading.Thread | None:
        """Restituisce il worker attualmente attivo, se presente."""
        if self.thread_backup is not None and self.thread_backup.is_alive():  # Controlla se il backup sta ancora lavorando.
            return self.thread_backup  # Restituisce il thread di backup attivo.

        if self.thread_ripristino is not None and self.thread_ripristino.is_alive():  # Controlla se il ripristino sta ancora lavorando.
            return self.thread_ripristino  # Restituisce il thread di ripristino attivo.

        return None  # Indica che non esistono operazioni attive.

    def processa_comandi_tray(self) -> None:
        """Esegue nel thread Tk i comandi ricevuti dall'icona Windows senza accedere ai widget dal thread pystray."""
        if self.chiusura_in_corso or not self.winfo_exists():  # Evita nuovi comandi mentre l'applicazione sta terminando definitivamente.
            return  # Interrompe il polling perché la finestra non deve più essere riaperta.
        while True:  # Consuma tutti i comandi già disponibili senza bloccare il mainloop.
            try:  # Tenta una lettura immediata della coda thread-safe.
                comando = self.coda_comandi_tray.get_nowait()  # Recupera il prossimo comando senza attendere il thread dell'icona.
            except queue.Empty:  # Riconosce che non esistono altre azioni da elaborare in questo ciclo.
                break  # Restituisce rapidamente il controllo a Tk.
            if comando == COMANDO_APRI:  # Riconosce l'azione primaria dell'icona o la voce Apri FDBackup.
                self.mostra_finestra()  # Ripristina la finestra esclusivamente dal thread che possiede Tk.
            elif comando == COMANDO_CHIUDI:  # Riconosce la voce di uscita definitiva del menu contestuale.
                self.richiedi_uscita_definitiva()  # Avvia il percorso di chiusura sicura già coordinato con eventuali worker.
        self.after(100, self.processa_comandi_tray)  # Pianifica il controllo successivo senza creare thread Tk aggiuntivi.

    def mostra_finestra(self) -> None:
        """Rende nuovamente visibile la finestra principale mantenendo la stessa istanza e lo stesso stato applicativo."""
        self.deiconify()  # Ripristina la finestra precedentemente nascosta con withdraw.
        self.lift()  # Porta la finestra sopra le altre senza ricreare widget o processi.

    def gestisci_richiesta_chiusura(self) -> None:
        """Nasconde la finestra nell'area di notifica quando l'utente preme la X senza interrompere operazioni o scheduler."""
        if not self.tray_disponibile:  # Evita di nascondere la GUI quando manca il punto di riapertura nell'area di notifica.
            messagebox.showwarning("Area di notifica non disponibile", "Impossibile nascondere FDBackup perché pystray non è disponibile. Installa la dipendenza e riavvia l'applicazione.", parent=self)  # Mantiene l'applicazione accessibile e spiega il requisito mancante.
            return  # Lascia aperta la finestra senza modificare worker o scheduler.
        self.withdraw()  # Nasconde soltanto la finestra mantenendo vivi mainloop, worker e runner scheduler.

    def richiedi_uscita_definitiva(self) -> None:
        """Gestisce il comando Chiudi FDBackup distinguendo l'uscita reale dalla semplice X della finestra."""
        thread_attivo = self.ottieni_thread_attivo()  # Cerca un eventuale backup o ripristino manuale ancora in esecuzione.
        if thread_attivo is None:  # Verifica se la GUI può terminare immediatamente senza interrompere un worker.
            self.finalizza_uscita_definitiva()  # Arresta icona e runner e distrugge la GUI.
            return  # Conclude il percorso rapido di uscita.
        self.mostra_finestra()  # Rende visibile la GUI prima di chiedere una decisione su un'operazione attiva.
        conferma = messagebox.askyesno("Operazione in corso", "È presente un'operazione in corso.\n\nVuoi richiedere l'arresto e chiudere definitivamente FDBackup quando l'operazione sarà terminata in sicurezza?", parent=self)  # Protegge il lavoro in corso da una terminazione brusca.
        if not conferma:  # Riconosce la scelta di lasciare proseguire l'operazione.
            return  # Mantiene applicazione, tray e runner nello stato corrente.
        self.chiusura_in_corso = True  # Segnala ai polling periodici che è iniziata la fase finale di chiusura.
        self.evento_arresto.set()  # Richiede al motore manuale un arresto cooperativo già supportato dal progetto.
        self.pulsante_avvia.configure(state="disabled")  # Impedisce nuovi avvii durante l'attesa della conclusione del worker.
        self.pulsante_stop.configure(state="disabled")  # Evita richieste Stop duplicate durante la fase finale.
        self.etichetta_stato.configure(text="Arresto in corso prima della chiusura definitiva...")  # Comunica chiaramente lo stato all'utente.
        self.aggiungi_log("Uscita definitiva: arresto cooperativo dell'operazione in corso...")  # Registra visivamente la richiesta senza alterare la cronologia persistente.
        self.after(100, self.verifica_chiusura_sicura)  # Attende il worker senza bloccare il ciclo degli eventi Tk.

    def verifica_chiusura_sicura(self) -> None:
        """Attende in modo non bloccante la conclusione del worker prima dell'uscita definitiva."""
        thread_attivo = self.ottieni_thread_attivo()  # Verifica se il worker ha terminato dopo la richiesta cooperativa.
        if thread_attivo is not None:  # Controlla se il motore sta ancora completando l'operazione corrente.
            self.after(100, self.verifica_chiusura_sicura)  # Rimanda il controllo senza bloccare Tk.
            return  # Evita di terminare il processo mentre il worker è ancora attivo.
        self.finalizza_uscita_definitiva()  # Completa l'uscita soltanto quando il worker non è più attivo.

    def finalizza_uscita_definitiva(self) -> None:
        """Segnala l'arresto al runner separato, rimuove l'icona e distrugge definitivamente la GUI."""
        self.chiusura_in_corso = True  # Blocca nuovi polling e comandi di riapertura durante la sequenza finale.
        try:  # Tenta di creare il segnale interprocesso senza impedire comunque la chiusura della GUI.
            FILE_RICHIESTA_ARRESTO_SCHEDULER.write_text("stop\n", encoding="utf-8")  # Chiede al runner separato di terminare e rilasciare il proprio lock entro il successivo controllo breve.
        except OSError as errore:  # Gestisce un eventuale filesystem non scrivibile senza lasciare la GUI bloccata.
            logger.error("Impossibile segnalare l'arresto al runner scheduler: %s", errore)  # Conserva nel log la possibilità che il runner debba essere chiuso separatamente.
        self.gestore_tray.arresta()  # Rimuove l'icona dall'area di notifica prima di terminare il mainloop.
        self.destroy()  # Distrugge la finestra e conclude il processo GUI.

    def destroy(self) -> None:
        """Rilascia sempre il lock di presenza GUI prima di distruggere definitivamente la finestra."""
        blocco_gui = getattr(self, "blocco_presenza_gui", None)  # Recupera il lock anche durante eventuali chiusure parziali dell'inizializzazione.
        if blocco_gui is not None:  # Verifica che il lock sia già stato costruito.
            blocco_gui.rilascia()  # Segnala al runner che la GUI non è più presente.
        super().destroy()  # Delega a CustomTkinter la distruzione reale della finestra e dei widget.

    # ========================================================
    # BANNER
    # ========================================================

    def carica_banner(self, percorso: str) -> None:
        """Carica il banner senza deformarlo e mostra dimensioni e peso del file."""
        try:  # Prova ad aprire e preparare l'immagine selezionata.
            percorso_banner = Path(percorso)  # Converte il percorso ricevuto in un oggetto Path.
            if not percorso_banner.is_file():  # Verifica che il file esista ancora sul disco.
                raise FileNotFoundError(f"File non trovato: {percorso_banner}")  # Segnala un percorso non più valido.

            with Image.open(percorso_banner) as immagine_aperta:  # Apre l'immagine e garantisce la chiusura automatica del file.
                larghezza_originale, altezza_originale = immagine_aperta.size  # Legge le dimensioni originali prima del ridimensionamento.
                immagine_rgb = immagine_aperta.convert("RGB")  # Converte l'immagine in RGB per una visualizzazione uniforme.
                rapporto = min(900 / larghezza_originale, 210 / altezza_originale, 1.0)  # Calcola un fattore che mantiene le proporzioni e non ingrandisce l'originale.
                larghezza_visualizzata = max(1, round(larghezza_originale * rapporto))  # Calcola la larghezza finale proporzionale.
                altezza_visualizzata = max(1, round(altezza_originale * rapporto))  # Calcola l'altezza finale proporzionale.
                immagine_finale = immagine_rgb.resize((larghezza_visualizzata, altezza_visualizzata), Image.Resampling.LANCZOS)  # Ridimensiona con filtro di alta qualità senza deformare.

            dimensione_byte = percorso_banner.stat().st_size  # Legge la dimensione effettiva del file sul disco.
            dimensione_mb = dimensione_byte / (1024 * 1024)  # Converte i byte in MiB per una lettura più comprensibile.
            self.immagine_banner = ctk.CTkImage(light_image=immagine_finale, dark_image=immagine_finale, size=(larghezza_visualizzata, altezza_visualizzata))  # Crea l'immagine compatibile con CustomTkinter.
            self.etichette_banner_globali = [etichetta for etichetta in self.etichette_banner_globali if etichetta.winfo_exists()]  # Elimina riferimenti a pagine già distrutte.
            for etichetta in self.etichette_banner_globali:  # Aggiorna contemporaneamente ogni sezione attualmente costruita.
                etichetta.configure(image=self.immagine_banner, text="")  # Mostra la stessa immagine aziendale senza duplicare lo stato.
            self.contenitore_segnaposto_banner.place_forget()  # Nasconde le istruzioni quando è presente un'immagine.
            self.etichetta_info_banner.configure(text=f"Dimensioni: {larghezza_originale} × {altezza_originale} px  |  Dimensione file: {dimensione_mb:.2f} MB")  # Mostra risoluzione e peso del file selezionato.

        except (OSError, ValueError) as errore:  # Gestisce file mancanti, immagini non valide e problemi di lettura.
            logger.error(  # Registra nel file di log il problema del banner senza produrre un traceback per un errore previsto.
                "Impossibile caricare il banner '%s': %s",
                percorso,
                errore,
            )
            self.rimuovi_banner()  # Ripristina lo stato senza banner se il file non è utilizzabile.

    def cambia_banner(self) -> None:
        """Permette all'utente di scegliere una nuova immagine e ne salva il percorso nella configurazione."""
        percorso = filedialog.askopenfilename(
            filetypes=[("Immagini", "*.png *.jpg *.jpeg")]
        )  # Mostra la finestra di scelta limitata ai formati immagine supportati dal prototipo.

        if percorso:  # Verifica che l'utente abbia effettivamente scelto un file.
            self.configurazione["banner"] = percorso  # Salva in memoria il percorso del nuovo banner.
            self.salva_configurazione()  # Persiste il percorso nel file JSON.
            self.carica_banner(percorso)  # Carica immediatamente il nuovo banner nella GUI.

    def rimuovi_banner(self) -> None:
        """Rimuove il banner, ripristina il segnaposto e aggiorna la configurazione persistente."""
        self.etichette_banner_globali = [etichetta for etichetta in self.etichette_banner_globali if etichetta.winfo_exists()]  # Mantiene soltanto le etichette ancora vive.
        for etichetta in self.etichette_banner_globali:  # Rimuove il banner da ogni sezione costruita.
            etichetta.configure(image=None, text="Banner non configurato • gestiscilo dalla Home" if etichetta is not self.etichetta_banner else "")  # Ripristina uno stato neutro fuori dalla Home operativa.
        self.immagine_banner = None  # Elimina il riferimento Python all'immagine precedente.
        self.etichetta_info_banner.configure(text="")  # Cancella le informazioni relative al vecchio banner.
        self.contenitore_segnaposto_banner.place(relx=0.5, rely=0.5, anchor="center")  # Ripristina le istruzioni nel riquadro vuoto.
        if "banner" in self.configurazione:  # Controlla se la configurazione contiene un percorso banner.
            del self.configurazione["banner"]  # Rimuove il percorso dalla configurazione in memoria.
            self.salva_configurazione()  # Persiste la rimozione nel file JSON.


# ============================================================
# PUNTO DI INGRESSO
# ============================================================

if __name__ == "__main__":  # Esegue l'interfaccia soltanto quando questo file viene avviato direttamente.
    applicazione = GestoreBackup()  # Crea l'istanza principale di FDBackup.
    if "--background" in sys.argv:  # Riconosce esclusivamente l'avvio automatico creato da FDBackup tramite Task Scheduler.
        applicazione.withdraw()  # Avvia in background lasciando disponibile l'icona nell'area di notifica senza mostrare la finestra.
    applicazione.mainloop()  # Avvia il ciclo degli eventi grafici.
