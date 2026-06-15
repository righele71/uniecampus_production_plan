import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configurazione della pagina Streamlit
st.set_page_config(page_title="AI Production Scheduler", layout="wide")

st.title("🏭 AI-Driven Production Scheduler - Versione Avanzata")
st.subheader("Master in AI for Business Administration - Ottimizzazione Vincolata")
st.markdown("Logica applicata: **Filtro AI Materiali → Coda Macchina EDD (Scadenze Protette) → Accorpamento Tondi → Calcolo Setup Recuperato**")

# ------------------------------------------------------------------------------
# 1. CARICAMENTO DATI
# ------------------------------------------------------------------------------
@st.cache_data
def load_data():
    try:
        ordini = pd.read_csv('1_ordini_produzione.csv')
        magazzino = pd.read_csv('2_magazzino_acquisti.csv')
        anagrafica = pd.read_csv('3_anagrafica_cicli.csv')
        operatori = pd.read_csv('4_storico_operatori.csv')
        return ordini, magazzino, anagrafica, operatori
    except Exception as e:
        st.error(f"Errore nel caricamento dei file CSV: {e}")
        return None, None, None, None

df_ordini, df_magazzino, df_anagrafica, df_operatori = load_data()

if df_ordini is not None:
    # Rilevamento automatico della colonna del materiale per evitare KeyError
    col_materiale_ordini = 'Codice_Materiale' if 'Codice_Materiale' in df_ordini.columns else 'Materiale_Richiesto'
    col_materiale_anagrafica = 'Codice_Materiale' if 'Codice_Materiale' in df_anagrafica.columns else 'Materiale_Richiesto'
    
    with st.expander("📊 Visualizza i Dati di Ingresso (Grezzi dal Gestionale)"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Ordini di Produzione in Coda:** {len(df_ordini)} righe")
            st.dataframe(df_ordini.head(5), use_container_width=True)
        with col2:
            st.markdown("**Stato Materiali e Previsioni AI:**")
            st.dataframe(df_magazzino.head(5), use_container_width=True)

    st.markdown("---")
    st.markdown("### ⚡ Azione di Pianificazione Ottimizzata")
    
    if st.button("🚀 ELABORA PIANO DI PRODUZIONE", type="primary"):
        with st.spinner("L'algoritmo sta ordinando le code e calcolando l'impatto dei setup..."):
            
            # --------------------------------------------------------------------------
            # FASE 1: FILTRO MATERIALI (AI PREVISIONI)
            # --------------------------------------------------------------------------
            df_merged = pd.merge(
                df_ordini, 
                df_magazzino[['Codice_Materiale', 'Stato_Disponibilita', 'Data_Previsione_AI_Ritardo']], 
                left_on=col_materiale_ordini, 
                right_on='Codice_Materiale', 
                how='left'
            ).drop(columns=['Codice_Materiale'] if col_materiale_ordini != 'Codice_Materiale' else [])
            
            ordini_bloccati = df_merged[df_merged['Stato_Disponibilita'].isin(['ESAURITO', 'IN_RITARDO'])].copy()
            ordini_superstiti = df_merged[~df_merged['Stato_Disponibilita'].isin(['ESAURITO', 'IN_RITARDO'])].copy()
            
            # Arricchiamo subito con i dati sui tempi standard dell'anagrafica cicli
            ordini_superstiti = pd.merge(
                ordini_superstiti,
                df_anagrafica[['Codice_Articolo', 'Tempo_Setup_Standard_Min', 'Tempo_Tornitura_Cad_Min']],
                on='Codice_Articolo',
                how='left'
            )
            
            # --------------------------------------------------------------------------
            # FASE 2: ORDINAMENTO E CODA MACCHINA (GARANZIA SCADENZE + ACCORPAMENTO PROTETTO)
            # --------------------------------------------------------------------------
            # Per evitare che l'accorpamento sballi le consegne, ordiniamo prima per Data Scadenza e Priorità.
            # L'algoritmo accorpa i tondi uguali solo se la data di scadenza è la medesima o se sono adiacenti nella coda critica.
            ordini_superstiti = ordini_superstiti.sort_values(
                by=['Macchina_Assegnata_Default', 'Data_Scadenza_Cliente', 'Priorita_Commerciale', col_materiale_ordini],
                ascending=[True, True, False, True]
            ).reset_index(drop=True)
            
            # Elenco finale degli ordini elaborati
            lista_ordini_finali = []
            
            # Simuliamo la linea temporale per ciascuna macchina partendo da oggi
            data_corrente_simulazione = datetime.now()
            
            # Raggruppiamo l'elaborazione fisica per ogni singola macchina
            macchine_presenti = ordini_superstiti['Macchina_Assegnata_Default'].dropna().unique()
            
            tempo_totale_recuperato_officina = 0
            
            for macchina in macchine_presenti:
                df_coda_macchina = ordini_superstiti[ordini_superstiti['Macchina_Assegnata_Default'] == macchina].copy().reset_index(drop=True)
                
                carico_cumulato_minuti = 0
                ultimo_materiale_lavorato = None
                
                for idx, row in df_coda_macchina.iterrows():
                    materiale_attuale = row[col_materiale_ordini]
                    
                    # Determinazione del centro di lavoro per associare l'operatore corretto
                    categoria_centro = 'TORNIO' if 'TORNO' in str(macchina) else ('TAGLIO' if 'TAGLIO' in str(macchina) else 'FRESA')
                    
                    # Cerca il miglior operatore per la macchina specifica basato sull'efficienza storica
                    filtro_op = df_operatori[
                        (df_operatori['Macchina_Specifica'] == macchina) & 
                        (df_operatori['Centro_Di_Lavoro'] == categoria_centro)
                    ]
                    
                    if not filtro_op.empty:
                        miglior_op = filtro_op.sort_values(by='Fattore_Efficienza_Storico', ascending=False).iloc[0]
                        nome_op = miglior_op['Nome_Operatore']
                        efficienza = miglior_op['Fattore_Efficienza_Storico']
                    else:
                        nome_op = "Operatore Standard"
                        efficienza = 1.0
                    
                    # Calcolo tempo puro di lavorazione del lotto rettificato per l'efficienza dell'operatore
                    tempo_lavorazione_puro = (row['Tempo_Tornitura_Cad_Min'] * row['Quantita_Da_Produrre']) / efficienza
                    
                    # Verifica accorpamento: se il materiale è lo stesso del lotto precedente sulla macchina, azzeriamo il setup
                    if ultimo_materiale_lavorato == materiale_attuale:
                        tempo_setup_effettivo = 0
                        tempo_recuperato = row['Tempo_Setup_Standard_Min']
                        tempo_totale_lotto = tempo_lavorazione_puro
                    else:
                        tempo_setup_effettivo = row['Tempo_Setup_Standard_Min']
                        tempo_recuperato = 0
                        tempo_totale_lotto = tempo_setup_effettivo + tempo_lavorazione_puro
                    
                    tempo_totale_recuperato_officina += tempo_recuperato
                    carico_cumulato_minuti += tempo_totale_lotto
                    
                    # Convertiamo il carico cumulato in giorni (assumendo turni standard di 8 ore lavorative al giorno)
                    giorni_lavorativi = carico_cumulato_minuti / (8 * 60)
                    data_fine_stimata = data_corrente_simulazione + timedelta(days=giorni_lavorativi)
                    
                    # Popoliamo i campi per l'output grafico
                    new_row = row.to_dict()
                    new_row['Operatore_Suggerito_AI'] = nome_op
                    new_row['Tempo_Totale_Min'] = round(tempo_totale_lotto, 1)
                    new_row['Tempo_Setup_Recuperato_Min'] = tempo_recuperato
                    new_row['Data_Fine_Prevista'] = data_fine_stimata.strftime('%Y-%m-%d')
                    new_row['In_Ritardo'] = new_row['Data_Fine_Prevista'] > row['Data_Scadenza_Cliente']
                    
                    lista_ordini_finali.append(new_row)
                    ultimo_materiale_lavorato = materiale_attuale
            
            df_pianificato_completo = pd.DataFrame(lista_ordini_finali)

        # ------------------------------------------------------------------------------
        # VISUALIZZAZIONE RISULTATI E KPI
        # ------------------------------------------------------------------------------
        st.success("Pianificazione e sequenziamento completati con successo!")
        
        # Dashboard KPI
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="✅ Ordini Schedulati", value=f"{len(df_pianificato_completo)} / {len(df_ordini)}")
        with kpi2:
            st.metric(label="🛑 Ordini Sospesi (Mancanza Materiale)", value=f"{len(ordini_bloccati)}")
        with kpi3:
            ritardi_rilevati = df_pianificato_completo['In_Ritardo'].sum() if len(df_pianificato_completo) > 0 else 0
            st.metric(label="⏱️ Tempo Totale Recuperato (Setup)", value=f"{int(tempo_totale_recuperato_officina)} min",
                      delta=f"{ritardi_rilevati} ordini in ritardo" if ritardi_rilevati > 0 else "Nessun ritardo generato",
                      delta_color="inverse" if ritardi_rilevati > 0 else "normal")

        # Funzione di stile per evidenziare le celle in rosso se l'ordine sballa la scadenza
        def evidenzia_scadenze_critiche(row):
            styles = [''] * len(row)
            if row['In_Ritardo']:
                idx_data = row.index.get_loc('Data_Fine_Prevista')
                styles[idx_data] = 'background-color: #fce8e6; color: #a51d24; font-weight: bold;'
            return styles

        # ------------------------------------------------------------------------------
        # VISUALIZZAZIONE SUDDIVISA PER MACCHINA
        # ------------------------------------------------------------------------------
        st.markdown("### 📋 Piani di Lavoro Sequenziali per Singola Macchina")
        st.markdown("_Il piano rispetta le date di consegna ed elimina i tempi di attrezzaggio duplicati solo quando consecutivo._")
        
        colonne_vista_officina = [
            'ID_Ordine', 'Codice_Articolo', 'Lotto', 'Quantita_Da_Produrre', 
            'Descrizione_Materiale', 'Operatore_Suggerito_AI', 'Tempo_Totale_Min', 
            'Tempo_Setup_Recuperato_Min', 'Data_Scadenza_Cliente', 'Data_Fine_Prevista'
        ]
        
        # Creiamo un tab grafico per ciascuna macchina presente in officina
        tabs_macchine = st.tabs(list(macchine_presenti))
        
        for i, macchina_id in enumerate(macchine_presenti):
            with tabs_macchine[i]:
                st.markdown(f"**Coda di Lavoro Corrente per il centro: `{macchina_id}`**")
                
                df_macchina_visualizza = df_pianificato_completo[df_pianificato_completo['Macchina_Assegnata_Default'] == macchina_id].copy()
                
                if not df_macchina_visualizza.empty:
                    # Isoliamo le colonne ed applichiamo lo stile
                    df_da_colorare = df_macchina_visualizza[colonne_vista_officina + ['In_Ritardo']].copy()
                    
                    df_styled = (df_da_colorare.style
                                 .apply(evidenzia_scadenze_critiche, axis=1)
                                 .hide(['In_Ritardo'], axis=1))
                    
                    st.dataframe(df_styled, use_container_width=True)
                else:
                    st.info("Nessun ordine schedulato per questa macchina.")

        # Visualizzazione degli ordini bloccati in coda materiali
        if len(ordini_bloccati) > 0:
            st.markdown("---")
            st.markdown("### 🛑 Avanzamento Bloccato da Approvvigionamento (Mancanza Stock / Ritardo AI)")
            st.dataframe(
                ordini_bloccati[['ID_Ordine', 'Codice_Articolo', 'Quantita_Da_Produrre', 'Descrizione_Materiale', 'Stato_Disponibilita', 'Data_Previsione_AI_Ritardo']], 
                use_container_width=True
            )
