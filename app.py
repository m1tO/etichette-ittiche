import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime, timedelta
import fitz 
import streamlit.components.v1 as components
import re # Per la pulizia del testo

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="FishLabel AI Pro", page_icon="⚓", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #262730; border: 1px solid #464b5c; border-radius: 8px; padding: 20px;
    }
    input[type="text"] { background-color: #1a1c24 !important; color: white !important; border: 1px solid #464b5c !important; }
    h1 { color: #4facfe; font-size: 2.2rem; font-weight: 800; }
    .label-text { font-size: 0.8rem; color: #aaa; }
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

if "learned_map" not in st.session_state:
    st.session_state.learned_map = carica_memoria()

if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key: return []
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # PROMPT AGGIORNATO: Niente commenti tra parentesi!
    prompt = f"""
    Analizza la fattura ittica ed estrai un array JSON.
    REGOLE RIGIDE:
    1. "nome": Nome commerciale pulito.
    2. "sci": Nome scientifico.
    3. "lotto": Codice lotto.
    4. "fao": Zona FAO (Solo numero, es: 27).
    5. "metodo": Solo "PESCATO" o "ALLEVATO".
    6. "conf": Data confezionamento originale (GG/MM/AAAA).
    
    IMPORTANTE: Non aggiungere MAI spiegazioni, note o parentesi come "(inferito da AI)".
    Rispondi SOLO con il JSON.
    
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
    # RIMUOVE QUALSIASI COSA TRA PARENTESI (per sicurezza extra)
    t = re.sub(r'\(.*?\)', '', str(t))
    return t.replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.ln(1)
    
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w_full, 7, pulisci_etichetta(p.get('nome','')).upper(), 0, 'C')
    
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(w_full, 4, f"({pulisci_etichetta(p.get('sci',''))})", 0, 'C')
    
    pdf.ln(1)
    pdf.set_font("helvetica", "", 8)
    # FAO e METODO PULITI
    tracc = f"FAO {pulisci_etichetta(p.get('fao',''))} - {pulisci_etichetta(p.get('metodo',''))}"
    pdf.multi_cell(w_full, 4, tracc, 0, 'C')
    
    pdf.cell(w_full, 5, f"Scadenza: {pulisci_etichetta(p.get('scadenza',''))}", 0, 1, 'C')

    if str(p.get('prezzo', '')).strip():
        pdf.set_y(34)
        pdf.set_font("helvetica", "B", 13)
        pdf.cell(w_full, 6, f"EUR/Kg: {p.get('prezzo','')}", 0, 1, 'C')

    pdf.set_y(41)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x((100 - 75) / 2)
    pdf.cell(75, 10, f"LOTTO: {pulisci_etichetta(p.get('lotto',''))}", 1, 0, 'C')
    
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
st.title("⚓ FishLabel AI Pro")

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
    c_inf, c_cl = st.columns([5, 1])
    with c_inf:
        st.subheader(f"✅ {len(st.session_state.prodotti)} Prodotti")
        st.download_button("🖨️ Scarica Rullino", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf", "application/pdf")
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
            p['prezzo'] = c3.text_input("Prezzo/Kg", p.get('prezzo',''), key=f"pr_{i}")

            c4, c5, c6 = st.columns(3)
            p['fao'] = c4.text_input("FAO", p.get('fao',''), key=f"f_{i}")
            p['scadenza'] = c5.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")
            p['conf'] = c6.text_input("Confezionamento", p.get('conf',''), key=f"cf_{i}")

            st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=350)
            if p['nome'] and p['sci']: st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
    
    salva_memoria(st.session_state.learned_map)