import os  # Importa le funzioni del sistema operativo usate per confrontare i percorsi secondo le regole della piattaforma.
import ntpath  # Importa esplicitamente le regole dei percorsi Windows, piattaforma di destinazione attuale di FDBackup.
from pathlib import Path  # Importa Path per rappresentare e normalizzare i percorsi dei job.

from fdbackup.modelli_backup import JobBackup, SorgenteBackup  # Importa i modelli reali già verificati dal progetto.


class ValidatoreBackup:
    """Valida i job prima dell'esecuzione senza modificare il filesystem."""

    @staticmethod
    def normalizza_percorso(percorso: Path) -> Path:
        """Normalizza un percorso con la stessa strategia già usata dal MotoreBackup."""
        return Path(percorso).expanduser().resolve(strict=False)  # Espande la home e risolve il percorso per quanto possibile senza richiederne l'esistenza.

    @staticmethod
    def chiave_percorso(percorso: Path) -> str:
        """Restituisce una rappresentazione confrontabile secondo le regole del sistema operativo."""
        percorso_normalizzato = ValidatoreBackup.normalizza_percorso(percorso)  # Normalizza il percorso prima del confronto.
        return os.path.normcase(str(percorso_normalizzato))  # Su Windows rende coerenti maiuscole/minuscole e separatori.

    @staticmethod
    def stesso_percorso(primo_percorso: Path, secondo_percorso: Path) -> bool:
        """Restituisce True quando due percorsi normalizzati rappresentano lo stesso percorso logico."""
        return ValidatoreBackup.chiave_percorso(primo_percorso) == ValidatoreBackup.chiave_percorso(secondo_percorso)  # Confronta le chiavi normalizzate.

    @staticmethod
    def contenuto_in(percorso_figlio: Path, percorso_genitore: Path) -> bool:
        """Restituisce True quando il primo percorso è strettamente contenuto nel secondo."""
        figlio = ValidatoreBackup.normalizza_percorso(percorso_figlio)  # Normalizza il possibile percorso figlio.
        genitore = ValidatoreBackup.normalizza_percorso(percorso_genitore)  # Normalizza il possibile percorso genitore.

        if ValidatoreBackup.stesso_percorso(figlio, genitore):  # Esclude intenzionalmente il caso di uguaglianza.
            return False  # Un percorso uguale non viene considerato un discendente stretto.

        try:  # Prova a calcolare il percorso relativo del figlio rispetto al genitore.
            figlio.relative_to(genitore)  # Solleva ValueError quando i percorsi non hanno la relazione richiesta.
            return True  # Conferma che il percorso è contenuto nel genitore.
        except ValueError:  # Gestisce anche percorsi appartenenti a radici o drive differenti.
            return False  # Indica che non esiste una relazione di contenimento.

    @staticmethod
    def _valida_nome_destinazione(sorgente: SorgenteBackup) -> None:
        """Verifica che il nome logico della sorgente rappresenti una sola sottocartella sicura."""
        nome = sorgente.nome_destinazione  # Recupera il nome persistente assegnato alla sorgente.
        percorso_nome = Path(nome)  # Interpreta il nome con le regole della piattaforma corrente.

        if nome in {".", ".."}:  # Blocca i riferimenti alla cartella corrente o genitore.
            raise ValueError("Il nome di destinazione della sorgente deve identificare una singola sottocartella.")  # Evita l'uscita dalla radice del job.

        if "/" in nome or "\\" in nome:  # Rifiuta esplicitamente entrambi i separatori prima degli altri controlli per produrre un errore preciso.
            raise ValueError("Il nome di destinazione della sorgente non può contenere separatori di percorso.")  # Impedisce nomi come cartella/sotto o cartella\sotto.

        if percorso_nome.is_absolute() or percorso_nome.name != nome:  # Rifiuta percorsi assoluti o nomi contenenti componenti di percorso residui.
            raise ValueError("Il nome di destinazione della sorgente deve identificare una singola sottocartella.")  # Mantiene ogni sorgente confinata nella propria sottocartella.

        if ntpath.isreserved(nome):  # Applica le regole Windows per nomi DOS, caratteri riservati, controlli ASCII e terminazioni non valide.
            raise ValueError(f"Il nome di destinazione '{nome}' è riservato o non valido su Windows.")  # Evita configurazioni che Windows non può creare in modo affidabile.

    @classmethod
    def valida_job(cls, job: JobBackup) -> None:
        """Valida completamente un singolo job prima che venga eseguito."""
        if not isinstance(job, JobBackup):  # Verifica che il chiamante abbia fornito il modello previsto.
            raise TypeError("Ogni job deve essere un oggetto JobBackup.")  # Blocca strutture arbitrarie prima della validazione.

        if not job.abilitato:  # Ignora i job conservati in configurazione ma esplicitamente disabilitati.
            return  # Un job disabilitato non partecipa all'esecuzione e non deve bloccarla.

        if not job.sorgenti:  # Verifica che un job eseguibile possieda almeno una sorgente.
            raise ValueError(f"Il job '{job.nome}' non contiene alcuna sorgente.")  # Evita job privi di lavoro da eseguire.

        destinazione = cls.normalizza_percorso(job.destinazione)  # Normalizza la destinazione principale del job.

        if destinazione.exists() and not destinazione.is_dir():  # Controlla che una destinazione esistente sia una directory.
            raise ValueError(f"La destinazione del job '{job.nome}' esiste ma non è una cartella.")  # Evita di usare un file come radice del backup.

        chiavi_sorgenti: set[str] = set()  # Memorizza le sorgenti già incontrate per individuare duplicati.
        nomi_destinazione: set[str] = set()  # Memorizza i nomi logici già assegnati nel job.
        sorgenti_normalizzate: list[tuple[SorgenteBackup, Path]] = []  # Conserva le sorgenti normalizzate per i controlli incrociati.

        for sorgente in job.sorgenti:  # Valida ogni sorgente configurata nel job.
            if not isinstance(sorgente, SorgenteBackup):  # Difende il validatore anche da modelli alterati dopo la costruzione.
                raise TypeError("Ogni sorgente del job deve essere un oggetto SorgenteBackup.")  # Rifiuta elementi arbitrari.

            cls._valida_nome_destinazione(sorgente)  # Verifica che il nome logico non possa uscire dalla radice di destinazione.
            percorso_sorgente = cls.normalizza_percorso(sorgente.percorso)  # Normalizza il percorso reale della sorgente.

            if not percorso_sorgente.exists():  # Verifica che la sorgente sia disponibile al momento dell'avvio.
                raise ValueError(f"La sorgente '{percorso_sorgente}' del job '{job.nome}' non esiste.")  # Blocca l'esecuzione prima di copiare file.

            if not percorso_sorgente.is_dir():  # Verifica che la sorgente sia realmente una cartella.
                raise ValueError(f"La sorgente '{percorso_sorgente}' del job '{job.nome}' deve essere una cartella.")  # Rifiuta file usati come sorgente.

            chiave_sorgente = cls.chiave_percorso(percorso_sorgente)  # Costruisce la chiave confrontabile della sorgente.

            if chiave_sorgente in chiavi_sorgenti:  # Controlla se la stessa sorgente è stata configurata due volte.
                raise ValueError(f"Il job '{job.nome}' contiene la stessa sorgente più di una volta: '{percorso_sorgente}'.")  # Evita copie duplicate.

            chiavi_sorgenti.add(chiave_sorgente)  # Registra la sorgente come già vista.

            chiave_nome = os.path.normcase(sorgente.nome_destinazione)  # Normalizza il nome secondo le regole della piattaforma.

            if chiave_nome in nomi_destinazione:  # Verifica che due sorgenti non scrivano nella stessa sottocartella logica.
                raise ValueError(f"Il job '{job.nome}' contiene nomi di destinazione duplicati: '{sorgente.nome_destinazione}'.")  # Evita collisioni tra sorgenti.

            nomi_destinazione.add(chiave_nome)  # Registra il nome logico come già utilizzato.

            destinazione_sorgente = destinazione / sorgente.nome_destinazione  # Costruisce la sottocartella effettiva assegnata alla sorgente.

            if cls.stesso_percorso(percorso_sorgente, destinazione_sorgente):  # Controlla l'uguaglianza con la destinazione effettiva della sorgente.
                raise ValueError(f"La sorgente '{percorso_sorgente}' coincide con la propria destinazione nel job '{job.nome}'.")  # Impedisce l'autocopia.

            if cls.contenuto_in(destinazione_sorgente, percorso_sorgente):  # Verifica che la destinazione effettiva non cada dentro la sorgente.
                raise ValueError(f"La destinazione della sorgente '{percorso_sorgente}' si trova all'interno della sorgente stessa.")  # Evita ricorsione del backup dentro se stesso.

            if cls.stesso_percorso(percorso_sorgente, destinazione) or cls.contenuto_in(percorso_sorgente, destinazione):  # Verifica che il job non legga dalla propria radice di backup o da una sua sottocartella.
                raise ValueError(f"La sorgente '{percorso_sorgente}' si trova all'interno della destinazione del proprio job '{job.nome}'.")  # Evita che un job utilizzi il proprio albero di backup come sorgente.

            sorgenti_normalizzate.append((sorgente, percorso_sorgente))  # Conserva la sorgente per i controlli tra coppie.

        for indice, (_, prima_sorgente) in enumerate(sorgenti_normalizzate):  # Scorre ogni sorgente una sola volta come primo elemento della coppia.
            for _, seconda_sorgente in sorgenti_normalizzate[indice + 1:]:  # Confronta soltanto le sorgenti successive evitando coppie duplicate.
                if cls.contenuto_in(prima_sorgente, seconda_sorgente) or cls.contenuto_in(seconda_sorgente, prima_sorgente):  # Rileva sorgenti annidate in entrambe le direzioni.
                    raise ValueError(f"Il job '{job.nome}' contiene sorgenti annidate tra loro: '{prima_sorgente}' e '{seconda_sorgente}'.")  # Evita duplicazioni e semantica ambigua.

    @classmethod
    def valida_job_multipli(cls, job: list[JobBackup]) -> None:
        """Valida l'insieme dei job abilitati e le loro relazioni globali."""
        for singolo_job in job:  # Esegue prima la validazione completa di ciascun job.
            cls.valida_job(singolo_job)  # Riutilizza il contratto del singolo job.

        identificatori_job: set[str] = set()  # Memorizza gli ID persistenti di tutti i job configurati.
        identificatori_sorgenti: set[str] = set()  # Memorizza gli ID persistenti di tutte le sorgenti configurate.

        for singolo_job in job:  # Verifica le identità sull'intera configurazione, indipendentemente dallo stato abilitato.
            if singolo_job.id_job in identificatori_job:  # Controlla se due job condividono la stessa identità persistente.
                raise ValueError(f"Più job utilizzano lo stesso identificatore: '{singolo_job.id_job}'.")  # Evita identità ambigue anche nei job temporaneamente disabilitati.
            identificatori_job.add(singolo_job.id_job)  # Registra l'identificatore del job come già utilizzato.

            for sorgente in singolo_job.sorgenti:  # Controlla anche l'identità persistente di ogni sorgente configurata.
                if sorgente.id_sorgente in identificatori_sorgenti:  # Rileva una sorgente con ID già assegnato altrove.
                    raise ValueError(f"Più sorgenti utilizzano lo stesso identificatore: '{sorgente.id_sorgente}'.")  # Impedisce collisioni nella persistenza e nella futura GUI.
                identificatori_sorgenti.add(sorgente.id_sorgente)  # Registra l'identificatore della sorgente.

        job_abilitati = [singolo_job for singolo_job in job if singolo_job.abilitato]  # Esclude i job disabilitati soltanto dai conflitti di esecuzione e filesystem.

        for indice, primo_job in enumerate(job_abilitati):  # Scorre ogni job una sola volta come primo elemento della coppia.
            prima_destinazione = cls.normalizza_percorso(primo_job.destinazione)  # Normalizza la destinazione del primo job.

            for secondo_job in job_abilitati[indice + 1:]:  # Confronta soltanto i job successivi.
                seconda_destinazione = cls.normalizza_percorso(secondo_job.destinazione)  # Normalizza la destinazione del secondo job.

                if cls.stesso_percorso(prima_destinazione, seconda_destinazione):  # Blocca due job che condividono la stessa radice di destinazione.
                    raise ValueError(f"I job '{primo_job.nome}' e '{secondo_job.nome}' utilizzano la stessa destinazione.")  # Evita scritture concorrenti o semanticamente ambigue.

                if cls.contenuto_in(prima_destinazione, seconda_destinazione) or cls.contenuto_in(seconda_destinazione, prima_destinazione):  # Rileva destinazioni annidate.
                    raise ValueError(f"Le destinazioni dei job '{primo_job.nome}' e '{secondo_job.nome}' sono annidate tra loro.")  # Evita sovrapposizioni tra radici di backup.

                for prima_sorgente in primo_job.sorgenti:  # Confronta le sorgenti del primo job con la destinazione del secondo.
                    percorso_prima_sorgente = cls.normalizza_percorso(prima_sorgente.percorso)  # Normalizza la sorgente del primo job.

                    if cls.stesso_percorso(percorso_prima_sorgente, seconda_destinazione) or cls.contenuto_in(percorso_prima_sorgente, seconda_destinazione) or cls.contenuto_in(seconda_destinazione, percorso_prima_sorgente):  # Rileva sovrapposizioni in entrambe le direzioni.
                        raise ValueError(f"La sorgente '{percorso_prima_sorgente}' del job '{primo_job.nome}' si sovrappone alla destinazione del job '{secondo_job.nome}'.")  # Impedisce catene di backup pericolose.

                for seconda_sorgente in secondo_job.sorgenti:  # Confronta simmetricamente le sorgenti del secondo job con la destinazione del primo.
                    percorso_seconda_sorgente = cls.normalizza_percorso(seconda_sorgente.percorso)  # Normalizza la sorgente del secondo job.

                    if cls.stesso_percorso(percorso_seconda_sorgente, prima_destinazione) or cls.contenuto_in(percorso_seconda_sorgente, prima_destinazione) or cls.contenuto_in(prima_destinazione, percorso_seconda_sorgente):  # Rileva sovrapposizioni in entrambe le direzioni.
                        raise ValueError(f"La sorgente '{percorso_seconda_sorgente}' del job '{secondo_job.nome}' si sovrappone alla destinazione del job '{primo_job.nome}'.")  # Blocca una configurazione globale ambigua.
