import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_veramente(testo):
    """Pulisce il nome senza cancellare l'identità del pesce."""
    if not testo: return ""
    testo = testo.upper().strip()
    
    # 1. Elimina indirizzi e codici fiscali (capita nelle tabelle Hermes)
    testo = re.sub(r'\d{5}\s+PALERMO.*', '', testo)
    testo = re.sub(r'P\.IVA.*|C\.F\..*', '', testo)
    
    # 2. Rimuove codici numerici iniziali (es. 46668255 o 0258)
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    
    # 3. Taglia alla prima pezzatura o zona FAO (es. 300-400 o 27)
    testo = re.split(r'\s\d+', testo)[0]
    
    # 4. Parole stop specifiche che sporcano l'interfaccia
    stop = ["IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ΑΙ", "ZONA", "FAO", "PRODOTTO", "UM", "Q.TÀ"]
    for s in stop:
        if s in testo: testo = testo.split(s)[0]
    
    res = testo.strip().strip('-').strip(',').strip('.')
    return res if len(res) > 2 else ""

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta 62x100mm per Brother."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Pesce
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'], align='C', new_x="LMARGIN", new_y="NEXT")
    
    # Scientifico
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
    l_txt = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_txt) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    pdf.set_x((100 - 75) / 2) 
    pdf.cell(w=75, h=11, text=l_txt, border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

def estrai_dati_hermes(file):
    reader = PdfReader(file)
    testo = "\n".join([p.extract_text() for p in reader.pages]).upper()
    testo = testo.replace('ΑΙ', ' AI ') # Fix caratteri greci Hermes 
    
    # Dividiamo per LOTTO
    blocchi = re.split(r'LOTTO\s*N?\.?\s*', testo)
    risultati = []
    
    for i in range(len(blocchi) - 1):
        pre = blocchi[i]
        post = blocchi[i+1]
        
        # 1. Trova lo scientifico (l'ultimo tra parentesi prima del lotto)
        sci_matches = re.findall(r'\(([^)]+)\)', pre)
        if not sci_matches: continue
        sci = sci_matches[-1].strip()
        if any(x in sci for x in ["IVA", "KG", "EURO", "PA"]): continue
        
        # 2. Trova il nome (riga sopra lo scientifico)
        parti = pre.split(f"({sci})")[0].strip().split('\n')
        nome_grezzo = parti[-1].strip()
        # Se è un codice, prendi la riga sopra
        if (re.fullmatch(r'\d+', nome_grezzo) or len(nome_grezzo) < 3) and len(parti) > 1:
            nome_grezzo = parti[-2].strip()
            
        # 3. Lotto (prima riga dopo la parola LOTTO)
        lotto_raw = post.split('\n')[0].strip()
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw)[0].strip()
        
        # 4. FAO e Metodo
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', pre + post)
        metodo = "ALLEVATO" if any(x in pre for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"
        
        nome_pulito = pulisci_nome_serio(nome_grezzo)
        
        risultati.append({
            "nome": nome_pulito if nome_pulito else "DA COMPILARE",
            "sci": sci,
            "lotto": lotto,
            "fao": fao_m.group(1) if fao_m else "37.2.1",
            "metodo": metodo
        })
    return risultati

# --- LOGICA STREAMLIT ---
st.title("⚓ FishLabel Scanner PRO")

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    # RESET SESSIONE: Se il nome del file cambia, svuota la memoria
    if "last_uploaded_file" not in st.session_state or st.session_state.last_uploaded_file != file.name:
        st.session_state.prodotti_list = estrai_dati_hermes(file)
        st.session_state.last_uploaded_file = file.name
        st.toast(f"Nuova fattura caricata: {file.name}")

    if st.session_state.prodotti_list:
        st.success(f"✅ Trovati {len(st.session_state.prodotti_list)} prodotti.")
        
        # PDF MASSIVO
        pdf_m = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_m.set_margins(4, 3, 4)
        pdf_m.set_auto_page_break(False)
        for p in st.session_state.prodotti_list: disegna_etichetta(pdf_m, p)
        st.download_button("🖨️ SCARICA TUTTE LE ETICHETTE", bytes(pdf_m.output()), "Rullino.pdf", type="primary")

        st.markdown("---")
        for i, p in enumerate(st.session_state.prodotti_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                c1, c2 = st.columns(2)
                p['nome'] = c1.text_input("Nome Pesce", p['nome'], key=f"n_{i}")
                p['lotto'] = c2.text_input("Lotto", p['lotto'], key=f"l_{i}")
                
                pdf_s = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_s.set_margins(4, 3, 4)
                pdf_s.set_auto_page_break(False)
                disegna_etichetta(pdf_s, p)
                st.download_button("Scarica PDF", bytes(pdf_s.output()), f"E_{i}.pdf", key=f"b_{i}")