import ast  # Importa il parser standard per verificare la struttura della GUI senza richiedere un display grafico.
import unittest  # Importa il framework di test standard già usato dal progetto.
from pathlib import Path  # Importa Path per individuare il file principale in modo indipendente dalla directory corrente.


PERCORSO_GUI = Path(__file__).resolve().parents[1] / "main.py"  # Individua la GUI reale appartenente allo stesso progetto dei test.


class TestIntegrazioneGuiAvanzata(unittest.TestCase):
    """Verifica i contratti strutturali dell'integrazione avanzata senza creare finestre Tk."""

    @classmethod
    def setUpClass(cls):
        """Analizza una sola volta il sorgente della GUI per tutti i controlli strutturali."""
        cls.testo = PERCORSO_GUI.read_text(encoding="utf-8")  # Legge esattamente il file che verrà distribuito all'utente.
        cls.albero = ast.parse(cls.testo)  # Richiede che l'intero sorgente sia sintatticamente valido prima delle asserzioni.
        cls.metodi = {nodo.name for nodo in ast.walk(cls.albero) if isinstance(nodo, ast.FunctionDef)}  # Indicizza le funzioni e i metodi definiti nel file.

    def test_sidebar_espone_strategie_e_sincronizzazione(self):
        """La navigazione deve rendere raggiungibili entrambe le nuove aree senza sostituire Backup e Ripristino."""
        for voce in ("Home", "Backup", "Strategie", "Sincronizza", "Ripristino", "Impostazioni", "Informazioni"):  # Elenca le sezioni che devono coesistere.
            self.assertIn(f'"{voce}"', self.testo)  # Verifica che ogni voce sia realmente presente nel sorgente distribuito.

    def test_gui_contiene_worker_separati_per_operazioni_avanzate(self):
        """Le operazioni avanzate devono restare fuori dal thread Tk e comunicare tramite worker dedicati."""
        richiesti = {"_worker_strategia_backup", "_worker_sincronizzazione", "_worker_ripristino_avanzato"}  # Definisce i worker che proteggono la responsività della GUI.
        self.assertTrue(richiesti.issubset(self.metodi))  # Richiede che tutti i worker siano definiti nella GUI reale.
        self.assertIn("self.coda_eventi.put", self.testo)  # Verifica che il trasferimento verso Tk utilizzi la coda thread-safe esistente.

    def test_mirror_richiede_conferma_esplicita(self):
        """La GUI deve avvertire l'utente prima di una sincronizzazione Mirror potenzialmente distruttiva."""
        self.assertIn("Conferma Mirror", self.testo)  # Richiede il dialogo specifico e non un avviso generico post-operazione.
        self.assertIn("può eliminare", self.testo)  # Richiede che il rischio di cancellazione sia dichiarato prima dell'avvio.

    def test_strategie_e_sincronizza_espongono_monitor_percentuale_e_attivita(self):
        """Entrambe le aree avanzate devono mostrare una percentuale determinata e un registro Attività."""
        self.assertIn('CTkProgressBar(riga_progresso, mode="determinate"', self.testo)  # Richiede una barra numericamente determinata.
        self.assertIn('text="Attività"', self.testo)  # Richiede il riquadro Attività nella nuova UI.
        self.assertIn('_crea_monitor_avanzato(scheda, "strategie", integrato=True)', self.testo)  # Verifica il monitor Strategie.
        self.assertIn('_crea_monitor_avanzato(scheda, "sincronizza", integrato=True)', self.testo)  # Verifica il monitor Sincronizza.

    def test_stato_avanzato_non_dipende_dalla_vita_del_worker_o_del_pannello(self):
        """La navigazione non deve azzerare stato, progresso e attività mentre Tk deve ancora finalizzare l'operazione."""
        self.assertIn("self.operazione_avanzata_in_corso", self.testo)  # Richiede un lifecycle esplicito separato da Thread.is_alive.
        self.assertIn("self.attivita_strategia", self.testo)  # Richiede un registro Strategie indipendente dal textbox.
        self.assertIn("self.attivita_sync", self.testo)  # Richiede un registro Sincronizza indipendente dal textbox.
        self.assertIn("_salva_stato_pannello_avanzato", self.metodi)  # Richiede la persistenza dei campi durante la navigazione.

    def test_pulsanti_avvio_avanzati_restano_leggibili_quando_disabilitati(self):
        """Il verde disabilitato non deve usare il testo attenuato predefinito di CustomTkinter."""
        self.assertGreaterEqual(self.testo.count('text_color_disabled="#FFFFFF"'), 2)  # Richiede testo bianco esplicito per Strategie e Sincronizza.

    def test_navigazione_non_blocca_durante_operazione(self):
        """Il cambio sezione deve restare disponibile mentre il lock impedisce soltanto una seconda operazione."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "cambia_modalita")
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""
        self.assertNotIn("Attendi il termine dell'operazione", testo_metodo)

    def test_attivita_avanzate_hanno_cancellazione_esplicita_e_scroll_locale(self):
        """Strategie, sincronizzazione e ripristino versionato devono conservare i log finché l'utente non li cancella."""
        self.assertIn("cancella_attivita_avanzata", self.metodi)
        self.assertIn("gestisci_scroll_testo_locale", self.metodi)
        self.assertNotIn("self.attivita_strategia.clear()  # Inizia un registro pulito", self.testo)
        self.assertNotIn("self.attivita_sync.clear()  # Inizia un registro pulito", self.testo)

    def test_attivita_avanzate_sono_persistite_anche_tra_riavvii(self):
        """I tre monitor avanzati devono usare un archivio su disco e non soltanto liste valide per la sessione corrente."""
        self.assertIn("carica_attivita_avanzate", self.testo)  # Richiede il caricamento dei registri all'avvio della GUI.
        self.assertIn("salva_attivita_avanzate", self.testo)  # Richiede il salvataggio dei registri durante l'uso.
        self.assertIn("FILE_ATTIVITA_AVANZATE", self.testo)  # Richiede un archivio separato dalla configurazione e dalla cronologia storica.
        self.assertIn("_salva_attivita_avanzate", self.metodi)  # Richiede un unico punto GUI per persistere coerentemente le tre sezioni.

    def test_file_attivita_avanzate_e_definito_prima_dell_uso(self):
        """Il percorso dei registri avanzati deve essere realmente assegnato a livello modulo prima di costruire la GUI."""
        assegnazioni = {
            bersaglio.id
            for nodo in self.albero.body
            if isinstance(nodo, (ast.Assign, ast.AnnAssign))
            for bersaglio in (nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target])
            if isinstance(bersaglio, ast.Name)
        }  # Raccoglie soltanto le variabili globali realmente definite, evitando un falso positivo dovuto alla semplice presenza testuale del nome.
        self.assertIn("FILE_ATTIVITA_AVANZATE", assegnazioni)  # Impedisce la regressione che causava NameError all'avvio reale della GUI.
        self.assertLess(self.testo.index("FILE_ATTIVITA_AVANZATE ="), self.testo.index("carica_attivita_avanzate(FILE_ATTIVITA_AVANZATE)"))  # Richiede che la costante venga definita prima del primo utilizzo.

    def test_popup_strategie_usa_lo_stesso_conteggio_eliminazioni_dell_attivita(self):
        """Il popup finale delle Strategie deve mostrare le tombstone del manifesto e non le cancellazioni fisiche del risultato."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "_concludi_operazione_avanzata")  # Individua il metodo che costruisce Attività e popup finali.
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""  # Estrae soltanto il codice interessato dal contratto.
        self.assertIn("eliminazioni_visualizzate =", testo_metodo)  # Richiede un conteggio semantico unico per Strategie e Sincronizza.
        self.assertIn("{etichetta_eliminazioni}: {eliminazioni_visualizzate}", testo_metodo)  # Richiede che anche il popup usi esattamente quel conteggio.

    def test_ripristino_versionato_espone_progresso_percentuale_e_attivita(self):
        """Il recupero di una versione deve avere un monitor separato e persistente."""
        for frammento in ("barra_ripristino_versionato", "percentuale_ripristino_versionato", "attivita_ripristino_versionato", "evento_ripristino_avanzato"):
            self.assertIn(frammento, self.testo)

    def test_banner_si_gestisce_dalla_home_e_si_mostra_globalmente(self):
        """I comandi di modifica appartengono alla Home mentre le altre viste ricevono il banner in sola lettura."""
        self.assertIn("_crea_banner_globale_sola_lettura", self.metodi)
        self.assertIn('text="Scegli banner"', self.testo)
        self.assertIn('text="Rimuovi banner"', self.testo)

    def test_reporting_backup_versionato_distingue_eliminazioni_registrate(self):
        """Le tombstone incrementali non devono essere presentate come cancellazioni fisiche."""
        self.assertIn("Eliminazioni registrate", self.testo)

    def test_ripristino_versionato_e_separato_dalle_strategie(self):
        """Il recupero di una versione deve vivere sotto Ripristino e non dentro la card Strategie."""
        self.assertIn("crea_centro_ripristino", self.metodi)
        self.assertIn("crea_ripristino_versionato", self.metodi)
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "crea_strategie_backup")
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""
        self.assertNotIn("Ripristino di una versione", testo_metodo)

    def test_scroll_attivita_propaga_quando_non_serve_scroll_locale(self):
        """La rotellina deve restare alla pagina quando il registro Attività è interamente visibile."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "gestisci_scroll_testo_locale")
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""
        self.assertIn("casella.yview()", testo_metodo)
        self.assertIn("return None", testo_metodo)

    def test_home_usa_comandi_compatti_allineati_a_destra(self):
        """I comandi Home devono restare compatti, separati e allineati a destra senza espandersi."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "crea_home")
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""
        self.assertNotIn('text="Home"', testo_metodo)
        self.assertIn('text="Scegli banner", width=120', testo_metodo)
        self.assertIn('text="Rimuovi banner", width=130', testo_metodo)
        self.assertIn('text="↻ Aggiorna", width=110', testo_metodo)
        self.assertGreaterEqual(testo_metodo.count('pack(side="right"'), 3)

    def test_ripristino_tradizionale_usa_la_navigazione_centrale(self):
        """Il tradizionale non deve avere un percorso grafico speciale diverso dalla vista Backup già verificata."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "apri_ripristino_tradizionale")  # Recupera il comando associato alla card del ripristino tradizionale.
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""  # Legge il codice effettivamente eseguito dal pulsante.
        self.assertIn('self.mostra_sezione("ripristino_tradizionale")', testo_metodo)  # Impone un unico percorso di navigazione invece della gestione manuale dei widget.
        nodo_mostra = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "mostra_sezione")  # Recupera il router grafico centrale.
        testo_mostra = ast.get_source_segment(self.testo, nodo_mostra) or ""  # Analizza il ramo operativo condiviso.
        self.assertIn('sezione in {"backup", "ripristino_tradizionale"}', testo_mostra)  # Backup e tradizionale devono condividere la stessa riapertura della vista persistente.
        self.assertIn('self.cambia_modalita(modalita_operativa, forza=sezione == "ripristino_tradizionale")', testo_mostra)  # Il tradizionale deve comunque forzare i propri testi e campi.

    def test_router_accetta_ripristino_tradizionale_come_sezione_operativa(self):
        """Il router deve riconoscere esplicitamente la sezione tradizionale e non farla ricadere nel pannello informativo."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "mostra_sezione")  # Recupera il router centrale della GUI.
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""  # Legge il ramo realmente distribuito nel programma.
        self.assertIn('"ripristino_tradizionale"', testo_metodo)  # Impone che la nuova destinazione sia ammessa tra le sezioni valide.
        self.assertIn('modalita_operativa = "backup" if sezione == "backup" else "ripristino"', testo_metodo)  # Verifica che il ramo tradizionale selezioni il motore storico di ripristino.
        self.assertIn('self.contenuto_principale.tkraise()', testo_metodo)  # Richiede che la vista operativa venga portata realmente in primo piano.

    def test_viste_backup_e_ripristino_riportano_scroll_in_alto(self):
        """Le viste operative persistenti non devono riapparire vuote a causa della vecchia posizione di scroll."""
        self.assertIn("_riporta_vista_operativa_in_alto", self.metodi)  # Richiede una correzione esplicita della posizione verticale.
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "_riporta_vista_operativa_in_alto")  # Recupera il metodo dedicato.
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""  # Legge il sorgente effettivo del metodo.
        self.assertIn("yview_moveto(0.0)", testo_metodo)  # Verifica che la vista venga realmente riportata all'inizio.
        nodo_mostra = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "mostra_sezione")  # Recupera il router che ora gestisce entrambe le viste operative.
        testo_mostra = ast.get_source_segment(self.testo, nodo_mostra) or ""  # Legge il relativo sorgente.
        self.assertIn("_riporta_vista_operativa_in_alto", testo_mostra)  # Impedisce regressioni dello scroll sia per Backup sia per Ripristino tradizionale.


    def test_ripristino_tradizionale_ha_pulsante_ritorno_al_centro_ripristino(self):
        """Il tradizionale deve offrire lo stesso ritorno ai tipi di ripristino disponibile nel versionato."""
        nodo_interfaccia = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "crea_interfaccia_principale")  # Recupera la costruzione della vista operativa persistente.
        testo_interfaccia = ast.get_source_segment(self.testo, nodo_interfaccia) or ""  # Legge il sorgente effettivamente distribuito.
        self.assertIn("pulsante_torna_tipi_ripristino", testo_interfaccia)  # Richiede un comando dedicato anche nella vista tradizionale.
        self.assertIn('self.mostra_sezione("ripristino")', testo_interfaccia)  # Il comando deve tornare al centro che permette di scegliere il tipo di ripristino.
        nodo_modalita = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "cambia_modalita")  # Recupera la gestione Backup/Ripristino della vista condivisa.
        testo_modalita = ast.get_source_segment(self.testo, nodo_modalita) or ""  # Analizza visibilità e posizionamento del comando.
        self.assertIn("self.pulsante_torna_tipi_ripristino.pack_forget()", testo_modalita)  # Il pulsante non deve comparire nella schermata Backup.
        self.assertIn('self.intestazione_operativa.pack(fill="x", padx=18, pady=(10, 4), after=self.etichetta_info_banner)', testo_modalita)  # Il titolo del tradizionale deve essere spostato sotto il banner globale.
        self.assertIn('self.pulsante_torna_tipi_ripristino.pack(anchor="w", padx=18, pady=(0, 10), after=self.intestazione_operativa)', testo_modalita)  # Il ritorno deve seguire immediatamente il titolo, come nel ripristino versionato.

    def test_pulsante_ritorno_tradizionale_non_si_estende_a_tutta_larghezza(self):
        """Il ritorno del tradizionale deve restare compatto come quello della pagina versionata."""
        nodo_modalita = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "cambia_modalita")  # Recupera il metodo che mostra il comando nella vista tradizionale.
        testo_modalita = ast.get_source_segment(self.testo, nodo_modalita) or ""  # Legge il sorgente distribuito per verificare il layout effettivo.
        riga_compatta = 'self.pulsante_torna_tipi_ripristino.pack(anchor="w", padx=18, pady=(0, 10), after=self.intestazione_operativa)'  # Definisce il posizionamento compatto richiesto dalla UI.
        self.assertIn(riga_compatta, testo_modalita)  # Impedisce che il pulsante torni ad occupare tutta la larghezza della pagina.
        self.assertNotIn('self.pulsante_torna_tipi_ripristino.pack(fill="x"', testo_modalita)  # Vieta esplicitamente la variante larga contestata nel test manuale.

    def test_ripristino_tradizionale_ordina_banner_titolo_ritorno_come_versionato(self):
        """Il tradizionale deve mostrare banner, titolo e ritorno nello stesso ordine visivo del ripristino versionato."""
        nodo_modalita = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "cambia_modalita")  # Recupera il metodo che riordina la vista operativa persistente.
        testo_modalita = ast.get_source_segment(self.testo, nodo_modalita) or ""  # Legge il codice distribuito per il layout del tradizionale.
        self.assertIn('after=self.etichetta_info_banner', testo_modalita)  # Impone che il titolo venga dopo banner e relative informazioni.
        self.assertIn('after=self.intestazione_operativa', testo_modalita)  # Impone che il pulsante venga subito dopo il titolo.
        self.assertNotIn('before=self.riquadro_banner)  # Mostra nel tradizionale', testo_modalita)  # Vieta il vecchio ordine titolo/pulsante prima del banner.

    def test_aggiorna_versioni_accetta_anche_cartella_singola_versione_e_da_feedback(self):
        """Il caricamento versioni deve correggere un livello selezionato troppo in basso e comunicare l'esito."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "carica_versioni_ripristino_gui")  # Recupera il caricatore GUI.
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""  # Legge il sorgente del caricatore.
        self.assertIn('(radice / ".backupcore-manifesto.json").is_file()', testo_metodo)  # Richiede il riconoscimento della cartella di una singola versione.
        self.assertIn("radice = radice.parent", testo_metodo)  # Richiede la normalizzazione alla radice comune.
        self.assertIn("Versioni disponibili:", testo_metodo)  # Richiede feedback positivo esplicito.
        self.assertIn("Nessuna versione valida trovata", testo_metodo)  # Richiede feedback negativo esplicito.

    def test_reporting_versionato_conta_tombstone_del_manifesto(self):
        """Il riepilogo Incrementale/Differenziale deve contare le eliminazioni logiche registrate nel manifesto."""
        nodo = next(n for n in ast.walk(self.albero) if isinstance(n, ast.FunctionDef) and n.name == "_concludi_operazione_avanzata")  # Recupera la finalizzazione comune.
        testo_metodo = ast.get_source_segment(self.testo, nodo) or ""  # Legge il sorgente effettivo.
        self.assertIn("len(risultato.manifesto.eliminati)", testo_metodo)  # Verifica che non venga riusato il contatore Mirror.
        self.assertIn("eliminazioni_visualizzate", testo_metodo)  # Richiede una variabile semanticamente distinta.

    def test_verifica_integrita_e_integrata_nel_centro_ripristino(self):
        """La GUI deve esporre la verifica come funzione separata senza sostituire i due motori di ripristino."""
        self.assertIn('text="Verifica integrità delle versioni"', self.testo)  # Richiede una card esplicita nel centro Ripristino.
        self.assertIn('self.mostra_sezione("verifica_integrita")', self.testo)  # Richiede una pagina dedicata raggiungibile dalla navigazione interna.
        self.assertIn('VerificatoreIntegritaAvanzata', self.testo)  # Richiede l’uso del backend verificato invece di duplicare l’hash nella GUI.

    def test_verifica_integrita_usa_worker_coda_stop_e_lock_condiviso(self):
        """La verifica non deve bloccare Tk né sovrapporsi a operazioni che possono modificare il repository."""
        self.assertIn('def _worker_verifica_integrita', self.testo)  # Richiede un worker separato dal thread Tk.
        self.assertIn('"evento_verifica_integrita"', self.testo)  # Richiede il passaggio degli aggiornamenti tramite la coda thread-safe.
        self.assertIn('if not self.acquisisci_blocco_operazione_manuale()', self.testo)  # Richiede il lock condiviso prima della lettura del repository.
        self.assertIn('command=self.richiedi_stop_avanzato', self.testo)  # Richiede lo Stop cooperativo già usato dalle operazioni avanzate.


if __name__ == "__main__":  # Consente anche l'esecuzione diretta del singolo modulo di test.
    unittest.main()  # Avvia unittest quando il file viene eseguito direttamente.

class TestRipristinoSelettivoGUI(unittest.TestCase):
    def test_gui_collega_selezione_al_backend(self):
        sorgente = Path(__file__).resolve().parents[1] / "main.py"
        testo = sorgente.read_text(encoding="utf-8")
        self.assertIn("campo_selezione_ripristino", testo)
        self.assertIn("selezione=selezione", testo)
        self.assertIn("percorsi relativi separati da ;", testo)
