import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_serio(testo):
    """Pulisce il nome eliminando codici, indirizzi e scarti della tabella."""
    if not testo: return "PESCE"
    testo = testo.upper().strip()
    
    # 1. Elimina indirizzi di Palermo che restano incastrati
    testo = re.sub(r'\d{5}\s+PALERMO.*', '', testo)
    # 2. Elimina codici articolo all'inizio (es. 0258, 46668255)
    testo = re.sub(r'^\d{3,10}', '', testo).strip()
    # 3. Taglia alla prima pezzatura (es. 300-400)
    testo = re.split(r'\s\d+', testo)[0]
    
    # Parole vietate
    stop = ["IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ΑΙ", "ZONA", "FAO", "PRODOTTO", "FRESCO", "UM", "Q.TÀ"]
    for s in stop:
        if s in testo: testo = testo.split(s)[0]
    
    res = testo.strip().strip('-').strip(',').strip('.')
    return res if len(res) > 2 else "PESCE"

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta senza mai crashare lo spazio orizzontale."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    # Intestazione
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

def estrai_dati_avanzato(file):
    reader = PdfReader(file)
    testo = "\n".join([p.extract_text() for p in reader.pages]).upper()
    
    # Puliamo il testo dai caratteri greci sporchi di Hermes (ΑΙ)
    testo = testo.replace('ΑΙ', ' AI ')
    
    # Dividiamo la fattura in blocchi usando "LOTTO" come separatore
    # Ogni blocco contiene: [Nome Pesce] (Scientifico) ... LOTTO [Valore]
    blocchi = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(blocchi) - 1):
        testo_pre = blocchi[i]   # Contiene Nome e Scientifico
        testo_post = blocchi[i+1] # Contiene il codice Lotto
        
        # 1. Trova il nome scientifico (l'ultimo tra parentesi nel blocco precedente)
        sci_matches = re.findall(r'\((.*?)\)', testo_pre)
        if not sci_matches: continue
        sci = sci_matches[-1].strip()
        if any(x in sci for x in ["IVA", "KG", "EURO", "DESCRIZIONE"]): continue
        
        # 2. Trova il nome commerciale (quello subito prima del nome scientifico)
        parti_nome = testo_pre.split(f"({sci})")[0].strip().split('\n')
        nome_grezzo = parti_nome[-1].strip()
        # Se la riga è solo un numero, prendi quella sopra
        if re.fullmatch(r'\d+', nome_grezzo) and len(parti_nome) > 1:
            nome_grezzo = parti_nome[-2].strip()
            
        # 3. Trova il lotto (all'inizio del blocco successivo)
        lotto_raw = testo_post.split('\n')[0].strip()
        # Taglia il prezzo o codici UM dal lotto
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw)[0].strip()
        
        # 4. FAO e Metodo
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', testo_pre + testo_post)
        metodo = "ALLEVATO" if "ALLEVATO" in testo_pre or "ACQUACOLTURA" in testo_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome_serio(nome_grezzo),
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
    if 'prodotti' not in st.session_state:
        st.session_state.prodotti = estrai_dati_avanzato(file)
    
    if st.session_state.prodotti:
        st.info("📦 Controlla i dati qui sotto. Se qualcosa è sbagliato, correggilo a mano nei box!")
        
        for i, p in enumerate(st.session_state.prodotti):
            with st.expander(f"🐟 {p['nome']} - Lotto: {p['lotto']}"):
                c1, c2 = st.columns(2)
                p['nome'] = c1.text_input("Nome Pesce", p['nome'], key=f"n_{i}")
                p['lotto'] = c2.text_input("Lotto", p['lotto'], key=f"l_{i}")
                
                pdf = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf.set_margins(4, 3, 4)
                pdf.set_auto_page_break(False)
                disegna_etichetta(pdf, p)
                st.download_button("Scarica Singola", bytes(pdf.output()), f"E_{i}.pdf", key=f"b_{i}")

        st.markdown("---")
        pdf_m = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_m.set_margins(4, 3, 4)
        pdf_m.set_auto_page_break(False)
        for p in st.session_state.prodotti: disegna_etichetta(pdf_m, p)
        st.download_button("🖨️ STAMPA TUTTO IL RULLINO", bytes(pdf_m.output()), "Rullino.pdf", type="primary")