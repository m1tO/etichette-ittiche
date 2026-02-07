import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Pulisce il nome eliminando codici articolo e sporcizia tecnica."""
    if not testo: return "PESCE"
    # Rimuove codici numerici all'inizio (es. 0258 o 46668255) 
    testo = re.sub(r'^\d{4,10}\s+', '', testo)
    testo = re.sub(r'^\d+\s+', '', testo)
    
    testo = testo.upper().strip()
    # Taglia appena vede numeri di pezzatura o zone FAO (es. 300-400 o 27) 
    testo = re.split(r'\s\d+', testo)[0]
    
    parole_stop = ["PRODOTTO", "PESCA", "PN", "AI", "ZONA", "FAO", "PESCATO", "ALLEVATO"]
    for parola in parole_stop:
        if parola in testo: testo = testo.split(parola)[0]
    
    return testo.strip().strip('-').strip(',').strip()

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta forzando il cursore a sinistra per evitare errori di spazio."""
    pdf.add_page()
    # Margine di sicurezza
    pdf.set_x(pdf.l_margin)
    
    # Intestazione
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale - Usiamo pdf.epw per garantire lo spazio orizzontale
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
    
    # Box Lotto - Posizionamento assoluto ma centrato
    pdf.set_y(38)
    l_text = f"LOTTO: {p['lotto']}"
    f_size = 13 if len(l_text) < 18 else 10
    pdf.set_font("helvetica", "B", f_size)
    
    # Centriamo il box calcolando lo spazio
    box_w = 70
    pdf.set_x((100 - box_w) / 2) 
    pdf.cell(w=box_w, h=11, text=l_text, border=1, align='C')
    
    # Data Confezionamento
    pdf.set_y(54)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text="Confezionato il: 07/02/2026", align='R')

def estrai_dati(file):
    reader = PdfReader(file)
    testo_completo = ""
    for page in reader.pages:
        testo_completo += page.extract_text() + "\n"
    
    # Taglia l'intestazione Hermes Fish 
    if "Descrizione" in testo_completo:
        testo_completo = testo_completo.split("Descrizione", 1)[1]
    
    # Pulizia caratteri sporchi comuni nelle fatture Hermes 
    testo_completo = testo_completo.replace('ΑΙ', ' AI ').replace('\n', ' ')
    
    # Regex per catturare blocco Nome, Scientifico e Lotto 
    pattern = r'([A-Z0-9\s\-/]+?)\s*\((.*?)\).*?LOTTO\s*N?\.?\s*([A-Z0-9\s\-/\\.]+)'
    matches = re.findall(pattern, testo_completo, re.IGNORECASE)
    
    prodotti = []
    for m in matches:
        nome_grezzo = m[0].strip()
        scientifico = m[1].strip()
        lotto_raw = m[2].strip()
        # Il lotto si ferma prima dei prezzi (numeri con virgola) o codici UM 
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw, flags=re.IGNORECASE)[0].strip()
        
        # Cerca FAO e Metodo nel raggio del prodotto
        context = testo_completo[testo_completo.find(scientifico):testo_completo.find(scientifico)+250]
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

# --- INTERFACCIA STREAMLIT ---
st.title("⚓ FishLabel Scanner PRO")
st.write("Versione consolidata per stampe massive senza crash.")

file = st.file_uploader("Carica Fattura PDF (Hermes, Catanzaro, ecc.)", type="pdf")

if file:
    prodotti = estrai_dati(file)
    if prodotti:
        st.success(f"✅ Trovati {len(prodotti)} prodotti pronti per la stampa!")
        
        # Generazione PDF MASSIVO
        pdf_massivo = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_massivo.set_margins(left=4, top=3, right=4)
        pdf_massivo.set_auto_page_break(auto=False)
        
        for p in prodotti:
            disegna_etichetta(pdf_massivo, p)
            
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