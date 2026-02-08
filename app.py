import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import re
from datetime import datetime, timedelta
import fitz 
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="FishLabel AI Pro", page_icon="⚓", layout="wide")

# Lista attrezzi senza "Sconosciuto" come default visibile
LISTA_ATTREZZI = [
    "Reti da traino", "Reti da posta", "Ami e palangari",
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
    .label-text { font-size: 0.8rem; color: #aaa; margin-bottom: 2px; }
    div.stDownloadButton > button {
        background-color: #FF4B4B !important; color: white !important; font-size: 18px !important;
        padding: 0.8rem 2rem !important; border: none !important; border-radius: 8px !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. LOGICA AI ---
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
        prompt = f"""
        Analizza la fattura ed estrai JSON array. Sii estremamente preciso.
        1. "nome": Nome commerciale (es. TRIGLIA DI SCOGLIO).
        2. "sci": Nome scientifico (es. Mullus surmuletus). OBBLIGATORIO.
        3. "lotto": Codice lotto.
        4. "metodo": "PESCATO" o "ALLEVATO".
        5. "zona": Zona FAO specifica (es. 37.1.3).
        6. "origine": Nazione (es. ITALIA, GRECIA).
        7. "attrezzo": Uno tra: {", ".join(LISTA_ATTREZZI)}. Se non lo trovi, scrivi "Sconosciuto".
        8. "conf": Data confezionamento originale (GG/MM/AAAA).
        Testo: {testo_pdf}
        """
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except: return []

# --- 3. MOTORE PDF (LAYOUT CORRETTO) ---
def pulisci(t):
    if not t: return ""
    t = re.sub(r'\(.*?\)', '', str(t)) # Rimuove commenti AI
    return t.replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    
    # Header
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.ln(1)
    
    # Nome Commerciale (Grande)
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w_full, 7, pulisci(p.get('nome','')).upper(), 0, 'C')
    
    # Nome Scientifico (Obbligatorio sotto il nome)
    pdf.set_font("helvetica", "I", 9)
    pdf.multi_cell(w_full, 5, f"({pulisci(p.get('sci',''))})", 0, 'C')
    
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    
    metodo = str(p.get('metodo', 'PESCATO')).upper()
    zona = pulisci(p.get('zona', ''))
    origine = pulisci(p.get('origine', ''))
    attrezzo = pulisci(p.get('attrezzo', ''))
    
    if "ALLEVATO" in metodo:
        pdf.multi_cell(w_full, 5, f"ALLEVATO IN: {origine.upper()}", 0, 'C')
        pdf.cell(w_full, 5, f"Zona: {zona.upper()}", 0, 1, 'C')
    else:
        # Layout Pescato: Metodo + Attrezzo
        attr_txt = f" CON {attrezzo.upper()}" if attrezzo and attrezzo != "SCONOSCIUTO" else ""
        pdf.set_font("helvetica", "B", 9)
        pdf.multi_cell(w_full, 5, f"PESCATO{attr_txt}", 0, 'C')
        # Sotto: Zona e Nazione
        pdf.set_font("helvetica", "", 9)
        naz_txt = f" - {origine.upper()}" if origine else ""
        pdf.multi_cell(w_full, 5, f"ZONA: {zona.upper()}{naz_txt}", 0, 'C')
    
    pdf.cell(w_full, 5, "PRODOTTO FRESCO", 0, 1, 'C')

    # Prezzo
    if str(p.get('prezzo', '')).strip():
        pdf.set_y(38)
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(w_full, 6, f"EUR/Kg: {p.get('prezzo','')}", 0, 1, 'C')

    # Lotto (Box Fisso)
    pdf.set_y(46)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x(12.5)
    pdf.cell(75, 9, f"LOTTO: {pulisci(p.get('lotto',''))}", 1, 0, 'C')
    
    # Footer Date
    pdf.set_y(56)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w_full, 4, f"Conf: {p.get('conf','')} - Scad: {p.get('scadenza','')}", 0, 0, 'R')

def genera_pdf(lista_p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

# --- 4. INTERFACCIA ---
st.title("⚓ FishLabel AI Pro")

col_model, _ = st.columns([2, 3])
with col_model:
    nome_modello = st.selectbox("🧠 Motore AI", list(MODELLI_AI.keys()))
    codice_modello = MODELLI_AI[nome_modello]

if not st.session_state.get("prodotti"):
    col_up, _ = st.columns([1, 2])
    with col_up:
        file = st.file_uploader("Fattura PDF", type="pdf", label_visibility="collapsed")
        if file and st.button("🚀 Analizza PDF", type="primary"):
            with st.spinner("Estrazione dati..."):
                reader = PdfReader(file)
                text = " ".join([p.extract_text() for p in reader.pages])
                res = chiedi_a_gemini(text, codice_modello)
                if res:
                    for p in res:
                        k = p.get('sci','').upper().strip()
                        if k in st.session_state.learned_map: p['nome'] = st.session_state.learned_map[k]
                        p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                        if not p.get('conf'): p['conf'] = datetime.now().strftime("%d/%m/%Y")
                    st.session_state.prodotti = res
                    st.rerun()
else:
    c_inf, c_cl = st.columns([5, 1])
    with c_inf:
        st.subheader(f"✅ {len(st.session_state.prodotti)} Prodotti")
        st.download_button("🖨️ SCARICA RULLINO", genera_pdf(st.session_state.prodotti), "Rullino.pdf", "application/pdf")
    with c_cl:
        if st.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()

    for i, p in enumerate(st.session_state.prodotti):
        with st.container(border=True):
            c_h1, c_h2 = st.columns([4, 1])
            with c_h1: p['nome'] = st.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}", label_visibility="collapsed")
            with c_h2: st.download_button("⬇️ PDF", genera_pdf([p]), f"{p['nome']}.pdf", key=f"dl_{i}")

            c1, c2, c3 = st.columns(3)
            p['sci'] = c1.text_input("Scientifico (Obbligatorio)", p.get('sci',''), key=f"s_{i}")
            p['lotto'] = c2.text_input("Lotto", p.get('lotto',''), key=f"l_{i}")
            p['metodo'] = c3.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=0 if "PESCATO" in str(p.get('metodo','')).upper() else 1, key=f"m_{i}")

            c4, c5, c6 = st.columns(3)
            p['zona'] = c4.text_input("Zona FAO (es. 37.1.3)", p.get('zona',''), key=f"z_{i}")
            p['origine'] = c5.text_input("Nazionalità (es. ITALIA)", p.get('origine',''), key=f"o_{i}")
            
            if p['metodo'] == "PESCATO":
                attr_curr = p.get('attrezzo', '')
                a_idx = LISTA_ATTREZZI.index(attr_curr) if attr_curr in LISTA_ATTREZZI else 0
                p['attrezzo'] = c6.selectbox("Attrezzo", LISTA_ATTREZZI, index=a_idx, key=f"a_{i}")
            else:
                p['attrezzo'] = ""; c6.empty()

            c7, c8, c9 = st.columns(3)
            p['prezzo'] = c7.text_input("Prezzo (€/Kg)", p.get('prezzo',''), key=f"pr_{i}")
            p['scadenza'] = c8.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")
            p['conf'] = c9.text_input("Confezionamento", p.get('conf',''), key=f"cf_{i}")

            if p['nome'] and p['sci']: st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
    
    salva_memoria(st.session_state.learned_map)