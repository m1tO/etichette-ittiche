import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_prodotto(testo):
    """Logica di taglio per isolare solo il nome commerciale del pesce."""
    if not testo:
        return "PESCE"
    
    # 1. Portiamo tutto in maiuscolo
    testo = testo.upper().strip()
    
    # 2. TAGLIO PEZZATURE: Se trova numeri tipo 100-200, 300/400, 1/2, ecc.
    # Taglia tutto quello che viene dopo la pezzatura
    testo = re.split(r'\d+[\-/]\d+', testo)[0]
    
    # 3. TAGLIO ZONE FAO: Se trova i codici zona 27 o 37 come numeri isolati
    testo = re.split(r'\b(27|37)\b', testo)[0]
    
    # 4. PAROLE STOP: Termini tecnici che segnano la fine del nome
    parole_stop = [
        "EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "ATTREZZI", 
        "FRANCIA", "GRECIA", "SPAGNA", "ITALIA", "MAROCCO", "TUNISIA",
        "SCIABICHE", "RETI", "AMI", "VOLANTE", "N.", "N°"
    ]
    for parola in parole_stop:
        if parola in testo:
            testo = testo.split(parola)[0]
            
    # Pulizia finale da simboli residui alla fine del nome
    testo = re.sub(r'[\.\,:\-_/]+$', '', testo)
    return testo.strip()

def crea_pdf_solido(p):
    """Genera il PDF per l'etichetta Brother 62mm x 100mm."""
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    
    # Nome Commerciale (Font grande ma bilanciato)
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(0, 8, p['nome'], align='C')
    
    # Nome Scientifico
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 6, f"({p['sci']})", ln=True, align='C')
    
    pdf.ln(2)
    
    # Dati Tracciabilità
    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 6, f"ZONA FAO: {p['fao']}", ln=True, align='C')
    pdf.cell(0, 6, f"METODO: {p['metodo']}", ln=True, align='C')
    
    pdf.ln(4)
    
    # Box del Lotto
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 12, f"LOTTO: {p['lotto']}", border=1, ln=True, align='C')
    
    # Data a fondo etichetta
    pdf.set_font("helvetica", "", 8)
    pdf.ln(2)
    pdf.cell(0, 5, "Data Arrivo: 07/02/2026", ln=True, align='R')
    
    return bytes(pdf.output())

def estrai_tutto(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    
    # Identifichiamo i blocchi tramite la parola LOTTO
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        
        # Estrazione Nome Scientifico
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        scientifico = sci_match.group(1) if sci_match else "N.D."
        
        # Identificazione Nome Commerciale
        linee = blocco_pre.strip().split('\n')
        nome_grezzo = "PESCE"
        for j, riga in enumerate(linee):
            if scientifico in riga:
                nome_grezzo = riga.split('(')[0].strip()
                if len(nome_grezzo) < 3 and j > 0:
                    nome_grezzo = linee[j-1].strip()
        
        # Estrazione Lotto
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        # Zona FAO e Metodo
        fao_match = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        fao = fao_match.group(1) if fao_match else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_prodotto(nome_grezzo),
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

# --- INTERFACCIA STREAMLIT ---
st.title("⚓ FishLabel Scanner PRO")
st.subheader("Ottimizzato per Triglia, Orata e Spigola")

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    prodotti = estrai_tutto(file)
    if not prodotti:
        st.error("Nessun dato trovato. Verifica il formato del PDF.")
    
    for i, p in enumerate(prodotti):
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            st.write(f"**Scientifico:** {p['sci']}")
            st.write(f"**Tracciabilità:** FAO {p['fao']} | {p['metodo']}")
            
            pdf_data = crea_pdf_solido(p)
            
            st.download_button(
                label="📥 SCARICA ETICHETTA",
                data=pdf_data,
                file_name=f"Etichetta_{i}.pdf",
                mime="application/pdf",
                key=f"btn_{i}_{p['lotto']}"
            )