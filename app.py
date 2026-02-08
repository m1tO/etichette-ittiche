import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime
from io import BytesIO
import json
import base64

# Configurazione Iniziale
st.set_page_config(page_title="Ittica Catanzaro AI PRO", page_icon="🐟", layout="wide")

# --- 1. CONFIGURAZIONE AI ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.sidebar.warning("⚠️ API Key non trovata nei Secrets.")

def chiedi_all_ai(testo_pdf):
    # Usiamo il modello 2.5/3 che hai nel tuo pannello
    model = genai.GenerativeModel('gemini-1.5-flash') 
    prompt = f"""
    Analizza questa fattura ittica. Estrai i prodotti e restituisci SOLO un array JSON.
    REGOLE:
    - "nome": Nome commerciale pulito (es: SEPPIA). No codici, no 'GRECIA'.
    - "sci": Nome scientifico esatto (es: Sepia officinalis).
    - "lotto": Codice lotto pulito (togli prezzi/pesi attaccati).
    - "fao": Zona FAO (es: 37.2.1).
    - "metodo": "PESCATO" o "ALLEVATO".
    
    Testo: {testo_pdf}
    """
    response = model.generate_content(prompt)
    json_str = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(json_str)

# --- 2. LOGICA PDF (LA TUA) ---
def disegna_etichetta(pdf, p):
    pdf.add_page()
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p["nome"].upper(), align="C")
    
    # Scientifico
    pdf.ln(1)
    f_sci = 9 if len(p["sci"]) < 25 else 7
    pdf.set_font("helvetica", "I", f_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align="C")
    
    # Tracciabilità
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Lotto
    pdf.set_y(38)
    l_txt = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_txt) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    pdf.set_x((pdf.w - 80) / 2)
    pdf.cell(w=80, h=11, text=l_txt, border=1, align="C")
    
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align="R")

def mostra_pdf_anteprima(pdf_bytes):
    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="250" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

# --- 3. UI PRINCIPALE ---
st.title("⚓ FishLabel AI Scanner PRO")

# Inizializzazione Memoria
if "learned_map" not in st.session_state:
    st.session_state.learned_map = {}

# Sidebar: Gestione Memoria (La tua sezione preferita)
with st.sidebar.expander("🧠 Memoria Nomi (JSON)"):
    cA, cB = st.columns(2)
    learned_export = json.dumps(st.session_state.learned_map, ensure_ascii=False, indent=2)
    cA.download_button("⬇️ Export", data=learned_export.encode("utf-8"), file_name="memoria_nomi.json")
    
    up = cB.file_uploader("⬆️ Import", type=["json"])
    if up:
        st.session_state.learned_map.update(json.load(up))
        st.success("Caricata!")

# Reset
if st.button("🗑️ SVUOTA TUTTO"):
    st.session_state.pop("p_list", None)
    st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if st.button("🚀 ANALIZZA CON INTELLIGENZA ARTIFICIALE", type="primary"):
        with st.spinner("Gemini sta leggendo la fattura..."):
            reader = PdfReader(file)
            testo_grezzo = "\n".join([p.extract_text() for p in reader.pages])
            
            try:
                prodotti_estratti = chiedi_all_ai(testo_grezzo)
                
                # Applica Memoria Storica
                for p in prodotti_estratti:
                    sci_key = p['sci'].upper().strip()
                    if sci_key in st.session_state.learned_map:
                        p['nome'] = st.session_state.learned_map[sci_key]
                
                st.session_state.p_list = prodotti_estratti
            except Exception as e:
                st.error(f"Errore AI: {e}")

    if st.session_state.get("p_list"):
        st.success(f"✅ Trovati {len(st.session_state.p_list)} prodotti.")

        # PDF Rullino Completo
        pdf_tot = FPDF(orientation="L", unit="mm", format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)
        for p in st.session_state.p_list:
            disegna_etichetta(pdf_tot, p)

        st.download_button(
            label="🖨️ SCARICA TUTTE LE ETICHETTE (PDF)",
            data=bytes(pdf_tot.output()),
            file_name="Rullino_Etichette.pdf",
            mime="application/pdf",
        )

        st.markdown("---")

        # EDITING + ANTEPRIMA INTEGRATA
        for i, p in enumerate(st.session_state.p_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}", expanded=True):
                col_edit, col_prev = st.columns([2, 1])
                
                with col_edit:
                    new_nome = st.text_input("Nome Commerciale", p["nome"], key=f"nm_{i}")
                    new_lotto = st.text_input("Lotto", p["lotto"], key=f"lt_{i}")
                    
                    # Aggiornamento dati e memoria
                    p["nome"] = new_nome.upper().strip()
                    p["lotto"] = new_lotto.upper().strip()
                    if p["nome"] != "DA COMPILARE":
                        st.session_state.learned_map[p["sci"].upper().strip()] = p["nome"]

                with col_prev:
                    # Genera PDF per l'anteprima singola
                    pdf_s = FPDF(orientation="L", unit="mm", format=(62, 100))
                    pdf_s.set_margins(4, 3, 4)
                    pdf_s.set_auto_page_break(False)
                    disegna_etichetta(pdf_s, p)
                    pdf_bytes = bytes(pdf_s.output())
                    
                    mostra_pdf_anteprima(pdf_bytes)
                    st.download_button("⬇️ Scarica Singola", pdf_bytes, f"Etic_{i}.pdf", key=f"btn_{i}")