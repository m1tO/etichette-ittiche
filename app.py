import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
import base64
from datetime import datetime, timedelta
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Ittica Catanzaro AI", page_icon="🐟", layout="wide")

# --- CSS CUSTOM PER IL TASTO STAMPA ---
st.markdown("""
<style>
    /* Stile per il bottone di stampa diretto */
    .print-btn {
        background-color: #007bff;
        color: white;
        padding: 8px 16px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: bold;
        text-decoration: none;
        display: inline-block;
        font-family: "Source Sans Pro", sans-serif;
    }
    .print-btn:hover {
        background-color: #0056b3;
    }
    /* Nascondi header Streamlit per pulizia */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 2. MEMORIA ---
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

# --- 3. AI ---
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
        dati = json.loads(txt)
        
        # Anti-Crash
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

# --- 4. MOTORE PDF ---
def genera_pdf_bytes(p):
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    pdf.set_auto_page_break(False)
    
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
    pdf.ln(1)
    
    nome = str(p.get('nome', '')).upper()
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=nome, align='C')
    
    pdf.ln(1)
    sci = str(p.get('sci', ''))
    fs = 9 if len(sci) < 25 else 7
    pdf.set_font("helvetica", "I", fs)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({sci})", align='C')
    
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    fao = p.get('fao', '')
    metodo = p.get('metodo', '')
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {fao} - {metodo}", align='C', ln=True)
    
    pdf.set_font("helvetica", "", 8)
    scad = p.get('scadenza', '')
    pdf.cell(w=pdf.epw, h=4, text=f"Scadenza: {scad}", align='C', ln=True)

    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((100 - 80) / 2)
    lotto = str(p.get('lotto', ''))
    pdf.cell(w=80, h=11, text=f"LOTTO: {lotto}", border=1, align='C')
    
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')
    
    return bytes(pdf.output())

# --- 5. FUNZIONE MAGICA JAVASCRIPT PER LA STAMPA ---
def pulsante_stampa_js(pdf_bytes, key_id):
    """
    Genera un bottone HTML che esegue JavaScript per stampare il PDF.
    """
    b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    
    # Questo script crea un "Blob" (oggetto file in memoria) e lo stampa
    html_code = f"""
    <html>
    <script>
    function printPDF_{key_id}() {{
        const byteCharacters = atob("{b64_pdf}");
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {{
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }}
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], {{type: 'application/pdf'}});
        const blobUrl = URL.createObjectURL(blob);
        
        // Apre il PDF in un iframe invisibile e stampa
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = blobUrl;
        document.body.appendChild(iframe);
        iframe.contentWindow.focus();
        iframe.onload = function() {{
            setTimeout(function() {{
                iframe.contentWindow.print();
            }}, 500);
        }};
    }}
    </script>
    <body>
        <button onclick="printPDF_{key_id}()" class="print-btn">🖨️ STAMPA SUBITO</button>
    </body>
    </html>
    """
    # Renderizza il bottone HTML personalizzato
    components.html(html_code, height=50)


# --- 6. INTERFACCIA ---
st.title("⚓ FishLabel AI")

with st.sidebar:
    st.header("⚙️ Gestione")
    mem_json = json.dumps(st.session_state.learned_map, indent=4, ensure_ascii=False)
    st.download_button("💾 Scarica Memoria", mem_json, "memoria.json", "application/json")
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

    if st.button("🚀 ANALIZZA", type="primary"):
        with st.spinner("Lettura in corso..."):
            reader = PdfReader(file)
            testo = " ".join([p.extract_text() for p in reader.pages])
            prodotti = chiedi_a_gemini(testo)
            
            if prodotti:
                for p in prodotti:
                    sci = p.get('sci', '').upper().strip()
                    if sci in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci]
                    p['scadenza'] = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
                
                st.session_state.prodotti = prodotti

    if st.session_state.get("prodotti"):
        
        # --- SEZIONE RULLINO (DISCRETA) ---
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        for p in st.session_state.prodotti:
            pdf_tot.add_page()
            # (Codice disegno identico, omesso per brevità ma incluso nel loop reale)
            # ... Ripete la logica di disegno per il PDF totale ...
            pdf_tot.set_font("helvetica", "B", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
            pdf_tot.ln(1)
            pdf_tot.set_font("helvetica", "B", 15)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=7, text=str(p.get('nome','')).upper(), align='C')
            pdf_tot.ln(1)
            fs = 9 if len(str(p.get('sci',''))) < 25 else 7
            pdf_tot.set_font("helvetica", "I", fs)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=4, text=f"({p.get('sci','')})", align='C')
            pdf_tot.ln(2)
            pdf_tot.set_font("helvetica", "", 9)
            pdf_tot.cell(w=pdf_tot.epw, h=5, text=f"FAO {p.get('fao','')} - {p.get('metodo','')}", align='C', ln=True)
            pdf_tot.set_font("helvetica", "", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Scadenza: {p.get('scadenza','')}", align='C', ln=True)
            pdf_tot.set_y(38)
            pdf_tot.set_font("helvetica", "B", 12)
            pdf_tot.set_x((100 - 80) / 2)
            pdf_tot.cell(w=80, h=11, text=f"LOTTO: {p.get('lotto','')}", border=1, align='C')
            pdf_tot.set_y(54)
            pdf_tot.set_font("helvetica", "", 7)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')

        # Bottone rullino normale (non primary)
        st.download_button("📄 Scarica Rullino Completo (PDF)", bytes(pdf_tot.output()), "Rullino.pdf", "application/pdf")
        
        st.divider()

        # --- LISTA PRODOTTI ---
        for i, p in enumerate(st.session_state.prodotti):
            with st.container():
                c1, c2, c3 = st.columns([1, 1, 1])
                
                with c1:
                    p['nome'] = st.text_input("Nome", p.get('nome', ''), key=f"n_{i}")
                    p['sci'] = st.text_input("Sci", p.get('sci', ''), key=f"s_{i}")
                    # Memoria rapida
                    if p['nome'] and p['sci']:
                         st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']

                with c2:
                    p['fao'] = st.text_input("FAO", p.get('fao', ''), key=f"f_{i}")
                    idx_met = 0 if "PESCATO" in p.get('metodo', 'PESCATO').upper() else 1
                    p['metodo'] = st.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=idx_met, key=f"m_{i}")
                    p['lotto'] = st.text_input("Lotto", p.get('lotto', ''), key=f"l_{i}")

                with c3:
                    p['scadenza'] = st.text_input("Scadenza", p.get('scadenza', ''), key=f"sc_{i}")
                    
                    # Genera bytes
                    pdf_bytes = genera_pdf_bytes(p)
                    
                    st.write("") # Spazio
                    # --- IL PULSANTE DI STAMPA DIRETTA ---
                    pulsante_stampa_js(pdf_bytes, f"btn_{i}")
                    
                    # Anteprima piccola
                    b64 = base64.b64encode(pdf_bytes).decode('utf-8')
                    # Usiamo embed che è più stabile di iframe per i pdf su Chrome
                    st.markdown(f'<embed src="data:application/pdf;base64,{b64}#toolbar=0&navpanes=0&scrollbar=0" type="application/pdf" width="100%" height="150" style="border:1px solid #ddd;">', unsafe_allow_html=True)
            
            st.markdown("---")