import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_serio(testo):
    """Pulisce il nome senza cancellarlo del tutto."""
    if not testo: return ""
    testo = testo.upper().strip()
    
    # 1. Elimina indirizzi di Palermo che restano incastrati
    testo = re.sub(r'\d{5}\s+PALERMO.*', '', testo)
    
    # 2. Rimuove codici numerici iniziali lunghi (es. 46668255 o 0258)
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    
    # 3. Taglia alla prima pezzatura o zona FAO (es. 300-400 o 27)
    testo = re.split(r'\s\d+', testo)[0]
    
    # 4. Parole vietate che non sono pesci
    stop = ["IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ΑΙ", "ZONA", "FAO", "PRODOTTO"]
    for s in stop:
        if s in testo: testo = testo.split(s)[0]
    
    return testo.strip().strip('-').strip(',').strip('.')

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta 62x100mm in una sola pagina."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Pesce (multi_cell evita che il testo esca dai bordi)
    pdf.set_font("helvetica", "B", 15)
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
    l_txt = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_txt) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    pdf.set_x((100 - 75) / 2) 
    pdf.cell(w=75, h=11, text=l_txt, border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

def estrai_dati_migliorato(file):
    reader = PdfReader(file)
    testo_completo = ""
    for page in reader.pages:
        testo_completo += page.extract_text() + "\n"
    
    # Pulizia preliminare per Hermes
    testo_completo = testo_completo.replace('ΑΙ', ' AI ')
    
    # Troviamo tutti i nomi scientifici tra parentesi
    blocchi = re.split(r'LOTTO\s*N?\.?\s*', testo_completo.upper())
    prodotti = []
    
    for i in range(len(blocchi) - 1):
        pre = blocchi[i]
        post = blocchi[i+1]
        
        # 1. Scientifico (l'ultimo nel blocco precedente)
        sci_match = re.findall(r'\(([^)]+)\)', pre)
        if not sci_match: continue
        sci = sci_match[-1].strip()
        if any(x in sci for x in ["IVA", "KG", "EURO", "DESCRIZIONE", "PA"]): continue
        
        # 2. Nome Commerciale (cerca nel testo precedente lo scientifico)
        pre_sci = pre.split(f"({sci})")[0].strip()
        linee = pre_sci.split('\n')
        nome_raw = linee[-1].strip()
        # Se la riga è solo un codice, prendiamo quella sopra
        if re.fullmatch(r'\d+', nome_raw) and len(linee) > 1:
            nome_raw = linee[-2].strip()
        
        # 3. Lotto
        lotto_raw = post.split('\n')[0].strip()
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw)[0].strip()
        
        # 4. FAO e Metodo
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', pre + post)
        metodo = "ALLEVATO" if "ALLEVATO" in pre or "ACQUACOLTURA" in pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_serio(nome_raw) or "PESCE",
            "sci": sci,
            "lotto": lotto,
            "fao": fao_m.group(1) if fao_m else "37.2.1",
            "metodo": metodo
        })
    return prodotti

# --- INTERFACCIA ---
st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    # Salviamo i prodotti in session_state per permettere la modifica manuale
    if 'lista_prodotti' not in st.session_state:
        st.session_state.lista_prodotti = estrai_dati_migliorato(file)
    
    if st.session_state.lista_prodotti:
        st.success(f"✅ Trovati {len(st.session_state.lista_prodotti)} prodotti!")
        
        # TASTONE STAMPA TUTTO
        pdf_m = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_m.set_margins(4, 3, 4)
        pdf_m.set_auto_page_break(False)
        for p in st.session_state.lista_prodotti: disegna_etichetta(pdf_m, p)
        st.download_button("🖨️ SCARICA TUTTE LE ETICHETTE", bytes(pdf_m.output()), "Rullino_Completo.pdf", type="primary")

        st.markdown("---")
        # BOX MODIFICA E DOWNLOAD SINGOLO
        for i, p in enumerate(st.session_state.lista_prodotti):
            with st.expander(f"📦 {p['nome']} - Lotto: {p['lotto']}"):
                col1, col2 = st.columns(2)
                p['nome'] = col1.text_input("Nome Pesce", p['nome'], key=f"n_{i}")
                p['lotto'] = col2.text_input("Lotto", p['lotto'], key=f"l_{i}")
                
                pdf_s = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_s.set_margins(4, 3, 4)
                pdf_s.set_auto_page_break(False)
                disegna_etichetta(pdf_s, p)
                st.download_button("Scarica Singola", bytes(pdf_s.output()), f"Etic_{i}.pdf", key=f"b_{i}")