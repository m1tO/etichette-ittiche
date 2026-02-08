import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime, timedelta

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Ittica Catanzaro AI", page_icon="🐟", layout="wide")

# --- 2. MEMORIA (JSON) ---
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

# --- 3. AI (GEMINI) ---
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Inserisci Gemini API Key", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key:
        st.error("Manca la API Key!")
        return []
    
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
    except:
        model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    Analizza fattura ittica. Estrai JSON array.
    REGOLE:
    1. "nome": Nome commerciale pulito (es. SEPPIA).
    2. "sci": Nome scientifico.
    3. "lotto": Codice lotto PULITO.
    4. "fao": Zona FAO (es. 37.2.1).
    5. "metodo": "PESCATO" o "ALLEVATO".
    
    Testo: {testo_pdf}
    RISPONDI SOLO JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(txt)
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return []

# --- 4. MOTORE PDF ---
def genera_pdf_etichetta(p):
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    pdf.set_auto_page_break(False)
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
    pdf.ln(1)
    
    # Nome
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=str(p['nome']).upper(), align='C')
    
    # Scientifico
    pdf.ln(1)
    fs = 9 if len(str(p['sci'])) < 25 else 7
    pdf.set_font("helvetica", "I", fs)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C')
    
    # Dati
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', ln=True)
    
    # Scadenza
    pdf.set_font("helvetica", "", 8)
    pdf.cell(w=pdf.epw, h=4, text=f"Scadenza: {p.get('scadenza', '')}", align='C', ln=True)

    # Lotto
    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((100 - 80) / 2)
    pdf.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align='C')
    
    # Data Conf
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')
    
    return pdf

# --- 5. INTERFACCIA ---
st.title("⚓ FishLabel AI")

with st.sidebar:
    st.header("⚙️ Memoria")
    # Tasti Download/Upload Memoria
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button("💾 Scarica Memoria", mem_json, "memoria.json", "application/json")
    up = st.file_uploader("Carica Memoria", type="json")
    if up:
        st.session_state.learned_map.update(json.load(up))
        st.success("Ok!")
        
    if st.button("🗑️ RESET"):
        st.session_state.clear()
        st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if "ultimo_f" not in st.session_state or st.session_state.ultimo_f != file.name:
        st.session_state.prodotti = None
        st.session_state.ultimo_f = file.name

    if st.button("🚀 ANALIZZA", type="primary"):
        with st.spinner("L'AI sta leggendo..."):
            reader = PdfReader(file)
            testo = " ".join([p.extract_text() for p in reader.pages])
            prodotti = chiedi_a_gemini(testo)
            
            if prodotti:
                for p in prodotti:
                    # Memoria
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                    # Scadenza default
                    p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                
                st.session_state.prodotti = prodotti

    if st.session_state.get("prodotti"):
        # --- BLOCCO STAMPA TOTALE (RULLINO) ---
        st.divider()
        st.subheader("🖨️ Stampa Tutto")
        
        # Rigeneriamo il PDF Totale con i dati attuali (incluse modifiche fatte sotto)
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        
        for p in st.session_state.prodotti:
            # Aggiungiamo pagina al rullino usando la logica condivisa (duplicata per FPDF structure)
            pdf_tot.add_page()
            # (Codice disegno identico alla singola)
            pdf_tot.set_font("helvetica", "B", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
            pdf_tot.ln(1)
            pdf_tot.set_font("helvetica", "B", 15)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=7, text=str(p['nome']).upper(), align='C')
            pdf_tot.ln(1)
            fs = 9 if len(str(p['sci'])) < 25 else 7
            pdf_tot.set_font("helvetica", "I", fs)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=4, text=f"({p['sci']})", align='C')
            pdf_tot.ln(2)
            pdf_tot.set_font("helvetica", "", 9)
            pdf_tot.cell(w=pdf_tot.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', ln=True)
            pdf_tot.set_font("helvetica", "", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Scadenza: {p.get('scadenza', '')}", align='C', ln=True)
            pdf_tot.set_y(38)
            pdf_tot.set_font("helvetica", "B", 12)
            pdf_tot.set_x((100 - 80) / 2)
            pdf_tot.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align='C')
            pdf_tot.set_y(54)
            pdf_tot.set_font("helvetica", "", 7)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')

        st.download_button(
            "📄 SCARICA RULLINO COMPLETO (PDF)", 
            bytes(pdf_tot.output()), 
            "Rullino.pdf", 
            "application/pdf", 
            type="primary",
            use_container_width=True
        )
        
        st.divider()

        # --- LISTA PRODOTTI EDITABILI ---
        for i, p in enumerate(st.session_state.prodotti):
            with st.container():
                st.markdown(f"**{i+1}. {p['nome']}**")
                c1, c2, c3 = st.columns([1, 1, 1])
                
                # Colonna 1: Identità
                with c1:
                    new_n = st.text_input("Nome", p['nome'], key=f"n_{i}")
                    new_s = st.text_input("Sci", p['sci'], key=f"s_{i}")
                    # Apprendimento
                    if new_n != p['nome']:
                        p['nome'] = new_n
                        st.session_state.learned_map[new_s.upper().strip()] = new_n
                        salva_memoria(st.session_state.learned_map)
                    if new_s != p['sci']: p['sci'] = new_s

                # Colonna 2: Dati Tecnici
                with c2:
                    p['fao'] = st.text_input("FAO", p['fao'], key=f"f_{i}")
                    p['metodo'] = st.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=0 if p['metodo']=="PESCATO" else 1, key=f"m_{i}")
                    p['lotto'] = st.text_input("Lotto", p['lotto'], key=f"l_{i}")

                # Colonna 3: Scadenza e Azioni
                with c3:
                    p['scadenza'] = st.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")
                    
                    # Genera PDF Singolo
                    pdf_s = genera_pdf_etichetta(p)
                    pdf_bytes = bytes(pdf_s.output())
                    
                    st.write("")
                    # TASTO DOWNLOAD SINGOLO (Funziona sempre)
                    st.download_button(
                        "🖨️ Scarica Etichetta", 
                        pdf_bytes, 
                        f"{p['nome']}.pdf", 
                        "application/pdf",
                        key=f"dl_{i}"
                    )
                    
                    # Anteprima semplificata (iframe standard)
                    b64 = base64.b64encode(pdf_bytes).decode('utf-8')
                    st.markdown(f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0&view=FitH" width="100%" height="150"></iframe>', unsafe_allow_html=True)
            
            st.markdown("---")