import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Ittica Catanzaro AI PRO", page_icon="🐟", layout="wide")

# --- 2. GESTIONE MEMORIA (IL CERVELLO DEL NEGOZIO) ---
MEMORIA_FILE = "memoria_nomi.json"

def carica_memoria():
    """Carica il file JSON con i nomi salvati."""
    if os.path.exists(MEMORIA_FILE):
        try:
            with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def salva_memoria(memoria):
    """Salva i nomi nel file JSON."""
    with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=4)

# Inizializza la memoria nello stato della sessione
if "learned_map" not in st.session_state:
    st.session_state.learned_map = carica_memoria()

# --- 3. CONFIGURAZIONE AI (GEMINI) ---
# Cerchiamo la chiave nei secrets, altrimenti chiediamo nella sidebar
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Inserisci Gemini API Key", type="password")

def chiedi_a_gemini(testo_pdf, model_name):
    """Interroga Gemini per estrarre i dati."""
    if not api_key:
        raise ValueError("Manca la API Key!")
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    prompt = f"""
    Sei un esperto di prodotti ittici. Analizza il testo di questa fattura ed estrai i prodotti in formato JSON.
    
    REGOLE DI ESTRAZIONE:
    1. "nome": Estrai SOLO il nome commerciale del pesce (es. "SEPPIA", "ORATA"). Rimuovi codici numerici, parole come "GRECIA", "SPAGNA", "ALLEVATO", "FRESCO".
    2. "sci": Estrai il nome scientifico (solitamente tra parentesi o in corsivo, es. "Sepia officinalis").
    3. "lotto": Estrai il codice del lotto pulito. Se vedi prezzi o pesi attaccati alla fine (es. "L1234530.00"), rimuovili.
    4. "fao": Estrai la zona FAO (es. "37.2.1").
    5. "metodo": Scrivi "PESCATO" o "ALLEVATO" in base al contesto.

    TESTO FATTURA:
    {testo_pdf}
    
    Rispondi ESCLUSIVAMENTE con un array JSON valido. Nessun altro testo.
    """
    
    response = model.generate_content(prompt)
    # Pulizia della risposta per garantire un JSON valido
    txt = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(txt)

