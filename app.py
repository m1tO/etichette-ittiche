import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Taglia il nome non appena iniziano i dati tecnici o le pezzature."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    
    # 1. TAGLIO AI NUMERI: Se trova uno spazio seguito da un numero (es. ' 100' o ' 27')
    # significa che sono iniziate le pezzature o le zone FAO. Tagliamo tutto lì.
    testo = re.split(r'\s\d+', testo)[0]
    
    # 2. TAGLIO PAROLE CHIAVE: Se appaiono termini tecnici, stop immediato.
    parole_stop = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "FRANCIA", "ITALIA", "GRECIA"]
    for parola in parole_stop:
        if parola in testo:
            testo = testo.split(parola)[0]
            
    return testo.strip().strip('-').strip(',')

def crea_pdf_sicuro(p):
    """Genera un PDF leggero in formato byte, perfetto per evitare crash su Streamlit."""
    # Formato 62x100mm (Brother standard)
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    
    # Titolo - Ridotto a 13 per evitare la seconda pagina
    pdf.set_font("helvetica", "B", 13)
    pdf.multi_cell(0, 7, p['nome'], align='C')
    
    # Scientifico - Piccolo e corsivo
    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 5, f"({p['sci']})", ln=True, align='C')
    
    pdf.ln(2)
    
    # FAO e Metodo
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, f"ZONA FAO: {p['fao']}", ln=True, align='C')
    pdf.cell(0, 5, f"METODO: {p['metodo']}", ln=True, align='C')
    
    pdf.ln(4)
    
    # Lotto - Box compatto
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, f"LOTTO: {p['lotto']}", border=1, ln=True, align='C')
    
    # Data automatica per oggi
    pdf.set_font("helvetica", "", 7)
    pdf.ln(2)
    pdf.cell(0, 4, "Data: 07/02/2026", ln=True, align='R')
    
    # Restituisce i byte puri (evita il crash "Sito non disponibile")
    return bytes(pdf.output())

def estrai_dati(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre, blocco_post = sezioni[i], sezioni[i+1]
        
        # Nome Scientifico
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        sci = sci_match.group(1) if sci_match else "N.D."
        
        # Nome Commerciale (cerca riga sopra scientifico)
        linee = blocco_pre.strip().split('\n')
        nome_grezzo = "PESCE"
        for j, riga in enumerate(linee):
            if sci in riga:
                nome_grezzo = riga.split('(')[0].strip()
                if len(nome_grezzo) < 3 and j > 0: nome_grezzo = linee[j-1].strip()
        
        # Lotto completo
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        # FAO e Metodo
        fao = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo),
            "sci": sci,
            "lotto": lotto,
            "fao": fao.group(1) if fao else "37.2.1",
            "metodo": metodo
        })
    return prodotti

# --- APP INTERFACE ---
st.title("⚓ FishLabel Scanner PRO")
st.write("Versione Anti-Crash per Python 3.13")

file = st.file_uploader("Trascina qui la fattura PDF", type="pdf")

if file:
    prodotti = estrai_dati(file)
    for i, p in enumerate(prodotti):
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            # Generazione sicura del PDF
            pdf_bytes = crea_pdf_sicuro(p)
            
            st.download_button(
                label="📥 SCARICA ETICHETTA",
                data=pdf_bytes,
                file_name=f"Etichetta_{i}.pdf",
                mime="application/pdf",
                key=f"btn_{i}_{p['lotto']}"
            )