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

# --- STILE CSS ---
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
        prompt = f"Analizza fattura. JSON: nome, sci, lotto, metodo, zona, origine, attrezzo. Testo: {testo_pdf}"
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except: return []

# --- 3. MOTORE STAMPA ---
def disegna_su_pdf(pdf, p):
    pdf.add_page(); pdf.set_margins(4, 3, 4); w_full = 92
    pdf.set_y(3); pdf.set_font("helvetica", "B", 8); pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.set_y(7); pdf.set_font("helvetica", "B", 18); pdf.multi_cell(w_full, 7, str(p.get('nome','')).upper(), 0, 'C')
    pdf.set_y(16); pdf.set_font("helvetica", "I", 10); pdf.multi_cell(w_full, 4, f"({str(p.get('sci',''))})", 0, 'C')
    pdf.set_y(23); metodo = str(p.get('metodo', 'PESCATO')).upper(); pdf.set_font("helvetica", "", 9)
    if "ALLEVATO" in metodo: testo = f"ALLEVATO IN: {str(p.get('origine','')).upper()} (Zona: {p.get('zona','')})"
    else:
        attr = f" CON {str(p.get('attrezzo','')).upper()}" if p.get('attrezzo') else ""
        testo = f"PESCATO{attr}\nZONA: {p.get('zona','')} - {str(p.get('origine','')).upper()}"
    pdf.multi_cell(w_full, 4, testo, 0, 'C')
    if p.get('prezzo'):
        pdf.set_y(36); pdf.set_font("helvetica", "B", 22); pdf.cell(w_full, 8, f"{p.get('prezzo','')} EUR/Kg", 0, 1, 'C')
    pdf.set_y(46); pdf.set_font("helvetica", "B", 11); pdf.set_x(5); pdf.cell(90, 8, f"LOTTO: {p.get('lotto','')}", 1, 0, 'C')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100)); pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

# --- 4. INTERFACCIA ---
tab_et, tab_mag, tab_gastro = st.tabs(["🏷️ ETICHETTE", "📦 MAGAZZINO", "👨‍🍳 GASTRONOMIA"])

with tab_et:
    if not st.session_state.get("prodotti"):
        file = st.file_uploader("Carica PDF", type="pdf")
        if file and st.button("🚀 Analizza"):
            reader = PdfReader(file); text = " ".join([p.extract_text() for p in reader.pages])
            st.session_state.prodotti = chiedi_a_gemini(text, "gemini-2.5-flash"); st.rerun()
    else:
        c1, c2, c3 = st.columns([1, 2, 1])
        c1.download_button("🖨️ RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf")
        if c2.button("📥 CARICA TUTTO IN MAGAZZINO", type="primary"):
            conn = sqlite3.connect(DB_FILE); c = conn.cursor(); dt = datetime.now().strftime("%d/%m/%Y")
            for pr in st.session_state.prodotti:
                c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                          (pr['nome'], pr.get('sci'), pr.get('lotto'), pr.get('metodo'), pr.get('zona'), pr.get('origine'), dt))
            conn.commit(); conn.close(); st.toast("✅ Magazzino aggiornato!"); st.rerun()
        if c3.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()
        
        for i, p in enumerate(st.session_state.prodotti):
            with st.container(border=True):
                r1_l, r1_m, r1_r = st.columns([1.5, 3, 1])
                p['nome'] = r1_l.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}", label_visibility="collapsed")
                p['lotto'] = r1_m.text_input("Lotto", p.get('lotto',''), key=f"l_{i}", label_visibility="collapsed")
                
                btns = r1_r.columns(2, gap="small")
                if btns[0].button("📥 Carica", key=f"sv_{i}", type="primary"):
                    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (p['nome'], p.get('sci'), p.get('lotto'), p.get('metodo'), p.get('zona'), p.get('origine'), datetime.now().strftime("%d/%m/%Y")))
                    conn.commit(); conn.close(); st.rerun() # AGGIORNAMENTO ISTANTANEO
                btns[1].download_button("🖨️ Stampa", genera_pdf_bytes([p]), f"{p['nome']}.pdf", key=f"dl_s_{i}")

                # Griglia Dati (come richiesto)
                r2_1, r2_2 = st.columns(2)
                p['sci'] = r2_1.text_input("Scientifico", p.get('sci',''), key=f"s_{i}")
                p['metodo'] = r2_2.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=0 if "PESCATO" in str(p.get('metodo','')).upper() else 1, key=f"m_{i}")
                
                if p['metodo'] == "PESCATO":
                    p['attrezzo'] = st.selectbox("Attrezzo", LISTA_ATTREZZI, key=f"a_{i}")
                else: st.write("")

                r4_1, r4_2 = st.columns(2)
                p['origine'] = r4_1.text_input("Nazione", p.get('origine',''), key=f"o_{i}")
                p['zona'] = r4_2.text_input("Zona FAO", p.get('zona',''), key=f"z_{i}")

                r5_1, r5_2 = st.columns(2)
                p['conf'] = r5_1.text_input("Conf.", p.get('conf',''), key=f"cf_{i}")
                p['scadenza'] = r5_2.text_input("Scad.", p.get('scadenza',''), key=f"sc_{i}")
                
                p['prezzo'] = st.text_input("Prezzo €/Kg", p.get('prezzo',''), key=f"pr_{i}")

with tab_mag:
    conn = sqlite3.connect(DB_FILE)
    dati = conn.execute("SELECT data_carico, nome, lotto, metodo, origine FROM magazzino ORDER BY id DESC").fetchall()
    if dati:
        st.dataframe([{"Data": d[0], "Prodotto": d[1], "Lotto": d[2], "Metodo": d[3], "Origine": d[4]} for d in dati], use_container_width=True, hide_index=True)
        if st.button("🚨 SVUOTA TUTTO"):
            conn.execute("DELETE FROM magazzino"); conn.commit(); st.rerun()
    else: st.info("Magazzino vuoto.")
    conn.close()

with tab_gastro:
    st.write("👨‍🍳 Registro Produzioni")
    # ... (Codice Gastro invariato)