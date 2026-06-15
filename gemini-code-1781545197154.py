import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configurazione della pagina Streamlit
st.set_page_config(page_title="AI Production Scheduler", layout="wide")

st.title("🏭 AI-Driven Production Scheduler")
st.subheader("Master in AI for Business Administration - Prototipo Avanzato")
st.markdown("Ottimizzazione in tempo reale: **Materiali (Filtro AI) → Raggruppamento Tondi → Efficienza Operatori → Controllo Scadenze**.")

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
    # Identificazione automatica del nome della colonna per evitare KeyError
    col_materiale_ordini = 'Codice_Materiale' if 'Codice_Materiale' in df_ordini.columns else 'Materiale_Richiesto'
    
    with st.expander("📊 Visualizza i Dati di Ingresso (Grezzi dal Gestionale)"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Ordini di Produzione in Coda:** {len(df_ordini)} righe")
            st.dataframe(df_ordini.head(5), use_container_width=True)
        with col2:
            st.markdown("**Stato Materiali e Previsioni AI:**")
            st.dataframe(df_magazzino.head(5), use_container_width=True)

    st.markdown("---")
    st.markdown("### ⚡ Azione di Pianificazione")
    
    if st.button("🚀 ELABORA PIANO DI PRODUZIONE OTTIMIZZATO", type="primary"):
        with st.spinner("L'algoritmo sta analizzando i vincoli e calcolando i tempi di consegna..."):
            
            # --------------------------------------------------------------------------
            # REGOLA 1: FILTRO MATERIALI
            # --------------------------------------------------------------------------
            df_merged = pd.merge(
                df_ordini, 
                df_magazzino[['Codice_Materiale', 'Stato_Disponibilita', 'Data_Previsione_AI_Ritardo']], 
                left_on=col_materiale_ordini, 
                right_on='Codice_Materiale', 
                how='left'
            )
            
            ordini_bloccati = df_merged[df_merged['Stato_Disponibilita'].isin(['ESAURITO', 'IN_RITARDO'])].copy()
            ordini_superstiti = df_merged[~df_merged['Stato_Disponibilita'].isin(['ESAURITO', 'IN_RITARDO'])].copy()
            
            # --------------------------------------------------------------------------
            # REGOLA 2: RAGGRUPPA TONDI SIMILI
            # --------------------------------------------------------------------------
            ordini_ottimizzati = ordini_superstiti.sort_values(
                by=['Descrizione_Materiale', 'Data_Scadenza_Cliente', 'Priorita_Commerciale'], 
                ascending=[True, True, False]
            ).reset_index(drop=True)
            
            # --------------------------------------------------------------------------
            # REGOLA 3: ASSEGNAZIONE OPERATORE & CALCOLO TEMPI / DATE
            # --------------------------------------------------------------------------
            ordini_ottimizzati = pd.merge(
                ordini_ottimizzati, 
                df_anagrafica[['Codice_Articolo', 'Tempo_Setup_Standard_Min', 'Tempo_Tornitura_Cad_Min']], 
                on='Codice_Articolo', 
                how='left'
            )
            
            suggerimenti_operatori = []
            tempi_totali_min = []
            date_fine_previste = []
            
            # Simuliamo che la produzione parta da oggi
            data_corrente_simulazione = datetime.now()
            
            # Tracciamento del carico cumulativo per ogni singola macchina (coda sequenziale)
            carico_macchine_minuti = {}
            
            for idx, row in ordini_ottimizzati.iterrows():
                macchina = row['Macchina_Assegnata_Default']
                if macchina not in carico_macchine_minuti:
                    carico_macchine_minuti[macchina] = 0
                
                categoria_centro = 'TORNIO' if 'TORNO' in str(macchina) else ('TAGLIO' if 'TAGLIO' in str(macchina) else 'FRESA')
                
                # Ricerca del miglior operatore disponibile per la macchina
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
                
                # Calcolo tempo totale per il lotto (Setup + Lavorazione/Efficienza)
                tempo_teorico = row['Tempo_Tornitura_Cad_Min'] * row['Quantita_Da_Produrre']
                tempo_totale_lavoro = row['Tempo_Setup_Standard_Min'] + (tempo_teorico / efficienza)
                
                # Avanzamento della coda sulla macchina specifica
                carico_macchine_minuti[macchina] += tempo_totale_lavoro
                
                # Conversione in giorni lavorativi (assumendo turni da 8 ore al giorno)
                giorni_da_aggiungere = carico_macchine_minuti[macchina] / (8 * 60)
                data_conclusione = data_corrente_simulazione + timedelta(days=giorni_da_aggiungere)
                
                suggerimenti_operatori.append(nome_op)
                tempi_totali_min.append(round(tempo_totale_lavoro, 1))
                date_fine_previste.append(data_conclusione.strftime('%Y-%m-%d'))
            
            ordini_ottimizzati['Operatore_Suggerito_AI'] = suggerimenti_operatori
            ordini_ottimizzati['Tempo_Totale_Min'] = tempi_totali_min
            ordini_ottimizzati['Data_Fine_Prevista'] = date_fine_previste
            
            # Verifica ritardo rispetto alla scadenza contrattuale del cliente
            ordini_ottimizzati['In_Ritardo'] = ordini_ottimizzati.apply(
                lambda r: r['Data_Fine_Prevista'] > r['Data_Scadenza_Cliente'], axis=1
            )

        # ------------------------------------------------------------------------------
        # VISUALIZZAZIONE RISULTATI E KPI
        # ------------------------------------------------------------------------------
        st.success("Pianificazione completata!")
        
        # Dashboard KPI
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="✅ Ordini Pronti al Lancio", value=f"{len(ordini_ottimizzati)} / {len(df_ordini)}")
        with kpi2:
            st.metric(label="🛑 Ordini Sospesi (Mancanza Materiale)", value=f"{len(ordini_bloccati)}")
        with kpi3:
            ritardi_totali = ordini_ottimizzati['In_Ritardo'].sum()
            st.metric(label="⚠️ Ordini in Ritardo su Scadenza", value=f"{ritardi_totali}", 
                      delta=f"{ritardi_totali} criticità" if ritardi_totali > 0 else "Tutto nei tempi",
                      delta_color="inverse" if ritardi_totali > 0 else "normal")

        # Funzione interna per applicare il colore rosso alle celle in ritardo
        def evidenzia_ritardi(row):
            styles = [''] * len(row)
            if row['In_Ritardo']:
                idx_data = row.index.get_loc('Data_Fine_Prevista')
                styles[idx_data] = 'background-color: #fce8e6; color: #a51d24; font-weight: bold;'
            return styles

        # Tabelle Risultati
        st.markdown("### 📋 Sequenza di Productione Ottimizzata (Piano del Giorno)")
        st.markdown("_Nota: Le celle nella colonna **Data Fine Prevista** sono evidenziate in **rosso** se il lavoro termina dopo la Scadenza Cliente._")
        
        vista_colonne = [
            'ID_Ordine', 'Codice_Articolo', 'Lotto', 'Quantita_Da_Produrre', 
            'Descrizione_Materiale', 'Macchina_Assegnata_Default', 'Operatore_Suggerito_AI', 
            'Tempo_Totale_Min', 'Data_Scadenza_Cliente', 'Data_Fine_Prevista'
        ]
        
        # Creiamo una copia del dataframe circoscritta alle colonne di interesse + colonna logica
        df_da_visualizzare = ordini_ottimizzati[vista_colonne + ['In_Ritardo']].copy()
        
        # Applichiamo lo stile condizionale e nascondiamo la colonna logica usando i metodi nativi di Styler
        df_styled = (df_da_visualizzare.style
                     .apply(evidenzia_ritardi, axis=1)
                     .hide(['In_Ritardo'], axis=1))
        
        st.dataframe(df_styled, use_container_width=True)

        if len(ordini_bloccati) > 0:
            st.markdown("### 🛑 Ordini Sospesi (In attesa di Materiale)")
            st.dataframe(ordini_bloccati[['ID_Ordine', 'Codice_Articolo', 'Quantita_Da_Produrre', 'Descrizione_Materiale', 'Stato_Disponibilita', 'Data_Previsione_AI_Ritardo']], use_container_width=True)
