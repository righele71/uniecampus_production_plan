import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configurazione della pagina Streamlit
st.set_page_config(page_title="AI Production Scheduler", layout="wide")

st.title("🏭 AI-Driven Production Scheduler (Scadenze Protette)")
st.subheader("Master in AI for Business Administration - Prototipo Avanzato")
st.markdown("Ottimizzazione vincolata: **Filtro AI Materiali → Sequenza Temporale di Consegna → Accorpamento Setup Dinamico → Operatore Ottimale**.")

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
    # Identificazione dinamica per prevenire KeyError sulle intestazioni dei materiali
    col_materiale_ordini = 'Codice_Materiale' if 'Codice_Materiale' in df_ordini.columns else 'Materiale_Richiesto'
    col_materiale_cicli = 'Codice_Materiale' if 'Codice_Materiale' in df_anagrafica.columns else 'Materiale_Richiesto'
    
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
        with st.spinner("Calcolo dell'euristica di sequenziamento e protezione scadenze..."):
            
            # --------------------------------------------------------------------------
            # REGOLA 1: FILTRO AI MATERIALI
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
            # REGOLA 2: ORDINAMENTO PER PROTEZIONE SCADENZE (Prima le Consegne Critiche)
            # --------------------------------------------------------------------------
            # Mettiamo in cima i lavori con priorità alta e scadenze più vicine per non sballare le date
            ordini_superstiti = ordini_superstiti.sort_values(
                by=['Data_Scadenza_Cliente', 'Priorita_Commerciale'], 
                ascending=[True, False]
            ).reset_index(drop=True)
            
            # Integrazione delle informazioni sui tempi standard dei cicli
            ordini_superstiti = pd.merge(
                ordini_superstiti, 
                df_anagrafica[['Codice_Articolo', 'Tempo_Setup_Standard_Min', 'Tempo_Tornitura_Cad_Min']], 
                on='Codice_Articolo', 
                how='left'
            )
            
            # --------------------------------------------------------------------------
            # REGOLA 3: CALCOLO CODA SEQUENZIALE MACCHINE, ACCORPAMENTO TONDI E OPERATORI
            # --------------------------------------------------------------------------
            suggerimenti_operatori = []
            tempi_totali_min = []
            minuti_recuperati = []
            date_fine_previste = []
            
            data_corrente_simulazione = datetime.now()
            
            # Dizionari per monitorare lo stato di ogni macchina durante la simulazione
            carico_macchine_minuti = {}
            ultimo_materiale_macchina = {} # Serve per capire se il tondo precedente era identico
            
            for idx, row in ordini_superstiti.iterrows():
                macchina = row['Macchina_Assegnata_Default']
                materiale_attuale = row[col_materiale_ordini]
                
                if macchina not in carico_macchine_minuti:
                    carico_macchine_minuti[macchina] = 0
                    ultimo_materiale_macchina[macchina] = None
                
                # Assegnazione Operatore Ottimale (Efficienza storica maggiore)
                categoria_centro = 'TORNIO' if 'TORNO' in str(macchina) else ('TAGLIO' if 'TAGLIO' in str(macchina) else 'FRESA')
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
                
                # Logica di Accorpamento Tondi: Verifichiamo se il tondo è lo stesso dell'ultimo lavoro fatto su QUELLA macchina
                tempo_setup_applicato = row['Tempo_Setup_Standard_Min']
                recupero = 0
                
                if ultimo_materiale_macchina[macchina] == materiale_attuale:
                    # Stesso tondo consecutivo! Azzeriamo il setup e calcoliamo il guadagno di tempo
                    recupero = tempo_setup_applicato
                    tempo_setup_applicato = 0
                
                # Calcolo durata effettiva del lotto
                tempo_lavorazione_teorico = row['Tempo_Tornitura_Cad_Min'] * row['Quantita_Da_Produrre']
                tempo_totale_lavoro = tempo_setup_applicato + (tempo_lavorazione_teorico / efficienza)
                
                # Aggiorniamo la coda temporale della macchina
                carico_macchine_minuti[macchina] += tempo_totale_lavoro
                ultimo_materiale_macchina[macchina] = materiale_attuale # Salvo il materiale come ultimo eseguito
                
                # Calcolo della Data Fine Stimata (assumendo turni di 8 ore lavorative al giorno)
                giorni_di_coda = carico_macchine_minuti[macchina] / (8 * 60)
                data_conclusione = data_corrente_simulazione + timedelta(days=giorni_di_coda)
                
                suggerimenti_operatori.append(nome_op)
                tempi_totali_min.append(round(tempo_totale_lavoro, 1))
                minuti_recuperati.append(round(recupero, 1))
                date_fine_previste.append(data_conclusione.strftime('%Y-%m-%d'))
            
            # Assegnazione delle liste calcolate al DataFrame finale
            ordini_superstiti['Operatore_Suggerito_AI'] = suggerimenti_operatori
            ordini_superstiti['Tempo_Totale_Min'] = tempi_totali_min
            ordini_superstiti['Minuti_Setup_Recuperati'] = minuti_recuperati
            ordini_superstiti['Data_Fine_Prevista'] = date_fine_previste
            
            # Generazione del flag di controllo ritardo per la formattazione
            ordini_superstiti['In_Ritardo'] = ordini_superstiti.apply(
                lambda r: r['Data_Fine_Prevista'] > r['Data_Scadenza_Cliente'], axis=1
            )

        # ------------------------------------------------------------------------------
        # INTERFACCIA GRAFICA: KPI E DATAFRAME FORMATTATO
        # ------------------------------------------------------------------------------
        st.success("Ottimizzazione completata bilanciando Setup e Scadenze!")
        
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="✅ Ordini Schedulati", value=f"{len(ordini_superstiti)} / {len(df_ordini)}")
        with kpi2:
            tot_minuti_salvati = ordini_superstiti['Minuti_Setup_Recuperati'].sum()
            st.metric(label="⏱️ Tempo di Setup Totale Risparmiato", value=f"{int(tot_minuti_salvati)} min", delta=f"+{(tot_minuti_sal
