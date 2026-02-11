import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import sqlite3
from datetime import datetime
import fitz  # PyMuPDF

# --- 1. CONFIGURAZIONE & DATABASE ---
st.set_page_config(page_title="FishLabel AI Pro", page_icon="⚓", layout="wide")

DB_FILE = "tracciabilita.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS magazzino 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, sci TEXT, lotto TEXT, 
                  metodo TEXT, zona TEXT, origine TEXT, data_carico TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS produzioni 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, piatto TEXT, ingredienti TEXT, data_prod TEXT)''')
    conn.commit()
    conn.close()

init_db()

LISTA_ATTREZZI = ["Sconosciuto", "Reti da traino", "Reti da posta", "Ami e palangari", "Reti da circuizione", "Nasse e trappole", "Draghe", "Raccolta manuale", "Sciabiche"]

# --- STILE CSS (BOTTONI VERDI E LAYOUT PULITO) ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #262730; border: 1px solid #464b5c; border-radius: 8px; padding: 15px; margin-bottom: 20px;
    }
    h1 { color: #4facfe; font-size: 2.2rem; font-weight: 800; }
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 20px !important; font-weight: 600 !important; color: #4facfe !important;
    }
    /* Tasto Carica Verde */
    button[kind="primary"] { background-color: #28a745 !important; border-color: #28a745 !important; color: white !important; }
    .stButton > button { border-radius: 6px; font-weight: bold !important; height: 35px; }
    .stTextInput input, .stSelectbox select { background-color: #1a1c24 !important; border: 1px solid #464b5c !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. LOGICA AI ---
if "GEMINI_API_KEY" in st.secrets: api_key = st.secrets["GEMINI_API_KEY"]
else: api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf, model_name):
    if not api_key: return []
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(model_name)
        prompt = f"Analizza fattura ittica. REGOLE: AI->ALLEVATO, RDT->Reti da traino, LM/EF->Ami e palangari. JSON array: nome, sci, lotto, metodo, zona, origine, attrezzo. Testo: {testo_pdf}"
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except: return []

# --- 3. MOTORE STAMPA ---
def pulisci_testo(t):
    if not t: return ""
    return str(t).replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    pdf.add_page(); pdf.set_margins(4, 3, 4); w_full = 92
    pdf.set_y(3); pdf.set_font("helvetica", "B", 8); pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.set_y(7); pdf.set_font("helvetica", "B", 18); pdf.multi_cell(w_full, 7, pulisci_testo(p.get('nome','')).upper(), 0, 'C')
    pdf.set_y(16); pdf.set_font("helvetica", "I", 10); pdf.multi_cell(w_full, 4, f"({pulisci_testo(p.get('sci',''))})", 0, 'C')
    pdf.set_y(23); metodo = str(p.get('metodo', 'PESCATO')).upper(); pdf.set_font("helvetica", "", 9)
    if "ALLEVATO" in metodo: testo = f"ALLEVATO IN: {str(p.get('origine','')).upper()} (Zona: {p.get('zona','')})"
    else:
        attr = f" CON {str(p.get('attrezzo','')).upper()}" if p.get('attrezzo') and "SCONOSCIUTO" not in str(p.get('attrezzo','')).upper() else ""
        testo = f"PESCATO{attr}\nZONA: {p.get('zona','')} - {str(p.get('origine','')).upper()}"
    pdf.multi_cell(w_full, 4, testo, 0, 'C'); pdf.cell(w_full, 4, "PRODOTTO FRESCO", 0, 1, 'C')
    if str(p.get('prezzo','')).strip():
        pdf.set_y(36); pdf.set_font("helvetica", "B", 22); pdf.cell(w_full, 8, f"{p.get('prezzo','')} EUR/Kg", 0, 1, 'C')
    pdf.set_y(46); pdf.set_font("helvetica", "B", 11); pdf.set_x(5); pdf.cell(90, 8, f"LOTTO: {pulisci_testo(p.get('lotto',''))}", 1, 0, 'C')
    pdf.set_y(56); pdf.set_font("helvetica", "", 8); pdf.cell(w_full, 4, f"Conf: {p.get('conf','')} - Scad: {p.get('scadenza','')}", 0, 0, 'R')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100)); pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

def converti_pdf_in_immagine(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc.load_page(0).get_pixmap(dpi=120).tobytes("png")

# --- 4. INTERFACCIA ---
tab_et, tab_mag, tab_gastro = st.tabs(["🏷️ ETICHETTE", "📦 MAGAZZINO", "👨‍🍳 GASTRONOMIA"])

with tab_et:
    if not st.session_state.get("prodotti"):
        s1, s2 = st.tabs(["📤 CARICA FATTURA", "✍️ INSERIMENTO MANUALE"])
        with s1:
            file = st.file_uploader("Fattura PDF", type="pdf")
            if file and st.button("🚀 Analizza"):
                with st.spinner("Analisi in corso..."):
                    reader = PdfReader(file); text = " ".join([p.extract_text() for p in reader.pages])
                    res = chiedi_a_gemini(text, "gemini-2.5-flash")
                    if res:
                        for p in res: p['scadenza'] = ""; p['conf'] = ""; p['prezzo'] = ""
                        st.session_state.prodotti = res; st.rerun()
    else:
        # BARRA SUPERIORE BILANCIATA
        c_rull, c_car_all, c_exit = st.columns([1, 2, 1])
        with c_rull: st.download_button("🖨️ RULLINO COMPLETO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf")
        with c_car_all: 
            if st.button("📥 CARICA TUTTO IN MAGAZZINO", type="primary"):
                conn = sqlite3.connect(DB_FILE); c = conn.cursor(); dt = datetime.now().strftime("%d/%m/%Y")
                for pr in st.session_state.prodotti:
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (pr['nome'], pr.get('sci'), pr.get('lotto'), pr.get('metodo'), pr.get('zona'), pr.get('origine'), dt))
                conn.commit(); conn.close(); st.toast("✅ Magazzino aggiornato!")
        with c_exit:
            st.markdown("<div style='text-align: right;'>", unsafe_allow_html=True)
            if st.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        
        for i, p in enumerate(st.session_state.prodotti):
            with st.container(border=True):
                # RIGA 1: NOME (CORTO) E LOTTO + BOTTONI
                r1_left, r1_mid, r1_right = st.columns([1.5, 3, 1])
                p['nome'] = r1_left.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}", label_visibility="collapsed")
                p['lotto'] = r1_mid.text_input("Lotto", p.get('lotto',''), key=f"l_{i}", label_visibility="collapsed")
                
                # Tasti Carica (Verde) e Stampa
                btn_cols = r1_right.columns([1, 1], gap="small")
                if btn_cols[0].button("📥 Carica", key=f"sv_{i}", type="primary"):
                    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (p['nome'], p.get('sci'), p.get('lotto'), p.get('metodo'), p.get('zona'), p.get('origine'), datetime.now().strftime("%d/%m/%Y")))
                    conn.commit(); conn.close(); st.toast("✅ Registrato!")
                btn_cols[1].download_button("🖨️ Stampa", genera_pdf_bytes([p]), f"{p['nome']}.pdf", key=f"dl_s_{i}")

                # RIGA 2: SCIENTIFICO E METODO
                r2_c1, r2_c2 = st.columns([1, 1])
                p['sci'] = r2_c1.text_input("Scientifico", p.get('sci',''), key=f"s_{i}")
                p['metodo'] = r2_c2.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=0 if "PESCATO" in str(p.get('metodo','')).upper() else 1, key=f"m_{i}")

                # RIGA 3: ATTREZZO (RIGA DEDICATA O VUOTA)
                if p['metodo'] == "PESCATO":
                    a_idx = LISTA_ATTREZZI.index(p['attrezzo']) if p.get('attrezzo') in LISTA_ATTREZZI else 0
                    p['attrezzo'] = st.selectbox("Attrezzo", LISTA_ATTREZZI, index=a_idx, key=f"a_{i}")
                else:
                    st.write("") # Spazio vuoto se allevato

                # RIGA 4: NAZIONE E ZONA
                r4_c1, r4_c2 = st.columns([1, 1])
                p['origine'] = r4_c1.text_input("Nazione", p.get('origine',''), key=f"o_{i}")
                p['zona'] = r4_c2.text_input("Zona FAO", p.get('zona',''), key=f"z_{i}")

                # RIGA 5: CONF E SCAD
                r5_c1, r5_c2 = st.columns([1, 1])
                p['conf'] = r5_c1.text_input("Conf.", p.get('conf',''), key=f"cf_{i}")
                p['scadenza'] = r5_c2.text_input("Scad.", p.get('scadenza',''), key=f"sc_{i}")

                # RIGA 6: PREZZO
                p['prezzo'] = st.text_input("Prezzo €/Kg", p.get('prezzo',''), key=f"pr_{i}")

                # ANTEPRIMA (FINE SCHEDA)
                st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=250)