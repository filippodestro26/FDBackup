import logging  # Importa il logging standard per registrare l'esecuzione coordinata dei job.
import threading  # Importa Event, già usato dal motore, per condividere lo stesso arresto cooperativo.
from dataclasses import dataclass, field  # Importa gli strumenti per rappresentare i risultati aggregati.
from pathlib import Path  # Importa Path per costruire le destinazioni effettive delle sorgenti.
from typing import Callable  # Importa Callable per descrivere la callback opzionale del coordinatore.

from fdbackup.modelli_backup import JobBackup, SorgenteBackup  # Importa i modelli persistenti dei job e delle sorgenti.
from fdbackup.motore_backup import MotoreBackup, RisultatoBackup  # Riutilizza il motore già verificato per ogni singola sorgente.
from fdbackup.validazione_backup import ValidatoreBackup  # Importa la validazione globale da eseguire prima della prima copia.


logger = logging.getLogger(__name__)  # Crea il logger del modulo, figlio del logger principale "fdbackup".


@dataclass(slots=True)
class RisultatoSorgenteBackup:
    """Raccoglie l'esito dell'esecuzione di una singola sorgente appartenente a un job."""

    id_sorgente: str  # Conserva l'identità persistente della sorgente.
    percorso_sorgente: Path  # Conserva il percorso sorgente realmente passato al motore.
    percorso_destinazione: Path  # Conserva la sottocartella di destinazione assegnata alla sorgente.
    risultato_backup: RisultatoBackup | None = None  # Conserva il risultato prodotto dal motore quando l'esecuzione è partita.
    errore_fatale: str | None = None  # Conserva un eventuale errore che ha impedito al motore di restituire un risultato.

    @property
    def successo(self) -> bool:
        """Restituisce True soltanto quando il motore ha prodotto un risultato completamente riuscito."""
        return self.risultato_backup is not None and self.risultato_backup.successo and self.errore_fatale is None  # Combina risultato del motore e assenza di errore fatale.

    @property
    def annullato(self) -> bool:
        """Restituisce True quando la singola operazione è stata annullata cooperativamente."""
        return self.risultato_backup is not None and self.risultato_backup.annullato  # Delega lo stato di annullamento al risultato del motore.


@dataclass(slots=True)
class RisultatoJobBackup:
    """Raccoglie gli esiti delle sorgenti effettivamente avviate per un singolo job."""

    id_job: str  # Conserva l'identità persistente del job.
    nome_job: str  # Conserva il nome leggibile del job.
    risultati_sorgenti: list[RisultatoSorgenteBackup] = field(default_factory=list)  # Conserva gli esiti delle sorgenti eseguite.
    annullato: bool = False  # Indica se l'esecuzione del job è stata interrotta da una richiesta di arresto.

    @property
    def successo(self) -> bool:
        """Restituisce True soltanto se il job non è annullato e tutte le sorgenti avviate sono riuscite."""
        return not self.annullato and bool(self.risultati_sorgenti) and all(risultato.successo for risultato in self.risultati_sorgenti)  # Valuta l'esito complessivo del job.


@dataclass(slots=True)
class RisultatoEsecuzioneBackup:
    """Raccoglie l'esito complessivo dell'esecuzione sequenziale di tutti i job abilitati."""

    risultati_job: list[RisultatoJobBackup] = field(default_factory=list)  # Conserva gli esiti dei job effettivamente avviati.
    annullato: bool = False  # Indica se l'esecuzione globale è stata fermata cooperativamente.

    @property
    def successo(self) -> bool:
        """Restituisce True soltanto se l'esecuzione non è annullata e tutti i job avviati sono riusciti."""
        return not self.annullato and bool(self.risultati_job) and all(risultato.successo for risultato in self.risultati_job)  # Combina gli esiti di tutti i job avviati.

    @property
    def sorgenti_eseguite(self) -> int:
        """Restituisce il numero totale di sorgenti che sono state effettivamente avviate."""
        return sum(len(risultato.risultati_sorgenti) for risultato in self.risultati_job)  # Somma le sorgenti registrate nei risultati dei job.


