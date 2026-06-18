import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="AI Production Planner - Optimizer", layout="wide")

st.title("🏭 Schedulatore e Ottimizzatore di Produzione")
st.write("Carica i file CSV per analizzare i ritardi e ottimizzare i tempi di attrezzaggio dei tondi.")

# --- CARICAMENTO DATI ---
# Utilizziamo i file caricati o permettiamo l'upload su Streamlit
col_f1, col_f2 = st.columns(2)
with col_f1:
    prod_file = st.file_uploader("Carica Lista Produzione (CSV)", type=["csv"])
with col_f2:
    mat_file = st.file_uploader("Carica Lista Materiali (CSV)", type=["csv"])

# Data di partenza della simulazione (Oggi)
DATA_INIZIO_PIANIFICAZIONE = datetime(2026, 6, 18)

if prod_file and mat_file:
    df_prod = pd.read_csv(prod_file)
    df_mat = pd.read_csv(mat_file)
    
    # Unione dei dati tramite Chiave Primaria: codice_articolo
    df_merge = pd.merge(df_prod, df_mat, on="codice_articolo", how="left")
    
    # Conversione date
    df_merge['data_consegna'] = pd.to_datetime(df_merge['data_consegna'])
    df_merge['data_consegna_materiale_ordinato'] = pd.to_datetime(df_merge['data_consegna_materiale_ordinato'])
    
    # Riempimento valori vuoti per materiali esistenti
    df_merge['materiale_esistente'] = df_merge['materiale_esistente'].fillna(0)
    df_merge['materiale_ordinato'] = df_merge['materiale_ordinato'].fillna(0)

    # --- TABELLA 2: MATERIALI NON ORDINATI ---
    # Identifichiamo subito gli articoli critici senza stock e senza ordine fornitore
    df_non_ordinati = df_merge[
        (df_merge['materiale_esistente'] <= 0) & 
        (df_merge['materiale_ordinato'] <= 0)
    ].copy()
    
    st.subheader("🚨 Criticità: Articoli senza Materiale e senza Ordine Fornitore")
    if not df_non_ordinati.empty:
        df_critici_visual = df_non_ordinati[[
            'numero_commessa', 'codice_articolo', 'codice_materiale', 
            'descrizione_materiale', 'centro_lavoro', 'data_consegna'
        ]].drop_duplicates()
        # Calcolo data stimata (es. 10 giorni lavorativi di lead time standard come stima)
        df_critici_visual['Data Consegna Stimata Materiale'] = DATA_INIZIO_PIANIFICAZIONE + timedelta(days=14)
        st.dataframe(df_critici_visual, use_container_width=True)
    else:
        st.success("Ottimo! Tutto il materiale mancante risulta almeno ordinato.")

    # --- BOTTONE DI OTTIMIZZAZIONE ---
    ottimizza = st.button("🚀 Ottimizza Produzione")

    # Prepariamo la base dati per la pianificazione ordinaria o ottimizzata
    df_lavorazione = df_merge.copy()
    
    # Calcolo disponibilità temporale del materiale
    # Se esiste stock la data è oggi, altrimenti è la data di arrivo dell'ordine
    df_lavorazione['materiale_disponibile_il'] = df_lavorazione.apply(
        lambda r: r['data_consegna_materiale_ordinato'] if r['materiale_esistente'] <= 0 and pd.notna(r['data_consegna_materiale_ordinato']) else DATA_INIZIO_PIANIFICAZIONE,
        axis=1
    )

    if ottimizza:
        st.subheader("📊 Programma di Produzione Ottimizzato per Macchina")
        
        # Algoritmo di Schedulazione con Vincolo di Consegna e Accorpamento Tondi
        # Ordiniamo prima per data consegna commessa (per non sballare le scadenze) e per disponibilità materiale
        df_lavorazione = df_lavorazione.sort_values(
            by=['data_consegna', 'materiale_disponibile_il', 'codice_materiale', 'fase_numero']
        ).reset_index(drop=True)
        
        elenco_macchine = df_lavorazione['centro_lavoro'].unique()
        
        for macchina in sorted(elenco_macchine):
            st.markdown(f"### 🖥️ Centro di Lavoro: {macchina}")
            df_macchina = df_lavorazione[df_lavorazione['centro_lavoro'] == macchina].copy().reset_index(drop=True)
            
            # Applicazione dell'accorpamento intelligente dei tondi sulla stessa macchina
            # Se la riga successiva usa lo stesso materiale e non viola la data di consegna, le avviciniamo
            i = 0
            while i < len(df_macchina) - 1:
                curr_mat = df_macchina.loc[i, 'codice_materiale']
                next_idx = i + 1
                
                # Cerchiamo se nelle prossime righe c'è lo stesso materiale accorpabile
                for j in range(i + 1, min(i + 4, len(df_macchina))): # Finestra di look-ahead corta per non violare le consegne
                    if df_macchina.loc[j, 'codice_materiale'] == curr_mat:
                        # Verifica che lo spostamento non causi un ritardo sulla commessa anticipata o posticipata
                        if df_macchina.loc[j, 'data_consegna'] >= df_macchina.loc[i, 'data_consegna']:
                            # Esegui lo shift/accorpamento nella coda della macchina
                            row_to_move = df_macchina.iloc[j].copy()
                            df_macchina = df_macchina.drop(j).reset_index(drop=True)
                            df_macchina = pd.concat([df_macchina.iloc[:i+1], pd.DataFrame([row_to_move]), df_macchina.iloc[i+1:]]).reset_index(drop=True)
                            break
                i += 1
            
            # Calcolo dei tempi e delle date presunte di conclusione sulla macchina
            orologio_macchina = DATA_INIZIO_PIANIFICAZIONE
            date_conclusione = []
            minuti_recuperati = []
            colore_riga = []
            
            ultimo_materiale = None
            
            for idx, row in df_macchina.iterrows():
                # Il lavoro può iniziare solo quando il materiale è fisicamente in officina
                if orologio_macchina < row['materiale_disponibile_il']:
                    orologio_macchina = row['materiale_disponibile_il']
                
                tempo_attr = row['tempo_attrezzatura_min']
                recuperato = 0
                riga_verde = False
                
                # Regola di accorpamento dei tondi
                if row['codice_materiale'] == ultimo_materiale:
                    recuperato = tempo_attr
                    tempo_attr = 0 # Tempo attrezzaggio azzerato
                    riga_verde = True
                
                durata_fase = tempo_attr + row['tempo_esecuzione_min']
                orologio_macchina += timedelta(minutes=int(durata_fase))
                
                date_conclusione.append(orologio_macchina)
                minuti_recuperati.append(recuperato)
                ultimo_materiale = row['codice_materiale']
                
                # Definizione colorazione di sfondo della riga
                if riga_verde:
                    colore_riga.append("background-color: #d4edda;") # Verde chiaro per attrezzaggio risparmiato
                elif row['materiale_esistente'] <= 0 and row['materiale_ordinato'] > 0:
                    colore_riga.append("background-color: #fff3cd;") # Giallo per materiale ordinato in arrivo
                else:
                    colore_riga.append("")

            df_macchina['Data Fine Lavorazione'] = date_conclusione
            df_macchina['Minuti Recuperati'] = minuti_recuperati
            df_macchina['Colore Background'] = colore_riga
            
            # Formattazione e visualizzazione condizionale delle celle (Testo Rosso per i ritardi)
            def style_row(row):
                styles = [row['Colore Background']] * len(row)
                # Se la data di fine lavoro supera la scadenza ordine, evidenzia in rosso il testo della data
                if row['Data Fine Lavorazione'] > row['data_consegna']:
                    styles[df_macchina.columns.get_loc('Data Fine Lavorazione')] = 'color: red; font-weight: bold;'
                return styles

            # Pulizia colonne per visualizzazione pulita
            visual_cols = [
                'numero_commessa', 'codice_articolo', 'descrizione_materiale', 
                'fase_numero', 'tempo_attrezzatura_min', 'tempo_esecuzione_min', 
                'data_consegna', 'Data Fine Lavorazione', 'Minuti Recuperati'
            ]
            
            df_styled = df_macchina[visual_cols].style.apply(style_row, axis=1)
            st.dataframe(df_styled, use_container_width=True)
            
            # Calcolo KPI per singola macchina
            tot_recuperato = df_macchina['Minuti Recuperati'].sum()
            st.info(f"💡 Su questa macchina sono stati recuperati in totale **{tot_recuperato} minuti** di attrezzaggio.")

    else:
        st.info("💡 Premi il bottone 'Ottimizza' per calcolare la sequenza ideale e analizzare i tempi risparmiati.")