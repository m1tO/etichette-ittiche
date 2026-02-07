import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

# --- FUNZIONE DI PULIZIA NOME ---
def pulisci_nome_chirurgico(testo):
    if not testo: return ""
    testo = testo.upper().strip()
    # 1. Elimina codici articolo all'inizio (es. 0258 o 46668255)
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    # 2. Taglia alle pezzature (es. 300-400 o 6/7)
    testo = re.split(r'\d+[\-/]\d+', testo)[0]
    # 3. Taglia a zone FAO o termini tecnici
    stop = ["AI", "FA0", "FAO", "ZONA", "PRODOTTO", "PESCA", "PN", "ΑΙ", "DESCRIZIONE", "FRESCO"]
    for s in stop:
        if s in testo: testo = testo.split(s)[0]
    return testo.strip().strip('-').strip(',').strip('.')

# --- DISEGNO ETICHETTA ---
def disegna_etichetta(pdf, p):
    pdf.add_page()
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'], align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    f_sci = 9 if len(p['sci']) < 25 else 7
    pdf.set_font("helvetica", "I", f_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(38)
    l_txt = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_txt) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    pdf.set_x(10) 
    pdf.cell(w=80, h=11, text=l_txt, border=1, align='C')
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

# --- ESTRAZIONE DATI ---
def estrai_tutto(file):
    reader = PdfReader(file)
    # Rendiamo tutto il testo una riga sola per non perdere i dati tra i "vado a capo"
    testo = " ".join([p.extract_text() for p in reader.pages]).upper()
    testo = testo.replace('ΑΙ', ' AI ').replace('FA0', ' FAO ')
    
    # Dividiamo per la parola LOTTO
    blocchi = re.split(r'LOTTO\s*N?\.?\s*', testo)
    risultati = []
    
    for i in range(len(blocchi) - 1):
        testo_prima = blocchi[i]
        testo_dopo = blocchi[i+1]
        
        # 1. Scientifico (l'ultima cosa tra parentesi prima di LOTTO)
        sci_match = re.findall(r'\(([^)]+)\)', testo_prima)
        if not sci_match: continue
        scientifico = sci_match[-1].strip()
        if any(x in scientifico for x in ["IVA", "KG", "EURO", "DESCRIZIONE"]): continue
        
        # 2. Nome (testo tra la fine del prodotto precedente e le parentesi)
        nome_sporco = testo_prima.split(f"({scientifico})")[0].strip()
        # Prende l'ultima riga/pezzo significativo
        nome_grezzo = nome_sporco.split('   ')[-1].split('\n')[-1].strip()
        
        # 3. Lotto (valore subito dopo la parola LOTTO)
        lotto_raw = testo_dopo.split(' ')[0].strip()
        # Pulisce se il prezzo è attaccato (es. 932350 -> 9323)
        lotto = re.split(r'CAS|KG|UM|\d+,\d+', lotto_raw)[0].strip()
        
        # 4. FAO e Metodo
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', testo_prima + testo_dopo)
        metodo = "ALLEVATO" if "ALLEVATO" in testo_prima or "ACQUACOLTURA" in testo_prima else "PESCATO"
        
        risultati.append({
            "nome": pulisci_nome_chirurgico(nome_grezzo) or "DA COMPILARE",
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao_m.group(1) if fao_m else "37.2.1",
            "metodo": metodo
        })
    return risultati

# --- INTERFACCIA ---
st.title("⚓ FishLabel Scanner PRO")

# Tasto per svuotare la memoria se si incanta
if st.sidebar.button("🗑️ SVUOTA TUTTA LA MEMORIA"):
    st.session_state.clear()
    st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    # Reset automatico se cambi file
    if "last_file" not in st.session_state or st.session_state.last_file != file.name:
        st.session_state.prodotti_list = estrai_tutto(file)
        st.session_state.last_file = file.name

    if st.session_state.prodotti_list:
        st.success(f"✅ Trovati {len(st.session_state.prodotti_list)} prodotti.")
        
        # TASTO STAMPA TOTALE
        pdf_m = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_m.set_margins(4, 3, 4)
        pdf_m.set_auto_page_break(False)
        for p in st.session_state.prodotti_list: disegna_etichetta(pdf_m, p)
        st.download_button("🖨️ SCARICA TUTTE LE ETICHETTE (PDF)", bytes(pdf_m.output()), "Rullino.pdf", type="primary")

        for i, p in enumerate(st.session_state.prodotti_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                c1, c2 = st.columns(2)
                p['nome'] = c1.text_input("Nome", p['nome'], key=f"n_{i}")
                p['lotto'] = c2.text_input("Lotto", p['lotto'], key=f"l_{i}")
                pdf_s = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_s.set_margins(4, 3, 4)
                pdf_s.set_auto_page_break(False)
                disegna_etichetta(pdf_s, p)
                st.download_button("Scarica", bytes(pdf_s.output()), f"E_{i}.pdf", key=f"b_{i}")