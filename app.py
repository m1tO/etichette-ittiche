import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Elimina codici, indirizzi e termini fiscali dal nome del pesce."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    # 1. Rimuove codici numerici isolati o iniziali
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    # 2. Taglia appena vede la pezzatura (es. 300-400) o la zona FAO
    testo = re.split(r'\s\d+', testo)[0]
    # 3. Lista nera (evitiamo che '00' o 'IMPONIBILE' diventino nomi)
    stop_words = ["IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ΑΙ", "ZONA", "FAO", "PRODOTTO"]
    for word in stop_words:
        if word in testo: testo = testo.split(word)[0]
    
    testo = testo.strip().strip('-').strip(',').strip()
    # Se il risultato è solo numeri o troppo corto, resettiamo a PESCE
    if re.fullmatch(r'\d+', testo) or len(testo) < 2:
        return "PESCE"
    return testo

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta 62x100mm ottimizzata per Brother."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale
    pdf.set_font("helvetica", "B", 14)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'], align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Nome Scientifico
    pdf.ln(1)
    f_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", f_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Tracciabilità
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Box Lotto
    pdf.set_y(38)
    l_text = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_text) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    pdf.set_x(12.5) 
    pdf.cell(w=75, h=11, text=l_text, border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

def estrai_dati(file):
    reader = PdfReader(file)
    testo_completo = ""
    for page in reader.pages:
        testo_completo += page.extract_text() + "\n"
    
    if "Descrizione" in testo_completo:
        testo_completo = testo_completo.split("Descrizione", 1)[1]
    
    testo_completo = testo_completo.replace('\n', ' ')
    pattern = r'([A-Z0-9\s\-/]{3,})?\(+(.*?)\)+.*?LOTTO\s*N?\.?\s*([A-Z0-9\s\-/\\.]+)'
    matches = re.findall(pattern, testo_completo, re.IGNORECASE)
    
    prodotti = []
    for m in matches:
        nome_grezzo = m[0].strip() if m[0] else "PESCE"
        # Se il nome estratto sembra un codice (solo numeri), cerchiamo meglio
        scientifico = m[1].strip()
        lotto_raw = m[2].strip()
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw, flags=re.IGNORECASE)[0].strip()
        
        start_idx = testo_completo.find(scientifico)
        context = testo_completo[max(0, start_idx-100):start_idx+250]
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', context)
        metodo = "ALLEVATO" if "ALLEVATO" in context or "ACQUACOLTURA" in context else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo),
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao_m.group(1) if fao_m else "37.2.1",
            "metodo": metodo
        })
    return prodotti

# --- INTERFACCIA ---
st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if 'prodotti_list' not in st.session_state:
        st.session_state.prodotti_list = estrai_dati(file)
    
    if st.session_state.prodotti_list:
        st.info("💡 Puoi modificare i nomi o i lotti cliccando nei box qui sotto prima di stampare.")
        
        for i, p in enumerate(st.session_state.prodotti_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                col1, col2 = st.columns(2)
                # MODIFICA MANUALE: L'utente può correggere se l'app sbaglia
                p['nome'] = col1.text_input("Nome Pesce", p['nome'], key=f"n_{i}")
                p['lotto'] = col2.text_input("Codice Lotto", p['lotto'], key=f"l_{i}")
                
                pdf_s = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_s.set_margins(left=4, top=3, right=4)
                pdf_s.set_auto_page_break(auto=False)
                disegna_etichetta(pdf_s, p)
                # FIX BINARY DATA: forziamo il cast a bytes()
                st.download_button("Scarica Etichetta", bytes(pdf_s.output()), f"Etic_ {i}.pdf", key=f"b_{i}")

        st.markdown("---")
        # PDF MASSIVO
        pdf_m = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_m.set_margins(left=4, top=3, right=4)
        pdf_m.set_auto_page_break(auto=False)
        for p in st.session_state.prodotti_list: disegna_etichetta(pdf_m, p)
        st.download_button("🖨️ STAMPA TUTTO IL RULLINO", bytes(pdf_m.output()), "Rullino_Completo.pdf", type="primary")