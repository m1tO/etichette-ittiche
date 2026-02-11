import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import sqlite3
from datetime import datetime, timedelta
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
MODELLI_AI = {"⚡ Gemini 2.5 Flash": "gemini-2.5-flash", "🧊 Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite", "🔥 Gemini 3 Flash": "gemini-3-flash"}

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #262730; border: 1px solid #464b5c; border-radius: 8px; padding: 20px;
    }
    h1 { color: #4facfe; font-size: 2.2rem; font-weight: 800; }
    button[data-baseweb="tab"] { font-size: 22px !important; font-weight: 700 !important; }
    .stButton > button { width: 100%; border-radius: 8px; }
    /* Ingrandimento tab opzioni iniziali */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 24px !important; font-weight: bold !important;
    }
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
        prompt = f"Analizza fattura ed estrai JSON array: nome, sci, lotto, metodo, zona, origine, attrezzo. Testo: {testo_pdf}"
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except: return []

# --- 3. MOTORE DI STAMPA (PRECISIONE MILLIMETRICA) ---
def pulisci_testo(t):
    if not t: return ""
    return str(t).replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    pdf.set_y(3); pdf.set_font("helvetica", "B", 8); pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.set_y(7); pdf.set_font("helvetica", "B", 18); pdf.multi_cell(w_full, 7, pulisci_testo(p.get('nome','')).upper(), 0, 'C')
    pdf.set_y(16); pdf.set_font("helvetica", "I", 10); pdf.multi_cell(w_full, 4, f"({pulisci_testo(p.get('sci',''))})", 0, 'C')
    pdf.set_y(23); pdf.set_font("helvetica", "", 9)
    metodo = str(p.get('metodo', 'PESCATO')).upper()
    if "ALLEVATO" in metodo: testo = f"ALLEVATO IN: {str(p.get('origine','')).upper()} (Zona: {p.get('zona','')})"
    else:
        attr = f" CON {p.get('attrezzo','').upper()}" if p.get('attrezzo') and "SCONOSCIUTO" not in str(p.get('attrezzo','')).upper() else ""
        testo = f"PESCATO{attr}\nZONA: {p.get('zona','')} - {str(p.get('origine','')).upper()}"
    pdf.multi_cell(w_full, 4, testo, 0, 'C')
    pdf.cell(w_full, 4, "PRODOTTO FRESCO", 0, 1, 'C')
    if str(p.get('prezzo','')).strip():
        pdf.set_y(36); pdf.set_font("helvetica", "B", 22); pdf.cell(w_full, 8, f"{p.get('prezzo','')} EUR/Kg", 0, 1, 'C')
    pdf.set_y(46); pdf.set_font("helvetica", "B", 11); pdf.set_x(5); pdf.cell(90, 8, f"LOTTO: {pulisci_testo(p.get('lotto',''))}", 1, 0, 'C')
    pdf.set_y(56); pdf.set_font("helvetica", "", 8); pdf.cell(w_full, 4, f"Conf: {p.get('conf','')} - Scad: {p.get('scadenza','')}", 0, 0, 'R')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

