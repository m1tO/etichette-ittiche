import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime, timedelta
import fitz  # Libreria PyMuPDF (pip install pymupdf)
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Ittica Catanzaro AI", page_icon="🐟", layout="wide")

# CSS per pulire l'interfaccia
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 1rem;}
    button[kind="primary"] {background-color: #007bff; border-color: #007bff;}
</style>
""", unsafe_allow_html=True)

# --- 2. GESTIONE MEMORIA ---
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

# --- 3. AI (GEMINI 2.5 FLASH) ---
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
        # Priorità al modello 2.5 Flash
        model = genai.GenerativeModel('gemini-2.5-flash')
    except:
        # Fallback se non disponibile
        model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    Analizza la fattura ittica. Estrai un array JSON.
    REGOLE:
    1. "nome": Nome commerciale pulito (es. SEPPIA). No codici.
    2. "sci": Nome scientifico (es. Sepia officinalis).
    3. "lotto": Codice lotto PULITO (rimuovi prezzi tipo 30.00).
    4. "fao": Zona FAO (es. 37.2.1).
    5. "metodo": "PESCATO" o "ALLEVATO".
    
    Testo: {testo_pdf}
    RISPONDI SOLO JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        dati = json.loads(txt)
        
        # Normalizzazione Anti-Crash
        lista_pulita = []
        if isinstance(dati, list):
            for p in dati:
                p_safe = {
                    "nome": p.get("nome", "DA COMPILARE"),
                    "sci": p.get("sci", ""),
                    "lotto": p.get("lotto", ""),
                    "fao": p.get("fao", ""),
                    "metodo": p.get("metodo", "PESCATO")
                }
                lista_pulita.append(p_safe)
            return lista_pulita
        else:
            return []
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return []

# --- 4. MOTORE PDF & IMMAGINI ---
def genera_pdf_bytes(p):
    # Setup foglio 62x100mm landscape
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    pdf.set_auto_page_break(False)
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
    pdf.ln(1)
    
    # Nome
    nome = str(p.get('nome', '')).upper()
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=nome, align='C')
    
    # Scientifico
    pdf.ln(1)
    sci = str(p.get('sci', ''))
    fs = 9 if len(sci) < 25 else 7
    pdf.set_font("helvetica", "I", fs)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({sci})", align='C')
    
    # Dati Tecnici
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    fao = p.get('fao', '')
    metodo = p.get('metodo', '')
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {fao} - {metodo}", align='C', ln=True)
    
    # Scadenza
    pdf.set_font("helvetica", "", 8)
    scad = p.get('scadenza', '')
    pdf.cell(w=pdf.epw, h=4, text=f"Scadenza: {scad}", align='C', ln=True)

    # Lotto
    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((100 - 80) / 2)
    lotto = str(p.get('lotto', ''))
    pdf.cell(w=80, h=11, text=f"LOTTO: {lotto}", border=1, align='C')
    
    # Data Conf
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')
    
    return bytes(pdf.output())

def converti_pdf_in_immagine(pdf_bytes):
    """Converte PDF in PNG per evitare blocchi browser."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=150)
    return pix.tobytes("png")

def bottone_stampa_immagine(img_bytes, key_id):
    """
    Crea un bottone che apre un popup dimensionato per Brother (62mm x 100mm).
    """
    b64_img = base64.b64encode(img_bytes).decode('utf-8')
    
    html = f"""
    <div style="text-align: center; margin-top: 10px;">
        <button onclick="stampa_{key_id}()" 
            style="background-color: #007bff; color: white; border: none; padding: 10px 20px; 
                   border-radius: 5px; font-weight: bold; cursor: pointer; width: 100%;">
            🖨️ STAMPA SUBITO
        </button>
    </div>
    <script>
        function stampa_{key_id}() {{
            // Apre popup dimensionato
            var win = window.open('', '_blank', 'width=500,height=400');
            win.document.write('<html><head><title>Stampa Etichetta</title>');
            win.document.write('<style>');
            // CSS MAGICO: Forza la stampante a usare queste dimensioni
            win.document.write('@page {{ size: 62mm 100mm; margin: 0; }}'); 
            win.document.write('body {{ margin: 0; padding: 0; display: flex; justify-content: center; align-items: flex-start; }}');
            win.document.write('img {{ width: 62mm; height: 100mm; object-fit: contain; }}');
            win.document.write('</style>');
            win.document.write('</head><body>');
            win.document.write('<img src="data:image/png;base64,{b64_img}" onload="window.print(); window.close();"/>');
            win.document.write('</body></html>');
            win.document.close();
        }}
    </script>
    """
    components.html(html, height=60)

# --- 5. INTERFACCIA UTENTE ---
st.title("⚓ FishLabel AI PRO")

with st.sidebar:
    st.header("⚙️ Memoria")
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button("💾 Scarica Memoria", mem_json, "memoria_nomi.json", "application/json")
    up = st.file_uploader("Carica Memoria", type="json")
    if up:
        st.session_state.learned_map.update(json.load(up))
    if st.button("🗑️ RESET"):
        st.session_state.clear()
        st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if "ultimo_f" not in st.session_state or st.session_state.ultimo_f != file.name:
        st.session_state.prodotti = None
        st.session_state.ultimo_f = file.name

    if st.button("🚀 ANALIZZA FATTURA", type="primary"):
        with st.spinner("Analisi in corso..."):
            reader = PdfReader(file)
            testo = " ".join([p.extract_text() for p in reader.pages])
            prodotti = chiedi_a_gemini(testo)
            
            if prodotti:
                for p in prodotti:
                    # Applica Memoria
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                    # Data scadenza default (Oggi + 5 gg)
                    p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                
                st.session_state.prodotti = prodotti

    if st.session_state.get("prodotti"):
        
        # Rullino PDF (Discreto, per backup)
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        for p in st.session_state.prodotti:
            pdf_tot.add_page()
            # ... Disegno PDF Totale (logica duplicata per brevità) ...
            pdf_tot.set_font("helvetica", "B", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text="ITTICA CATANZARO", align='C', ln=True)
            pdf_tot.ln(1)
            pdf_tot.set_font("helvetica", "B", 15)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=7, text=str(p.get('nome','')).upper(), align='C')
            pdf_tot.ln(1)
            pdf_tot.set_font("helvetica", "I", 8)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=4, text=f"({p.get('sci','')})", align='C')
            pdf_tot.ln(2)
            pdf_tot.set_font("helvetica", "", 9)
            pdf_tot.cell(w=pdf_tot.epw, h=5, text=f"FAO {p.get('fao','')} - {p.get('metodo','')}", align='C', ln=True)
            pdf_tot.set_font("helvetica", "", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Scad: {p.get('scadenza','')}", align='C', ln=True)
            pdf_tot.set_y(38)
            pdf_tot.set_font("helvetica", "B", 12)
            pdf_tot.set_x((100 - 80) / 2)
            pdf_tot.cell(w=80, h=11, text=f"LOTTO: {p.get('lotto','')}", border=1, align='C')
            pdf_tot.set_y(54)
            pdf_tot.set_font("helvetica", "", 7)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')

        st.download_button("📄 Scarica Rullino PDF", bytes(pdf_tot.output()), "Rullino.pdf", "application/pdf")
        st.divider()

        # --- LISTA EDITABILE ---
        for i, p in enumerate(st.session_state.prodotti):
            with st.container():
                c1, c2, c3 = st.columns([1, 1, 1])
                
                # Col 1: Identità
                with c1:
                    p['nome'] = st.text_input("Nome", p.get('nome', ''), key=f"n_{i}")
                    p['sci'] = st.text_input("Scientifico", p.get('sci', ''), key=f"s_{i}")
                    # Memoria Live
                    if p['nome'] and p['sci']:
                         st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']

                # Col 2: Dati Tecnici
                with c2:
                    p['fao'] = st.text_input("FAO", p.get('fao', ''), key=f"f_{i}")
                    # Selectbox sicura
                    met_val = p.get('metodo', 'PESCATO').upper()
                    idx = 0 if "PESCATO" in met_val else 1
                    p['metodo'] = st.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=idx, key=f"m_{i}")
                    p['lotto'] = st.text_input("Lotto", p.get('lotto', ''), key=f"l_{i}")

                # Col 3: Scadenza e Stampa
                with c3:
                    p['scadenza'] = st.text_input("Scadenza", p.get('scadenza', ''), key=f"sc_{i}")
                    
                    # Genera PDF in memoria
                    pdf_bytes = genera_pdf_bytes(p)
                    # Converti in Immagine per anteprima e stampa sicura
                    img_bytes = converti_pdf_in_immagine(pdf_bytes)
                    
                    st.write("") # Spaziatore
                    # Tasto Blu Stampa
                    bottone_stampa_immagine(img_bytes, f"btn_{i}")
                    
                    # Anteprima Immagine (Non si blocca mai)
                    st.image(img_bytes, caption="Anteprima", width=250)

            st.markdown("---")