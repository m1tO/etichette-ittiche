import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Pulisce il nome eliminando indirizzi, codici iniziali e dati tecnici."""
    if not testo: return "PESCE"
    # 1. Rimuove codici numerici lunghi (es. 46668255) o codici articolo (0258)
    testo = re.sub(r'^\d{4,10}\s+', '', testo)
    testo = re.sub(r'^\d+\s+', '', testo)
    
    testo = testo.upper().strip()
    # 2. Taglia ai numeri di pezzatura (es. 300-400)
    testo = re.split(r'\s\d+', testo)[0]
    
    # 3. Parole stop Hermes
    parole_stop = ["PRODOTTO", "PESCA", "PN", "AI", "ZONA", "FAO", "PESCATO", "ALLEVATO"]
    for parola in parole_stop:
        if parola in testo: testo = testo.split(parola)[0]
    
    return testo.strip().strip('-').strip(',').strip()

def crea_pdf_blindato(p):
    pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
    pdf.set_margins(left=4, top=3, right=4)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 4, "ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome (Multi-riga per nomi lunghi)
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(0, 7, p['nome'], align='C')
    
    # Scientifico (Rimpicciolisce se lungo)
    pdf.ln(1)
    font_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", font_sci)
    pdf.multi_cell(0, 4, f"({p['sci']})", align='C')
    
    # Tracciabilità
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Box Lotto (Font dinamico per lotti lunghi tipo Hermes)
    pdf.set_y(38)
    lotto_text = f"LOTTO: {p['lotto']}"
    font_lotto = 13 if len(lotto_text) < 18 else 10 # Rimpicciolisce se serve
    pdf.set_font("helvetica", "B", font_lotto)
    pdf.set_x(15)
    pdf.cell(70, 11, lotto_text, border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, f"Confezionato il: 07/02/2026", align='R')
    
    return bytes(pdf.output())

def estrai_dati(file):
    reader = PdfReader(file)
    testo = ""
    for page in reader.pages:
        testo += page.extract_text() + "\n"
    
    # Taglia via l'intestazione della fattura
    if "Descrizione" in testo:
        testo = testo.split("Descrizione", 1)[1]
    
    # Normalizzazione testo per facilitare i regex
    testo = testo.replace('\n', ' ')
    
    # 1. Trova tutti i blocchi che iniziano con un nome scientifico tra parentesi
    # e finiscono con un LOTTO
    matches = re.findall(r'([A-Z0-9\s\-/]+?)\s*\((.*?)\).*?LOTTO\s*N?\.?\s*([A-Z0-9\s\-/\\.]+)', testo, re.IGNORECASE)
    
    prodotti = []
    for m in matches:
        nome_grezzo = m[0].strip()
        scientifico = m[1].strip()
        # Il lotto si ferma se trova "Cas" o "Kg" o numeri decimali (il prezzo)
        lotto_sporco = m[2].strip()
        lotto = re.split(r'\s{2,}|Cas|Kg|\d+,\d+', lotto_sporco)[0].strip()
        
        # Estrazione FAO e Metodo specifica per quel blocco
        # Cerchiamo nel testo vicino al nome scientifico
        fao_match = re.search(r'FAO\s*N?°?\s*([\d\.]+)', testo[testo.find(scientifico):testo.find(scientifico)+200])
        fao = fao_match.group(1) if fao_match else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in testo[testo.find(scientifico)-100:testo.find(scientifico)+100] else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo),
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

# --- UI ---
st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Carica Fattura Hermes", type="pdf")

if file:
    prodotti = estrai_dati(file)
    if prodotti:
        st.success(f"Trovati {len(prodotti)} prodotti!")
        
        # Crea PDF UNICO
        pdf_f = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_f.set_margins(left=4, top=3, right=4)
        pdf_f.set_auto_page_break(auto=False)
        for p in prodotti:
            # Riutilizziamo la logica di disegno
            pdf_f.add_page()
            pdf_f.set_font("helvetica", "B", 8)
            pdf_f.cell(0, 4, "ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
            pdf_f.ln(1)
            pdf_f.set_font("helvetica", "B", 14)
            pdf_f.multi_cell(0, 7, p['nome'], align='C')
            font_sci = 9 if len(p['sci']) < 25 else 7
            pdf_f.set_font("helvetica", "I", font_sci)
            pdf_f.multi_cell(0, 4, f"({p['sci']})", align='C')
            pdf_f.ln(1)
            pdf_f.set_font("helvetica", "", 9)
            pdf_f.cell(0, 5, f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
            pdf_f.set_y(38)
            l_txt = f"LOTTO: {p['lotto']}"
            f_l = 13 if len(l_txt) < 18 else 10
            pdf_f.set_font("helvetica", "B", f_l)
            pdf_f.set_x(15)
            pdf_f.cell(70, 11, l_txt, border=1, align='C')
            pdf_f.set_y(54)
            pdf_f.set_font("helvetica", "", 7)
            pdf_f.cell(0, 4, "Confezionato il: 07/02/2026", align='R')
            
        st.download_button("🖨️ STAMPA TUTTO (PDF UNICO)", data=bytes(pdf_f.output()), file_name="Etichette_Hermes_OK.pdf")
        
        for i, p in enumerate(prodotti):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                st.write(f"Scientifico: {p['sci']}")
                st.download_button("Scarica Singola", data=crea_pdf_blindato(p), file_name=f"Etichetta_{i}.pdf", key=f"s_{i}")