class GestoreBackup:
    """Coordina più job in modo sequenziale riutilizzando MotoreBackup per ogni sorgente."""

    def __init__(
        self,
        evento_arresto: threading.Event,
        funzione_avanzamento: Callable[[str, dict], None] | None = None,
    ) -> None:
        """Memorizza l'evento condiviso e la callback opzionale usata per notificare l'orchestrazione."""
        self.evento_arresto = evento_arresto  # Conserva lo stesso Event che verrà passato a ogni MotoreBackup.
        self.funzione_avanzamento = funzione_avanzamento  # Conserva la callback del livello superiore.

    def _notifica(self, evento: str, **dati) -> None:
        """Invia un evento al chiamante soltanto quando è stata fornita una callback."""
        if self.funzione_avanzamento is not None:  # Verifica che esista un destinatario degli eventi.
            self.funzione_avanzamento(evento, dati)  # Invia il nome dell'evento e il relativo dizionario.

    def _inoltra_evento_motore(
        self,
        job: JobBackup,
        sorgente: SorgenteBackup,
        evento: str,
        dati: dict,
    ) -> None:
        """Inoltra un evento del MotoreBackup aggiungendo il contesto del job e della sorgente."""
        self._notifica(  # Produce un unico evento del coordinatore per evitare collisioni con gli eventi propri del gestore.
            "evento_motore",
            id_job=job.id_job,
            nome_job=job.nome,
            id_sorgente=sorgente.id_sorgente,
            nome_destinazione=sorgente.nome_destinazione,
            evento_motore=evento,
            dati_motore=dati,
        )

    def _esegui_sorgente(
        self,
        job: JobBackup,
        sorgente: SorgenteBackup,
    ) -> RisultatoSorgenteBackup:
        """Esegue una singola sorgente tramite MotoreBackup e converte l'esito nel modello aggregato."""
        percorso_sorgente = ValidatoreBackup.normalizza_percorso(sorgente.percorso)  # Usa la stessa normalizzazione già applicata dalla validazione.
        destinazione_job = ValidatoreBackup.normalizza_percorso(job.destinazione)  # Normalizza la radice di destinazione del job.
        percorso_destinazione = destinazione_job / sorgente.nome_destinazione  # Costruisce la sottocartella stabile riservata alla sorgente.

        risultato_sorgente = RisultatoSorgenteBackup(  # Prepara il contenitore anche nel caso in cui il motore sollevi un errore fatale.
            id_sorgente=sorgente.id_sorgente,
            percorso_sorgente=percorso_sorgente,
            percorso_destinazione=percorso_destinazione,
        )

        self._notifica(  # Comunica l'avvio della singola sorgente prima di invocare il motore.
            "inizio_sorgente",
            id_job=job.id_job,
            nome_job=job.nome,
            id_sorgente=sorgente.id_sorgente,
            sorgente=str(percorso_sorgente),
            destinazione=str(percorso_destinazione),
        )

        try:  # Isola gli errori fatali di una sorgente per consentire la prosecuzione dei job successivi.
            motore = MotoreBackup(  # Crea un motore indipendente per la sorgente corrente.
                evento_arresto=self.evento_arresto,
                funzione_avanzamento=lambda evento, dati: self._inoltra_evento_motore(job, sorgente, evento, dati),
                includi_sottocartelle=job.includi_sottocartelle,  # Trasferisce al motore la scelta del job sulla scansione ricorsiva.
                verifica_integrita=job.verifica_integrita,  # Trasferisce al motore la scelta del job sulla verifica SHA-256 post-copia.
            )
            risultato_sorgente.risultato_backup = motore.esegui(percorso_sorgente, percorso_destinazione)  # Esegue il motore già verificato e conserva il suo risultato.

        except (OSError, ValueError) as errore:  # Gestisce gli errori previsti che possono sfuggire al ciclo interno del motore.
            risultato_sorgente.errore_fatale = f"{type(errore).__name__}: {errore}"  # Conserva tipo e messaggio dell'errore senza perdere informazione diagnostica.
            logger.error(  # Registra l'errore fatale nel logging persistente.
                "Errore fatale durante l'esecuzione della sorgente | job=%s | sorgente=%s | tipo=%s | errore=%s",
                job.nome,
                percorso_sorgente,
                type(errore).__name__,
                errore,
            )
            self._notifica(  # Comunica l'errore al livello superiore senza interrompere automaticamente gli altri job.
                "errore_fatale_sorgente",
                id_job=job.id_job,
                nome_job=job.nome,
                id_sorgente=sorgente.id_sorgente,
                sorgente=str(percorso_sorgente),
                errore=risultato_sorgente.errore_fatale,
            )

        self._notifica(  # Comunica sempre la conclusione della sorgente, riuscita, fallita o annullata.
            "fine_sorgente",
            id_job=job.id_job,
            nome_job=job.nome,
            id_sorgente=sorgente.id_sorgente,
            risultato=risultato_sorgente,
        )
        return risultato_sorgente  # Restituisce al coordinatore l'esito completo della sorgente.

    def esegui(self, job: list[JobBackup]) -> RisultatoEsecuzioneBackup:
        """Valida tutti i job e poi esegue sequenzialmente soltanto quelli abilitati."""
        ValidatoreBackup.valida_job_multipli(job)  # Esegue tutta la validazione globale prima di avviare la prima copia.
        risultato_esecuzione = RisultatoEsecuzioneBackup()  # Crea il contenitore dell'esito complessivo.
        job_abilitati = [singolo_job for singolo_job in job if singolo_job.abilitato]  # Mantiene l'ordine configurato escludendo i job disabilitati.

        logger.info("Esecuzione backup multipla avviata | job_abilitati=%d", len(job_abilitati))  # Registra l'avvio del coordinatore.
        self._notifica("inizio_esecuzione", numero_job=len(job_abilitati))  # Comunica quanti job verranno considerati.

        for singolo_job in job_abilitati:  # Esegue i job uno alla volta nell'ordine ricevuto.
            if self.evento_arresto.is_set():  # Controlla lo Stop prima di iniziare un nuovo job.
                risultato_esecuzione.annullato = True  # Registra l'annullamento globale.
                break  # Impedisce l'avvio dei job successivi.

            risultato_job = RisultatoJobBackup(id_job=singolo_job.id_job, nome_job=singolo_job.nome)  # Prepara il risultato del job corrente.
            risultato_esecuzione.risultati_job.append(risultato_job)  # Registra subito il job come effettivamente avviato.
            self._notifica("inizio_job", id_job=singolo_job.id_job, nome_job=singolo_job.nome)  # Comunica l'avvio del job.

            for sorgente in singolo_job.sorgenti:  # Esegue sequenzialmente le sorgenti configurate nel job.
                if self.evento_arresto.is_set():  # Controlla lo Stop prima di avviare ogni nuova sorgente.
                    risultato_job.annullato = True  # Registra l'annullamento del job corrente.
                    risultato_esecuzione.annullato = True  # Propaga lo stato al risultato globale.
                    break  # Impedisce l'avvio delle sorgenti successive.

                risultato_sorgente = self._esegui_sorgente(singolo_job, sorgente)  # Delega la singola cartella al MotoreBackup.
                risultato_job.risultati_sorgenti.append(risultato_sorgente)  # Conserva l'esito nell'ordine di esecuzione.

                if risultato_sorgente.annullato or self.evento_arresto.is_set():  # Rileva uno Stop osservato durante il lavoro del motore.
                    risultato_job.annullato = True  # Segna il job come annullato.
                    risultato_esecuzione.annullato = True  # Segna l'intera esecuzione come annullata.
                    break  # Non avvia altre sorgenti.

            self._notifica("fine_job", id_job=singolo_job.id_job, nome_job=singolo_job.nome, risultato=risultato_job)  # Comunica sempre la fine del job avviato.

            if risultato_esecuzione.annullato:  # Verifica se lo Stop è stato osservato nel job appena terminato.
                break  # Impedisce l'avvio dei job successivi.

        if risultato_esecuzione.annullato:  # Distingue nel log una conclusione richiesta dall'utente.
            logger.warning("Esecuzione backup multipla annullata | job_eseguiti=%d | sorgenti_eseguite=%d", len(risultato_esecuzione.risultati_job), risultato_esecuzione.sorgenti_eseguite)  # Registra il riepilogo dell'annullamento.
        else:  # Gestisce la conclusione normale dell'orchestrazione.
            logger.info("Esecuzione backup multipla terminata | job_eseguiti=%d | sorgenti_eseguite=%d | successo=%s", len(risultato_esecuzione.risultati_job), risultato_esecuzione.sorgenti_eseguite, risultato_esecuzione.successo)  # Registra il riepilogo finale.

        self._notifica("fine_esecuzione", risultato=risultato_esecuzione)  # Comunica sempre la conclusione del coordinatore.
        return risultato_esecuzione  # Restituisce tutti gli esiti aggregati al chiamante.
