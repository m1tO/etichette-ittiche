import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Taglia il nome non appena iniziano i dati tecnici o le pezzature."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    
    # 1. Taglia appena vede uno spazio seguito da un numero (es. ' 100' o ' 27')
    testo = re.split(r'\s\d+', testo)[0]
    
    # 2. Parole stop
    parole_stop = ["EF", "ZONA", "FAO", "PESCATO", "ALLEVATO", "FRANCIA", "ITALIA", "GRECIA", "SPAGNA", "37.", "27."]
    for parola in parole_stop:
        if parola in testo:
            testo = testo.split(parola)[0]
            
    return testo.strip().strip('-').strip(',').strip()

def crea_pdf_blindato(p):
    # Formato Brother 62x100mm
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=4, top=4, right=4) # Margini minimi
    pdf.set_auto_page_break(auto=False)     # BLOCCO ASSOLUTO 2° PAGINA
    pdf.add_page()
    
    # --- INTESTAZIONE ---
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # --- NOME COMMERCIALE ---
    pdf.set_font("helvetica", "B", 15)
    # multi_cell gestisce l'andata a capo automatica se il nome è lungo
    pdf.multi_cell(0, 7, p['nome'], align='C')
    
    # --- NOME SCIENTIFICO ---
    pdf.ln(1)
    font_sci = 9 if len(p['sci']) < 25 else 7 # Font dinamico
    pdf.set_font("helvetica", "I", font_sci)
    pdf.multi_cell(0, 4, f"({p['sci']})", align='C')
    
    # --- TRACCIABILITÀ ---
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # --- BOX LOTTO ---
    # Posizionamento assoluto per evitare che scivoli in pagina 2
    pdf.set_y(38) 
    pdf.set_font("helvetica", "B", 13)
    pdf.set_x(25) # Centratura manuale del box
    pdf.cell(50, 11, f"LOTTO: {p['lotto']}", border=1, align='C')
    
    # --- PIÈ DI PAGINA ---
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, f"Confezionato il: 07/02/2026", align='R')
    
    # --- IL FIX FONDAMENTALE PER L'ERRORE ROSSO ---
    # fpdf2 restituisce un bytearray. Streamlit vuole bytes.
    # Facciamo il cast esplicito:
    return bytes(pdf.output())

def estrai_dati(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        
        # Nome Scientifico
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        sci = sci_match.group(1) if sci_match else "N.D."
        
        # Nome Commerciale
        linee = blocco_pre.strip().split('\n')
        nome_grezzo = "PESCE"
        for j, riga in enumerate(linee):
            if sci in riga:
                nome_grezzo = riga.split('(')[0].strip()
                if len(nome_grezzo) < 3 and j > 0: nome_grezzo = linee[j-1].strip()
        
        # Lotto
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        # FAO
        fao_search = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        fao = fao_search.group(1) if fao_search else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        
        # Pulizia IMMEDIATA
        nome_pulito = pulisci_nome_chirurgico(nome_grezzo)
        
        prodotti.append({
            "nome": nome_pulito,
            "sci": sci,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

# --- UI ---
st.title("⚓ FishLabel Scanner PRO")

file = st.file_uploader("Trascina la fattura qui", type="pdf")

if file:
    prodotti = estrai_dati(file)
    for i, p in enumerate(prodotti):
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            try:
                # Generazione PDF
                pdf_bytes = crea_pdf_blindato(p)
                
                # Pulizia nome file per evitare errori di download
                nome_file_safe = re.sub(r'[\\/*?:"<>|]', "", p['nome'])
                
                st.download_button(
                    label=f"SCARICA ETICHETTA {p['nome']}",
                    data=pdf_bytes,
                    file_name=f"Etichetta_{nome_file_safe}.pdf",
                    mime="application/pdf",
                    key=f"btn_{i}"
                )
            except Exception as e:
                # Questo mostrerà l'errore vero se succede ancora qualcosa
                st.error(f"Errore: {e}")