import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
from datetime import datetime, timedelta

# --- 1. CONFIGURAZIONE E TEMA DARK ---
st.set_page_config(page_title="FishLabel Dark", page_icon="🐟", layout="wide")

# CSS: Sfondo Scuro, Bottoni Compatti, Card Eleganti
st.markdown("""
<style>
    /* Sfondo Generale Scuro */
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    
    /* Nascondi menu standard */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Stile Card Prodotto (Sfondo leggermente più chiaro del nero) */
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
    
    /* Bottoni: NON più larghezza intera, ma compatti */
    div.stButton > button {
        width: auto !important;
        min-width: 120px;
        height: 40px;
        border-radius: 6px;
        font-weight: 600;
        border: none;
        transition: all 0.2s;
    }
    
    /* Hover effetti bottoni */
    div.stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 2px 8px rgba(255,255,255,0.1);
    }
    
    /* Titoli */
    h1, h2, h3 { color: #4facfe; }
    .fish-name { font-size: 1.4rem; font-weight: bold; color: #4facfe; margin-bottom: 5px; }
    .label-text { font-size: 0.8rem; color: #aaa; }

</style>
""", unsafe_allow_html=True)

# --- 2. LOGICA BACKEND ---
MEMORIA_FILE = "memoria_nomi.json"

def carica_memoria():
    if os.path.exists(MEMORIA_FILE):
        try:
            with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
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
    api_key = st.sidebar.text_input("🔑 API Key", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key: return []
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
    except:
        model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"Estrai JSON da fattura ittica: nome, sci (scientifico), lotto, fao, metodo, conf (data confezionamento). Testo: {testo_pdf}"
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        dati = json.loads(txt)
        return dati if isinstance(dati, list) else []
    except: return []

# --- 3. MOTORE PDF (FIX CRASH) ---
def pulisci(t):
    return str(t).replace("€", "EUR").encode('latin-1', 'replace').decode('latin-1') if t else ""

def disegna_su_pdf(pdf, p):
    pdf.add_page()
    # Margini espliciti: Sinistra 4, Alto 3, Destra 4
    pdf.set_margins(4, 3, 4)
    
    # Larghezza effettiva area stampabile (62 - 4 - 4 = 54mm)
    w_eff = 54 
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w_eff, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.ln(1)
    
    # Nome (Grande)
    nome = pulisci(p.get('nome','')).upper()
    pdf.set_font("helvetica", "B", 14)
    pdf.multi_cell(w_eff, 6, nome, 0, 'C')
    
    # Scientifico (FIX ERRORE: w=w_eff invece di 0)
    sci = pulisci(p.get('sci',''))
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(w_eff, 4, f"({sci})", 0, 'C')
    
    pdf.ln(1)
    # Dati Tecnici
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w_eff, 4, f"FAO {p.get('fao','')} - {p.get('metodo','')}", 0, 1, 'C')
    pdf.cell(w_eff, 4, f"Scadenza: {p.get('scadenza','')}", 0, 1, 'C')

    # Prezzo
    prezzo = str(p.get('prezzo', '')).strip()
    if prezzo:
        pdf.set_y(34)
        pdf.set_font("helvetica", "B", 13)
        pdf.cell(w_eff, 6, f"EUR/Kg: {prezzo}", 0, 1, 'C')

    # Lotto
    pdf.set_y(42)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x(14) # Centratura manuale per box lotto
    lotto = pulisci(p.get('lotto',''))
    pdf.cell(70, 9, f"LOTTO: {lotto}", 1, 0, 'C')
    
    # Conf
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w_eff, 4, f"Conf: {p.get('conf','')}", 0, 0, 'R')

def genera_pdf_rullino(lista_p):
    # Formato 62x100 mm Landscape
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    for p in lista_p:
        disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

