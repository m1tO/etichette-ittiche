import streamlit as st
from PyPDF2 import PdfReader
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome(nome_grezzo):
    # Rimuove parole inutili che sporcano il nome del pesce
    scarti = ["ATTREZZI", "PESCA", "USATI", "SCI", "RETI", "AMI", "ZONA", "FAO"]
    parole = nome_grezzo.split()
    pulite = [p for p in parole if p not in scarti and not any(c.isdigit() for c in p)]
    return " ".join(pulite)

def estrai_tutto(file):
    reader = PdfReader(file)
    testo = ""
    for page in reader.pages:
        testo += page.extract_text().upper() + "\n"
    
    # Dividiamo il documento in base alla parola chiave LOTTO
    sezioni = re.split(r'LOTTO\s*N\.', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        
        # 1. Nome Scientifico
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        scientifico = sci_match.group(1) if sci_match else "N.D."
        
        # 2. Nome Commerciale (Cerchiamo la riga che contiene il nome scientifico)
        linee = blocco_pre.strip().split('\n')
        nome_comm = "PESCE"
        for j, riga in enumerate(linee):
            if f"({scientifico})" in riga:
                # Il nome è solitamente nella stessa riga prima della parentesi o in quella sopra
                nome_comm = riga.split('(')[0].strip()
                if len(nome_comm) < 3 and j > 0:
                    nome_comm = linee[j-1].strip()
        
        # 3. Lotto
        lotto_match = re.search(r'^\s*([A-Z0-9/\-]+)', blocco_post)
        lotto = lotto_match.group(1) if lotto_match else "N.D."
        
        # 4. FAO e Metodo
        fao_match = re.search(r'FAO\s*(\d+[\.\d]*)', blocco_pre)
        fao = fao_match.group(1) if fao_match else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_nome(nome_comm),
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

st.title("⚓ FishLabel Scanner Universale")
file = st.file_uploader("Carica Fattura", type="pdf")

if file:
    prodotti = estrai_tutto(file)
    for p in prodotti:
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            if st.button(f"Stampa {p['nome']}", key=p['lotto']):
                st.components.v1.html(f"""
                    <script>
                    const win = window.open('', '', 'width=600,height=400');
                    win.document.write('<html><body style="font-family:sans-serif; text-align:center; border:5px solid black; padding:20px;">');
                    win.document.write('<h1 style="font-size:40px; margin-bottom:0;">{p['nome']}</h1>');
                    win.document.write('<p style="font-size:20px;"><i>({p['sci']})</i></p><hr>');
                    win.document.write('<p style="font-size:22px;">ZONA FAO: <b>{p['fao']}</b></p>');
                    win.document.write('<p style="font-size:22px;">METODO: <b>{p['metodo']}</b></p>');
                    win.document.write('<p style="font-size:35px; margin-top:20px; border:2px solid black; display:inline-block; padding:10px;">LOTTO: {p['lotto']}</p>');
                    win.document.write('</body></html>');
                    win.document.close(); win.print(); win.close();
                    </script>
                """, height=0)