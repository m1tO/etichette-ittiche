import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome(testo):
    """Pulisce il nome del pesce da codici e pezzature."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    # Taglia su numeri e pezzature
    testo = re.split(r'\s\d+', testo)[0]
    parole_stop = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "FRANCIA", "ITALIA", "GRECIA", "SPAGNA", "37.", "27."]
    for word in parole_stop:
        if word in testo: testo = testo.split(word)[0]
    return testo.strip().strip('-').strip(',').strip()

def disegna_pagina_etichetta(pdf, p):
    """Disegna la grafica di una singola etichetta sulla pagina corrente."""
    pdf.add_page()
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(0, 7, p['nome'], align='C')
    
    # Nome Scientifico
    pdf.ln(1)
    font_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", font_sci)
    pdf.multi_cell(0, 4, f"({p['sci']})", align='C')
    
    # Tracciabilità
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Box Lotto
    pdf.set_y(38) 
    pdf.set_font("helvetica", "B", 13)
    pdf.set_x(25)
    pdf.cell(50, 11, f"LOTTO: {p['lotto']}", border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, f"Confezionato il: 07/02/2026", align='R')

def genera_pdf_unico(prodotti):
    """Crea un unico file PDF con tutte le etichette."""
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=4, top=4, right=4)
    pdf.set_auto_page_break(auto=False)
    
    for p in prodotti:
        disegna_pagina_etichetta(pdf, p)
        
    return bytes(pdf.output())

def genera_pdf_singolo(p):
    """Crea un PDF per un solo pesce."""
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=4, top=4, right=4)
    pdf.set_auto_page_break(auto=False)
    disegna_pagina_etichetta(pdf, p)
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
        fao_search = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        fao = fao_search.group(1) if fao_search else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome(nome_grezzo),
            "sci": sci,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

# --- INTERFACCIA ---
st.title("⚓ FishLabel Scanner PRO")
st.write("Carica la fattura e stampa tutto in un colpo solo.")

file = st.file_uploader("Trascina qui la fattura PDF", type="pdf")

if file:
    prodotti = estrai_dati(file)
    
    if prodotti:
        # --- TASTONE PER STAMPA MASSIVA ---
        st.success(f"Trovati {len(prodotti)} prodotti!")
        pdf_totale = genera_pdf_unico(prodotti)
        
        st.download_button(
            label=f"🖨️ SCARICA TUTTE LE {len(prodotti)} ETICHETTE (PDF UNICO)",
            data=pdf_totale,
            file_name="Stampa_Massiva_Etichette.pdf",
            mime="application/pdf",
            type="primary" # Lo rende evidente e colorato
        )
        
        st.markdown("---")
        st.write("Oppure scarica singolarmente:")

    # --- LISTA SINGOLA (per ristampe) ---
    for i, p in enumerate(prodotti):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text(f"📦 {p['nome']} - Lotto: {p['lotto']}")
        with col2:
            pdf_singolo = genera_pdf_singolo(p)
            st.download_button(
                label="Scarica",
                data=pdf_singolo,
                file_name=f"Etichetta_{i}.pdf",
                mime="application/pdf",
                key=f"btn_{i}"
            )