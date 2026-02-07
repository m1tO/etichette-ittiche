import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_testo(testo):
    parole = ["ATTREZZI", "PESCA", "USATI", "SCI", "AI", "ZONA", "FAO", "N.", "N°"]
    for p in parole:
        testo = re.sub(rf'\b{p}\b', '', testo)
    return re.sub(r'\s+', ' ', testo).strip()

def crea_pdf_bytes(p):
    # Generazione PDF specifica per Python 3.13 e Streamlit
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    
    # Nome Pesce (Font standard per evitare errori di caricamento)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, p['nome'][:30], ln=True, align='C')
    
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 5, f"({p['sci']})", ln=True, align='C')
    
    pdf.ln(5)
    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 7, f"ZONA FAO: {p['fao']}", ln=True, align='C')
    pdf.cell(0, 7, f"METODO: {p['metodo']}", ln=True, align='C')
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 12, f"LOTTO: {p['lotto']}", border=1, ln=True, align='C')
    
    # dest='S' restituisce il PDF come byte string, perfetto per il download_button
    return pdf.output(dest='S')

def estrai_tutto(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    for i in range(len(sezioni) - 1):
        blocco_pre, blocco_post = sezioni[i], sezioni[i+1]
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        scientifico = sci_match.group(1) if sci_match else "N.D."
        linee = blocco_pre.strip().split('\n')
        nome_comm = "PESCE"
        for j, riga in enumerate(linee):
            if scientifico in riga:
                nome_comm = riga.split('(')[0].strip()
                if len(nome_comm) < 3 and j > 0: nome_comm = linee[j-1].strip()
        
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        fao_match = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        fao = fao_match.group(1) if fao_match else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        prodotti.append({"nome": pulisci_testo(nome_comm), "sci": scientifico, "lotto": lotto, "fao": fao, "metodo": metodo})
    return prodotti

st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    prodotti = estrai_tutto(file)
    for p in prodotti:
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            # Generiamo i byte qui per essere sicuri che siano freschi
            pdf_data = crea_pdf_bytes(p)
            
            st.download_button(
                label=f"Scarica Etichetta {p['lotto']}",
                data=pdf_data,
                file_name=f"Etichetta_{p['lotto'].replace(' ', '_')}.pdf",
                mime="application/pdf",
                key=f"btn_{p['lotto']}_{i}" # Chiave univoca per evitare conflitti
            )