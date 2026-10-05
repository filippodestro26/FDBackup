# FDBackup

FDBackup è un'applicazione desktop per Windows, sviluppata in Python, dedicata al backup, al versioning, alla sincronizzazione e al ripristino di file e cartelle.

Il progetto nasce con un obiettivo preciso: trattare il backup come un processo verificabile e recuperabile, non come una semplice copia di file. Per questo integra controlli di integrità SHA-256, strategie versionate, ricostruzione delle catene, gestione delle eliminazioni e strumenti di ripristino.

> **Stato del progetto:** v0.1.0-beta — baseline verificata su Windows con Python 3.14. Lo sviluppo continua in modo incrementale.

## Funzionalità principali

### Backup

- backup tradizionale di file e cartelle;
- strategie versionate **Full**, **Incrementale** e **Differenziale**;
- mantenimento della struttura delle directory, incluse le cartelle vuote;
- versioni identificabili e metadati persistenti;
- registrazione logica delle eliminazioni tramite tombstone;
- rotazione Full e retention per catene complete;
- arresto cooperativo delle operazioni;
- avanzamento, statistiche e Activity persistente.

### Integrità e recuperabilità

- verifica SHA-256 dei payload;
- verifica automatica post-backup opzionale;
- verifica della catena necessaria al ripristino;
- rilevamento di file mancanti, dimensioni incoerenti e contenuti alterati;
- test di recuperabilità opzionale;
- report esportabili e dashboard del repository.

La verifica SHA-256 controlla la coerenza dei dati rispetto ai digest registrati. Non costituisce una firma crittografica contro un soggetto in grado di alterare contemporaneamente dati e metadati.

### Ripristino

- ripristino tradizionale conservativo;
- ripristino completo di versioni Full, Incrementali e Differenziali;
- ricostruzione delle catene;
- applicazione delle eliminazioni registrate;
- ripristino selettivo di singoli file o cartelle;
- ricreazione delle directory vuote;
- gestione esplicita dei conflitti.

### Sincronizzazione

- **Update**: copia gli elementi nuovi o modificati senza eliminare quelli presenti soltanto nella destinazione;
- **Mirror**: allinea la destinazione alla sorgente e richiede conferma prima delle eliminazioni.

### Filtri e politiche

- inclusioni ed esclusioni per estensione o pattern;
- esclusioni per dimensione minima/massima;
- esclusione di file nascosti o sola lettura;
- gestione conservativa dei reparse point;
- anteprima della retention GFS;
- supporto infrastrutturale a destinazioni aggiuntive locali o share SMB già accessibili dal sistema.

### Integrazione Windows

- interfaccia grafica CustomTkinter;
- System Tray;
- notifiche Windows;
- avvio automatico tramite `HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`;
- scheduler eseguito in un processo indipendente dalla GUI;
- lock interprocesso per coordinare GUI, scheduler e operazioni.

## Installazione

### Requisiti

- Windows;
- Python 3.14 consigliato per la baseline attualmente verificata;
- dipendenze elencate in `requirements.txt`.

Clona il repository e crea un ambiente virtuale:

```powershell
git clone <URL-DEL-REPOSITORY>
cd FDBackup
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

Avvia FDBackup:

```powershell
py .\main.py
```

## Test

La suite usa `unittest`:

```powershell
py -m unittest discover -s tests -v
```

La baseline v0.1.0-beta è stata verificata su Windows/Python 3.14 con **361 test automatici completati con successo**, oltre a test manuali dei flussi principali e dell'interfaccia grafica.

## Architettura

```text
FDBackup/
├── fdbackup/          # motori, scheduler, persistenza e servizi
├── tests/             # suite automatica
├── main.py            # entry point GUI
├── requirements.txt
└── README.md
```

I componenti principali sono separati tra motori di backup/ripristino, persistenza, scheduler, verifica dell'integrità, politiche avanzate e integrazione Windows. Le operazioni incompatibili sono coordinate tramite lock dedicati.

## Limitazioni attuali

FDBackup è attualmente un sistema di backup **file-level**. Non deve essere considerato equivalente a un prodotto di imaging o disaster recovery completo.

In particolare, questa versione non include ancora:

- Volume Shadow Copy Service (VSS) per snapshot consistenti di file aperti;
- imaging di partizioni o dischi;
- bare-metal recovery o ambiente di ripristino avviabile;
- gestione integrata delle credenziali NAS/SFTP;
- cifratura del repository;
- deduplicazione;
- preservazione completa di ACL, proprietari e Alternate Data Streams NTFS.

Python documenta inoltre che `shutil.copy2()` tenta di preservare i metadati supportati, ma su Windows non copia proprietari, ACL e Alternate Data Streams.

## Sicurezza dei dati

Le operazioni potenzialmente distruttive sono progettate in modo conservativo. In particolare, Mirror richiede conferma e le eliminazioni non vengono applicate se la fase di copia termina con errori o viene annullata. La retention dispone di anteprima prima della cancellazione delle catene.

Per dati importanti è comunque raccomandato mantenere più copie indipendenti e verificare periodicamente il ripristino.

## Compatibilità

FDBackup mantiene la lettura dei metadati prodotti dalle precedenti versioni del progetto per evitare di rendere inutilizzabili repository già esistenti. Alcuni identificatori tecnici legacy possono quindi rimanere intenzionalmente nel codice come percorso di compatibilità.

## Roadmap

Le prossime aree di sviluppo comprendono alert sullo spazio disponibile, reportistica periodica, gestione più completa delle destinazioni multiple, supporto NAS/remoto, cifratura e, in una fase architetturale successiva, VSS e funzionalità di disaster recovery.

## Autore

**Filippo Destro**

FDBackup è un progetto personale sviluppato come applicazione desktop Windows e come percorso di approfondimento su backup, affidabilità, concorrenza, persistenza, verifica dell'integrità e progettazione di software testabile.
