import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

# Configurazione della pagina
st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_prodotto(testo):
    """Isola solo il nome del pesce, tagliando pezzature e codici tecnici."""
    if not testo:
        return "PESCE"
    
    testo = testo.upper().strip()
    
    # 1. TAGLIO PEZZATURE: se trova numeri tipo 100-200, 300/400, 1/2, ecc.
    # Taglia tutto quello che viene dopo
    testo = re.split(r'\d+[\-/]\d+', testo)[0]
    
    # 2. TAGLIO ZONE FAO: se trova i codici 27 o 37 come numeri isolati
    testo = re.split(r'\b(27|37)\b', testo)[0]
    
    # 3. PAROLE STOP: termini che segnano la fine del nome commerciale
    parole_stop = [
        "EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "ATTREZZI", 
        "FRANCIA", "GRECIA", "SPAGNA", "ITALIA", "MAROCCO", "TUNISIA",
        "SCIABICHE", "RETI", "AMI", "VOLANTE", "N.", "N°"
    ]
    for parola in parole_stop:
        if parola in testo:
            testo = testo.split(parola)[0]
            
    # Rimuove simboli residui alla fine (punti, virgole, trattini)
    testo = re.sub(r'[\.\,:\-_/]+$', '', testo)
    return testo.strip()

def crea_pdf_solido(p):
    """Genera il PDF per l'etichetta Brother 62mm x 100mm (Pagina Singola)."""
    # L = Landscape (Orizzontale), 62mm altezza, 100mm larghezza
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.add_page()
    
    # Nome Commerciale (Font ridotto a 14 per farlo stare in una riga)
    pdf.set_font("helvetica", "B", 14)
    # multi_cell manda a capo se il nome è troppo lungo invece di creare una nuova pagina
    pdf.multi_cell(0, 8, p['nome'], align='C')
    
    # Nome Scientifico
    pdf.set_font("helvetica", "I", 9)
    pdf.cell(0, 5, f"({p['sci']})", ln=True, align='C')
    
    pdf.ln(2)
    
    # Dati Tracciabilità
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, f"ZONA FAO: {p['fao']}", ln=True, align='C')
    pdf.cell(0, 6, f"METODO: {p['metodo']}", ln=True, align='C')
    
    pdf.ln(3)
    
    # Box del Lotto (Font 12 per sicurezza)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, f"LOTTO: {p['lotto']}", border=1, ln=True, align='C')
    
    # Data a fondo etichetta
    pdf.set_font("helvetica", "", 7)
    pdf.ln(2)
    pdf.cell(0, 4, "Data Arrivo: 07/02/2026", ln=True, align='R')
    
    # Converte in bytes per il download sicuro su Streamlit
    return bytes(pdf.output())

def estrai_tutto(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    
    # Divide il testo ogni volta che trova 'LOTTO'
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        
        # Cerca il nome scientifico tra parentesi
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        scientifico = sci_match.group(1) if sci_match else "N.D."
        
        # Isola la riga del nome
        linee = blocco_pre.strip().split('\n')
        nome_grezzo = "PESCE"
        for j, riga in enumerate(linee):
            if scientifico in riga:
                nome_grezzo = riga.split('(')[0].strip()
                if len(nome_grezzo) < 3 and j > 0:
                    nome_grezzo = linee[j-1].strip()
        
        # Estrae il codice lotto (prende tutto fino allo spazio lungo o a capo)
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        # FAO e Metodo
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

# --- INTERFACCIA APP ---
st.title("⚓ FishLabel Scanner PRO")
st.write("Versione ottimizzata per etichette Brother 62mm")

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    prodotti = estrai_tutto(file)
    
    for i, p in enumerate(prodotti):
        # Mostra un'anteprima pulita nell'app
        with st.expander(f"📦 {p['nome']} - Lotto: {p['lotto']}"):
            st.write(f"**Scientifico:** {p['sci']}")
            st.write(f"**Tracciabilità:** FAO {p['fao']} | {p['metodo']}")
            
            # Genera i dati binari del PDF
            pdf_bytes = crea_pdf_solido(p)
            
            st.download_button(
                label="📥 SCARICA ETICHETTA PDF",
                data=pdf_bytes,
                file_name=f"Etichetta_{p['lotto'].replace(' ', '_')}.pdf",
                mime="application/pdf",
                key=f"btn_{i}_{p['lotto']}"
            )