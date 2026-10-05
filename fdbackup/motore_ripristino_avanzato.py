"""Ripristino delle versioni Full, Incrementali e Differenziali prodotte dal motore avanzato."""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fdbackup.metadati_backup_avanzato import ManifestoBackup, carica_manifesto, calcola_sha256, valida_percorso_relativo_manifesto


@dataclass(slots=True)
class RisultatoRipristinoAvanzato:
    """Raccoglie l'esito del ripristino di una versione avanzata."""

    file_ripristinati: int = 0  # Conta i file materializzati con successo nella destinazione.
    file_ignorati: int = 0  # Conta i conflitti conservati quando la sovrascrittura non è consentita.
    byte_ripristinati: int = 0  # Somma i byte effettivamente ripristinati.
    annullato: bool = False  # Indica un arresto cooperativo osservato dal motore.
    errori: list[str] = field(default_factory=list)  # Conserva gli errori incontrati durante il ripristino.

    @property
    def successo(self) -> bool:
        """Restituisce True soltanto per un ripristino concluso senza errori né annullamento."""
        return not self.annullato and not self.errori  # Considera riuscita anche una politica conservativa con file ignorati.


class MotoreRipristinoAvanzato:
    """Ricostruisce una versione selezionata seguendo in modo esplicito la relativa catena di manifesti."""

    def __init__(self, evento_arresto: threading.Event, funzione_avanzamento: Callable[[str, dict], None] | None = None) -> None:
        """Memorizza l'evento condiviso e la callback opzionale usata per notificare il progresso."""
        self.evento_arresto = evento_arresto  # Conserva lo stesso contratto di Stop usato dagli altri motori FDBackup.
        self.funzione_avanzamento = funzione_avanzamento  # Conserva il destinatario opzionale degli eventi senza introdurre dipendenze dalla GUI.

    def _notifica(self, evento: str, **dati) -> None:
        """Invia un evento di avanzamento soltanto quando il chiamante ha fornito una callback."""
        if self.funzione_avanzamento is not None:  # Evita lavoro aggiuntivo nei test e negli usi che non richiedono progresso.
            self.funzione_avanzamento(evento, dati)  # Inoltra un dizionario immutabile per contratto al chiamante.

    @staticmethod
    def _carica_indice(radice_versioni: Path) -> dict[str, tuple[ManifestoBackup, Path]]:
        """Indicizza tutte le versioni valide presenti nella radice indicata."""
        radice_versioni = Path(radice_versioni).expanduser().resolve(strict=True)  # Richiede una radice realmente esistente.
        if not radice_versioni.is_dir():  # Verifica che la radice sia una directory.
            raise ValueError("La radice delle versioni deve essere una cartella.")  # Rifiuta file e percorsi incompatibili.
        indice: dict[str, tuple[ManifestoBackup, Path]] = {}  # Prepara la mappa ID-versione necessaria a seguire le dipendenze.
        for manifesto_file in sorted((*radice_versioni.glob("*/.backupcore-manifesto.json"), *radice_versioni.glob("*/manifesto.json"))):  # Considera soltanto il layout ufficiale a un livello.
            manifesto = carica_manifesto(manifesto_file)  # Valida il documento prima di inserirlo nell'indice.
            if manifesto.id_backup in indice:  # Impedisce identità duplicate che renderebbero ambiguo il ripristino.
                raise ValueError(f"Identificatore di backup duplicato: {manifesto.id_backup}")  # Blocca una catena non deterministica.
            indice[manifesto.id_backup] = (manifesto, manifesto_file.parent)  # Associa manifesto e directory fisica della versione.
        return indice  # Restituisce tutte le versioni utilizzabili.

    @staticmethod
    def _costruisci_catena(indice: dict[str, tuple[ManifestoBackup, Path]], id_backup: str) -> list[tuple[ManifestoBackup, Path]]:
        """Costruisce la sequenza minima necessaria a ricostruire la versione richiesta."""
        if id_backup not in indice:  # Verifica che la versione richiesta sia disponibile.
            raise ValueError("La versione di backup richiesta non esiste.")  # Evita un ripristino parziale da dati mancanti.
        richiesto, percorso_richiesto = indice[id_backup]  # Recupera la versione selezionata dall'utente.
        if richiesto.tipo_backup == "completo":  # Un Full è autosufficiente.
            return [(richiesto, percorso_richiesto)]  # Restituisce una catena composta da una sola versione.
        if richiesto.tipo_backup == "differenziale":  # Un differenziale dipende soltanto dal Full originario.
            if richiesto.id_full_base not in indice:  # Verifica che il Full necessario sia disponibile.
                raise ValueError("Il Full richiesto dal backup differenziale non è disponibile.")  # Blocca una ricostruzione incompleta.
            full, percorso_full = indice[richiesto.id_full_base]  # Recupera la base dichiarata dal manifesto.
            if full.tipo_backup != "completo" or full.id_backup != full.id_full_base:  # Verifica che la dipendenza sia realmente una base Full autonoma.
                raise ValueError("La base del differenziale non è un backup completo valido.")  # Rifiuta catene corrotte.
            if full.sorgente != richiesto.sorgente:  # Richiede che base e differenziale descrivano la stessa sorgente normalizzata.
                raise ValueError("Il differenziale e il Full di base appartengono a sorgenti diverse.")  # Impedisce ricostruzioni ottenute incrociando repository incompatibili.
            return [(full, percorso_full), (richiesto, percorso_richiesto)]  # Applica Full e poi differenziale selezionato.
        catena_inversa: list[tuple[ManifestoBackup, Path]] = []  # Prepara la risalita dagli incrementali fino al Full.
        visitati: set[str] = set()  # Rileva eventuali cicli nei metadati corrotti.
        corrente = richiesto  # Inizia dalla versione incrementale richiesta.
        percorso_corrente = percorso_richiesto  # Conserva la directory fisica associata alla versione corrente.
        while True:  # Risale la catena finché incontra il Full.
            if corrente.id_backup in visitati:  # Controlla che la catena non contenga cicli.
                raise ValueError("La catena incrementale contiene un ciclo.")  # Evita loop e ricostruzioni ambigue.
            visitati.add(corrente.id_backup)  # Registra la versione come già visitata.
            catena_inversa.append((corrente, percorso_corrente))  # Conserva la versione corrente nella sequenza inversa.
            if corrente.tipo_backup == "completo":  # Riconosce il punto di origine valido della catena.
                break  # Termina la risalita.
            precedente = corrente.id_backup_precedente  # Recupera l'identità dichiarata della versione precedente.
            if not precedente or precedente not in indice:  # Verifica che la dipendenza sia disponibile.
                raise ValueError("La catena incrementale è incompleta.")  # Non tenta un ripristino da una catena spezzata.
            corrente, percorso_corrente = indice[precedente]  # Prosegue con la versione precedente effettivamente indicizzata.
        catena = list(reversed(catena_inversa))  # Riordina la sequenza dal Full alla versione selezionata.
        if catena[0][0].id_backup != richiesto.id_full_base or catena[0][0].tipo_backup != "completo":  # Verifica che l'origine raggiunta sia il Full dichiarato e realmente autonomo.
            raise ValueError("La catena incrementale non appartiene al Full dichiarato.")  # Rifiuta collegamenti incrociati incoerenti.
        if any(manifesto.sorgente != richiesto.sorgente for manifesto, _ in catena):  # Richiede la stessa sorgente normalizzata lungo l'intera catena.
            raise ValueError("La catena incrementale contiene versioni appartenenti a sorgenti diverse.")  # Impedisce l'unione accidentale o malevola di repository incompatibili.
        if any(manifesto.tipo_backup != "incrementale" for manifesto, _ in catena[1:]):  # Dopo il Full accetta soltanto delta Incrementali nella catena incrementale.
            raise ValueError("La catena incrementale contiene un tipo di backup incompatibile.")  # Rifiuta Differenziali o altri tipi inseriti tra i predecessori.
        return catena  # Restituisce la sequenza pronta per la materializzazione.

    def ripristina(self, radice_versioni: Path, id_backup: str, destinazione: Path, sovrascrivi: bool = False, selezione: list[str] | tuple[str, ...] | None = None) -> RisultatoRipristinoAvanzato:
        """Ripristina l'intera versione o una selezione di file/cartelle applicando Full e delta necessari."""
        if not isinstance(sovrascrivi, bool):  # Richiede una scelta esplicita e non valori truthy ambigui.
            raise TypeError("L'opzione di sovrascrittura deve essere booleana.")  # Mantiene il contratto del motore rigoroso.
        indice = self._carica_indice(radice_versioni)  # Carica tutte le versioni necessarie alla validazione delle dipendenze.
        catena = self._costruisci_catena(indice, id_backup.strip())  # Costruisce la sequenza minima e ne verifica la coerenza.
        destinazione = Path(destinazione).expanduser().resolve(strict=False)  # Normalizza la destinazione anche quando non esiste ancora.
        destinazione.mkdir(parents=True, exist_ok=True)  # Crea la radice del ripristino quando necessario.
        risultato = RisultatoRipristinoAvanzato()  # Prepara il riepilogo pubblico dell'operazione.
        manifesto_finale = catena[-1][0]  # Usa lo snapshot logico finale come autorità sui file che devono esistere.
        selezione_normalizzata: tuple[str, ...] | None = None  # Mantiene None per distinguere il ripristino completo da una selezione esplicita.
        if selezione is not None:  # Applica il filtro soltanto quando il chiamante richiede un recupero selettivo.
            if not isinstance(selezione, (list, tuple)) or not selezione:  # Richiede almeno un elemento esplicito e una collezione supportata.
                raise ValueError("La selezione di ripristino deve contenere almeno un file o una cartella.")  # Evita operazioni apparentemente riuscite ma prive di oggetti richiesti.
            selezione_normalizzata = tuple(dict.fromkeys(valida_percorso_relativo_manifesto(elemento.rstrip("/")) for elemento in selezione))  # Valida, normalizza e deduplica mantenendo l'ordine richiesto.
        def elemento_selezionato(relativo: str) -> bool:  # Centralizza la semantica file esatto oppure contenuto di una cartella selezionata.
            if selezione_normalizzata is None:  # Un ripristino completo include ogni elemento dello snapshot.
                return True  # Non applica filtri quando l'utente non ha richiesto una selezione.
            return any(relativo == elemento or relativo.startswith(elemento + "/") for elemento in selezione_normalizzata)  # Include il file esatto o i discendenti della cartella richiesta.
        file_finali = {relativo: metadati for relativo, metadati in manifesto_finale.file.items() if elemento_selezionato(relativo)}  # Riduce lo snapshot ai soli file richiesti.
        cartelle_finali = tuple(relativo for relativo in manifesto_finale.cartelle if elemento_selezionato(relativo) or (selezione_normalizzata is not None and any(elemento.startswith(relativo + "/") for elemento in selezione_normalizzata)))  # Conserva cartelle selezionate e antenati necessari.
        if selezione_normalizzata is not None and not file_finali and not cartelle_finali:  # Verifica che almeno un oggetto della selezione esista nello snapshot finale.
            raise ValueError("La selezione richiesta non esiste nella versione di backup scelta.")  # Evita un falso successo su percorsi inesistenti.
        totale_byte = sum(metadati.dimensione for metadati in file_finali.values())  # Calcola il totale logico limitato alla selezione effettiva.
        byte_elaborati = 0  # Conta i byte dei file già gestiti, copiati oppure conservati per politica.
        self._notifica("inizio_ripristino", totale_file=len(file_finali), totale_byte=totale_byte)  # Comunica alla GUI il denominatore della selezione prima della materializzazione.
        for relativo in cartelle_finali:  # Ricrea le directory pertinenti, comprese quelle vuote esplicitamente selezionate.
            (destinazione / Path(relativo)).mkdir(parents=True, exist_ok=True)  # Materializza idempotentemente la struttura prima dei file.
        origine_per_file: dict[str, Path] = {}  # Associa ogni file finale alla versione più recente che ne contiene materialmente i dati.
        for manifesto, cartella_versione in catena:  # Applica logicamente ogni versione nell'ordine corretto.
            for relativo in manifesto.eliminati:  # Rimuove dalla mappa logica i file eliminati in quella versione.
                origine_per_file.pop(relativo, None)  # Ignora eliminazioni già assenti senza generare errori.
            dati = cartella_versione / "dati"  # Identifica la directory che contiene i payload della versione.
            for relativo in manifesto.file:  # Considera tutti i file noti nello snapshot della versione.
                candidato = dati / Path(relativo)  # Costruisce l'eventuale payload materializzato nella versione corrente.
                if candidato.is_file():  # Aggiorna l'origine soltanto quando questa versione contiene realmente il file.
                    origine_per_file[relativo] = candidato  # Fa prevalere il payload più recente disponibile nella catena.
        mancanti = sorted(set(file_finali) - set(origine_per_file))  # Individua esattamente i payload necessari alla selezione che non sono materializzabili.
        if mancanti:  # Blocca soltanto quando manca un dato effettivamente richiesto dal ripristino corrente.
            raise ValueError(f"La catena non contiene tutti i dati necessari al ripristino: {', '.join(mancanti)}")  # Evita ripristini selettivi o completi dichiarati validi senza tutti i payload necessari.
        for relativo in sorted(file_finali):  # Ripristina i file selezionati in ordine deterministico.
            if self.evento_arresto.is_set():  # Controlla lo Stop prima di iniziare un nuovo file.
                risultato.annullato = True  # Registra l'interruzione cooperativa.
                break  # Non avvia altre copie dopo lo Stop.
            origine = origine_per_file[relativo]  # Recupera il payload corretto dalla catena validata.
            arrivo = destinazione / Path(relativo)  # Costruisce il percorso finale richiesto.
            try:  # Isola i problemi del singolo file.
                if arrivo.exists() and not sovrascrivi:  # Applica la politica conservativa predefinita.
                    if arrivo.is_file() and calcola_sha256(arrivo) == file_finali[relativo].sha256:  # Riconosce un file già identico alla versione richiesta.
                        risultato.file_ignorati += 1  # Conta il file già corretto senza copiarlo nuovamente.
                        byte_elaborati += file_finali[relativo].dimensione  # Considera completato anche un file già identico.
                        self._notifica("avanzamento_ripristino", file=relativo, byte_elaborati=byte_elaborati, totale_byte=totale_byte)  # Aggiorna la barra senza ricopiare dati inutilmente.
                        continue  # Passa al file successivo.
                    risultato.file_ignorati += 1  # Conserva un conflitto differente quando la sovrascrittura è disabilitata.
                    byte_elaborati += file_finali[relativo].dimensione  # Avanza sul lavoro logico anche quando la politica conserva il conflitto.
                    self._notifica("avanzamento_ripristino", file=relativo, byte_elaborati=byte_elaborati, totale_byte=totale_byte)  # Mantiene determinata la progressione complessiva.
                    continue  # Non modifica il file esistente.
                arrivo.parent.mkdir(parents=True, exist_ok=True)  # Prepara la gerarchia di destinazione.
                shutil.copy2(origine, arrivo)  # Copia contenuto e metadati supportati dal filesystem.
                if calcola_sha256(arrivo) != file_finali[relativo].sha256:  # Verifica il contenuto rispetto allo snapshot finale atteso.
                    raise IOError(f"Verifica SHA-256 fallita per '{relativo}'.")  # Non dichiara riuscito un file differente dal manifesto.
                risultato.file_ripristinati += 1  # Conta il file soltanto dopo la verifica riuscita.
                risultato.byte_ripristinati += arrivo.stat().st_size  # Somma la dimensione effettivamente materializzata.
                byte_elaborati += file_finali[relativo].dimensione  # Avanza soltanto dopo copia e verifica riuscite.
                self._notifica("avanzamento_ripristino", file=relativo, byte_elaborati=byte_elaborati, totale_byte=totale_byte)  # Comunica il progresso determinato al chiamante.
            except OSError as errore:  # Raccoglie errori di copia, permessi e verifica.
                risultato.errori.append(f"{relativo}: {type(errore).__name__}: {errore}")  # Conserva una diagnostica completa.
        return risultato  # Restituisce l'esito finale del ripristino.
