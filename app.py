import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime
from io import BytesIO

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Ittica Catanzaro AI PRO", page_icon="🐟", layout="wide")

# --- 2. GESTIONE MEMORIA (JSON) ---
MEMORIA_FILE = "memoria_nomi.json"

def carica_memoria():
    if os.path.exists(MEMORIA_FILE):
        try:
            with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def salva_memoria(memoria):
    with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=4)

if "learned_map" not in st.session_state:
    st.session_state.learned_map = carica_memoria()

# --- 3. CONFIGURAZIONE AI (GEMINI 2.5 FLASH) ---
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Inserisci Gemini API Key", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key:
        st.error("Manca la API Key!")
        return []
        
    genai.configure(api_key=api_key)
    # Usiamo il modello che funziona dai tuoi screenshot
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Analizza questa fattura ittica. Estrai i prodotti e crea un array JSON.
    REGOLE:
    - "nome": Nome commerciale pulito (es. SEPPIA). No codici, no zone (es. NO GRECIA).
    - "sci": Nome scientifico (es. Sepia officinalis).
    - "lotto": Codice lotto pulito (rimuovi prezzi finali tipo 30.00).
    - "fao": Zona FAO (es. 37.2.1).
    - "metodo": "PESCATO" o "ALLEVATO".
    Testo: {testo_pdf}
    RISPONDI SOLO CON IL JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return []

# --- 4. MOTORE PDF (ETICHETTE 62x100mm) ---
def disegna_etichetta(pdf, p):
    pdf.add_page()
    pdf.set_auto_page_break(False)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
    pdf.ln(1)
    
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'].upper(), align='C')
    
    pdf.ln(1)
    fs = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", fs)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C')
    
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', ln=True)
    
    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((100 - 80) / 2)
    pdf.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align='C')
    
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

def mostra_anteprima(pdf_bytes):
    """Mostra il PDF evitando il blocco di Chrome se possibile."""
    b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    # Usiamo un embed più moderno
    pdf_display = f'<embed src="data:application/pdf;base64,{b64}" width="100%" height="250" type="application/pdf">'
    st.markdown(pdf_display, unsafe_allow_html=True)

# --- 5. INTERFACCIA UTENTE ---
st.title("⚓ FishLabel AI PRO (v2.5 Flash)")

with st.sidebar:
    st.header("⚙️ Memoria Nomi")
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button("💾 Scarica JSON", mem_json, "memoria_nomi.json", "application/json")
    
    up_mem = st.file_uploader("Carica JSON", type="json")
    if up_mem:
        st.session_state.learned_map.update(json.load(up_mem))
        st.success("Memoria caricata!")

    if st.button("🗑️ RESET TOTALE"):
        st.session_state.pop('prodotti', None)
        st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if "ultimo_f" not in st.session_state or st.session_state.ultimo_f != file.name:
        st.session_state.prodotti = None
        st.session_state.ultimo_f = file.name

    if st.button("🚀 ANALIZZA CON AI", type="primary"):
        with st.spinner("Gemini 2.5 Flash sta leggendo..."):
            reader = PdfReader(file)
            testo = " ".join([p.extract_text() for p in reader.pages])
            prodotti_ai = chiedi_a_gemini(testo)
            
            if prodotti_ai:
                # Applica memoria JSON subito
                for p in prodotti_ai:
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                st.session_state.prodotti = prodotti_ai

    if st.session_state.get("prodotti"):
        # Tasto Scarica Tutto
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        for p in st.session_state.prodotti:
            disegna_etichetta(pdf_tot, p)
        
        st.download_button("🖨️ SCARICA TUTTO IL RULLINO", bytes(pdf_tot.output()), "Rullino_Completo.pdf", type="primary")
        st.divider()

        # Lista Prodotti Editabile
        for i, p in enumerate(st.session_state.prodotti):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}", expanded=True):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    # I campi che volevi modificare!
                    n_val = st.text_input("Nome Commerciale", p['nome'], key=f"n_{i}")
                    l_val = st.text_input("Lotto", p['lotto'], key=f"l_{i}")
                    
                    # Apprendimento
                    if n_val != p['nome']:
                        p['nome'] = n_val
                        sci_key = p['sci'].upper().strip()
                        st.session_state.learned_map[sci_key] = n_val
                        salva_memoria(st.session_state.learned_map)
                        st.toast(f"Imparato: {sci_key} -> {n_val}")
                    
                    p['lotto'] = l_val

                with col2:
                    # Anteprima e Stampa Singola
                    pdf_s = FPDF(orientation='L', unit='mm', format=(62, 100))
                    pdf_s.set_margins(4, 3, 4)
                    disegna_etichetta(pdf_s, p)
                    pdf_bytes = bytes(pdf_s.output())
                    
                    mostra_anteprima(pdf_bytes)
                    st.download_button("🖨️ Stampa", pdf_bytes, f"Etic_{i}.pdf", key=f"b_{i}")