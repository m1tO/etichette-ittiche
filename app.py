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
        dati = json.loads(txt)
        
        # --- FIX ANTI-CRASH: NORMALIZZAZIONE DATI ---
        # Se l'AI dimentica un campo, lo aggiungiamo noi vuoto per non far crashare l'app
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
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
    pdf.ln(1)
    
    # Nome (Usa .get per sicurezza estrema)
    nome = str(p.get('nome', '')).upper()
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=nome, align='C')
    
    # Scientifico
    pdf.ln(1)
    sci = str(p.get('sci', ''))
    fs = 9 if len(sci) < 25 else 7
    pdf.set_font("helvetica", "I", fs)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({sci})", align='C')
    
    # Dati Tracciabilità
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

# --- 5. INTERFACCIA ---
st.title("⚓ FishLabel AI")

with st.sidebar:
    st.header("⚙️ Memoria")
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
        # --- STAMPA TOTALE (RULLINO) ---
        st.divider()
        
        # Rigenera PDF Totale
        pdf_tot = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        
        for p in st.session_state.prodotti:
            pdf_tot.add_page()
            # Stessa logica sicura .get()
            pdf_tot.set_font("helvetica", "B", 8)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', ln=True)
            pdf_tot.ln(1)
            
            nome = str(p.get('nome', '')).upper()
            pdf_tot.set_font("helvetica", "B", 15)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=7, text=nome, align='C')
            
            pdf_tot.ln(1)
            sci = str(p.get('sci', ''))
            fs = 9 if len(sci) < 25 else 7
            pdf_tot.set_font("helvetica", "I", fs)
            pdf_tot.multi_cell(w=pdf_tot.epw, h=4, text=f"({sci})", align='C')
            
            pdf_tot.ln(2)
            pdf_tot.set_font("helvetica", "", 9)
            fao = p.get('fao', '')
            met = p.get('metodo', '')
            pdf_tot.cell(w=pdf_tot.epw, h=5, text=f"FAO {fao} - {met}", align='C', ln=True)
            
            pdf_tot.set_font("helvetica", "", 8)
            scad = p.get('scadenza', '')
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Scadenza: {scad}", align='C', ln=True)
            
            pdf_tot.set_y(38)
            pdf_tot.set_font("helvetica", "B", 12)
            pdf_tot.set_x((100 - 80) / 2)
            lotto = str(p.get('lotto', ''))
            pdf_tot.cell(w=80, h=11, text=f"LOTTO: {lotto}", border=1, align='C')
            
            pdf_tot.set_y(54)
            pdf_tot.set_font("helvetica", "", 7)
            pdf_tot.cell(w=pdf_tot.epw, h=4, text=f"Conf: {datetime.now().strftime('%d/%m/%Y')}", align='R')

        st.download_button(
            "🖨️ SCARICA RULLINO COMPLETO (PDF)", 
            bytes(pdf_tot.output()), 
            "Rullino.pdf", 
            "application/pdf", 
            type="primary",
            use_container_width=True
        )
        
        st.divider()

        # --- LISTA MODIFICABILE ---
        for i, p in enumerate(st.session_state.prodotti):
            with st.container():
                # Visualizza nome sicuro
                n_display = p.get('nome', 'Prodotto')
                st.markdown(f"**{i+1}. {n_display}**")
                
                c1, c2, c3 = st.columns([1, 1, 1])
                
                # Col 1
                with c1:
                    p['nome'] = st.text_input("Nome", p.get('nome', ''), key=f"n_{i}")
                    p['sci'] = st.text_input("Scientifico", p.get('sci', ''), key=f"s_{i}")
                    # Memoria automatica
                    if p['nome'] and p['sci']:
                         st.session_state.learned_map[p['sci'].upper().strip()] = p['nome']
                         # Salva ogni volta che cambi? Meglio di no per performance, ma qui ok
                         # salva_memoria(...) lo lasciamo al tasto laterale o fine sessione

                # Col 2
                with c2:
                    p['fao'] = st.text_input("FAO", p.get('fao', ''), key=f"f_{i}")
                    
                    # Metodo con gestione sicura dell'index
                    met_val = p.get('metodo', 'PESCATO')
                    idx_met = 0 if "PESCATO" in met_val.upper() else 1
                    p['metodo'] = st.selectbox("Metodo", ["PESCATO", "ALLEVATO"], index=idx_met, key=f"m_{i}")
                    
                    p['lotto'] = st.text_input("Lotto", p.get('lotto', ''), key=f"l_{i}")

                # Col 3
                with c3:
                    p['scadenza'] = st.text_input("Scadenza", p.get('scadenza', ''), key=f"sc_{i}")
                    
                    # Genera PDF e Preview
                    pdf_bytes = genera_pdf_bytes(p)
                    
                    st.write("")
                    st.download_button(
                        "🖨️ Scarica Etichetta", 
                        pdf_bytes, 
                        f"Etichetta_{i}.pdf", 
                        "application/pdf",
                        key=f"dl_{i}"
                    )
                    
                    b64 = base64.b64encode(pdf_bytes).decode('utf-8')
                    st.markdown(f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0&view=FitH" width="100%" height="150"></iframe>', unsafe_allow_html=True)
            
            st.markdown("---")