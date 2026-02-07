import streamlit as st
from PyPDF2 import PdfReader
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_testo(testo):
    # Rimuove residui fastidiosi e parole tecniche dal nome
    parole_da_eliminare = ["ATTREZZI", "PESCA", "USATI", "SCI", "AI", "ZONA", "FAO", "N.", "N°"]
    for p in parole_da_eliminare:
        testo = re.sub(rf'\b{p}\b', '', testo)
    return re.sub(r'\s+', ' ', testo).strip()

def estrai_tutto(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    
    # Dividiamo per la parola chiave LOTTO
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        
        # 1. Nome Scientifico (tra parentesi)
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        scientifico = sci_match.group(1) if sci_match else "N.D."
        
        # 2. Nome Commerciale (cerca la riga del nome scientifico)
        linee = blocco_pre.strip().split('\n')
        nome_comm = "PESCE"
        for j, riga in enumerate(linee):
            if scientifico in riga:
                nome_comm = riga.split('(')[0].strip()
                if len(nome_comm) < 3 and j > 0:
                    nome_comm = linee[j-1].strip()
        
        # 3. LOTTO (Cattura tutto fino a fine riga o cambio dato)
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        # 4. FAO e Metodo
        fao_match = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        fao = fao_match.group(1) if fao_match else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        
        prodotti.append({
            "nome": pulisci_testo(nome_comm),
            "sci": scientifico,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })
    return prodotti

st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Carica Fattura", type="pdf")

if file:
    prodotti = estrai_tutto(file)
    for p in prodotti:
        with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
            if st.button(f"Stampa {p['lotto']}", key=p['lotto']):
                st.components.v1.html(f"""
                    <script>
                    const win = window.open('', '', 'width=600,height=400');
                    win.document.write('<html><body style="font-family:sans-serif; text-align:center; border:3px solid black; padding:15px;">');
                    win.document.write('<h1 style="font-size:38px; margin:0;">{p['nome']}</h1>');
                    win.document.write('<p style="font-size:20px;"><i>({p['sci']})</i></p><hr>');
                    win.document.write('<p style="font-size:22px;">ZONA FAO: <b>{p['fao']}</b></p>');
                    win.document.write('<p style="font-size:22px;">METODO: <b>{p['metodo']}</b></p>');
                    win.document.write('<div style="font-size:32px; margin-top:15px; border:3px solid black; padding:10px; display:inline-block;">');
                    win.document.write('LOTTO: <b>{p['lotto']}</b></div>');
                    win.document.write('<p style="font-size:14px; margin-top:10px;">Data Arrivo: 07/02/2026</p>');
                    win.document.write('</body></html>');
                    win.document.close(); win.print(); win.close();
                    </script>
                """, height=0)