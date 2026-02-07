import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Pulisce il nome del pesce eliminando indirizzi e dati tecnici."""
    if not testo: return "PESCE"
    
    # 1. Rimuoviamo righe che sembrano indirizzi (es. 90147 PALERMO)
    testo = re.sub(r'\d{5}\s+PALERMO.*', '', testo)
    
    testo = testo.upper().strip()
    # 2. Taglia ai numeri o pezzature (es. ' 100-200' o ' 300')
    testo = re.split(r'\s\d+', testo)[0]
    
    # 3. Parole stop
    parole_stop = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "ATTREZZI", "PRODOTTO"]
    for parola in parole_stop:
        if parola in testo: testo = testo.split(parola)[0]
    
    return testo.strip().strip('-').strip(',').strip()

def disegna_pagina_etichetta(pdf, p):
    pdf.add_page()
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(0, 7, p['nome'], align='C')
    
    # Scientifico
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
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=4, top=4, right=4)
    pdf.set_auto_page_break(auto=False)
    for p in prodotti: disegna_pagina_etichetta(pdf, p)
    return bytes(pdf.output())

def estrai_dati(file):
    reader = PdfReader(file)
    testo_completo = ""
    for page in reader.pages:
        testo_completo += page.extract_text() + "\n"
    
    # SICUREZZA: Tagliamo via l'intestazione della fattura fino alla tabella prodotti
    if "Descrizione" in testo_completo:
        testo_completo = testo_completo.split("Descrizione", 1)[1]
    
    testo_completo = testo_completo.upper()
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo_completo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        
        # 1. Scientifico
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        sci = sci_match.group(1) if sci_match else "N.D."
        
        # 2. Nome (Cerca la riga del nome scientifico e pulisce)
        linee = blocco_pre.strip().split('\n')
        nome_grezzo = "PESCE"
        for j, riga in enumerate(linee):
            if sci in riga:
                nome_grezzo = riga.split('(')[0].strip()
                # Se è troppo corto (solo un codice), prendiamo la riga sopra
                if len(nome_grezzo) < 4 and j > 0:
                    nome_grezzo = linee[j-1].strip()
        
        # 3. Lotto (Migliorato: si ferma al primo spazio lungo o virgola del prezzo)
        # In image_7a9fc6.png vedevamo SP/14-01-202630. Ora tagliamo prima del prezzo.
        lotto_match = re.search(r'^([A-Z0-9\-/]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        fao = re.search(r'FAO\s*N?°?\s*([\d\.]+)', blocco_pre)
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre or "ACQUACOLTURA" in blocco_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo),
            "sci": sci,
            "lotto": lotto,
            "fao": fao.group(1) if fao else "37.2.1",
            "metodo": metodo
        })
    return prodotti

# --- UI ---
st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Trascina la fattura Hermes Fish", type="pdf")

if file:
    prodotti = estrai_dati(file)
    if prodotti:
        st.success(f"Trovati {len(prodotti)} prodotti!")
        pdf_totale = genera_pdf_unico(prodotti)
        st.download_button(
            label="🖨️ SCARICA TUTTE LE ETICHETTA",
            data=pdf_totale,
            file_name="Etichette_Hermes.pdf",
            mime="application/pdf"
        )
        for i, p in enumerate(prodotti):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                st.write(f"Scientifico: {p['sci']} | FAO: {p['fao']}")