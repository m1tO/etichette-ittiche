import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime, timedelta
import fitz  # PyMuPDF
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Ittica Catanzaro AI", page_icon="🐟", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 1rem;}
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
        model = genai.GenerativeModel('gemini-2.5-flash')
    except:
        model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    Analizza la fattura ittica ed estrai i dati in un array JSON.
    REGOLE:
    1. "nome": Nome commerciale (es. SEPPIA).
    2. "sci": Nome scientifico.
    3. "lotto": Codice lotto.
    4. "fao": Zona FAO (es. 34).
    5. "metodo": "PESCATO" o "ALLEVATO".
    6. "conf": Cerca la data di confezionamento originale sulla fattura (formato GG/MM/AAAA). Se non la trovi, lascia vuoto.
    
    Testo: {testo_pdf}
    RISPONDI SOLO COL JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        dati = json.loads(txt)
        
        lista_pulita = []
        if isinstance(dati, list):
            for p in dati:
                p_safe = {
                    "nome": p.get("nome", "DA COMPILARE"),
                    "sci": p.get("sci", ""),
                    "lotto": p.get("lotto", ""),
                    "fao": p.get("fao", ""),
                    "metodo": p.get("metodo", "PESCATO"),
                    "conf": p.get("conf", "") # Data confezionamento estratta
                }
                lista_pulita.append(p_safe)
            return lista_pulita
        return []
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return []

# --- 4. MOTORE PDF ---
def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_auto_page_break(False)
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
    pdf.ln(1)
    
    # Nome
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=str(p.get('nome','')).upper(), align='C')
    
    # Scientifico
    pdf.ln(1)
    sci = str(p.get('sci',''))
    fs = 9 if len(sci) < 25 else 7
    pdf.set_font("helvetica", "I", fs)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({sci})", align='C')
    
    # Tracciabilità
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p.get('fao','')} - {p.get('metodo','')}", align='C', ln=True)
    
    # Scadenza
    pdf.set_font("helvetica", "", 8)
    pdf.cell(w=pdf.epw, h=4, text=f"Scadenza: {p.get('scadenza','')}", align='C', ln=True)

    # Lotto
    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((100 - 80) / 2)
    pdf.cell(w=80, h=11, text=f"LOTTO: {p.get('lotto','')}", border=1, align='C')
    
    # Data Confezionamento (MODIFICATA: non più datetime.now)
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Conf: {p.get('conf','')}", align='R')

def genera_pdf_bytes(p):
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

def converti_pdf_in_immagine(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=150)
    return pix.tobytes("png")

def bottone_stampa_immagine(img_bytes, key_id):
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
            var win = window.open('', '_blank', 'width=500,height=400');
            win.document.write('<html><head><title>Stampa</title>');
            win.document.write('<style>@page {{ size: 62mm 100mm; margin: 0; }} body {{ margin: 0; display: flex; justify-content: center; }} img {{ width: 62mm; height: 100mm; object-fit: contain; }}</style>');
            win.document.write('</head><body>');
            win.document.write('<img src="data:image/png;base64,{b64_img}" onload="window.print(); window.close();"/>');
            win.document.write('</body></html>');
            win.document.close();
        }}
    </script>
    """
    components.html(html, height=60)

# --- 5. INTERFACCIA ---
st.title("⚓ FishLabel AI PRO")

with st.sidebar:
    st.header("⚙️ Memoria")
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button("💾 Scarica Memoria", mem_json, "memoria.json", "application/json")
    up = st.file_uploader("Carica Memoria", type="json")
    if up: st.session_state.learned_map.update(json.load(up))
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
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                    # Default Scadenza se non trova nulla
                    p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                    # Se l'AI non ha trovato la data confezionamento, mettiamo oggi come aiuto, ma l'utente deve controllare
                    if not p['conf']: p['conf'] = datetime.now().strftime("%d/%m/%Y")
                
                st.session_state.prodotti = prodotti

    if st.session_state.get("prodotti"):
        # Rullino PDF
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        for p in st.session_state.prodotti:
            disegna_su_pdf(pdf_tot, p)
        st.download_button("📄 Scarica Rullino PDF", bytes(pdf_tot.output()), "Rullino.pdf", "application/pdf")
        
        st.divider()

        for i, p in enumerate(st.session_state.prodotti):
            with st.container():
                c1, c2, c3 = st.columns([1, 1, 1])
                with c1:
                    p['nome'] = st.text_input("Nome", p.get('nome', ''), key=f"n_{i}")
                    p['sci'] = st.text_input("Scientifico", p.get('sci', ''), key=f"s_{i}")
                    if p['nome'] and p['sci']:
                        st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
                with c2:
                    p['fao'] = st.text_input("FAO", p.get('fao', ''), key=f"f_{i}")
                    idx = 0 if "PESCATO" in p.get('metodo', '').upper() else 1
                    p['metodo'] = st.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=idx, key=f"m_{i}")
                    p['lotto'] = st.text_input("Lotto", p.get('lotto', ''), key=f"l_{i}")
                with c3:
                    p['scadenza'] = st.text_input("Scadenza", p.get('scadenza', ''), key=f"sc_{i}")
                    # NUOVO CAMPO CONFEZIONAMENTO
                    p['conf'] = st.text_input("Confezionamento (Conf)", p.get('conf', ''), key=f"cf_{i}")
                    
                    pdf_bytes = genera_pdf_bytes(p)
                    img_bytes = converti_pdf_in_immagine(pdf_bytes)
                    bottone_stampa_immagine(img_bytes, f"btn_{i}")
                    st.image(img_bytes, width=250)
            st.markdown("---")