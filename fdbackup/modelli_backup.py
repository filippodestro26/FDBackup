from dataclasses import dataclass, field  # Importa gli strumenti standard per definire modelli dati espliciti e leggeri.
from datetime import datetime  # Importa datetime per validare l’istante civile locale dal quale una pianificazione diventa effettiva.
from pathlib import Path  # Importa Path per rappresentare i percorsi senza legarli alla GUI.
import re  # Importa le espressioni regolari per validare in modo rigoroso il formato HH:MM della pianificazione.
from uuid import uuid4  # Importa UUID4 per generare identificatori persistenti casuali indipendenti dal percorso.


FORMATO_ORA = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")  # Accetta esclusivamente ore locali nel formato a due cifre HH:MM.
FORMATO_ATTIVAZIONE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")  # Impone un istante civile locale con precisione al secondo e senza fuso incorporato.


def genera_identificatore() -> str:
    """Genera un identificatore UUID4 testuale per un job o una sorgente."""
    return str(uuid4())  # Restituisce l'UUID in formato testuale standard, adatto alla serializzazione JSON.


@dataclass(slots=True)
class PianificazioneBackup:
    """Descrive quando una singola sorgente dovrà essere eseguita dal futuro scheduler."""

    abilitata: bool = False  # Mantiene disabilitata la pianificazione per impostazione predefinita e per le sorgenti storiche.
    giorni: tuple[int, ...] = field(default_factory=tuple)  # Usa 0=lunedì ... 6=domenica, coerentemente con datetime.weekday().
    ora: str = ""  # Conserva l'orario locale HH:MM; resta vuoto finché la pianificazione non viene configurata.
    attiva_dal: str = ""  # Conserva l’istante civile locale dal quale la regola è valida; vuoto mantiene compatibili le configurazioni storiche.

    def __post_init__(self) -> None:
        """Normalizza la collezione dei giorni e rifiuta configurazioni temporali ambigue o non valide."""
        if not isinstance(self.abilitata, bool):  # Richiede un booleano reale senza conversioni implicite.
            raise TypeError("L'opzione 'abilitata' della pianificazione deve essere booleana.")  # Segnala chiaramente un tipo errato.

        if not isinstance(self.giorni, (list, tuple)):  # Accetta liste dal JSON e tuple dal codice applicativo.
            raise TypeError("I giorni della pianificazione devono essere una lista o una tupla.")  # Rifiuta stringhe, set e altri contenitori ambigui.

        giorni_normalizzati = tuple(self.giorni)  # Crea una copia immutabile per impedire modifiche esterne accidentali.

        for giorno in giorni_normalizzati:  # Controlla ogni giorno prima di pubblicare il modello normalizzato.
            if isinstance(giorno, bool) or not isinstance(giorno, int):  # Esclude anche bool, che in Python è una sottoclasse di int.
                raise TypeError("Ogni giorno della pianificazione deve essere un intero compreso tra 0 e 6.")  # Impone il tipo previsto.
            if giorno < 0 or giorno > 6:  # Verifica l'intervallo lunedì-domenica.
                raise ValueError("Ogni giorno della pianificazione deve essere compreso tra 0 e 6.")  # Rifiuta valori fuori calendario settimanale.

        if len(set(giorni_normalizzati)) != len(giorni_normalizzati):  # Confronta cardinalità per individuare duplicati.
            raise ValueError("I giorni della pianificazione non possono contenere duplicati.")  # Evita trigger settimanali duplicati.

        if not isinstance(self.ora, str):  # Richiede una stringa perché il formato persistente è testuale.
            raise TypeError("L'ora della pianificazione deve essere una stringa nel formato HH:MM.")  # Rifiuta tipi incompatibili.

        ora_normalizzata = self.ora.strip()  # Elimina soltanto spazi accidentali ai margini senza correggere il formato.

        if not isinstance(self.attiva_dal, str):  # Richiede una rappresentazione testuale coerente con il formato JSON della configurazione.
            raise TypeError("L’istante di attivazione della pianificazione deve essere una stringa.")  # Rifiuta timestamp numerici o oggetti datetime non serializzati.

        attivazione_normalizzata = self.attiva_dal.strip()  # Elimina soltanto spazi accidentali senza modificare il valore temporale.
        if attivazione_normalizzata:  # Valida il limite temporale soltanto quando è presente nelle configurazioni nuove.
            if FORMATO_ATTIVAZIONE.fullmatch(attivazione_normalizzata) is None:  # Impone una forma deterministica prima del parsing semantico.
                raise ValueError("L’istante di attivazione deve usare il formato YYYY-MM-DDTHH:MM:SS.")  # Rifiuta formati ambigui o privi di precisione.
            try:  # Verifica anche che data e ora rappresentino un valore civile realmente esistente nel calendario.
                datetime.strptime(attivazione_normalizzata, "%Y-%m-%dT%H:%M:%S")  # Analizza anno, mese, giorno, ora, minuti e secondi.
            except ValueError as errore:  # Converte l’errore di parsing in un messaggio appartenente al contratto del modello.
                raise ValueError("L’istante di attivazione della pianificazione non è valido.") from errore  # Non accetta date impossibili come il 31 febbraio.

        if ora_normalizzata and FORMATO_ORA.fullmatch(ora_normalizzata) is None:  # Valida ore e minuti con formato rigoroso a due cifre.
            raise ValueError("L'ora della pianificazione deve usare il formato HH:MM con valori validi.")  # Rifiuta 9:00, 24:00 e minuti oltre 59.

        if self.abilitata and not giorni_normalizzati:  # Una pianificazione attiva deve indicare almeno un giorno settimanale.
            raise ValueError("Una pianificazione abilitata deve contenere almeno un giorno.")  # Evita pianificazioni attive che non possono scattare.

        if self.abilitata and not ora_normalizzata:  # Una pianificazione attiva deve avere anche un orario eseguibile.
            raise ValueError("Una pianificazione abilitata deve specificare un'ora nel formato HH:MM.")  # Evita configurazioni attive incomplete.

        self.giorni = giorni_normalizzati  # Pubblica la copia immutabile soltanto dopo la validazione completa.
        self.ora = ora_normalizzata  # Conserva l'orario normalizzato dopo averne verificato il formato.
        self.attiva_dal = attivazione_normalizzata  # Pubblica il limite temporale soltanto dopo averne completato la validazione.