def converti_pdf_in_immagine(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc.load_page(0).get_pixmap(dpi=120).tobytes("png")

# --- 4. INTERFACCIA A 3 TAB ---
tab_et, tab_mag, tab_gastro = st.tabs(["🏷️ ETICHETTE", "📦 MAGAZZINO", "👨‍🍳 GASTROMIA"])

with tab_et:
    if not st.session_state.get("prodotti"):
        # REINSERIMENTO TABS MANUALI/AI
        sub_tab1, sub_tab2 = st.tabs(["📤 CARICA FATTURA", "✍️ INSERIMENTO MANUALE"])
        
        with sub_tab1:
            n_modello = st.selectbox("🧠 Motore AI", list(MODELLI_AI.keys()), key="model_sel")
            file = st.file_uploader("Trascina qui il PDF", type="pdf")
            if file and st.button("🚀 Analizza PDF", type="primary"):
                with st.spinner("Analisi in corso..."):
                    reader = PdfReader(file); text = " ".join([p.extract_text() for p in reader.pages])
                    res = chiedi_a_gemini(text, MODELLI_AI[n_modello])
                    if res:
                        for p in res: p['scadenza'] = ""; p['conf'] = ""; p['prezzo'] = ""
                        st.session_state.prodotti = res; st.rerun()
        
        with sub_tab2:
            st.write("### Crea un'etichetta da zero")
            if st.button("➕ Crea Nuova Etichetta", type="secondary"):
                p_vuoto = {"nome": "NUOVO PRODOTTO", "sci": "", "lotto": "", "metodo": "PESCATO", "zona": "37.1.3", "origine": "ITALIA", "attrezzo": "Sconosciuto", "conf": "", "scadenza": "", "prezzo": ""}
                st.session_state.prodotti = [p_vuoto]; st.rerun()
    else:
        st.success(f"✅ Trovati {len(st.session_state.prodotti)} prodotti")
        
        c_act1, c_act2, c_act3 = st.columns([2,2,1])
        with c_act1: st.download_button("🖨️ SCARICA RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf")
        with c_act2:
            if st.button("📥 SALVA TUTTO IN MAGAZZINO", type="primary"):
                conn = sqlite3.connect(DB_FILE); c = conn.cursor(); data_c = datetime.now().strftime("%d/%m/%Y")
                for prod in st.session_state.prodotti:
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (prod['nome'], prod.get('sci'), prod.get('lotto'), prod.get('metodo'), prod.get('zona'), prod.get('origine'), data_c))
                conn.commit(); conn.close(); st.toast("✅ Magazzino aggiornato!")
        with c_act3:
            if st.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()
        
        for i, p in enumerate(st.session_state.prodotti):
            with st.container(border=True):
                ca, cb, cc = st.columns([3, 1, 1])
                p['nome'] = ca.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}")
                p['lotto'] = cb.text_input("Lotto", p.get('lotto',''), key=f"l_{i}")
                if cc.button("📥 SALVA", key=f"sv_{i}"):
                    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (p['nome'], p.get('sci'), p.get('lotto'), p.get('metodo'), p.get('zona'), p.get('origine'), datetime.now().strftime("%d/%m/%Y")))
                    conn.commit(); conn.close(); st.toast(f"✅ {p['nome']} salvato!")

                c1, c2, c3 = st.columns(3)
                p['sci'] = c1.text_input("Scientifico", p.get('sci',''), key=f"s_{i}")
                p['metodo'] = c2.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=0 if "PESCATO" in str(p.get('metodo','')).upper() else 1, key=f"m_{i}")
                p['zona'] = c3.text_input("Zona FAO", p.get('zona',''), key=f"z_{i}")

                c4, c5, c6 = st.columns(3)
                p['origine'] = c4.text_input("Nazionalità", p.get('origine',''), key=f"o_{i}")
                if p['metodo'] == "PESCATO":
                    a_idx = LISTA_ATTREZZI.index(p['attrezzo']) if p.get('attrezzo') in LISTA_ATTREZZI else 0
                    p['attrezzo'] = c5.selectbox("Attrezzo", LISTA_ATTREZZI, index=a_idx, key=f"a_{i}")
                p['prezzo'] = c6.text_input("Prezzo (€/Kg)", p.get('prezzo',''), key=f"pr_{i}")

                c7, c8 = st.columns(2)
                p['conf'] = c7.text_input("Confezionamento", p.get('conf',''), key=f"cf_{i}")
                p['scadenza'] = c8.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")

                st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=400)

with tab_mag:
    st.subheader("📋 Registro Materie Prime")
    conn = sqlite3.connect(DB_FILE)
    dati = conn.execute("SELECT data_carico, nome, lotto, metodo, origine FROM magazzino ORDER BY id DESC").fetchall()
    st.table(dati); conn.close()

with tab_gastro:
    st.subheader("👨‍🍳 Registro Produzioni")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        piatto = st.text_input("Nome Piatto")
        conn = sqlite3.connect(DB_FILE); materie = conn.execute("SELECT nome, lotto, data_carico FROM magazzino ORDER BY id DESC").fetchall(); conn.close()
        ingredienti = st.multiselect("Ingredienti", [f"{m[0]} (Lotto: {m[1]} - {m[2]})" for m in materie])
        if st.button("📝 Registra Produzione"):
            if piatto and ingredienti:
                conn = sqlite3.connect(DB_FILE); c = conn.cursor()
                c.execute("INSERT INTO produzioni (piatto, ingredienti, data_prod) VALUES (?,?,?)", (piatto, ", ".join(ingredienti), datetime.now().strftime("%d/%m/%Y")))
                conn.commit(); conn.close(); st.success("✅ Registrato!")
    with col_g2:
        conn = sqlite3.connect(DB_FILE); st.write("Storico:"); st.table(conn.execute("SELECT data_prod, piatto, ingredienti FROM produzioni ORDER BY id DESC LIMIT 10").fetchall()); conn.close()