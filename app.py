import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import re
from datetime import datetime, timedelta
import fitz  # PyMuPDF
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE E STILE ---
st.set_page_config(page_title="FishLabel AI Pro", page_icon="⚓", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    
    /* Card Prodotto */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #262730; 
        border: 1px solid #464b5c; 
        border-radius: 8px; 
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Input text scuri */
    input[type="text"] { 
        background-color: #1a1c24 !important; 
        color: white !important; 
        border: 1px solid #464b5c !important; 
    }
    
    /* TITOLI */
    h1 { color: #4facfe; font-size: 2.2rem; font-weight: 800; }
    .label-text { font-size: 0.8rem; color: #aaa; margin-bottom: 2px; }

    /* BOTTONI STANDARD */
    div.stButton > button {
        border-radius: 6px;
        font-weight: 600;
        border: none;
    }

    /* BOTTONE RULLINO (ROSSO E GRANDE, MA CORTO) */
    div.stDownloadButton > button {
        background-color: #FF4B4B !important;
        color: white !important;
        font-size: 18px !important;
        padding: 0.8rem 2rem !important;
        border: 2px solid #FF4B4B !important;
        box-shadow: 0 4px 10px rgba(255, 75, 75, 0.4);
        transition: transform 0.2s;
        height: auto !important;
    }
    div.stDownloadButton > button:hover {
        background-color: #FF2B2B !important;
        transform: scale(1.05);
    }
    
</style>
""", unsafe_allow_html=True)

# --- 2. LOGICA BACKEND ---
MEMORIA_FILE = "memoria_nomi.json"

def carica_memoria():
    if os.path.exists(MEMORIA_FILE):
        try:
            with open(MEMORIA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def salva_memoria(memoria):
    with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=4)

if "learned_map" not in st.session_state:
    st.session_state.learned_map = carica_memoria()

if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key: return []
    genai.configure(api_key=api_key)
    try: model = genai.GenerativeModel('gemini-2.5-flash')
    except: model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Analizza fattura ittica. Estrai JSON array.
    REGOLE:
    1. "nome": Nome commerciale.
    2. "sci": Nome scientifico.
    3. "lotto": Codice lotto.
    4. "fao": Zona FAO (Solo numero).
    5. "metodo": "PESCATO" o "ALLEVATO".
    6. "conf": Data confezionamento (GG/MM/AAAA).
    
    NO commenti tra parentesi. Solo JSON.
    Testo: {testo_pdf}
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        dati = json.loads(txt)
        return dati if isinstance(dati, list) else []
    except: return []

# --- 3. MOTORE PDF ---
def pulisci_etichetta(t):
    if not t: return ""
    t = re.sub(r'\(.*?\)', '', str(t)) # Via le parentesi AI
    return t.replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.ln(1)
    
    # Nome
    nome = pulisci_etichetta(p.get('nome','')).upper()
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w_full, 7, nome, 0, 'C')
    
    # Scientifico
    sci = pulisci_etichetta(p.get('sci',''))
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(w_full, 4, f"({sci})", 0, 'C')
    
    pdf.ln(1)
    # FAO e Metodo
    tracc = f"FAO {pulisci_etichetta(p.get('fao',''))} - {pulisci_etichetta(p.get('metodo',''))}"
    pdf.set_font("helvetica", "", 8)
    pdf.multi_cell(w_full, 4, tracc, 0, 'C')
    
    # Scadenza
    pdf.cell(w_full, 5, f"Scadenza: {pulisci_etichetta(p.get('scadenza',''))}", 0, 1, 'C')

    # Prezzo
    if str(p.get('prezzo', '')).strip():
        pdf.set_y(34)
        pdf.set_font("helvetica", "B", 13)
        pdf.cell(w_full, 6, f"EUR/Kg: {p.get('prezzo','')}", 0, 1, 'C')

    # Lotto
    pdf.set_y(41)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x((100 - 75) / 2)
    pdf.cell(75, 10, f"LOTTO: {pulisci_etichetta(p.get('lotto',''))}", 1, 0, 'C')
    
    # Conf
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w_full, 4, f"Conf: {pulisci_etichetta(p.get('conf',''))}", 0, 0, 'R')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

def converti_pdf_in_immagine(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc.load_page(0).get_pixmap(dpi=120).tobytes("png")

# --- 4. INTERFACCIA ---
c_title, c_logo = st.columns([5, 1])
with c_title: st.title("⚓ FishLabel AI Pro")
with c_logo: st.markdown("<h1 style='text-align: right;'>🐟</h1>", unsafe_allow_html=True)

if not st.session_state.get("prodotti"):
    col_up, _ = st.columns([1, 2])
    with col_up:
        file = st.file_uploader("Carica Fattura", type="pdf", label_visibility="collapsed")
        if file and st.button("🚀 Analizza PDF", type="primary"):
            with st.spinner("Analisi..."):
                reader = PdfReader(file)
                text = " ".join([p.extract_text() for p in reader.pages])
                res = chiedi_a_gemini(text)
                final = []
                for p in res:
                    k = p.get('sci','').upper().strip()
                    if k in st.session_state.learned_map: p['nome'] = st.session_state.learned_map[k]
                    p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                    if not p.get('conf'): p['conf'] = datetime.now().strftime("%d/%m/%Y")
                    p['prezzo'] = ""
                    final.append(p)
                st.session_state.prodotti = final
                st.rerun()
else:
    # --- BARRA SUPERIORE ---
    c_inf, c_cl = st.columns([5, 1])
    with c_inf:
        st.subheader(f"✅ {len(st.session_state.prodotti)} Prodotti")
        # TASTO RULLINO ROSSO E GRANDE (ma non largo 100%)
        col_btn, _ = st.columns([2, 3]) # Colonna stretta per il bottone
        with col_btn:
            st.download_button("🖨️ SCARICA RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf", "application/pdf")
            
    with c_cl:
        if st.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()

    # --- LOOP SCHEDE ---
    for i, p in enumerate(st.session_state.prodotti):
        with st.container(border=True):
            # Intestazione e Download Singolo
            c_h1, c_h2 = st.columns([4, 1])
            with c_h1: p['nome'] = st.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}", label_visibility="collapsed")
            with c_h2: st.download_button("⬇️ PDF", genera_pdf_bytes([p]), f"{p['nome']}.pdf", key=f"dl_{i}")

            # RIGA 1: Scientifico, FAO, Metodo (TORNATO!)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("<div class='label-text'>Scientifico</div>", unsafe_allow_html=True)
                p['sci'] = st.text_input("sci", p.get('sci',''), key=f"s_{i}", label_visibility="collapsed")
            with c2:
                st.markdown("<div class='label-text'>Zona FAO</div>", unsafe_allow_html=True)
                p['fao'] = st.text_input("fao", p.get('fao',''), key=f"f_{i}", label_visibility="collapsed")
            with c3:
                st.markdown("<div class='label-text'>Metodo</div>", unsafe_allow_html=True)
                # TENDINA PESCATO/ALLEVATO
                m_idx = 0 if "PESCATO" in str(p.get('metodo','')).upper() else 1
                p['metodo'] = st.selectbox("metodo", ["PESCATO", "ALLEVATO"], index=m_idx, key=f"m_{i}", label_visibility="collapsed")

            # RIGA 2: Lotto, Scadenza, Conf
            c4, c5, c6 = st.columns(3)
            with c4:
                st.markdown("<div class='label-text'>Lotto</div>", unsafe_allow_html=True)
                p['lotto'] = st.text_input("lotto", p.get('lotto',''), key=f"l_{i}", label_visibility="collapsed")
            with c5:
                st.markdown("<div class='label-text'>Scadenza</div>", unsafe_allow_html=True)
                p['scadenza'] = st.text_input("scad", p.get('scadenza',''), key=f"sc_{i}", label_visibility="collapsed")
            with c6:
                st.markdown("<div class='label-text'>Confezionamento</div>", unsafe_allow_html=True)
                p['conf'] = st.text_input("conf", p.get('conf',''), key=f"cf_{i}", label_visibility="collapsed")

            # RIGA 3: Prezzo (Opzionale)
            c7, _ = st.columns([1, 2])
            with c7:
                st.markdown("<div class='label-text'>Prezzo (€/Kg)</div>", unsafe_allow_html=True)
                p['prezzo'] = st.text_input("prz", p.get('prezzo',''), key=f"pr_{i}", label_visibility="collapsed")

            # Anteprima
            st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=350)
            
            # Memoria
            if p['nome'] and p['sci']:
                st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
                
    salva_memoria(st.session_state.learned_map)