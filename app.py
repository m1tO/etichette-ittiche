import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import re
from datetime import datetime, timedelta
import fitz  # PyMuPDF

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="FishLabel AI Pro", page_icon="⚓", layout="wide")

LISTA_ATTREZZI = [
    "Sconosciuto", "Reti da traino", "Reti da posta", "Ami e palangari",
    "Reti da circuizione", "Nasse e trappole", "Draghe", "Raccolta manuale", "Sciabiche"
]

MODELLI_AI = {
    "⚡ Gemini 2.5 Flash": "gemini-2.5-flash",
    "🧊 Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
    "🔥 Gemini 3 Flash": "gemini-3-flash"
}

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #262730; border: 1px solid #464b5c; border-radius: 8px; padding: 20px;
    }
    input[type="text"] { background-color: #1a1c24 !important; color: white !important; border: 1px solid #464b5c !important; }
    h1 { color: #4facfe; font-size: 2.2rem; font-weight: 800; }
    div.stDownloadButton > button {
        background-color: #FF4B4B !important; color: white !important; font-size: 18px !important;
        padding: 0.8rem 2rem !important; border: none !important; border-radius: 8px !important;
        box-shadow: 0 4px 10px rgba(255, 75, 75, 0.4);
    }
    button[data-baseweb="tab"] {
        font-size: 26px !important; font-weight: 700 !important;
        padding: 10px 20px !important; margin: 0 5px !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. LOGICA BACKEND (TRADUTTORE SIGLE FORNITORI) ---
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

if "learned_map" not in st.session_state: st.session_state.learned_map = carica_memoria()

if "GEMINI_API_KEY" in st.secrets: api_key = st.secrets["GEMINI_API_KEY"]
else: api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf, model_name):
    if not api_key: return []
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(model_name)
        # PROMPT ULTRA-SPECIFICO PER LE SIGLE DELLA FATTURA
        prompt = f"""
        Analizza questa fattura ittica. Sii estremamente preciso con queste regole:
        1. METODO: Se leggi 'AI' o 'Acquacoltura' o 'Allevato', il metodo è 'ALLEVATO'. Il Salmone con 'AI' è SEMPRE ALLEVATO.
        2. ATTREZZI (Sigle Tecniche):
           - Se leggi 'RDT' -> l'attrezzo è 'Reti da traino'.
           - Se leggi 'LM' o 'EF' -> l'attrezzo è 'Ami e palangari'.
           - Se leggi 'GNS' -> l'attrezzo è 'Reti da posta'.
        3. Se non trovi sigle ma leggi 'Pescato', metti metodo 'PESCATO'.
        4. Campi richiesti: nome, sci (nome scientifico), lotto, metodo (PESCATO o ALLEVATO), zona (es. 37.2.1), origine (Nazione), attrezzo (scegli tra quelli della lista sopra), conf.
        
        Testo: {testo_pdf}
        """
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except: return []

# --- 3. MOTORE DI STAMPA (LAYOUT FINALE CONSERVATO) ---
def pulisci_testo(t):
    if not t: return ""
    return str(t).replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    pdf.set_y(3)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.set_y(7)
    pdf.set_font("helvetica", "B", 18)
    pdf.multi_cell(w_full, 7, pulisci_testo(p.get('nome','')).upper(), 0, 'C')
    pdf.set_y(16)
    sci = pulisci_testo(p.get('sci',''))
    pdf.set_font("helvetica", "I", 10)
    pdf.multi_cell(w_full, 4, f"({sci})", 0, 'C')
    pdf.set_y(23)
    metodo = str(p.get('metodo', 'PESCATO')).upper()
    zona = pulisci_testo(p.get('zona', ''))
    origine = pulisci_testo(p.get('origine', ''))
    attrezzo = pulisci_testo(p.get('attrezzo', ''))
    pdf.set_font("helvetica", "", 9)
    if "ALLEVATO" in metodo:
        testo = f"ALLEVATO IN: {origine.upper()} (Zona: {zona.upper()})"
    else:
        attr = f" CON {attrezzo.upper()}" if attrezzo and "SCONOSCIUTO" not in attrezzo.upper() else ""
        testo = f"PESCATO{attr}\nZONA: {zona.upper()} - {origine.upper()}"
    pdf.multi_cell(w_full, 4, testo, 0, 'C')
    pdf.cell(w_full, 4, "PRODOTTO FRESCO", 0, 1, 'C')
    if str(p.get('prezzo', '')).strip():
        pdf.set_y(36)
        pdf.set_font("helvetica", "B", 22)
        pdf.cell(w_full, 8, f"{p.get('prezzo','')} EUR/Kg", 0, 1, 'C')
    pdf.set_y(46)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x(5)
    pdf.cell(90, 8, f"LOTTO: {pulisci_testo(p.get('lotto',''))}", 1, 0, 'C')
    pdf.set_y(56)
    pdf.set_font("helvetica", "", 8)
    pdf.cell(w_full, 4, f"Conf: {p.get('conf','')} - Scad: {p.get('scadenza','')}", 0, 0, 'R')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

def converti_pdf_in_immagine(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc.load_page(0).get_pixmap(dpi=120).tobytes("png")

# --- 4. INTERFACCIA ---
st.title("⚓ FishLabel AI Pro")

if not st.session_state.get("prodotti"):
    tab1, tab2 = st.tabs(["📤 CARICA FATTURA", "✍️ INSERIMENTO MANUALE"])
    with tab1:
        n_modello = st.selectbox("🧠 Motore AI", list(MODELLI_AI.keys()))
        file = st.file_uploader("Fattura PDF", type="pdf")
        if file and st.button("🚀 Analizza PDF", type="primary"):
            with st.spinner("Analisi in corso..."):
                reader = PdfReader(file); text = " ".join([p.extract_text() for p in reader.pages])
                res = chiedi_a_gemini(text, MODELLI_AI[n_modello])
                if res:
                    for p in res:
                        k = p.get('sci','').upper().strip()
                        if k in st.session_state.learned_map: p['nome'] = st.session_state.learned_map[k]
                        p['scadenza'] = ""; p['conf'] = ""; p['prezzo'] = ""
                    st.session_state.prodotti = res; st.rerun()
    with tab2:
        if st.button("➕ Crea Nuova Etichetta"):
            st.session_state.prodotti = [{"nome": "NUOVO PRODOTTO", "sci": "", "lotto": "", "metodo": "PESCATO", "zona": "37.1.3", "origine": "ITALIA", "attrezzo": "", "conf": "", "scadenza": "", "prezzo": ""}]
            st.rerun()
else:
    st.success(f"✅ Trovati {len(st.session_state.prodotti)} prodotti!")
    col_dl, col_cl = st.columns([5, 1])
    with col_dl: st.download_button("🖨️ SCARICA RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf")
    with col_cl:
        if st.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()

    for i, p in enumerate(st.session_state.prodotti):
        with st.container(border=True):
            c_h1, c_h2 = st.columns([4, 1])
            with c_h1: p['nome'] = st.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}")
            with c_h2: st.download_button("⬇️ PDF", genera_pdf_bytes([p]), f"{p['nome']}.pdf", key=f"dl_{i}")
            c1, c2, c3 = st.columns(3)
            p['sci'] = c1.text_input("Scientifico", p.get('sci',''), key=f"s_{i}")
            p['lotto'] = c2.text_input("Lotto", p.get('lotto',''), key=f"l_{i}")
            p['metodo'] = c3.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=0 if "PESCATO" in str(p.get('metodo','')).upper() else 1, key=f"m_{i}")
            c4, c5, c6 = st.columns(3)
            p['zona'] = c4.text_input("Zona FAO", p.get('zona',''), key=f"z_{i}")
            p['origine'] = c5.text_input("Nazionalità", p.get('origine',''), key=f"o_{i}")
            if p['metodo'] == "PESCATO":
                a_curr = p.get('attrezzo', '')
                a_idx = LISTA_ATTREZZI.index(a_curr) if a_curr in LISTA_ATTREZZI else 0
                p['attrezzo'] = c6.selectbox("Attrezzo", LISTA_ATTREZZI, index=a_idx, key=f"a_{i}")
            else: p['attrezzo'] = ""; c6.empty()
            c7, c8, c9 = st.columns(3)
            p['prezzo'] = c7.text_input("Prezzo (€/Kg)", p.get('prezzo',''), key=f"pr_{i}")
            p['scadenza'] = c8.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")
            p['conf'] = c9.text_input("Confezionamento", p.get('conf',''), key=f"cf_{i}")
            st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=380)
            if p['nome'] and p['sci']: st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
    salva_memoria(st.session_state.learned_map)