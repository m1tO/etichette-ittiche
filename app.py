import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Pulisce il nome del pesce eliminando codici articolo, indirizzi e dati fiscali."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    
    # 1. Rimuove codici numerici all'inizio (es. 0258 o 46668255)
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    
    # 2. Taglia ai numeri di pezzatura o zone FAO
    testo = re.split(r'\s\d+', testo)[0]
    
    # 3. Parole stop (incluse quelle fiscali trovate nei tuoi screenshot)
    parole_stop = [
        "IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ZONA", 
        "FAO", "PESCATO", "ALLEVATO", "ATTREZZI", "PRODOTTO"
    ]
    for parola in parole_stop:
        if parola in testo: testo = testo.split(parola)[0]
    
    return testo.strip().strip('-').strip(',').strip()

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta forzando il cursore a sinistra per evitare errori di spazio."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'], align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Nome Scientifico
    pdf.ln(1)
    font_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", font_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Tracciabilità
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Box Lotto
    pdf.set_y(38)
    l_text = f"LOTTO: {p['lotto']}"
    f_size = 12 if len(l_text) < 20 else 10 # Font dinamico per evitare overflow
    pdf.set_font("helvetica", "B", f_size)
    
    box_w = 75
    pdf.set_x((100 - box_w) / 2) 
    pdf.cell(w=box_w, h=11, text=l_text, border=1, align='C')
    
    # Data Confezionamento (Oggi)
    pdf.set_y(54)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "", 7)
    oggi = datetime.now().strftime("%d/%m/%Y")
    pdf.cell(w=pdf.epw, h=4, text=f"Confezionato il: {oggi}", align='R')

def estrai_dati(file):
    reader = PdfReader(file)
    testo_completo = ""
    for page in reader.pages:
        testo_completo += page.extract_text() + "\n"
    
    # Filtriamo l'intestazione fino alla tabella prodotti
    if "Descrizione" in testo_completo:
        testo_completo = testo_completo.split("Descrizione", 1)[1]
    
    testo_completo = testo_completo.replace('\n', ' ')
    
    # Regex migliorata per catturare Nome, Scientifico e Lotto
    # Accetta anche caratteri sporchi come ΑΙ o spazi nel lotto
    pattern = r'([A-Z0-9\s\-/]{3,})?\(+(.*?)\)+.*?LOTTO\s*N?\.?\s*([A-Z0-9\s\-/\\.]+)'
    matches = re.findall(pattern, testo_completo, re.IGNORECASE)
    
    prodotti = []
    for m in matches:
        nome_grezzo = m[0].strip() if m[0] else "PESCE"
        scientifico = m[1].strip()
        lotto_raw = m[2].strip()
        
        # Pulizia Lotto: si ferma ai prezzi (numeri con virgola) o codici UM
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw, flags=re.IGNORECASE)[0].strip()
        
        # FAO e Metodo nel raggio del prodotto
        start_idx = testo_completo.find(scientifico)
        context = testo_completo[start_idx-50:start_idx+250]
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', context)
        fao = fao_m.group(1) if fao_m else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in context or "ACQUACOLTURA" in context else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo),
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

# --- INTERFACCIA ---
st.title("⚓ FishLabel Scanner PRO")
st.write("Stampa tutto il rullino Hermes Fish in un colpo solo.")

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    prodotti = estrai_dati(file)
    if prodotti:
        st.success(f"✅ Trovati {len(prodotti)} prodotti pronti!")
        
        # PDF MASSIVO
        pdf_massivo = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_massivo.set_margins(left=4, top=3, right=4)
        pdf_massivo.set_auto_page_break(auto=False)
        for p in prodotti: disegna_etichetta(pdf_massivo, p)
            
        st.download_button(
            label="🖨️ SCARICA TUTTE LE ETICHETTE (PDF UNICO)",
            data=bytes(pdf_massivo.output()),
            file_name="Stampa_Massiva_Ittica.pdf",
            mime="application/pdf",
            type="primary"
        )
        
        st.markdown("---")
        for i, p in enumerate(prodotti):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                pdf_singolo = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_singolo.set_margins(left=4, top=3, right=4)
                pdf_singolo.set_auto_page_break(auto=False)
                disegna_etichetta(pdf_singolo, p)
                st.download_button(
                    label=f"Scarica singola {p['nome']}",
                    data=bytes(pdf_singolo.output()),
                    file_name=f"Etichetta_{i}.pdf",
                    key=f"btn_{i}"
                )