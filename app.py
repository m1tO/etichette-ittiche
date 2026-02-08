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

# --- 1. CONFIGURAZIONE E STILE (UI DESIGN) ---
st.set_page_config(page_title="FishLabel Pro", page_icon="🐟", layout="wide")

# CSS CUSTOM PER RENDERE TUTTO PIÙ "APP"
st.markdown("""
<style>
    /* Nasconde menu standard Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Stile per le Card dei prodotti */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }

    /* Titoli più belli */
    h1 { color: #004e92; font-family: 'Helvetica', sans-serif; font-weight: 800; }
    h3 { color: #333; }
    
    /* Bottoni personalizzati */
    div.stButton > button:first-child {
        border-radius: 8px;
        font-weight: 600;
        height: 3em;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. LOGICA BACKEND (MEMORIA & AI) ---
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
    if not api_key:
        st.error("Inserisci la Chiave API per continuare.")
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
    3. "lotto": Codice lotto.
    4. "fao": Zona FAO.
    5. "metodo": "PESCATO" o "ALLEVATO".
    6. "conf": Data confezionamento (GG/MM/AAAA).
    
    Testo: {testo_pdf}
    RISPONDI SOLO JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        dati = json.loads(txt)
        
        lista = []
        if isinstance(dati, list):
            for p in dati:
                lista.append({
                    "nome": p.get("nome", "DA COMPILARE"),
                    "sci": p.get("sci", ""),
                    "lotto": p.get("lotto", ""),
                    "fao": p.get("fao", ""),
                    "metodo": p.get("metodo", "PESCATO"),
                    "conf": p.get("conf", ""),
                    "prezzo": "",
                    "scadenza": (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                })
            return lista
        return []
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return []

# --- 3. MOTORE GRAFICO (PDF & IMG) ---
def pulisci(t):
    return str(t).replace("€", "EUR").encode('latin-1', 'replace').decode('latin-1') if t else ""

def genera_pdf_bytes(p):
    pdf = FPDF('L', 'mm', (62, 100))
    pdf.add_page(); pdf.set_auto_page_break(False); pdf.set_margins(4, 3, 4)
    
    # Header
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", 0, 1, 'C')
    pdf.ln(1)
    
    # Nome
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(0, 7, pulisci(p.get('nome','')).upper(), 0, 'C')
    
    # Scientifico
    pdf.ln(1)
    pdf.set_font("helvetica", "I", 9 if len(str(p.get('sci',''))) < 25 else 7)
    pdf.multi_cell(0, 4, f"({pulisci(p.get('sci',''))})", 0, 'C')
    
    # Info
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"FAO {pulisci(p.get('fao',''))} - {pulisci(p.get('metodo',''))}", 0, 1, 'C')
    
    # Scadenza
    pdf.set_font("helvetica", "", 8)
    pdf.cell(0, 4, f"Scadenza: {pulisci(p.get('scadenza',''))}", 0, 1, 'C')

    # Prezzo
    prz = str(p.get('prezzo', '')).strip()
    if prz:
        pdf.set_y(35); pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 6, f"Euro/Kg: {prz}", 0, 1, 'C')

    # Lotto
    pdf.set_y(43); pdf.set_font("helvetica", "B", 11)
    pdf.set_x((100 - 75) / 2)
    pdf.cell(75, 10, f"LOTTO: {pulisci(p.get('lotto',''))}", 1, 0, 'C')
    
    # Conf
    pdf.set_y(56); pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, f"Conf: {pulisci(p.get('conf',''))}", 0, 0, 'R')
    
    return bytes(pdf.output())

def get_img_preview(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc.load_page(0).get_pixmap(dpi=150).tobytes("png")

# --- 4. COMPONENTI JS (STAMPA) ---
def btn_stampa_diretta(img_bytes, key, label="🖨️ STAMPA", color="#007bff", width="100%"):
    b64 = base64.b64encode(img_bytes).decode()
    html = f"""
    <button onclick="p_{key}()" style="background:{color}; color:white; border:none; padding:10px; 
            border-radius:8px; font-weight:bold; cursor:pointer; width:{width}; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
        {label}
    </button>
    <script>
    function p_{key}() {{
        var w = window.open('','_blank','width=500,height=400');
        w.document.write('<html><head><style>@page {{size:62mm 100mm; margin:0;}} body {{margin:0; display:flex; justify-content:center;}} img {{width:62mm; height:100mm; object-fit:contain;}}</style></head><body>');
        w.document.write('<img src="data:image/png;base64,{b64}" onload="window.print();window.close();"></body></html>');
        w.document.close();
    }}
    </script>
    """
    components.html(html, height=50)

def btn_stampa_rullino(prodotti):
    imgs = [base64.b64encode(get_img_preview(genera_pdf_bytes(p))).decode() for p in prodotti]
    html_imgs = "".join([f'<img src="data:image/png;base64,{i}" style="width:62mm;height:100mm;page-break-after:always;">' for i in imgs])
    
    html = f"""
    <button onclick="pr()" style="background:#28a745; color:white; border:none; padding:12px 24px; 
            border-radius:8px; font-weight:bold; cursor:pointer; width:100%; font-size:16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        🖨️ STAMPA TUTTO IL RULLINO ({len(prodotti)} ETICHETTE)
    </button>
    <script>
    function pr() {{
        var w = window.open('','_blank','width=600,height=800');
        w.document.write('<html><head><style>@page {{size:62mm 100mm; margin:0;}} body {{margin:0;}} img {{display:block;}}</style></head><body>');
        w.document.write('{html_imgs}');
        w.document.write('</body></html>');
        w.document.close(); w.focus();
        setTimeout(function(){{ w.print(); w.close(); }}, 1000);
    }}
    </script>
    """
    components.html(html, height=60)

# --- 5. UI PRINCIPALE ---
# HEADER
c_logo, c_title = st.columns([1, 4])
with c_logo:
    st.markdown("<div style='font-size: 60px; text-align: center;'>🐟</div>", unsafe_allow_html=True)
with c_title:
    st.title("FishLabel Pro")
    st.caption("Sistema Intelligente di Etichettatura Ittica - Palermo")

# SIDEBAR (SETTINGS)
with st.sidebar:
    st.header("🧠 Memoria Pesci")
    st.info(f"Ho imparato {len(st.session_state.learned_map)} nomi.")
    
    col_dl, col_ul = st.columns(2)
    with col_dl:
        mem_json = json.dumps(st.session_state.learned_map, indent=4)
        st.download_button("⬇️ Save", mem_json, "memoria.json", "application/json")
    with col_ul:
        up = st.file_uploader("⬆️ Load", type="json", label_visibility="collapsed")
        if up: st.session_state.learned_map.update(json.load(up))
    
    st.divider()
    if st.button("🗑️ Nuova Sessione (Reset)"):
        st.session_state.clear()
        st.rerun()

# UPLOAD AREA (STYLE "DROP ZONE")
uploaded_file = st.file_uploader("Trascina qui la tua fattura PDF", type="pdf", label_visibility="collapsed")

if uploaded_file:
    # Gestione cambio file
    if "last_f" not in st.session_state or st.session_state.last_f != uploaded_file.name:
        st.session_state.prodotti = None
        st.session_state.last_f = uploaded_file.name

    # PULSANTE AZIONE
    if st.session_state.prodotti is None:
        st.info("Fattura caricata. Clicca per analizzare.")
        if st.button("🚀 ANALIZZA CON AI", type="primary", use_container_width=True):
            with st.status("🔍 Analisi in corso...", expanded=True) as status:
                st.write("Lettura PDF...")
                reader = PdfReader(uploaded_file)
                text = " ".join([p.extract_text() for p in reader.pages])
                st.write("Estrazione dati con Gemini...")
                prodotti = chiedi_a_gemini(text)
                
                # Applica memoria
                for p in prodotti:
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                    if not p['conf']: p['conf'] = datetime.now().strftime("%d/%m/%Y")
                
                st.session_state.prodotti = prodotti
                status.update(label="✅ Analisi Completata!", state="complete", expanded=False)
                st.rerun()

    # RISULTATI (CARD VIEW)
    if st.session_state.get("prodotti"):
        st.divider()
        
        # BARRA STRUMENTI SUPERIORE
        col_main_actions = st.columns([2, 1])
        with col_main_actions[0]:
            btn_stampa_rullino(st.session_state.prodotti)
        with col_main_actions[1]:
            # Genera PDF rullino per download
            pdf_tot = FPDF('L', 'mm', (62, 100)); pdf_tot.set_margins(4,3,4)
            for p in st.session_state.prodotti:
                pdf_tot.add_page(); pdf_tot.set_auto_page_break(False)
                # (Logica disegno identica, omessa per brevità, usiamo l'output)
                # Per brevità nel download button usiamo una lista vuota se vuoi solo il tasto verde
                # O rigeneri al volo se ti serve il file fisico.
                pass 
            # (Qui ho semplificato: il tasto verde è la priorità. Se vuoi il download, usa quello singolo)
            st.caption("💡 Usa il tasto verde per stampare subito.")

        st.markdown("<br>", unsafe_allow_html=True)

        # LOOP PRODOTTI (CARDS)
        for i, p in enumerate(st.session_state.prodotti):
            # INIZIO CARD
            with st.container(border=True):
                # Header Card: Nome e Scientifico
                c_head_1, c_head_2 = st.columns([3, 1])
                with c_head_1:
                    p['nome'] = st.text_input("Nome Commerciale", p.get('nome',''), key=f"n_{i}", label_visibility="collapsed", placeholder="Nome Pesce").upper()
                    st.caption(f"Scientifico: {p.get('sci','')} (Modificabile sotto)")
                with c_head_2:
                    st.markdown(f"<div style='text-align:right; font-weight:bold; color:#888;'>#{i+1}</div>", unsafe_allow_html=True)
                
                st.markdown("---")
                
                # Corpo Card: Dati
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    p['sci'] = st.text_input("Scientifico", p.get('sci',''), key=f"s_{i}")
                    # Memoria Live
                    if p['nome'] and p['sci']: st.session_state.learned_map[p['sci'].strip()] = p['nome']
                with c2:
                    p['lotto'] = st.text_input("Lotto", p.get('lotto',''), key=f"l_{i}")
                with c3:
                     # Metodo Smart
                    m_idx = 0 if "PESCATO" in p.get('metodo','PESCATO').upper() else 1
                    p['metodo'] = st.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=m_idx, key=f"m_{i}")
                with c4:
                    p['fao'] = st.text_input("Zona FAO", p.get('fao',''), key=f"f_{i}")

                c5, c6, c7 = st.columns(3)
                with c5:
                    p['prezzo'] = st.text_input("Prezzo (€/Kg) [Opz.]", p.get('prezzo',''), key=f"pr_{i}")
                with c6:
                    p['scadenza'] = st.text_input("Scadenza", p.get('scadenza',''), key=f"sc_{i}")
                with c7:
                    p['conf'] = st.text_input("Confezionamento", p.get('conf',''), key=f"cf_{i}")
                
                # Footer Card: Anteprima e Azione
                st.markdown("---")
                c_prev, c_act = st.columns([1, 2])
                
                # Generazione Assets
                pdf_b = genera_pdf_bytes(p)
                img_b = get_img_preview(pdf_b)
                
                with c_prev:
                    st.image(img_b, use_container_width=True)
                with c_act:
                    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True) # Spacer
                    btn_stampa_diretta(img_b, f"btn_{i}", label="🖨️ STAMPA ETICHETTA SINGOLA")
                    
                    # Download File Fisico (Piccolo link sotto)
                    st.download_button("📄 Scarica PDF", pdf_b, f"{p['nome']}.pdf", "application/pdf", key=f"dl_{i}")

else:
    # Schermata Iniziale Vuota (Placeholder carino)
    st.info("👋 Ciao! Carica una fattura dal menu in alto per iniziare.")