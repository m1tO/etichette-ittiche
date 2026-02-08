import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import re
from datetime import datetime, timedelta
import fitz 

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

if "learned_map" not in st.session_state: st.session_state.learned_map = carica_memoria()

if "GEMINI_API_KEY" in st.secrets: api_key = st.secrets["GEMINI_API_KEY"]
else: api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf, model_name):
    if not api_key: return []
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(model_name)
        prompt = f"Estrai JSON array da fattura: nome, sci (nome scientifico), lotto, metodo (PESCATO/ALLEVATO), zona (FAO), origine (Nazione), attrezzo, conf (GG/MM/AAAA). Testo: {testo_pdf}"
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except: return []

# --- 3. MOTORE DI STAMPA UNICO E DEFINITIVO ---
def pulisci_testo(t):
    if not t: return ""
    return str(t).replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    """Funzione universale di disegno per singola e rullino."""
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    
    # 1. Intestazione (Y=3)
    pdf.set_y(3)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    
    # 2. Nome Commerciale (Y=8)
    pdf.set_y(8)
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w_full, 6, pulisci_testo(p.get('nome','')).upper(), 0, 'C')
    
    # 3. Nome Scientifico (Y=19)
    pdf.set_y(19)
    sci = pulisci_testo(p.get('sci',''))
    pdf.set_font("helvetica", "I", 10) # Leggermente più grande per leggibilità
    pdf.multi_cell(w_full, 4, f"({sci})", 0, 'C')
    
    # 4. Blocco Unico: Metodo, Attrezzo, Zona e Nazione (Y=27)
    pdf.set_y(27)
    metodo = str(p.get('metodo', 'PESCATO')).upper()
    zona = pulisci_testo(p.get('zona', ''))
    origine = pulisci_testo(p.get('origine', ''))
    attrezzo = pulisci_testo(p.get('attrezzo', ''))
    
    if "ALLEVATO" in metodo:
        testo_origine = f"ALLEVATO IN: {origine.upper()} (Zona: {zona.upper()})"
    else:
        # Pescato: Unisco tutto in un'unica stringa per multi_cell
        attr_txt = f" CON {attrezzo.upper()}" if attrezzo and "SCONOSCIUTO" not in attrezzo.upper() else ""
        testo_origine = f"PESCATO{attr_txt}\nZONA: {zona.upper()} - {origine.upper()}"
    
    pdf.set_font("helvetica", "", 9)
    pdf.multi_cell(w_full, 4, testo_origine, 0, 'C')
    
    # Prodotto Fresco (Sempre sotto l'origine)
    pdf.cell(w_full, 4, "PRODOTTO FRESCO", 0, 1, 'C')

    # 5. Prezzo (Y=40)
    if str(p.get('prezzo', '')).strip():
        pdf.set_y(40)
        pdf.set_font("helvetica", "B", 13)
        pdf.cell(w_full, 6, f"EUR/Kg: {p.get('prezzo','')}", 0, 1, 'C')

    # 6. Lotto (Y=48)
    pdf.set_y(48)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x(12.5) 
    pdf.cell(75, 8, f"LOTTO: {pulisci_testo(p.get('lotto',''))}", 1, 0, 'C')
    
    # 7. Date (Y=57)
    pdf.set_y(57)
    pdf.set_font("helvetica", "", 7)
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
nome_modello = st.selectbox("🧠 Motore AI", list(MODELLI_AI.keys()))

if not st.session_state.get("prodotti"):
    col_up, _ = st.columns([1, 2])
    with col_up:
        file = st.file_uploader("Fattura PDF", type="pdf", label_visibility="collapsed")
        if file and st.button("🚀 Analizza PDF", type="primary"):
            with st.spinner("Estrazione dati..."):
                reader = PdfReader(file); text = " ".join([p.extract_text() for p in reader.pages])
                res = chiedi_a_gemini(text, MODELLI_AI[nome_modello])
                if res:
                    for p in res:
                        k = p.get('sci','').upper().strip()
                        if k in st.session_state.learned_map: p['nome'] = st.session_state.learned_map[k]
                        p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                        if not p.get('conf'): p['conf'] = datetime.now().strftime("%d/%m/%Y")
                        p['prezzo'] = ""
                    st.session_state.prodotti = res
                    st.rerun()
else:
    c_inf, c_cl = st.columns([5, 1])
    with c_inf:
        st.download_button("🖨️ SCARICA RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf", "application/pdf")
    with c_cl:
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
            else:
                p['attrezzo'] = ""; c6.empty()

            c7, c8, c9 = st.columns(3)
            p['prezzo'] = c7.text_input("Prezzo (€/Kg)", p.get('prezzo',''), key=f"pr_{i}")
            p['scadenza'] = c8.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")
            p['conf'] = c9.text_input("Confezionamento", p.get('conf',''), key=f"cf_{i}")

            st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=380)
            if p['nome'] and p['sci']: st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']

    salva_memoria(st.session_state.learned_map)