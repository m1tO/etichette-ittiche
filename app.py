import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
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
MODELLI_AI = {"⚡ Gemini 2.5 Flash": "gemini-2.5-flash", "🧊 Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite", "🔥 Gemini 3 Flash": "gemini-3-flash"}

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #262730; border: 1px solid #464b5c; border-radius: 8px; padding: 20px;
    }
    h1 { color: #4facfe; font-size: 2.2rem; font-weight: 800; }
    
    /* Font Schede (Tab) Fissato e Leggibile */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 20px !important; 
        font-weight: 600 !important;
        color: #4facfe !important;
    }
    .stButton > button { width: 100%; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- 2. LOGICA AI (VERSIONE POTENZIATA) ---
if "GEMINI_API_KEY" in st.secrets: api_key = st.secrets["GEMINI_API_KEY"]
else: api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf, model_name):
    if not api_key: return []
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(model_name)
        prompt = f"""Analizza fattura. REGOLE: AI->ALLEVATO, RDT->Reti da traino, LM/EF->Ami e palangari. 
        JSON array: nome, sci, lotto, metodo, zona, origine, attrezzo. Testo: {testo_pdf}"""
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
                with st.spinner("Analisi..."):
                    reader = PdfReader(file); text = " ".join([p.extract_text() for p in reader.pages])
                    res = chiedi_a_gemini(text, "gemini-2.5-flash")
                    if res:
                        for p in res: p['scadenza'] = ""; p['conf'] = ""; p['prezzo'] = ""
                        st.session_state.prodotti = res; st.rerun()
        with s2:
            if st.button("➕ Crea Nuova"):
                st.session_state.prodotti = [{"nome": "NUOVO PRODOTTO", "sci": "", "lotto": "", "metodo": "PESCATO", "zona": "37.1.3", "origine": "ITALIA", "attrezzo": "Sconosciuto", "conf": "", "scadenza": "", "prezzo": ""}]; st.rerun()
    else:
        c_a1, c_a2, c_a3 = st.columns([2,2,1])
        with c_a1: st.download_button("🖨️ RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf")
        with c_a2:
            if st.button("📥 SALVA TUTTO", type="primary"):
                conn = sqlite3.connect(DB_FILE); c = conn.cursor(); dt = datetime.now().strftime("%d/%m/%Y")
                for pr in st.session_state.prodotti:
                    c.execute("INSERT INTO magazzino (nome, sci, lotto, metodo, zona, origine, data_carico) VALUES (?,?,?,?,?,?,?)",
                              (pr['nome'], pr.get('sci'), pr.get('lotto'), pr.get('metodo'), pr.get('zona'), pr.get('origine'), dt))
                conn.commit(); conn.close(); st.toast("✅ Magazzino aggiornato!")
        with c_a3:
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
                
                c_1, c_2, c_3 = st.columns(3)
                p['sci'] = c_1.text_input("Scientifico", p.get('sci',''), key=f"s_{i}")
                p['metodo'] = c_2.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=0 if "PESCATO" in str(p.get('metodo','')).upper() else 1, key=f"m_{i}")
                p['zona'] = c_3.text_input("Zona FAO", p.get('zona',''), key=f"z_{i}")
                
                c_4, c_5, c_6 = st.columns(3)
                p['origine'] = c_4.text_input("Origine", p.get('origine',''), key=f"o_{i}")
                if p['metodo'] == "PESCATO":
                    a_idx = LISTA_ATTREZZI.index(p['attrezzo']) if p.get('attrezzo') in LISTA_ATTREZZI else 0
                    p['attrezzo'] = c_5.selectbox("Attrezzo", LISTA_ATTREZZI, index=a_idx, key=f"a_{i}")
                p['prezzo'] = c_6.text_input("Prezzo (€/Kg)", p.get('prezzo',''), key=f"pr_{i}")
                
                st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=300)

with tab_mag:
    st.subheader("📋 Registro Materie Prime")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    dati = c.execute("SELECT id, data_carico, nome, lotto, metodo, origine FROM magazzino ORDER BY id DESC").fetchall()
    
    if dati:
        display_data = [{"Data Carico": d[1], "Prodotto": d[2], "Lotto": d[3], "Metodo": d[4], "Origine": d[5]} for d in dati]
        st.dataframe(display_data, use_container_width=True, hide_index=True)
        
        st.divider()
        st.write("🗑️ **Area Rimozione Selettiva**")
        # Selezione riga tramite Dropdown invece di ID manuale
        opzioni_del = {f"{d[1]} - {d[2]} (Lotto: {d[3]})": d[0] for d in dati}
        scelta = st.selectbox("Seleziona il prodotto da eliminare dal registro:", list(opzioni_del.keys()))
        
        if st.button("❌ ELIMINA PRODOTTO SELEZIONATO", type="secondary"):
            id_to_del = opzioni_del[scelta]
            c.execute("DELETE FROM magazzino WHERE id=?", (id_to_del,))
            conn.commit(); conn.close(); st.rerun()
            
        if st.button("🚨 SVUOTA TUTTO IL REGISTRO"):
            c.execute("DELETE FROM magazzino"); conn.commit(); conn.close(); st.rerun()
    else:
        st.info("Magazzino vuoto.")
    conn.close()

with tab_gastro:
    st.subheader("👨‍🍳 Registro Produzioni")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        piatto = st.text_input("Nome Piatto")
        conn = sqlite3.connect(DB_FILE)
        materie = conn.execute("SELECT nome, lotto, data_carico FROM magazzino ORDER BY id DESC").fetchall()
        ingredienti = st.multiselect("Ingredienti", [f"{m[0]} (Lotto: {m[1]} - {m[2]})" for m in materie])
        if st.button("📝 Registra"):
            if piatto and ingredienti:
                c = conn.cursor()
                c.execute("INSERT INTO produzioni (piatto, ingredienti, data_prod) VALUES (?,?,?)", (piatto, ", ".join(ingredienti), datetime.now().strftime("%d/%m/%Y")))
                conn.commit(); st.success("Registrato!"); st.rerun()
        conn.close()
    with col_g2:
        conn = sqlite3.connect(DB_FILE)
        prods = conn.execute("SELECT id, data_prod, piatto, ingredienti FROM produzioni ORDER BY id DESC").fetchall()
        for pr in prods:
            with st.expander(f"📅 {pr[1]} - {pr[2]}"):
                st.write(f"Ingredienti: {pr[3]}")
                if st.button("🗑️ Elimina", key=f"del_g_{pr[0]}"):
                    c = conn.cursor(); c.execute("DELETE FROM produzioni WHERE id=?", (pr[0],))
                    conn.commit(); conn.close(); st.rerun()
        conn.close()