import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re

st.set_page_config(page_title="Ottimizzatore Produzione AI", layout="wide")
st.title("⚙️ Sistema di Pianificazione e Ottimizzazione Avanzata")

# Funzione per estrarre il tipo di tondo (Materiale + Diametro) dalla descrizione
def estrai_tipo_tondo(desc):
    if pd.isna(desc):
        return "Sconosciuto"
    # Cerca pattern tipo "TONDO AISI316 Ø40" o simili
    match = re.search(r'(TONDO\s+[^\s]+)\s+(Ø\d+)', str(desc), re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2)}".upper()
    return str(desc).strip().upper()

# Caricamento file nella barra laterale
st.sidebar.header("Caricamento Dati Input (CSV)")
file_ordini = st.sidebar.file_uploader("1_ordini_produzione.csv", type="csv")
file_magazzino = st.sidebar.file_uploader("2_magazzino_acquisti.csv", type="csv")
file_cicli = st.sidebar.file_uploader("3_anagrafica_cicli.csv", type="csv")
file_operatori = st.sidebar.file_uploader("4_storico_operatori.csv", type="csv")

if file_ordini and file_magazzino and file_cicli and file_operatori:
    
    # Lettura dataframe
    df_ordini = pd.read_csv(file_ordini)
    df_magazzino = pd.read_csv(file_magazzino)
    df_cicli = pd.read_csv(file_cicli)
    df_operatori = pd.read_csv(file_operatori)
    
    st.success("Tutti i file sono stati caricati correttamente!")
    
    if st.button("🚀 Ottimizza Piano di Produzione"):
        
        # --- PRE-ELABORAZIONE E MERGE ---
        # Pulizia date
        df_ordini['Data_Scadenza_Cliente'] = pd.to_datetime(df_ordini['Data_Scadenza_Cliente'])
        df_magazzino['Data_Previsione_AI_Ritardo'] = pd.to_datetime(df_magazzino['Data_Previsione_AI_Ritardo'])
        df_magazzino['Data_Consegna_Fornitore'] = pd.to_datetime(df_magazzino['Data_Consegna_Fornitore'])
        
        # Estrazione tondo per accorpamenti
        df_ordini['Tipo_Tondo'] = df_ordini['Descrizione_Materiale'].apply(estrai_tipo_tondo)
        
        # Unione con anagrafica cicli per i tempi unitari
        df_master = df_ordini.merge(df_cicli, on='Codice_Articolo', how='left', suffixes=('', '_ciclo'))
        # Unione con magazzino
        df_master = df_master.merge(df_magazzino, left_on='Materiale_Richiesto', right_on='Codice_Materiale', how='left')
        
        # Calcolo tempi totali di lavorazione per riga (Tornitura + Taglio + Fresa) in minuti
        df_master['Tempo_Lavorazione_Totale_Min'] = (
            df_master['Quantita_Da_Produrre'] * (
                df_master['Tempo_Tornitura_Cad_Min'].fillna(0) + 
                df_master['Tempo_Taglio_Cad_Min'].fillna(0) + 
                df_master['Tempo_Fresa_Cad_Min'].fillna(0)
            )
        )
        
        # --- DIVISIONE CATEGORIE ORDINI ---
        # 1. Materiale NON Ordinato (Bloccati)
        df_non_ordinati = df_master[df_master['Stato_Disponibilita'] == 'ESAURITO'].copy()
        
        # 2. Materiale in Ritardo/In Arrivo (Gialli)
        df_in_arrivo = df_master[df_master['Stato_Disponibilita'].isin(['IN_RITARDO', 'IN_TEMPO'])].copy()
        
        # 3. Materiale Disponibile Subito (Pronti)
        df_pronti = df_master[df_master['Stato_Disponibilita'] == 'DISPONIBILE'].copy()
        
        # --- SIMULAZIONE E SCHEDULAZIONE SU MACCHINE ---
        data_inizio_simulazione = datetime(2026, 6, 16, 8, 0) # Assumiamo data odierna di simulazione
        
        # Trova miglior operatore per macchina di default (basato su TORNIO)
        # Sceglie l'operatore con Fattore_Efficienza_Storico più alto
        best_ops = df_operatori[df_operatori['Centro_Di_Lavoro'] == 'TORNIO'].sort_values('Fattore_Efficienza_Storico', ascending=False)
        
