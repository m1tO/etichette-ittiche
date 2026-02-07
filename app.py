import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo):
    """Elimina solo i codici e le pezzature, lasciando il nome del pesce."""
    if not testo or len(testo) < 2: return "PESCE"
    testo = testo.upper().strip()
    
    # 1. Rimuove codici numerici (es. 0258 o 46668255) all'inizio della riga
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    
    # 2. Taglia se trova pezzature tipo 300-400 o 100/200
    testo = re.split(r'\d+[\-/]\d+', testo)[0]
    
    # 3. Lista nera: termini che NON devono stare nel nome commerciale
    stop_words = ["IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ΑΙ", "ZONA", "FAO", "PRODOTTO", "FRESCO"]
    for word in stop_words:
        if word in testo: testo = testo.split(word)[0]
    
    # Pulizia finale da simboli residui
    testo = testo.strip().strip('-').strip(',').strip('.')
    
    return testo if len(testo) > 2 else "PESCE"

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta Brother 62x100mm in una sola pagina."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale (multi_cell evita che il testo esca dai bordi)
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

def estrai_dati_hermes(file):
    reader = PdfReader(file)
    testo_pagine = [page.extract_text() for page in reader.pages]
    testo_completo = "\n".join(testo_pagine).upper()
    
    # Ignora l'intestazione della fattura
    if "DESCRIZIONE" in testo_completo:
        testo_completo = testo_completo.split("DESCRIZIONE", 1)[1]
    
    # Cerchiamo tutti i nomi scientifici tra parentesi
    sci_names = re.findall(r'\(([^)]+)\)', testo_completo)
    prodotti = []
    
    for sci in sci_names:
        if len(sci) < 5 or any(x in sci for x in ["IVA", "EURO", "KG", "PA"]): continue
        
        # Cerchiamo il nome commerciale SUBITO PRIMA del nome scientifico
        # Prendiamo i 50 caratteri precedenti
        pattern_nome = re.escape(f"({sci})")
        match_pos = re.search(pattern_nome, testo_completo)
        if not match_pos: continue
        
        testo_precedente = testo_completo[max(0, match_pos.start()-60):match_pos.start()]
        # Il nome è solitamente l'ultima riga o l'ultimo pezzo di testo
        nome_grezzo = testo_precedente.strip().split('\n')[-1]
        
        # Cerchiamo il lotto SUBITO DOPO
        testo_successivo = testo_completo[match_pos.end():match_pos.end()+300]
        lotto_match = re.search(r'LOTTO\s*N?\.?\s*([A-Z0-9\s\-/\\.]+)', testo_successivo)
        lotto_raw = lotto_match.group(1).strip() if lotto_match else "N.D."
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw)[0].strip()
        
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', testo_successivo)
        metodo = "ALLEVATO" if "ALLEVATO" in testo_successivo or "ACQUACOLTURA" in testo_successivo else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo),
            "sci": sci,
            "lotto": lotto,
            "fao": fao_m.group(1) if fao_m else "37.2.1",
            "metodo": metodo
        })
    return prodotti

# --- UI STREAMLIT ---
st.title("⚓ FishLabel Scanner PRO")

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    # Usiamo la cache per non perdere le modifiche manuali al ricaricamento
    if 'prodotti_list' not in st.session_state:
        st.session_state.prodotti_list = estrai_dati_hermes(file)
    
    if st.session_state.prodotti_list:
        st.success(f"✅ Trovati {len(st.session_state.prodotti_list)} prodotti!")
        
        for i, p in enumerate(st.session_state.prodotti_list):
            with st.expander(f"📦 {p['nome']} - Lotto: {p['lotto']}"):
                col1, col2 = st.columns(2)
                p['nome'] = col1.text_input("Nome Prodotto", p['nome'], key=f"n_{i}")
                p['lotto'] = col2.text_input("Lotto", p['lotto'], key=f"l_{i}")
                
                pdf_s = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_s.set_margins(left=4, top=3, right=4)
                pdf_s.set_auto_page_break(auto=False)
                disegna_etichetta(pdf_s, p)
                # FIX BINARY DATA: cast a bytes() per evitare errori di formato
                st.download_button("Scarica Etichetta", bytes(pdf_s.output()), f"Etichetta_{i}.pdf", key=f"b_{i}")

        st.markdown("---")
        pdf_m = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_m.set_margins(left=4, top=3, right=4)
        pdf_m.set_auto_page_break(auto=False)
        for p in st.session_state.prodotti_list: disegna_etichetta(pdf_m, p)
        st.download_button("🖨️ SCARICA TUTTO IL RULLINO", bytes(pdf_m.output()), "Rullino_Completo.pdf", type="primary")