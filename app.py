import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_serio(testo):
    """Pulisce il nome del pesce eliminando codici e scarti tecnici."""
    if not testo: return ""
    testo = testo.upper().strip()
    
    # 1. Rimuove indirizzi di Palermo che spesso finiscono nel testo estratto
    testo = re.sub(r'\d{5}\s+PALERMO.*', '', testo)
    
    # 2. Rimuove codici numerici iniziali (es. 0258 o 46668255)
    testo = re.sub(r'^\d{3,10}\s+', '', testo)
    
    # 3. Taglia alla prima pezzatura o zona FAO (es. 300-400 o 27)
    testo = re.split(r'\s\d+', testo)[0]
    
    # 4. Parole stop specifiche che sporcano i nomi commerciali
    stop = ["IMPONIBILE", "TOTALE", "DESCRIZIONE", "PN", "AI", "ΑΙ", "ZONA", "FAO", "PRODOTTO", "UM", "Q.TÀ"]
    for s in stop:
        if s in testo: testo = testo.split(s)[0]
    
    res = testo.strip().strip('-').strip(',').strip('.')
    return res if len(res) > 2 else ""

def disegna_etichetta(pdf, p):
    """Disegna l'etichetta 62x100mm ottimizzata per Brother."""
    pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    
    # Nome Commerciale (multi_cell gestisce l'andata a capo automatica)
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
    l_txt = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_txt) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    pdf.set_x((100 - 75) / 2) 
    pdf.cell(w=75, h=11, text=l_txt, border=1, align='C')
    
    # Data Confezionamento
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align='R')

def estrai_dati_hermes(file):
    reader = PdfReader(file)
    testo = "\n".join([p.extract_text() for p in reader.pages]).upper()
    testo = testo.replace('ΑΙ', ' AI ') # Fix per il carattere greco usato da Hermes
    
    # Dividiamo il testo ogni volta che troviamo la parola LOTTO
    blocchi = re.split(r'LOTTO\s*N?\.?\s*', testo)
    risultati = []
    
    for i in range(len(blocchi) - 1):
        testo_precedente = blocchi[i]
        testo_successivo = blocchi[i+1]
        
        # 1. Troviamo il nome scientifico (l'ultimo tra parentesi nel blocco precedente)
        sci_matches = re.findall(r'\(([^)]+)\)', testo_precedente)
        if not sci_matches: continue
        scientifico = sci_matches[-1].strip()
        # Filtriamo termini tecnici che non sono nomi scientifici
        if any(x in scientifico for x in ["IVA", "KG", "EURO", "DESCRIZIONE"]): continue
        
        # 2. Troviamo il nome commerciale (quello subito prima dello scientifico)
        parti_nome = testo_precedente.split(f"({scientifico})")[0].strip().split('\n')
        nome_grezzo = parti_nome[-1].strip()
        # Se la riga è solo un codice numerico, prendiamo la riga sopra
        if (re.fullmatch(r'\d+', nome_grezzo) or len(nome_grezzo) < 3) and len(parti_nome) > 1:
            nome_grezzo = parti_nome[-2].strip()
            
        # 3. Estraiamo il valore del Lotto
        lotto_raw = testo_successivo.split('\n')[0].strip()
        # Tagliamo via il prezzo o codici unità di misura attaccati al lotto
        lotto = re.split(r'\s{2,}|CAS|KG|\d+,\d+', lotto_raw)[0].strip()
        
        # 4. FAO e Metodo
        fao_m = re.search(r'FAO\s*N?°?\s*([\d\.]+)', testo_precedente + testo_successivo)
        metodo = "ALLEVATO" if any(x in testo_precedente for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"
        
        nome_pulito = pulisci_nome_serio(nome_grezzo)
        
        risultati.append({
            "nome": nome_pulito if nome_pulito else "DA COMPILARE",
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao_m.group(1) if fao_m else "37.2.1",
            "metodo": metodo
        })
    return risultati

# --- INTERFACCIA STREAMLIT ---
st.title("⚓ FishLabel Scanner PRO")

file = st.file_uploader("Trascina qui la fattura PDF", type="pdf")

if file:
    # Reset della sessione quando carichi un file con nome diverso
    if "nome_ultimo_file" not in st.session_state or st.session_state.nome_ultimo_file != file.name:
        st.session_state.prodotti_list = estrai_dati_hermes(file)
        st.session_state.nome_ultimo_file = file.name
        st.toast(f"Nuova fattura: {file.name}")

    if st.session_state.prodotti_list:
        st.success(f"✅ Trovati {len(st.session_state.prodotti_list)} prodotti.")
        
        # TASTONE STAMPA MASSIVA
        pdf_massivo = FPDF(orientation='L', unit='mm', format=(62, 100))
        pdf_massivo.set_margins(4, 3, 4)
        pdf_massivo.set_auto_page_break(False)
        for p in st.session_state.prodotti_list:
            disegna_etichetta(pdf_massivo, p)
        
        st.download_button(
            label="🖨️ SCARICA TUTTO IL RULLINO",
            data=bytes(pdf_massivo.output()),
            file_name="Rullino_Etichette.pdf",
            mime="application/pdf",
            type="primary"
        )

        st.markdown("---")
        # LISTA PRODOTTI MODIFICABILE
        for i, p in enumerate(st.session_state.prodotti_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                col1, col2 = st.columns(2)
                p['nome'] = col1.text_input("Nome Pesce", p['nome'], key=f"nome_{i}")
                p['lotto'] = col2.text_input("Lotto", p['lotto'], key=f"lotto_{i}")
                
                pdf_singolo = FPDF(orientation='L', unit='mm', format=(62, 100))
                pdf_singolo.set_margins(4, 3, 4)
                pdf_singolo.set_auto_page_break(False)
                disegna_etichetta(pdf_singolo, p)
                
                st.download_button(
                    label="Scarica PDF",
                    data=bytes(pdf_singolo.output()),
                    file_name=f"Etichetta_{i}.pdf",
                    key=f"btn_{i}"
                )