def assegna_operatore_efficienza(macchina):
            op_match = best_ops[best_ops['Macchina_Specifica'] == macchina]
            if not op_match.empty:
                return op_match.iloc[0]['Nome_Operatore'], op_match.iloc[0]['Fattore_Efficienza_Storico']
            return "Operatore Standard", 1.0

        # RIGHE COINVOLTE (Ora perfettamente allineate con il "def" sopra):
        elenchi_macchine = {}
        
        # Lista di tutte le macchine uniche presenti
        macchine = df_master['Macchina_Assegnata_Default'].dropna().unique()
        
        for m in macchine:
            # Ordini pronti ordinati per data scadenza (EDD) per garantire le consegne
            m_pronti = df_pronti[df_pronti['Macchina_Assegnata_Default'] == m].sort_values('Data_Scadenza_Cliente').to_dict('records')
            # Ordini con materiale in arrivo (ordinati prima per disponibilità materiale, poi scadenza)
            m_arrivo = df_in_arrivo[df_in_arrivo['Macchina_Assegnata_Default'] == m].sort_values(['Data_Previsione_AI_Ritardo', 'Data_Scadenza_Cliente']).to_dict('records')
            
            coda_totale = m_pronti + m_arrivo
            if not coda_totale:
                continue
                
            op_nome, op_eff = assegna_operatore_efficienza(m)
            
            tempo_corrente = data_inizio_simulazione
            ultimo_tondo = None
            risultati_macchina = []
            
            for i, ordine in enumerate(coda_totale):
                # Se materiale non è ancora disponibile, la macchina attende l'arrivo del tondo
                if pd.notna(ordine['Data_Previsione_AI_Ritardo']) and tempo_corrente < ordine['Data_Previsione_AI_Ritardo']:
                    tempo_corrente = ordine['Data_Previsione_AI_Ritardo']
                
                # Applica fattore efficienza operatore al tempo di lavorazione
                tempo_lavorazione_effettivo = ordine['Tempo_Lavorazione_Totale_Min'] / op_eff
                tempo_setup = ordine['Tempo_Setup_Standard_Min'] if pd.notna(ordine['Tempo_Setup_Standard_Min']) else 90
                
                accorpato = False
                minuti_recuperati = 0
                
                # Logica di accorpamento condizionale: stesso tondo del precedente?
                if ultimo_tondo and ordine['Tipo_Tondo'] == ultimo_tondo:
                    # Ipotizziamo di azzerare il setup
                    tempo_senza_setup = tempo_corrente + timedelta(minutes=tempo_lavorazione_effettivo)
                    
                    # Verifica cautelativa: sballa la data di questo ordine?
                    if tempo_senza_setup <= ordine['Data_Scadenza_Cliente']:
                        tempo_setup = 0
                        accorpato = True
                        minuti_recuperati = 90
                
                # Calcolo fine lavoro effettivo
                tempo_fine = tempo_corrente + timedelta(minutes=tempo_setup + tempo_lavorazione_effettivo)
                
                # Controllo Ritardo
                ritardo = tempo_fine > ordine['Data_Scadenza_Cliente']
                
                risultati_macchina.append({
                    'ID_Ordine': ordine['ID_Ordine'],
                    'Codice_Articolo': ordine['Codice_Articolo'],
                    'Tipo_Tondo': ordine['Tipo_Tondo'],
                    'Quantita': ordine['Quantita_Da_Produrre'],
                    'Operatore_Assegnato': op_nome,
                    'Efficienza': op_eff,
                    'Stato_Materiale': ordine['Stato_Disponibilita'],
                    'Scadenza_Contrattuale': ordine['Data_Scadenza_Cliente'].strftime('%Y-%m-%d'),
                    'Data_Fine_Prevista': tempo_fine,
                    'Ritardo': ritardo,
                    'Accorpato': accorpato,
                    'Minuti_Recuperati': minuti_recuperati
                })
                
                # Avanzamento tempo e tracciamento ultimo tondo lavorato sulla macchina
                tempo_corrente = tempo_fine
                ultimo_tondo = ordine['Tipo_Tondo']
                
            elenchi_macchine[m] = pd.DataFrame(risultati_macchina)
        
        # --- VISUALIZZAZIONE RISULTATI ---
        
        st.subheader("📋 Programmazione Carichi di Lavoro per Singola Macchina")
        
        for mac, df_res in elenchi_macchine.items():
            st.markdown(f"### 🖥️ Centro di Lavoro: **{mac}**")
            
            # Funzione di stile per applicare i colori richiesti alle righe
            def style_rows(row):
                styles = [''] * len(row)
                # 1. Colore Giallo per materiale in arrivo/ritardo AI
                if row['Stato_Materiale'] in ['IN_RITARDO', 'IN_TEMPO']:
                    return ['background-color: #fff9c4; color: black;'] * len(row)
                # 2. Colore Verde Chiaro per riga accorpata (risparmio attrezzaggio)
                if row['Accorpato']:
                    return ['background-color: #e8f5e9; color: black;'] * len(row)
                # 3. Testo data fine lavoro in rosso se in ritardo sulla scadenza ordine
                return styles

            # Applichiamo una formattazione specifica per la colonna Data Fine se in ritardo
            def evidenzia_data_ritardo(val, ritardo):
                if ritardo:
                    return f'<span style="color: red; font-weight: bold;">{val.strftime("%Y-%m-%d %H:%M")} ⚠️</span>'
                return val.strftime("%Y-%m-%d %H:%M")

            df_display = df_res.copy()
            df_display['Data_Fine_Prevista_Str'] = df_display.apply(lambda r: evidenzia_data_ritardo(r['Data_Fine_Prevista'], r['Ritardo']), axis=1)
            
            # Riordino e rinomina colonne per l'utente
            df_display = df_display[['ID_Ordine', 'Codice_Articolo', 'Tipo_Tondo', 'Quantita', 'Operatore_Assegnato', 'Efficienza', 'Scadenza_Contrattuale', 'Data_Fine_Prevista_Str', 'Minuti_Recuperati', 'Stato_Materiale', 'Accorpato']]
            
            styled_df = df_display.style.apply(style_rows, axis=1)
            st.write(styled_df.to_html(escape=False), unsafe_allow_html=True)
            st.markdown("---")
            
        # --- TABELLA CODICI MATERIALE NON ORDINATO ---
        st.subheader("⚠️ Ordini Bloccati - Materiale Non Ordinato (Giacenza Esaurita)")
        if not df_non_ordinati.empty:
            df_bloccati_display = df_non_ordinati[['ID_Ordine', 'Codice_Articolo', 'Materiale_Richiesto', 'Descrizione_Materiale', 'Quantita_Da_Produrre', 'Data_Scadenza_Cliente']].copy()
            df_bloccati_display['Data_Consegna_Stimata'] = "Da definire (Acquisti)"
            df_bloccati_display['Data_Scadenza_Cliente'] = df_bloccati_display['Data_Scadenza_Cliente'].dt.strftime('%Y-%m-%d')
            st.table(df_bloccati_display)
        else:
            st.info("Nessun ordine bloccato. Tutti i materiali risultano disponibili o coperti da ordini d'acquisto.")

else:
    st.info("👋 Per iniziare, carica i 4 file CSV richiesti nella barra laterale sinistra.")
