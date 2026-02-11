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

# --- 3. MOTORE DI STAMPA ---
def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    pdf.set_y(3); pdf.set_font("helvetica", "B", 8); pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.set_y(7); pdf.set_font("helvetica", "B", 18); pdf.multi_cell(w_full, 7, str(p.get('nome','')).upper(), 0, 'C')
    pdf.set_y(16); pdf.set_font("helvetica", "I", 10); pdf.multi_cell(w_full, 4, f"({p.get('sci','')})", 0, 'C')
    pdf.set_y(23); pdf.set_font("helvetica", "", 9)
    metodo = str(p.get('metodo', 'PESCATO')).upper()
    if "ALLEVATO" in metodo: testo = f"ALLEVATO IN: {str(p.get('origine','')).upper()} (Zona: {p.get('zona','')})"
    else: testo = f"PESCATO CON {p.get('attrezzo','').upper()}\nZONA: {p.get('zona','')} - {p.get('origine','').upper()}"
    pdf.multi_cell(w_full, 4, testo, 0, 'C')
    if p.get('prezzo'):
        pdf.set_y(36); pdf.set_font("helvetica", "B", 22); pdf.cell(w_full, 8, f"{p.get('prezzo','')} EUR/Kg", 0, 1, 'C')
    pdf.set_y(46); pdf.set_font("helvetica", "B", 11); pdf.set_x(5); pdf.cell(90, 8, f"LOTTO: {p.get('lotto','')}", 1, 0, 'C')
    pdf.set_y(56); pdf.set_font("helvetica", "", 8); pdf.cell(w_full, 4, f"Conf: {p.get('conf','')} - Scad: {p.get('scadenza','')}", 0, 0, 'R')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

# --- 4. INTERFACCIA A 3 TAB ---
tab_et, tab_mag, tab_gastro = st.tabs(["🏷️ ETICHETTE", "📦 MAGAZZINO", "👨‍🍳 GASTROMIA"])

with tab_et:
    if not st.session_state.get("prodotti"):
        col_up, _ = st.columns([1, 2])
        with col_up:
            file = st.file_uploader("Fattura o Scontrino (PDF)", type="pdf")
            if file and st.button("🚀 Analizza"):
                with st.spinner("Lavoro in corso..."):
                    reader = PdfReader(file); text = " ".join([p.extract_text() for p in reader.pages])
                    res = chiedi_a_gemini(text, "gemini-2.5-flash")
                    if res: st.session_state.prodotti = res; st.rerun()
    else:
        st.success(f"✅ Trovati {len(st.session_state.prodotti)} prodotti")
        
        # TASTI AZIONE RAPIDA
        c_act1, c_act2, c_act3 = st.columns([2,2,1])
        with c_act1:
            st.download_button("🖨️ SCARICA RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf")
        with c_act2:
            # TASTO SALVA TUTTO (LA NOVITÀ)
            if st.button("📥 SALVA TUTTO IN MAGAZZINO", type="primary"):
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                data_c = datetime.now().strftime("%d/%m/%Y")
                for prod in st.session_state.prodotti:
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (prod['nome'], prod.get('sci'), prod.get('lotto'), prod.get('metodo'), prod.get('zona'), prod.get('origine'), data_c))
                conn.commit(); conn.close()
                st.toast("✅ Tutti i prodotti salvati nel Registro!")
        with c_act3:
            if st.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()
        
        for i, p in enumerate(st.session_state.prodotti):
            with st.container(border=True):
                ca, cb, cc = st.columns([3, 1, 1])
                p['nome'] = ca.text_input("Nome", p.get('nome',''), key=f"n_{i}")
                p['lotto'] = cb.text_input("Lotto", p.get('lotto',''), key=f"l_{i}")
                if cc.button("📥 SALVA", key=f"sv_{i}"):
                    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (p['nome'], p.get('sci'), p.get('lotto'), p.get('metodo'), p.get('zona'), p.get('origine'), datetime.now().strftime("%d/%m/%Y")))
                    conn.commit(); conn.close()
                    st.toast(f"✅ {p['nome']} salvato!")

with tab_mag:
    st.subheader("📋 Registro Materie Prime")
    conn = sqlite3.connect(DB_FILE)
    dati = conn.execute("SELECT data_carico, nome, lotto, metodo, origine FROM magazzino ORDER BY id DESC").fetchall()
    st.table(dati) # Visualizzazione pulita per il controllo rapido
    conn.close()

with tab_gastro:
    st.subheader("👨‍🍳 Registro Produzioni")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        piatto = st.text_input("Piatto prodotto")
        conn = sqlite3.connect(DB_FILE)
        materie = conn.execute("SELECT nome, lotto, data_carico FROM magazzino ORDER BY id DESC").fetchall()
        conn.close()
        opzioni = [f"{m[0]} (Lotto: {m[1]} - {m[2]})" for m in materie]
        ingredienti = st.multiselect("Ingredienti usati", opzioni)
        if st.button("📝 Registra Produzione"):
            if piatto and ingredienti:
                conn = sqlite3.connect(DB_FILE); c = conn.cursor()
                c.execute("INSERT INTO produzioni (piatto, ingredienti, data_prod) VALUES (?,?,?)",
                          (piatto, ", ".join(ingredienti), datetime.now().strftime("%d/%m/%Y")))
                conn.commit(); conn.close()
                st.success("✅ Registrato!")
    with col_g2:
        conn = sqlite3.connect(DB_FILE)
        st.write("Storico:")
        st.table(conn.execute("SELECT data_prod, piatto, ingredienti FROM produzioni ORDER BY id DESC LIMIT 10").fetchall())
        conn.close()