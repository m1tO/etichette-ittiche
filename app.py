import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Taglia il nome non appena iniziano i dati tecnici o le pezzature."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    # Taglia appena vede uno spazio seguito da un numero o pezzature tipo 100-200
    testo = re.split(r'\s\d+', testo)[0]
    parole_stop = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "FRANCIA", "ITALIA"]
    for parola in parole_stop:
        if parola in testo: testo = testo.split(parola)[0]
    return testo.strip().strip('-').strip(',')

def crea_pdf_blindato(p):
    # Formato 62x100mm - Margini azzerati per usare tutto lo spazio
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=5, top=5, right=5)
    pdf.set_auto_page_break(auto=False) # BLOCCO TOTALE SECONDA PAGINA
    pdf.add_page()
    
    # 1. Nome Commerciale
    pdf.set_font("helvetica", "B", 14)
    pdf.multi_cell(0, 8, p['nome'], align='C')
    
    # 2. Nome Scientifico (Ridotto per non uscire dai bordi)
    pdf.ln(1)
    font_sci = 9 if len(p['sci']) < 25 else 7 # Se il nome è lungo, rimpicciolisce
    pdf.set_font("helvetica", "I", font_sci)
    pdf.cell(0, 5, f"({p['sci']})", ln=True, align='C')
    
    pdf.ln(2)
    
    # 3. FAO e Metodo (Più compatti)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"ZONA FAO: {p['fao']} - {p['metodo']}", ln=True, align='C')
    
    # 4. Box del Lotto (Spostato più in alto per non cadere fuori)
    pdf.ln(3)
    pdf.set_font("helvetica", "B", 13)
    # Riquadro centrato
    pdf.cell(20) # Sposta a destra
    pdf.cell(50, 12, f"LOTTO: {p['lotto']}", border=1, ln=True, align='C')
    
    # 5. Data piccolissima in basso
    pdf.set_y(55) # Forza la posizione a fondo etichetta
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, "Data: 07/02/2026", ln=True, align='R')
    
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
        prodotti.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo),
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
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            # Creiamo i byte del PDF
            pdf_bytes = crea_pdf_blindato(p)
            st.download_button(
                label="📥 SCARICA ETICHETTA",
                data=pdf_bytes,
                file_name=f"Etichetta_{i}.pdf",
                mime="application/pdf",
                key=f"btn_{i}"
            )