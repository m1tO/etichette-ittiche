import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    # Taglia ai numeri o pezzature
    testo = re.split(r'\s\d+', testo)[0]
    parole_stop = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "FRANCIA", "ITALIA", "GRECIA"]
    for parola in parole_stop:
        if parola in testo: testo = testo.split(parola)[0]
    return testo.strip().strip('-').strip(',')

def crea_pdf_definitivo(p):
    # Formato Brother 62x100mm
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=5, top=3, right=5)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # --- INTESTAZIONE NEGOZIO ---
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", ln=True, align='C')
    pdf.ln(1)
    
    # --- NOME PRODOTTO ---
    pdf.set_font("helvetica", "B", 16)
    pdf.multi_cell(0, 8, p['nome'], align='C')
    
    # --- SCIENTIFICO ---
    font_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", font_sci)
    pdf.cell(0, 5, f"({p['sci']})", ln=True, align='C')
    
    pdf.ln(2)
    
    # --- TRACCIABILITÀ ---
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, f"ZONA FAO: {p['fao']} - {p['metodo']}", ln=True, align='C')
    
    # --- BOX LOTTO ---
    pdf.ln(3)
    pdf.set_font("helvetica", "B", 14)
    # Calcolo per centrare il box
    pdf.set_x(25)
    pdf.cell(50, 12, f"LOTTO: {p['lotto']}", border=1, ln=True, align='C')
    
    # --- PIÈ DI PAGINA ---
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, f"Confezionato il: 07/02/2026", ln=True, align='R')
    
    return bytes(pdf.output())

def estrai_dati(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    for i in range(len(sezioni) - 1):
        blocco_pre, blocco_post = sezioni[i], sezioni[i+1]
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        sci = sci_match.group(1) if sci_match else "N.D."
        linee = blocco_pre.strip().split('\n')
        nome_grezzo = "PESCE"
        for j, riga in enumerate(linee):
            if sci in riga:
                nome_grezzo = riga.split('(')[0].strip()
                if len(nome_grezzo) < 3 and j > 0: nome_grezzo = linee[j-1].strip()
        
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        fao = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        
        # Puliamo il nome già qui per l'interfaccia
        nome_pulito = pulisci_nome_chirurgico(nome_grezzo)
        
        prodotti.append({
            "nome": nome_pulito,
            "sci": sci,
            "lotto": lotto,
            "fao": fao.group(1) if fao else "37.2.1",
            "metodo": "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        })
    return prodotti

st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    prodotti = estrai_dati(file)
    for i, p in enumerate(prodotti):
        # L'expander ora è pulitissimo: "📦 TRIGLIA DI SCOGLIO - Lotto: ..."
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            pdf_bytes = crea_pdf_definitivo(p)
            st.download_button(
                label="📥 SCARICA ETICHETTA PRONTA",
                data=pdf_bytes,
                file_name=f"Etichetta_{p['nome']}.pdf",
                mime="application/pdf",
                key=f"btn_{i}"
            )