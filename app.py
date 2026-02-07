import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Taglia il nome non appena iniziano i dati tecnici o le pezzature."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    # Taglia appena vede uno spazio seguito da un numero (es. ' 100' o ' 27')
    testo = re.split(r'\s\d+', testo)[0]
    parole_stop = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "FRANCIA", "ITALIA", "GRECIA"]
    for parola in parole_stop:
        if parola in testo: testo = testo.split(parola)[0]
    return testo.strip().strip('-').strip(',')

def crea_pdf_blindato(p):
    # Formato 62x100mm - Brother
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=5, top=3, right=5)
    pdf.set_auto_page_break(auto=False) # BLOCCO TOTALE 2° PAGINA
    pdf.add_page()
    
    # 1. INTESTAZIONE NEGOZIO
    pdf.set_font("helvetica", "B", 8)
    # new_x="LMARGIN", new_y="NEXT" sostituisce il vecchio ln=True per Python 3.13
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # 2. NOME COMMERCIALE (Font 14 bilanciato)
    pdf.set_font("helvetica", "B", 14)
    pdf.multi_cell(0, 7, p['nome'], align='C')
    
    # 3. NOME SCIENTIFICO (Multi-riga se troppo lungo per evitare overflow)
    pdf.ln(1)
    font_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", font_sci)
    pdf.multi_cell(0, 4, f"({p['sci']})", align='C')
    
    # 4. TRACCIABILITÀ
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # 5. BOX LOTTO (Posizione fissa alta per non cadere fuori dal foglio)
    pdf.set_y(38) 
    pdf.set_font("helvetica", "B", 13)
    pdf.set_x(25)
    pdf.cell(50, 11, f"LOTTO: {p['lotto']}", border=1, align='C', new_x="LMARGIN", new_y="NEXT")
    
    # 6. DATA CONFEZIONAMENTO
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, "Confezionato il: 07/02/2026", align='R')
    
    # Convertiamo bytearray in bytes per Streamlit
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

file = st.file_uploader("Trascina qui la fattura PDF", type="pdf")

if file:
    prodotti = estrai_dati(file)
    for i, p in enumerate(prodotti):
        # UI pulita: mostra solo il nome pesce e lotto senza sporcizia
        with st.expander(f"📦 {p['nome']} - Lotto: {p['lotto']}"):
            try:
                # Generazione PDF sicura per Python 3.13
                pdf_output = crea_pdf_blindato(p)
                st.download_button(
                    label=f"SCARICA ETICHETTA {p['nome']}",
                    data=pdf_output,
                    file_name=f"Etichetta_{p['lotto'].replace('/', '_')}.pdf",
                    mime="application/pdf",
                    key=f"btn_{i}_{p['lotto']}"
                )
            except Exception as e:
                st.error(f"Errore tecnico: {str(e)}")