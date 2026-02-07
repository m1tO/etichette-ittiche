import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_definitivo(testo):
    """Ghigliottina totale: taglia tutto ciò che non è il nome del pesce."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    
    # 1. Taglia appena vede una pezzatura (es. 100-200, 300/400) o numeri isolati
    # Cerchiamo lo schema numero-numero o spazio-numero
    testo = re.split(r'\s\d+[\-/]\d+', testo)[0]
    testo = re.split(r'\s\d+', testo)[0]
    
    # 2. Lista nera di parole tecniche
    stop_words = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "FRANCIA", "ITALIA", "GRECIA", "SPAGNA", "37.", "27."]
    for word in stop_words:
        if word in testo:
            testo = testo.split(word)[0]
            
    return testo.strip().strip('-').strip(',')

def crea_pdf_blindato(p):
    """Genera un PDF a pagina singola garantita senza crash."""
    # Formato Brother 62x100mm
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=5, top=3, right=5)
    pdf.set_auto_page_break(auto=False) # IMPEDISCE LA SECONDA PAGINA
    pdf.add_page()
    
    # --- INTESTAZIONE ---
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", ln=True, align='C')
    pdf.ln(1)
    
    # --- NOME COMMERCIALE ---
    pdf.set_font("helvetica", "B", 16)
    # multi_cell gestisce l'andata a capo automatica
    pdf.multi_cell(0, 8, p['nome'], align='C')
    
    # --- NOME SCIENTIFICO ---
    # Se il nome è troppo lungo, lo rimpiccioliamo drasticamente
    font_sci = 9 if len(p['sci']) < 20 else 7
    pdf.set_font("helvetica", "I", font_sci)
    pdf.multi_cell(0, 5, f"({p['sci']})", align='C')
    
    pdf.ln(1)
    
    # --- TRACCIABILITÀ ---
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, f"FAO {p['fao']} - {p['metodo']}", ln=True, align='C')
    
    # --- BOX LOTTO (Posizione fissa per evitare salti pagina) ---
    pdf.set_y(38) 
    pdf.set_font("helvetica", "B", 14)
    pdf.set_x(25)
    pdf.cell(50, 12, f"LOTTO: {p['lotto']}", border=1, ln=True, align='C')
    
    # --- PIÈ DI PAGINA ---
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, f"Confezionato il: 07/02/2026", ln=True, align='R')
    
    return bytes(pdf.output())

def estrai_dati(file):
    reader = PdfReader(file)
    testo = ""
    for page in reader.pages:
        testo += page.extract_text().upper() + "\n"
    
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        
        # Nome Scientifico
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        sci = sci_match.group(1) if sci_match else "N.D."
        
        # Identificazione Nome (cerca la riga sopra lo scientifico)
        linee = blocco_pre.strip().split('\n')
        nome_grezzo = "PESCE"
        for j, riga in enumerate(linee):
            if sci in riga:
                nome_grezzo = riga.split('(')[0].strip()
                if len(nome_grezzo) < 3 and j > 0: nome_grezzo = linee[j-1].strip()
        
        # Lotto
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        # FAO e Metodo
        fao_search = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        fao = fao_search.group(1) if fao_search else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_definitivo(nome_grezzo),
            "sci": sci,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

# --- UI ---
st.title("⚓ FishLabel Scanner PRO")
st.write("Versione 2.0 - Risoluzione Crash & Layout")

file = st.file_uploader("Trascina la fattura qui", type="pdf")

if file:
    prodotti = estrai_dati(file)
    for i, p in enumerate(prodotti):
        # UI pulita con nome già tagliato
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            try:
                pdf_bytes = crea_pdf_blindato(p)
                st.download_button(
                    label=f"SCARICA ETICHETTA {p['nome']}",
                    data=pdf_bytes,
                    file_name=f"Etichetta_{p['lotto'].replace('/', '_')}.pdf",
                    mime="application/pdf",
                    key=f"btn_{i}"
                )
            except Exception as e:
                st.error("Errore generazione. Riprova tra un attimo.")