def genera_pdf_singolo(p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

# --- 4. INTERFACCIA UTENTE ---
c_title, c_logo = st.columns([5, 1])
with c_title:
    st.title("FishLabel Dark")
    st.caption("Gestione Etichette Professionale - Palermo")
with c_logo:
    st.markdown("<h1>🐟</h1>", unsafe_allow_html=True)

# Sidebar Semplificata
with st.sidebar:
    st.header("Memoria")
    st.metric("Nomi Imparati", len(st.session_state.learned_map))
    if st.button("🗑️ Reset Tutto"):
        st.session_state.clear()
        st.rerun()

# AREA UPLOAD (Compatta)
uploaded_file = st.file_uploader("Carica Fattura (PDF)", type="pdf", label_visibility="collapsed")

if uploaded_file:
    # Se nuovo file, resetta
    if "last_f" not in st.session_state or st.session_state.last_f != uploaded_file.name:
        st.session_state.prodotti = None
        st.session_state.last_f = uploaded_file.name

    # PULSANTE ANALIZZA (PICCOLO E COMPATTO)
    if st.session_state.prodotti is None:
        col_btn, col_void = st.columns([1, 5]) # Trucco per rendere il bottone piccolo a sinistra
        with col_btn:
            if st.button("🚀 Analizza PDF", type="primary"):
                with st.spinner("Lettura in corso..."):
                    reader = PdfReader(uploaded_file)
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

# RISULTATI
if st.session_state.get("prodotti"):
    st.divider()
    
    # Barra Azioni (Download Rullino)
    col_res_1, col_res_2 = st.columns([2, 1])
    with col_res_1:
        st.subheader(f"Trovati {len(st.session_state.prodotti)} prodotti")
    with col_res_2:
        pdf_roll = genera_pdf_rullino(st.session_state.prodotti)
        st.download_button("🖨️ Scarica Rullino Completo", pdf_roll, "Rullino.pdf", "application/pdf", type="primary")

    st.markdown("<br>", unsafe_allow_html=True)

    # LOOP PRODOTTI (CARD SCURE)
    for i, p in enumerate(st.session_state.prodotti):
        with st.container(border=True): # Bordo crea la "Card"
            # Header Card
            c_h1, c_h2 = st.columns([3, 1])
            with c_h1:
                # Nome Pesce Editabile ma stilizzato
                p['nome'] = st.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}", label_visibility="collapsed")
            with c_h2:
                # Bottone scarica singolo allineato a destra
                pdf_s = genera_pdf_singolo(p)
                st.download_button("📄 PDF", pdf_s, f"{p['nome']}.pdf", key=f"dl_{i}")

            # Dati
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("<div class='label-text'>Nome Scientifico</div>", unsafe_allow_html=True)
                p['sci'] = st.text_input("sci", p.get('sci',''), key=f"s_{i}", label_visibility="collapsed")
            with c2:
                st.markdown("<div class='label-text'>Lotto</div>", unsafe_allow_html=True)
                p['lotto'] = st.text_input("lotto", p.get('lotto',''), key=f"l_{i}", label_visibility="collapsed")
            with c3:
                st.markdown("<div class='label-text'>Prezzo (€/Kg)</div>", unsafe_allow_html=True)
                p['prezzo'] = st.text_input("prz", p.get('prezzo',''), key=f"pr_{i}", label_visibility="collapsed")

            c4, c5, c6 = st.columns(3)
            with c4:
                st.markdown("<div class='label-text'>Zona FAO</div>", unsafe_allow_html=True)
                p['fao'] = st.text_input("fao", p.get('fao',''), key=f"f_{i}", label_visibility="collapsed")
            with c5:
                st.markdown("<div class='label-text'>Scadenza</div>", unsafe_allow_html=True)
                p['scadenza'] = st.text_input("scad", p.get('scadenza',''), key=f"sc_{i}", label_visibility="collapsed")
            with c6:
                st.markdown("<div class='label-text'>Confezionamento</div>", unsafe_allow_html=True)
                p['conf'] = st.text_input("conf", p.get('conf',''), key=f"cf_{i}", label_visibility="collapsed")

            # Logica Memoria
            if p['nome'] and p['sci']:
                st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']