# --- 4. MOTORE PDF (GENERAZIONE ETICHETTE) ---
def genera_etichetta_bytes(p):
    """Crea il PDF di una singola etichetta in memoria (bytes)."""
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    pdf.set_auto_page_break(False)
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Pesce (Grande)
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'].upper(), align='C')
    
    # Nome Scientifico
    pdf.ln(1)
    font_size = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", font_size)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C')
    
    # Tracciabilità
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Box Lotto
    pdf.set_y(38)
    lotto_txt = f"LOTTO: {p['lotto']}"
    font_lotto = 12 if len(lotto_txt) < 20 else 10
    pdf.set_font("helvetica", "B", font_lotto)
    pdf.set_x((100 - 80) / 2) # Centrato
    pdf.cell(w=80, h=11, text=lotto_txt, border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')
    
    return bytes(pdf.output())

def mostra_anteprima_pdf(pdf_bytes):
    """Visualizza il PDF direttamente nella pagina Streamlit."""
    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="250" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

# --- 5. INTERFACCIA UTENTE (STREAMLIT) ---
st.title("⚓ FishLabel AI Scanner PRO")

# Sidebar: Opzioni e Memoria
with st.sidebar:
    st.header("⚙️ Configurazione")
    # Seleziona modello (per evitare l'errore 404)
    modello_scelto = st.selectbox("Modello AI", ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"])
    
    st.divider()
    st.subheader("🧠 Gestione Memoria")
    # Tasto per scaricare il JSON aggiornato (fondamentale per il Cloud)
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button(
        "💾 Scarica Memoria (.json)", 
        mem_json, 
        "memoria_nomi.json", 
        "application/json",
        help="Salva questo file a fine giornata per non perdere i nomi imparati!"
    )
    
    # Upload per ripristinare la memoria
    uploaded_mem = st.file_uploader("Carica Memoria", type="json")
    if uploaded_mem:
        st.session_state.learned_map.update(json.load(uploaded_mem))
        st.success("Memoria ripristinata!")

    if st.button("🗑️ RESET TOTALE"):
        st.session_state.clear()
        st.rerun()

# Area Principale
file = st.file_uploader("Trascina qui la Fattura PDF", type="pdf")

if file:
    # Reset automatico se cambia il file
    if "ultimo_file" not in st.session_state or st.session_state.ultimo_file != file.name:
        st.session_state.prodotti = None
        st.session_state.ultimo_file = file.name

    # Tasto Analisi
    if st.button("🚀 ANALIZZA FATTURA", type="primary"):
        with st.spinner(f"Sto leggendo con {modello_scelto}..."):
            try:
                # 1. Lettura PDF
                reader = PdfReader(file)
                testo = " ".join([p.extract_text() for p in reader.pages])
                
                # 2. Estrazione AI
                prodotti_ai = chiedi_a_gemini(testo, modello_scelto)
                
                # 3. APPLICAZIONE MEMORIA (Il punto cruciale)
                for p in prodotti_ai:
                    sci_clean = p['sci'].upper().strip()
                    # Se conosciamo già questo pesce scientifico, usiamo il NOSTRO nome salvato
                    if sci_clean in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci_clean]
                
                st.session_state.prodotti = prodotti_ai
                st.success(f"Trovati {len(prodotti_ai)} prodotti!")
                
            except Exception as e:
                st.error(f"Errore durante l'analisi: {e}")

    # Visualizzazione Risultati
    if st.session_state.get("prodotti"):
        
        # Tasto Stampa Massiva in alto
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        
        # Prepariamo il PDF totale (lo rigeneriamo coi dati attuali)
        # Nota: lo rigeneriamo nel loop sotto per essere sicuri di prendere le modifiche
        
        st.divider()
        
        # Loop sui prodotti
        for i, p in enumerate(st.session_state.prodotti):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}", expanded=True):
                col_form, col_preview = st.columns([1, 1])
                
                with col_form:
                    # Input modificabili
                    nuovo_nome = st.text_input("Nome Commerciale", p['nome'], key=f"n_{i}")
                    nuovo_lotto = st.text_input("Lotto", p['lotto'], key=f"l_{i}")
                    
                    # LOGICA DI APPRENDIMENTO
                    # Se l'utente cambia il nome, aggiorniamo la memoria e il file JSON
                    if nuovo_nome != p['nome']:
                        p['nome'] = nuovo_nome
                        sci_key = p['sci'].upper().strip()
                        # Salva nella memoria di sessione
                        st.session_state.learned_map[sci_key] = new_nome
                        # Salva fisicamente nel file JSON (se in locale)
                        salva_memoria(st.session_state.learned_map)
                        st.toast(f"Ho imparato che {p['sci']} si chiama {nuovo_nome}!")
                    
                    # Aggiorna lotto se cambiato
                    if nuovo_lotto != p['lotto']:
                        p['lotto'] = nuovo_lotto

                with col_preview:
                    # Genera anteprima al volo
                    pdf_bytes = genera_etichetta_bytes(p)
                    mostra_anteprima_pdf(pdf_bytes)
                    st.download_button("🖨️ Stampa Etichetta", pdf_bytes, f"Etichetta_{i}.pdf", key=f"down_{i}")
        
        st.divider()
        
        # Generazione PDF Totale alla fine (così include le modifiche fatte sopra)
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        for p in st.session_state.prodotti:
            # Ricostruiamo la pagina per il totale
            pdf_tot.add_page()
            # ... (Logica di disegno identica a genera_etichetta_bytes ma su pdf_tot)
            pdf_tot.set_font("helvetica", "B", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
            pdf_tot.ln(1)
            pdf_tot.set_font("helvetica", "B", 15)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=7, text=p['nome'].upper(), align='C')
            pdf_tot.ln(1)
            fs = 9 if len(p['sci']) < 25 else 7
            pdf_tot.set_font("helvetica", "I", fs)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=4, text=f"({p['sci']})", align='C')
            pdf_tot.ln(2)
            pdf_tot.set_font("helvetica", "", 9)
            pdf_tot.cell(w=pdf_tot.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
            pdf_tot.set_y(38)
            pdf_tot.set_font("helvetica", "B", 12)
            pdf_tot.set_x((100 - 80) / 2)
            pdf_tot.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align='C')
            pdf_tot.set_y(54)
            pdf_tot.set_font("helvetica", "", 7)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

        st.download_button("🖨️ SCARICA TUTTO IL RULLINO", bytes(pdf_tot.output()), "Rullino_Completo.pdf", type="primary")