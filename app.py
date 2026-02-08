import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime, timedelta

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
    except Exception as e:
        st.error(f"Errore modello: {e}")
        return []
    
    prompt = f"""
    Sei un esperto ittico. Analizza questa fattura e crea un JSON array.
    REGOLE:
    1. "nome": Nome commerciale pulito (es. "SEPPIA"). NO codici.
    2. "sci": Nome scientifico (es. "Sepia officinalis").
    3. "lotto": Codice lotto PULITO.
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
        st.error(f"Errore Gemini: {e}")
        return []

# --- 4. MOTORE PDF & STAMPA WEB ---
def genera_pdf_bytes(p):
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
    
    # Tracciabilità
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    dati_tracc = f"FAO {p['fao']} - {p['metodo']}"
    pdf.cell(w=pdf.epw, h=5, text=dati_tracc, align='C', ln=True)
    
    # Scadenza (Nuovo Campo)
    pdf.set_font("helvetica", "", 8)
    pdf.cell(w=pdf.epw, h=4, text=f"Scadenza: {p.get('scadenza', '')}", align='C', ln=True)

    # Lotto
    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((100 - 80) / 2)
    pdf.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align='C')
    
    # Data Confezionamento
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')
    
    return bytes(pdf.output())

def link_stampa_diretta(pdf_bytes, label_text="🖨️ STAMPA SUBITO"):
    """
    Crea un link che apre il PDF in una nuova scheda, attivando (se il browser lo supporta) la stampa.
    """
    b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    # Questo HTML apre il PDF in un iframe nascosto o nuova tab per stampare
    href = f'<a href="data:application/pdf;base64,{b64}" target="_blank" class="css-button">{label_text}</a>'
    return href

# --- 5. INTERFACCIA ---
st.title("⚓ FishLabel AI: Edit & Print")

# CSS per rendere il link simile a un bottone
st.markdown("""
<style>
.css-button {
    display: inline-block;
    padding: 0.5em 1em;
    color: #FFFFFF;
    background-color: #FF4B4B;
    border-radius: 4px;
    text-decoration: none;
    font-weight: bold;
    text-align: center;
}
.css-button:hover {
    background-color: #FF2B2B;
    color: white;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Gestione")
    
    # Download Memoria
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button("💾 Scarica Memoria", mem_json, "memoria_nomi.json", "application/json")
    
    # Upload Memoria
    up_mem = st.file_uploader("Carica Memoria", type="json")
    if up_mem:
        st.session_state.learned_map.update(json.load(up_mem))
        st.success("Memoria aggiornata!")

    if st.button("🗑️ RESET"):
        st.session_state.pop('prodotti', None)
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
                # Post-processing dati
                for p in prodotti:
                    # 1. Applica memoria nomi
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                    
                    # 2. Aggiungi campo scadenza default (+5 giorni)
                    scad_date = datetime.now() + timedelta(days=5)
                    p['scadenza'] = scad_date.strftime("%d/%m/%Y")

                st.session_state.prodotti = prodotti
                st.success(f"Trovati {len(prodotti)} prodotti!")

    if st.session_state.get("prodotti"):
        st.divider()

        # LOOP PRODOTTI - TUTTO MODIFICABILE
        for i, p in enumerate(st.session_state.prodotti):
            with st.container():
                # Intestazione colorata per separare visivamente
                st.markdown(f"### 🐟 {i+1}. {p['nome']}")
                
                c1, c2, c3 = st.columns([1, 1, 1])
                
                # COLONNA 1: Identità Pesce
                with c1:
                    new_n = st.text_input("Nome Commerciale", p['nome'], key=f"n_{i}")
                    new_s = st.text_input("Nome Scientifico", p['sci'], key=f"s_{i}")
                    
                    # Logica Apprendimento
                    if new_n != p['nome']:
                        p['nome'] = new_n
                        sci_key = new_s.upper().strip()
                        st.session_state.learned_map[sci_key] = new_n
                        salva_memoria(st.session_state.learned_map)
                        st.toast(f"Memorizzato: {new_s} -> {new_n}")
                    
                    if new_s != p['sci']:
                        p['sci'] = new_s

                # COLONNA 2: Tracciabilità & Lotto
                with c2:
                    new_fao = st.text_input("Zona FAO", p['fao'], key=f"f_{i}")
                    new_met = st.selectbox("Metodo", ["PESCATO", "ALLEVATO"], 
                                         index=0 if p['metodo']=="PESCATO" else 1, key=f"m_{i}")
                    new_lot = st.text_input("Lotto", p['lotto'], key=f"l_{i}")
                    
                    p['fao'] = new_fao
                    p['metodo'] = new_met
                    p['lotto'] = new_lot

                # COLONNA 3: Scadenza & Stampa
                with c3:
                    # Campo Scadenza Editabile
                    p['scadenza'] = st.text_input("Scadenza", p.get('scadenza', ''), key=f"sc_{i}")
                    
                    st.write("") # Spaziatore
                    st.write("") 
                    
                    # GENERAZIONE PDF AL VOLO
                    pdf_bytes = genera_pdf_bytes(p)
                    
                    # TASTO STAMPA WEB (Apre nuova scheda)
                    link_html = link_stampa_diretta(pdf_bytes)
                    st.markdown(link_html, unsafe_allow_html=True)
                    
                    # Anteprima piccola
                    b64_prev = base64.b64encode(pdf_bytes).decode('utf-8')
                    # Preview non intrusiva
                    st.markdown(f'<iframe src="data:application/pdf;base64,{b64_prev}#toolbar=0&view=FitH" width="100%" height="150" style="border:1px solid #ccc; margin-top:10px;"></iframe>', unsafe_allow_html=True)

            st.markdown("---") # Linea divisoria tra prodotti