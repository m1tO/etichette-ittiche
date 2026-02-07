import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Elimina codici articolo, indirizzi e termini fiscali dal nome del pesce."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    
    # 1. Rimuove codici numerici iniziali lunghi (es. 46668255 o 0258)
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    
    # 2. Taglia appena vede la pezzatura (es. 300-400) o la zona FAO
    testo = re.split(r'\s\d+', testo)[0]
    
    # 3. Lista nera di parole che NON sono pesci
    stop_words = [
        "IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ΑΙ", 
        "ZONA", "FAO", "PESCATO", "ALLEVATO", "ATTREZZI", "PRODOTTO"
    ]
    for word in stop_words:
        if word in testo: testo = testo.split(word)[0]
    
    return testo.strip().strip('-').strip(',').strip()

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta Brother 62x100mm in una sola pagina garantita."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    
    # Intestazione Negozio
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale (Font grande e centrato)
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'], align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Nome Scientifico (Rimpicciolisce se troppo lungo)
    pdf.ln(1)
    font_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", font_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Tracciabilità
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Box Lotto (Font dinamico per lotti complessi)
    pdf.set_y(38)
    l_text = f"LOTTO: {p['lotto']}"
    f_size = 12 if len(l_text) < 20 else 10
    pdf.set_font("helvetica", "B", f_size)
    
    box_w = 75
    pdf.set_x((100 - box_w) / 2) 
    pdf.cell(w=box_w, h=11, text=l_text, border=1, align='C')
    
    # Data Confezionamento
    pdf.set_y(54)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "", 7)
    oggi = datetime.now().strftime("%d/%m/%Y")
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {oggi}", align='R')

def estrai_dati(file):
    reader = PdfReader(file)
    testo_completo = ""
    for page in reader.pages:
        testo_completo += page.extract_text() + "\n"
    
    # Salta l'intestazione della fattura Hermes
    if "Descrizione" in testo_completo:
        testo_completo = testo_completo.split("Descrizione", 1)[1]
    
    testo_completo = testo_completo.replace('\n', ' ')
    
    # Regex per catturare (Nome) (Scientifico) e (Lotto)
    pattern = r'([A-Z0-9\s\-/]{3,})?\(+(.*?)\)+.*?LOTTO\s*N?\.?\s*([A-Z0-9\s\-/\\.]+)'
    matches = re.findall(pattern, testo_completo, re.IGNORECASE)
    
    prodotti = []
    for m in matches:
        nome_grezzo = m[0].strip() if m[0] else "PESCE"
        scientifico = m[1].strip()
        lotto_raw = m[2].strip()
        
        # Pulisce il lotto dai prezzi finali (es. taglia il '30' finale di Hermes)
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw, flags=re.IGNORECASE)[0].strip()
        
        # Cerca FAO e Metodo vicino al prodotto
        start_idx = testo_completo.find(scientifico)
        context = testo_completo[max(0, start_idx-50):start_idx+250]
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
st.write("Stampa il rullino Hermes Fish in un colpo solo.")

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    prodotti = estrai_dati(file)
    if prodotti:
        st.success(f"✅ Trovati {len(prodotti)} prodotti!")
        
        # PDF MASSIVO (Tutte le etichette insieme)
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