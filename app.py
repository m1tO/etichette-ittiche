import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import re
from datetime import datetime, timedelta
import fitz  # PyMuPDF
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE E LISTE UE ---
st.set_page_config(page_title="FishLabel AI Pro", page_icon="⚓", layout="wide")

# Lista Ufficiale Attrezzi di Pesca (Reg. UE)
LISTA_ATTREZZI = [
    "Sconosciuto",
    "Reti da traino",
    "Reti da posta/imbrocco",
    "Ami e palangari",
    "Reti da circuizione",
    "Nasse e trappole",
    "Draghe",
    "Raccolta manuale",
    "Sciabiche"
]

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #262730; border: 1px solid #464b5c; border-radius: 8px; padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    input[type="text"] { background-color: #1a1c24 !important; color: white !important; border: 1px solid #464b5c !important; }
    h1 { color: #4facfe; font-size: 2.2rem; font-weight: 800; }
    .label-text { font-size: 0.8rem; color: #aaa; margin-bottom: 2px; }

    div.stButton > button { border-radius: 6px; font-weight: 600; border: none; }
    
    /* TASTO RULLINO ROSSO */
    div.stDownloadButton > button {
        background-color: #FF4B4B !important; color: white !important; font-size: 18px !important;
        padding: 0.8rem 2rem !important; border: 2px solid #FF4B4B !important;
        box-shadow: 0 4px 10px rgba(255, 75, 75, 0.4); height: auto !important;
    }
    div.stDownloadButton > button:hover { transform: scale(1.05); }
</style>
""", unsafe_allow_html=True)

# --- 2. BACKEND ---
MEMORIA_FILE = "memoria_nomi.json"

def carica_memoria():
    if os.path.exists(MEMORIA_FILE):
        try:
            with open(MEMORIA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def salva_memoria(memoria):
    with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=4)

if "learned_map" not in st.session_state: st.session_state.learned_map = carica_memoria()

if "GEMINI_API_KEY" in st.secrets: api_key = st.secrets["GEMINI_API_KEY"]
else: api_key = st.sidebar.text_input("🔑 API Key Gemini", type="password")

def chiedi_a_gemini(testo_pdf):
    if not api_key: return []
    genai.configure(api_key=api_key)
    try: model = genai.GenerativeModel('gemini-2.5-flash')
    except: model = genai.GenerativeModel('gemini-1.5-flash')
    
    # PROMPT SPECIFICO PER NORMATIVA UE
    prompt = f"""
    Analizza fattura ittica. Estrai JSON array.
    REGOLE NORMATIVA UE:
    1. "nome": Nome commerciale.
    2. "sci": Nome scientifico.
    3. "lotto": Codice lotto.
    4. "metodo": "PESCATO" o "ALLEVATO".
    5. "zona": 
       - Se PESCATO -> Zona FAO (es. "FAO 37.1").
       - Se ALLEVATO -> Paese di allevamento (es. "Italia", "Norvegia").
    6. "attrezzo": Se PESCATO, tipo di attrezzo (es. "Reti da traino"). Se ALLEVATO, lascia vuoto.
    7. "conf": Data confezionamento (GG/MM/AAAA).
    
    NO commenti. Solo JSON.
    Testo: {testo_pdf}
    """
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        dati = json.loads(txt)
        return dati if isinstance(dati, list) else []
    except: return []

# --- 3. MOTORE PDF (CONFORME UE) ---
def pulisci_etichetta(t):
    if not t: return ""
    t = re.sub(r'\(.*?\)', '', str(t))
    return t.replace("€", "EUR").strip().encode('latin-1', 'replace').decode('latin-1')

def disegna_su_pdf(pdf, p):
    pdf.add_page()
    pdf.set_margins(4, 3, 4)
    w_full = 92
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w_full, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.ln(1)
    
    # Nome Commerciale
    nome = pulisci_etichetta(p.get('nome','')).upper()
    pdf.set_font("helvetica", "B", 14)
    pdf.multi_cell(w_full, 6, nome, 0, 'C')
    
    # Nome Scientifico (Obbligatorio)
    sci = pulisci_etichetta(p.get('sci',''))
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(w_full, 4, f"({sci})", 0, 'C')
    
    pdf.ln(1)
    
    # --- BLOCCO ORIGINE (DINAMICO) ---
    pdf.set_font("helvetica", "", 8)
    metodo = p.get('metodo', 'PESCATO')
    zona = pulisci_etichetta(p.get('zona', ''))
    attrezzo = pulisci_etichetta(p.get('attrezzo', ''))
    
    riga_origine = ""
    riga_attrezzo = ""
    
    if "ALLEVATO" in metodo.upper():
        riga_origine = f"ALLEVATO IN: {zona.upper()}"
    else:
        # Pescato
        riga_origine = f"PESCATO IN: {zona.upper()}"
        if attrezzo and attrezzo != "Sconosciuto":
            riga_attrezzo = f"Attrezzi: {attrezzo}"
            
    pdf.multi_cell(w_full, 4, riga_origine, 0, 'C')
    if riga_attrezzo:
        pdf.multi_cell(w_full, 4, riga_attrezzo, 0, 'C')
    
    # Stato Fisico (Fresco)
    pdf.cell(w_full, 4, "PRODOTTO FRESCO", 0, 1, 'C')

    # Prezzo
    if str(p.get('prezzo', '')).strip():
        pdf.set_y(38)
        pdf.set_font("helvetica", "B", 13)
        pdf.cell(w_full, 6, f"EUR/Kg: {p.get('prezzo','')}", 0, 1, 'C')

    # Lotto
    pdf.set_y(45)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_x((100 - 75) / 2)
    pdf.cell(75, 9, f"LOTTO: {pulisci_etichetta(p.get('lotto',''))}", 1, 0, 'C')
    
    # Date
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 6)
    conf = pulisci_etichetta(p.get('conf',''))
    scad = pulisci_etichetta(p.get('scadenza',''))
    pdf.cell(w_full, 4, f"Conf: {conf} - Scad: {scad}", 0, 0, 'C')

def genera_pdf_bytes(lista_p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.set_auto_page_break(False)
    for p in lista_p: disegna_su_pdf(pdf, p)
    return bytes(pdf.output())

def converti_pdf_in_immagine(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc.load_page(0).get_pixmap(dpi=120).tobytes("png")

# --- 4. INTERFACCIA ---
c_t, c_l = st.columns([5,1])
with c_t: st.title("⚓ FishLabel AI Pro")
with c_l: st.markdown("<h1>🐟</h1>", unsafe_allow_html=True)

if not st.session_state.get("prodotti"):
    col_up, _ = st.columns([1, 2])
    with col_up:
        file = st.file_uploader("Carica Fattura", type="pdf", label_visibility="collapsed")
        if file and st.button("🚀 Analizza PDF", type="primary"):
            with st.spinner("Estrazione dati conformi UE..."):
                reader = PdfReader(file)
                text = " ".join([p.extract_text() for p in reader.pages])
                res = chiedi_a_gemini(text)
                final = []
                for p in res:
                    k = p.get('sci','').upper().strip()
                    if k in st.session_state.learned_map: p['nome'] = st.session_state.learned_map[k]
                    p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                    if not p.get('conf'): p['conf'] = datetime.now().strftime("%d/%m/%Y")
                    p['prezzo'] = ""
                    # Default Attrezzo
                    if not p.get('attrezzo'): p['attrezzo'] = "Reti da traino"
                    final.append(p)
                st.session_state.prodotti = final
                st.rerun()
else:
    c_inf, c_cl = st.columns([5, 1])
    with c_inf:
        st.subheader(f"✅ {len(st.session_state.prodotti)} Prodotti")
        col_b, _ = st.columns([2,3])
        with col_b:
            st.download_button("🖨️ SCARICA RULLINO", genera_pdf_bytes(st.session_state.prodotti), "Rullino.pdf", "application/pdf")
    with c_cl:
        if st.button("❌ CHIUDI"): st.session_state.prodotti = None; st.rerun()

    for i, p in enumerate(st.session_state.prodotti):
        with st.container(border=True):
            # Header
            c_h1, c_h2 = st.columns([4, 1])
            with c_h1: p['nome'] = st.text_input("Nome", p.get('nome','').upper(), key=f"n_{i}", label_visibility="collapsed")
            with c_h2: st.download_button("⬇️ PDF", genera_pdf_bytes([p]), f"{p['nome']}.pdf", key=f"dl_{i}")

            # RIGA 1: Scientifico, Lotto
            c1, c2 = st.columns(2)
            p['sci'] = c1.text_input("Scientifico (Obbligatorio)", p.get('sci',''), key=f"s_{i}")
            p['lotto'] = c2.text_input("Lotto", p.get('lotto',''), key=f"l_{i}")

            # RIGA 2: Metodo di Produzione (Cruciale per il form dinamico)
            c3, c4 = st.columns(2)
            m_idx = 0 if "PESCATO" in str(p.get('metodo','')).upper() else 1
            tipo_metodo = c3.selectbox("Metodo Produzione", ["PESCATO", "ALLEVATO"], index=m_idx, key=f"m_{i}")
            p['metodo'] = tipo_metodo

            # RIGA 3: LOGICA DINAMICA (IL CUORE DELLA CONFORMITÀ)
            c_zona, c_attr = st.columns(2)
            
            if tipo_metodo == "PESCATO":
                # Se Pescato: Serve Zona FAO + Attrezzo
                p['zona'] = c_zona.text_input("Zona FAO (es. 37.1)", p.get('zona',''), key=f"z_{i}")
                
                # Cerco l'indice dell'attrezzo attuale nella lista, se non c'è uso 0
                attr_curr = p.get('attrezzo', 'Sconosciuto')
                attr_idx = LISTA_ATTREZZI.index(attr_curr) if attr_curr in LISTA_ATTREZZI else 0
                p['attrezzo'] = c_attr.selectbox("Attrezzo di Pesca", LISTA_ATTREZZI, index=attr_idx, key=f"a_{i}")
            
            else:
                # Se Allevato: Serve PAESE DI ORIGINE (Non FAO)
                p['zona'] = c_zona.text_input("Paese di Allevamento (es. Italia, Grecia)", p.get('zona',''), key=f"z_{i}")
                p['attrezzo'] = "" # Niente attrezzi per l'allevato

            # RIGA 4: Date e Prezzo
            c5, c6, c7 = st.columns(3)
            p['conf'] = c5.text_input("Conf", p.get('conf',''), key=f"cf_{i}")
            p['scadenza'] = c6.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")
            p['prezzo'] = c7.text_input("Prezzo (€/Kg)", p.get('prezzo',''), key=f"pr_{i}")

            st.image(converti_pdf_in_immagine(genera_pdf_bytes([p])), width=350)
            
            if p['nome'] and p['sci']: st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
            
    salva_memoria(st.session_state.learned_map)