@dataclass(slots=True)
class SorgenteBackup:
    """Descrive una singola sorgente appartenente a un job di backup."""

    percorso: Path  # Memorizza la cartella originale che dovrà essere elaborata dal motore di backup.
    nome_destinazione: str  # Memorizza il nome stabile della sottocartella assegnata a questa sorgente nella destinazione.
    id_sorgente: str = field(default_factory=genera_identificatore)  # Genera un ID distinto per ogni nuova sorgente.
    pianificazione: PianificazioneBackup = field(default_factory=PianificazioneBackup)  # Assegna a ogni sorgente una pianificazione indipendente e disabilitata di default.

    def __post_init__(self) -> None:
        """Normalizza i tipi di base senza verificare ancora l'esistenza reale dei percorsi."""
        self.percorso = Path(self.percorso)  # Converte anche eventuali stringhe ricevute dalla configurazione in oggetti Path.
        self.nome_destinazione = self.nome_destinazione.strip()  # Elimina spazi accidentali ai margini del nome logico.
        self.id_sorgente = self.id_sorgente.strip()  # Elimina spazi accidentali da un ID eventualmente caricato dalla configurazione.

        if not self.nome_destinazione:  # Verifica che la sorgente possieda un nome logico utilizzabile.
            raise ValueError("Il nome di destinazione della sorgente non può essere vuoto.")  # Impedisce di creare un modello ambiguo.

        if not self.id_sorgente:  # Verifica che l'identità persistente della sorgente sia presente.
            raise ValueError("L'identificatore della sorgente non può essere vuoto.")  # Impedisce modelli privi di identità stabile.

        if not isinstance(self.pianificazione, PianificazioneBackup):  # Impedisce di collegare dizionari o oggetti arbitrari direttamente al modello.
            raise TypeError("La pianificazione della sorgente deve essere un oggetto PianificazioneBackup.")  # Mantiene esplicito il contratto del modello.


@dataclass(slots=True)
class JobBackup:
    """Descrive un'attività di backup con una o più sorgenti e una sola destinazione."""

    nome: str  # Memorizza il nome leggibile mostrato all'utente nella schermata dei job.
    destinazione: Path  # Memorizza la cartella principale nella quale il job salverà le proprie sorgenti.
    sorgenti: list[SorgenteBackup] = field(default_factory=list)  # Crea una lista indipendente per ogni job, evitando default mutabili condivisi.
    abilitato: bool = True  # Permette di conservare un job configurato senza eseguirlo.
    id_job: str = field(default_factory=genera_identificatore)  # Genera un ID stabile indipendente dal nome e dai percorsi del job.
    includi_sottocartelle: bool = True  # Indica se il backup deve attraversare anche le sottocartelle delle sorgenti.
    verifica_integrita: bool = True  # Indica se il motore dovrà eseguire la verifica di integrità dopo la copia.

    def __post_init__(self) -> None:
        """Normalizza i tipi di base senza eseguire la validazione globale dei percorsi."""
        self.nome = self.nome.strip()  # Elimina spazi accidentali ai margini del nome visualizzato.
        self.destinazione = Path(self.destinazione)  # Converte anche eventuali stringhe provenienti dalla configurazione in Path.
        self.sorgenti = list(self.sorgenti)  # Copia la collezione ricevuta per evitare alias involontari con liste esterne.
        self.id_job = self.id_job.strip()  # Elimina spazi accidentali da un ID eventualmente ricaricato dalla configurazione.

        if not self.nome:  # Verifica che il job abbia un nome comprensibile per l'utente.
            raise ValueError("Il nome del job di backup non può essere vuoto.")  # Rifiuta job anonimi già a livello di modello.

        if not self.id_job:  # Verifica che il job mantenga sempre un'identità persistente.
            raise ValueError("L'identificatore del job di backup non può essere vuoto.")  # Rifiuta job senza identità stabile.

        if not isinstance(self.includi_sottocartelle, bool):  # Verifica che l'opzione di ricorsione sia un vero booleano.
            raise TypeError("L'opzione 'includi_sottocartelle' deve essere booleana.")  # Evita valori ambigui come stringhe o numeri.

        if not isinstance(self.verifica_integrita, bool):  # Verifica che l'opzione di controllo integrità sia un vero booleano.
            raise TypeError("L'opzione 'verifica_integrita' deve essere booleana.")  # Evita conversioni implicite che potrebbero cambiare il comportamento del backup.

        for sorgente in self.sorgenti:  # Controlla che la collezione contenga esclusivamente modelli sorgente validi.
            if not isinstance(sorgente, SorgenteBackup):  # Individua elementi di tipo errato prima che raggiungano il coordinatore.
                raise TypeError("Ogni elemento di 'sorgenti' deve essere un oggetto SorgenteBackup.")  # Fornisce un errore esplicito al chiamante.
