import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime

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

# --- 3. CONFIGURAZIONE AI ---
# Recupera la chiave dai secrets o dalla sidebar
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Inserisci Gemini API Key", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key:
        st.error("Manca la API Key!")
        return []
        
    genai.configure(api_key=api_key)
    
    # --- QUI C'È IL FIX: USIAMO SOLO IL 2.5 FLASH ---
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        st.error(f"Errore inizializzazione modello: {e}")
        return []
    
    prompt = f"""
    Sei un esperto ittico. Analizza questa fattura e crea un JSON array.
    
    REGOLE DI ESTRAZIONE:
    1. "nome": Nome commerciale pulito (es. "SEPPIA"). NO codici, NO provenienze.
    2. "sci": Nome scientifico (es. "Sepia officinalis").
    3. "lotto": Codice lotto PULITO (rimuovi prezzi finali tipo '30.00' o pesi).
    4. "fao": Zona FAO (es. "37.2.1").
    5. "metodo": "PESCATO" o "ALLEVATO".

    Testo Fattura:
    {testo_pdf}
    
    RISPONDI SOLO CON IL JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except Exception as e:
        st.error(f"Errore Gemini 2.5: {e}")
        return []

# --- 4. MOTORE PDF ---
def genera_etichetta_bytes(p):
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    pdf.set_auto_page_break(False)
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'].upper(), align='C')
    
    # Scientifico
    pdf.ln(1)
    fs = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", fs)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C')
    
    # Tracciabilità
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Lotto
    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((100 - 80) / 2)
    pdf.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')
    
    return bytes(pdf.output())

def mostra_anteprima(pdf_bytes):
    b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    html = f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="200" type="application/pdf"></iframe>'
    st.markdown(html, unsafe_allow_html=True)

# --- 5. INTERFACCIA ---
st.title("⚓ FishLabel AI (Gemini 2.5 Flash)")

with st.sidebar:
    st.success("✅ Modello attivo: gemini-2.5-flash")
    st.divider()
    
    st.subheader("🧠 Memoria Nomi")
    # Download JSON
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button("💾 Scarica Memoria (.json)", mem_json, "memoria_nomi.json", "application/json")
    
    # Upload JSON
    up_mem = st.file_uploader("Carica Memoria", type="json")
    if up_mem:
        st.session_state.learned_map.update(json.load(up_mem))
        st.success("Memoria aggiornata!")

    if st.button("🗑️ RESET Dati"):
        st.session_state.pop('prodotti', None)
        st.rerun()

# AREA PRINCIPALE
file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if "ultimo_f" not in st.session_state or st.session_state.ultimo_f != file.name:
        st.session_state.prodotti = None
        st.session_state.ultimo_f = file.name

    if st.button("🚀 ANALIZZA FATTURA (v2.5)", type="primary"):
        with st.spinner("Analisi in corso con Gemini 2.5..."):
            reader = PdfReader(file)
            testo = " ".join([p.extract_text() for p in reader.pages])
            
            # CHIAMATA AI
            prodotti = chiedi_a_gemini(testo)
            
            if prodotti:
                # SOVRASCRITTURA CON MEMORIA JSON
                for p in prodotti:
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                
                st.session_state.prodotti = prodotti
                st.success(f"Trovati {len(prodotti)} prodotti!")

    # RISULTATI
    if st.session_state.get("prodotti"):
        
        # TASTO STAMPA TOTALE
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        
        for p in st.session_state.prodotti:
            pdf_tot.add_page()
            pdf_tot.set_font("helvetica", "B", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
            pdf_tot.ln(1)
            pdf_tot.set_font("helvetica", "B", 15)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=7, text=p['nome'].upper(), align='C')
            pdf_tot.ln(1)
            fs = 9 if len(p['sci']) < 25 else 7
            pdf_tot.set_font("helvetica", "I", fs)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=4, text=f"({p['sci']})", align='C')
            pdf_tot.ln(2)
            pdf_tot.set_font("helvetica", "", 9)
            pdf_tot.cell(w=pdf_tot.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
            pdf_tot.set_y(38)
            pdf_tot.set_font("helvetica", "B", 12)
            pdf_tot.set_x((100 - 80) / 2)
            pdf_tot.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align='C')
            pdf_tot.set_y(54)
            pdf_tot.set_font("helvetica", "", 7)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')
            
        st.download_button("🖨️ SCARICA RULLINO COMPLETO", bytes(pdf_tot.output()), "Rullino_Completo.pdf", type="primary")
        
        st.divider()

        # LISTA PRODOTTI
        for i, p in enumerate(st.session_state.prodotti):
            with st.expander(f"📦 {p['nome']}", expanded=True):
                c1, c2 = st.columns([1, 1])
                
                with c1:
                    new_n = st.text_input("Nome", p['nome'], key=f"n_{i}")
                    new_l = st.text_input("Lotto", p['lotto'], key=f"l_{i}")
                    
                    # LOGICA APPRENDIMENTO
                    if new_n != p['nome']:
                        p['nome'] = new_n
                        sci_key = p['sci'].upper().strip()
                        st.session_state.learned_map[sci_key] = new_n
                        salva_memoria(st.session_state.learned_map)
                        st.toast(f"Salvato: {sci_key} = {new_n}")
                    
                    if new_l != p['lotto']:
                        p['lotto'] = new_l

                with c2:
                    pdf_b = genera_etichetta_bytes(p)
                    mostra_anteprima(pdf_b)
                    st.download_button("🖨️ Stampa", pdf_b, f"Etic_{i}.pdf", key=f"b_{i}")