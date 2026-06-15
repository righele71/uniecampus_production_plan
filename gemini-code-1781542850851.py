import streamlit as st
import pandas as pd
import numpy as np

# Configurazione della pagina Streamlit con layout ampio
st.set_page_config(page_title="AI Production Scheduler", layout="wide")

st.title("🏭 AI-Driven Production Scheduler")
st.subheader("Master in AI for Business Administration - Prototipo MVP")
st.markdown("Questo tool ottimizza la sequenza dei lavori in officina applicando le 3 regole in cascata: **Materiale Disponibile → Raggruppamento Tondi → Operatore più veloce**.")

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
    # Mostriamo una panoramica dei dati iniziali in delle tab espandibili
    with st.expander("📊 Visualizza i Dati di Ingresso (Grezzi dal Gestionale)"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Ordini di Produzione in Coda:** {len(df_ordini)} righe")
            st.dataframe(df_ordini.head(5), use_container_width=True)
        with col2:
            st.markdown("**Stato Materiali e Previsioni AI Ritardi:**")
            st.dataframe(df_magazzino.head(5), use_container_width=True)

    # ------------------------------------------------------------------------------
    # INTERFACCIA: IL BOTTONE DI OTTIMIZZAZIONE
    # ------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### ⚡ Azione di Pianificazione")
    
    if st.button("🚀 ELABORA PIANO DI PRODUZIONE OTTIMIZZATO", type="primary"):
        
with st.spinner("L'algoritmo sta analizzando i vincoli e ottimizzando la sequenza..."):
            
            # --------------------------------------------------------------------------
            # REGOLA 1: VERIFICA MATERIALE (Filtro AI) - CORRETTO
            # --------------------------------------------------------------------------
            # Usiamo left_on e right_on perché i due file usano nomi di colonna differenti
            df_merged = pd.merge(df_ordini, df_magazzino[['Codice_Materiale', 'Stato_Disponibilita', 'Data_Previsione_AI_Ritardo']], 
                                 left_on='Materiale_Richiesto', right_on='Codice_Materiale', how='left')
            
            # Identifichiamo gli ordini bloccati (materiale ESAURITO o IN_RITARDO secondo l'AI)
            ordini_bloccati = df_merged[df_merged['Stato_Disponibilita'].isin(['ESAURITO', 'IN_RITARDO'])].copy()
            ordini_superstiti = df_merged[~df_merged['Stato_Disponibilita'].isin(['ESAURITO', 'IN_RITARDO'])].copy()
            
            # --------------------------------------------------------------------------
            # REGOLA 2: RAGGRUPPA TONDI SIMILI (Minimizzazione Setup)
            # --------------------------------------------------------------------------
            # Ordiniamo i superstiti mettendo vicini i materiali identici (Descrizione_Materiale)
            # e usiamo la Data di Scadenza Cliente come criterio secondario per non generare ritardi commerciali
            ordini_ottimizzati = ordini_superstiti.sort_values(
                by=['Descrizione_Materiale', 'Data_Scadenza_Cliente', 'Priorita_Commerciale'], 
                ascending=[True, True, False]
            ).reset_index(drop=True)
            
            # --------------------------------------------------------------------------
            # REGOLA 3: ASSEGNAZIONE OPERATORE PIÙ VELOCE - OTTIMIZZATO
            # --------------------------------------------------------------------------
            ordini_ottimizzati = pd.merge(ordini_ottimizzati, 
                                          df_anagrafica[['Codice_Articolo', 'Tempo_Setup_Standard_Min', 'Tempo_Tornitura_Cad_Min', 'Ciclo_Fasi']], 
                                          on='Codice_Articolo', how='left')
            
            suggerimenti_operatori = []
            tempi_effettivi = []
            
            for idx, row in ordini_ottimizzati.iterrows():
                macchina = row['Macchina_Assegnata_Default']
                
                # Controllo robusto della categoria centro
                if 'TORNO' in str(macchina):
                    categoria_centro = 'TORNIO'
                elif 'TAGLIO' in str(macchina):
                    categoria_centro = 'TAGLIO'
                else:
                    categoria_centro = 'FRESA'
                
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
                
                tempo_teorico_lavoro = row['Tempo_Tornitura_Cad_Min'] * row['Quantita_Da_Produrre']
                tempo_effettivo_lavoro = tempo_teorico_lavoro / efficienza
                tempo_totale_stimato = row['Tempo_Setup_Standard_Min'] + tempo_effettivo_lavoro
                
                suggerimenti_operatori.append(nome_op)
                tempi_effettivi.append(round(tempo_totale_stimato, 1))
            
            ordini_ottimizzati['Operatore_Suggerito_AI'] = suggerimenti_operatori
            ordini_ottimizzati['Tempo_Totale_Stimato_Min'] = tempi_effettivi

        # ------------------------------------------------------------------------------
        # VISUALIZZAZIONE RISULTATI E KPI
        # ------------------------------------------------------------------------------
        st.success("Pianificazione elaborata con successo!")
        
        # Righe dei KPI in alto
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="✅ Ordini Pronti al Lancio", value=f"{len(ordini_ottimizzati)} / {len(df_ordini)}")
        with kpi2:
            st.metric(label="⚠️ Ordini Sospesi (Ritardo Materiale)", value=f"{len(ordini_bloccati)}", delta="- Materiale mancante", delta_color="inverse")
        with kpi3:
            cambi_setup_evitati = len(ordini_ottimizzati) - ordini_ottimizzati['Descrizione_Materiale'].nunique()
            st.metric(label="⏱️ Sequenze di Setup Ottimizzate", value=f"{cambi_setup_evitati}", help="Numero di lavori consecutivi che condividono lo stesso materiale evitando riattrezzaggi completi.")

        # Tabella Principale degli Ordini Ottimizzati
        st.markdown("### 📋 Sequenza di Produzione Ottimizzata (Piano del Giorno)")
        st.markdown("_I lavori sono ordinati per minimizzare i fermi macchina (Tondi simili vicini) e massimizzare la velocità._")
        
        # Pulizia colonne per visualizzazione pulita da mostrare al tutor
        vista_colonne = [
            'ID_Ordine', 'Codice_Articolo', 'Lotto', 'Quantita_Da_Produrre', 
            'Descrizione_Materiale', 'Macchina_Assegnata_Default', 'Operatore_Suggerito_AI',
            'Tempo_Totale_Stimato_Min', 'Data_Scadenza_Cliente', 'Priorita_Commerciale'
        ]
        
        st.dataframe(
            ordini_ottimizzati[vista_colonne].style.set_properties(**{'background-color': '#e6f4ea'}, subset=['Operatore_Suggerito_AI']),
            use_container_width=True
        )

        # Sezione Ordini Bloccati
        if len(ordini_bloccati) > 0:
            st.markdown("### 🛑 Ordini Sospesi (In attesa di Materiale)")
            st.markdown("_L'AI ha bloccato questi ordini perché ha previsto un ritardo reale nella consegna del fornitore._")
            
            vista_colonne_bloccati = [
                'ID_Ordine', 'Codice_Articolo', 'Quantita_Da_Produrre', 
                'Descrizione_Materiale', 'Stato_Disponibilita', 'Data_Previsione_AI_Ritardo', 'Data_Scadenza_Cliente'
            ]
            st.dataframe(
                ordini_bloccati[vista_colonne_bloccati].style.set_properties(**{'background-color': '#fce8e6'}, subset=['Stato_Disponibilita']),
                use_container_width=True
            )
else:
    st.info("In attesa che i file CSV siano presenti nella stessa cartella del progetto.")