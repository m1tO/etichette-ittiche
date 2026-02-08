import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime, timedelta

# --- 1. SETTINGS & STYLE ---
st.set_page_config(page_title="Ittica Catanzaro AI", page_icon="🐟", layout="wide")

st.markdown("""
<style>
    /* Pulizia totale dell'interfaccia */
    .stApp { background-color: #f8f9fa; }
    .block-container { padding-top: 2rem; }
    
    /* Card Prodotto compatte */
    .product-card {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Titoli e Label */
    .fish-title { color: #1a73e8; font-weight: bold; font-size: 1.2rem; margin-bottom: 1rem; }
    label { font-weight: 600 !important; color: #555 !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. BACKEND: MEMORIA & AI ---
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
    api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key: return []
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"Analizza fattura ittica. Estrai JSON array: nome (comm), sci (scientifico), lotto, fao, metodo, conf (data confezionamento GG/MM/AAAA). Testo: {testo_pdf}"
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        dati = json.loads(txt)
        return dati if isinstance(dati, list) else []
    except: return []

# --- 3. MOTORE PDF (DIMENSIONI FISSE 62x100) ---
def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.ln(1)
    
    nome = str(p.get('nome','')).upper()[:30]
    pdf.set_font("helvetica", "B", 14)
    pdf.multi_cell(0, 6, nome, 0, 'C')
    
    sci = str(p.get('sci',''))
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(0, 4, f"({sci})", 0, 'C')
    
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 4, f"FAO {p.get('fao','')} - {p.get('metodo','')}", 0, 1, 'C')
    pdf.cell(0, 4, f"Scadenza: {p.get('scadenza','')}", 0, 1, 'C')

    prezzo = str(p.get('prezzo', '')).strip()
    if prezzo:
        pdf.set_y(34)
        pdf.set_font("helvetica", "B", 13)
        pdf.cell(0, 6, f"EUR/Kg: {prezzo}", 0, 1, 'C')

    pdf.set_y(42)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x(15)
    pdf.cell(70, 9, f"LOTTO: {p.get('lotto','')}", 1, 0, 'C')
    
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, f"Conf: {p.get('conf','')}", 0, 0, 'R')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100))
    for p in lista_p:
        disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

# --- 4. INTERFACCIA ---
st.title("⚓ FishLabel AI")

with st.sidebar:
    st.header("⚙️ Memoria & Reset")
    st.write(f"Nomi salvati: {len(st.session_state.learned_map)}")
    if st.button("🗑️ Svuota Sessione"):
        st.session_state.clear()
        st.rerun()

# Uploader compatto
uploaded_file = st.file_uploader("Carica fattura PDF", type="pdf")

if uploaded_file:
    if "prodotti" not in st.session_state or st.session_state.get("last_f") != uploaded_file.name:
        if st.button("🚀 ANALIZZA FATTURA", type="primary", use_container_width=True):
            with st.spinner("L'AI sta leggendo..."):
                reader = PdfReader(uploaded_file)
                text = " ".join([p.extract_text() for p in reader.pages])
                raw_prod = chiedi_a_gemini(text)
                
                final_prod = []
                for p in raw_prod:
                    # Applica memoria
                    sci_key = p.get('sci', '').upper().strip()
                    if sci_key in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci_key]
                    
                    # Campi default
                    p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                    p['prezzo'] = ""
                    if not p.get('conf'): p['conf'] = datetime.now().strftime("%d/%m/%Y")
                    final_prod.append(p)
                
                st.session_state.prodotti = final_prod
                st.session_state.last_f = uploaded_file.name

    if st.session_state.get("prodotti"):
        # Tasto download Rullino in alto, compatto
        st.divider()
        pdf_rullino = genera_pdf_bytes(st.session_state.prodotti)
        st.download_button("🖨️ SCARICA RULLINO COMPLETO (PDF)", pdf_rullino, "Rullino_Etichette.pdf", "application/pdf", use_container_width=True)
        st.divider()

        # Layout prodotti in card compatte
        for i, p in enumerate(st.session_state.prodotti):
            with st.container():
                st.markdown(f"<div class='fish-title'>{i+1}. {p['nome']}</div>", unsafe_allow_html=True)
                
                # Prima riga: Identità e Lotto
                c1, c2, c3 = st.columns(3)
                p['nome'] = c1.text_input("Nome Comm.", p['nome'], key=f"n_{i}").upper()
                p['sci'] = c2.text_input("Scientifico", p['sci'], key=f"s_{i}")
                p['lotto'] = c3.text_input("Lotto", p['lotto'], key=f"l_{i}")
                
                # Seconda riga: FAO, Metodo, Prezzo
                c4, c5, c6 = st.columns(3)
                p['fao'] = c4.text_input("FAO", p['fao'], key=f"f_{i}")
                m_idx = 0 if "PESCATO" in p['metodo'].upper() else 1
                p['metodo'] = c5.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=m_idx, key=f"m_{i}")
                p['prezzo'] = c6.text_input("Prezzo/Kg (opz.)", p['prezzo'], key=f"p_{i}")
                
                # Terza riga: Date
                c7, c8 = st.columns(2)
                p['scadenza'] = c7.text_input("Scadenza", p['scadenza'], key=f"sc_{i}")
                p['conf'] = c8.text_input("Confezionamento", p['conf'], key=f"cf_{i}")
                
                # Memoria automatica
                if p['nome'] and p['sci']:
                    st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
                
                # Bottone stampa singola discreto
                pdf_singolo = genera_pdf_bytes([p])
                st.download_button(f"📄 Scarica Etichetta {i+1}", pdf_singolo, f"Etichetta_{p['nome']}.pdf", "application/pdf")
                st.markdown("---")

salva_memoria(st.session_state.learned_map)