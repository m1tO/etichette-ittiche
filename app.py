import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_definitivo(testo):
    """Isola il nome del pesce eliminando codici iniziali e scarti tecnici."""
    if not testo: return "DA COMPILARE"
    testo = testo.upper().strip()
    
    # 1. Elimina indirizzi che restano incastrati nelle tabelle Hermes
    testo = re.sub(r'\d{5}\s+PALERMO.*', '', testo)
    
    # 2. Rimuove codici numerici iniziali (es. 0258 o 46668255)
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    
    # 3. Taglia a numeri di pezzatura (es. 300-400) o zone FAO
    testo = re.split(r'\s\d+', testo)[0]
    
    # 4. Elimina sigle tecniche che sporcano il nome
    stop = ["AI", "PN", "ΑΙ", "FRESCO", "CONGELATO", "ZONA", "FAO", "PRODOTTO", "UM"]
    for s in stop:
        if s in testo: testo = testo.split(s)[0]
    
    res = testo.strip().strip('-').strip(',').strip('.')
    return res if len(res) > 2 else "DA COMPILARE"

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta Brother 62x100mm in una sola pagina garantita."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale
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
    pdf.set_x((100 - 80) / 2) 
    pdf.cell(w=80, h=11, text=l_txt, border=1, align='C')
    
    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

def estrai_dati_sicuri(file):
    reader = PdfReader(file)
    testo = "\n".join([p.extract_text() for p in reader.pages]).upper()
    testo = testo.replace('ΑΙ', ' AI ') # Fix carattere greco Hermes
    
    # Dividiamo per LOTTO per isolare i prodotti
    blocchi = re.split(r'LOTTO\s*N?\.?\s*', testo)
    risultati = []
    
    for i in range(len(blocchi) - 1):
        pre = blocchi[i]
        post = blocchi[i+1]
        
        # 1. Scientifico (l'ultimo tra parentesi prima del lotto)
        sci_matches = re.findall(r'\(([^)]+)\)', pre)
        if not sci_matches: continue
        sci = sci_matches[-1].strip()
        if any(x in sci for x in ["IVA", "KG", "EURO", "PA"]): continue
        
        # 2. Nome (Prendiamo solo quello che c'è PRIMA dello scientifico)
        parti_pre = pre.split(f"({sci})")
        testo_nome = parti_pre[0].strip().split('\n')[-1]
        
        # Se è un codice numerico, cerchiamo nella riga sopra
        if (re.fullmatch(r'\d+', testo_nome) or len(testo_nome) < 3) and len(parti_pre[0].strip().split('\n')) > 1:
            testo_nome = parti_pre[0].strip().split('\n')[-2]
            
        # 3. Lotto (si ferma al prezzo o unità di misura)
        lotto_raw = post.split('\n')[0].strip()
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw)[0].strip()
        
        # 4. FAO e Metodo
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', pre + post)
        metodo = "ALLEVATO" if any(x in pre for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"
        
        risultati.append({
            "nome": pulisci_nome_definitivo(testo_nome),
            "sci": sci,
            "lotto": lotto,
            "fao": fao_m.group(1) if fao_m else "37.2.1",
            "metodo": metodo
        })
    return risultati

# --- UI STREAMLIT ---
st.title("⚓ FishLabel Scanner PRO")

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    # RESET AUTOMATICO: se il file è nuovo, svuota la lista vecchia
    if "current_file" not in st.session_state or st.session_state.current_file != file.name:
        st.session_state.prodotti_list = estrai_dati_sicuri(file)
        st.session_state.current_file = file.name
        st.toast(f"Nuova fattura rilevata: {file.name}")

    if st.session_state.prodotti_list:
        st.success(f"✅ Trovati {len(st.session_state.prodotti_list)} prodotti.")
        
        # TASTONE STAMPA TUTTO
        pdf_m = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_m.set_margins(4, 3, 4)
        pdf_m.set_auto_page_break(False)
        for p in st.session_state.prodotti_list: disegna_etichetta(pdf_m, p)
        
        # bytes() cast obbligatorio per evitare crash "bytearray"
        st.download_button("🖨️ SCARICA TUTTE LE ETICHETTE (PDF UNICO)", bytes(pdf_m.output()), "Rullino_Completo.pdf", type="primary")

        st.markdown("---")
        for i, p in enumerate(st.session_state.prodotti_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                col1, col2 = st.columns(2)
                p['nome'] = col1.text_input("Modifica Nome", p['nome'], key=f"n_{i}")
                p['lotto'] = col2.text_input("Modifica Lotto", p['lotto'], key=f"l_{i}")
                
                pdf_s = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_s.set_margins(4, 3, 4)
                pdf_s.set_auto_page_break(False)
                disegna_etichetta(pdf_s, p)
                st.download_button("Scarica PDF Singolo", bytes(pdf_s.output()), f"Etic_{i}.pdf", key=f"b_{i}")