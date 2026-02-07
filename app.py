import streamlit as st
from PyPDF2 import PdfReader
import re

# Configurazione iniziale dell'app
st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_testo(testo):
    """Rimuove residui tecnici e parole non necessarie dal nome del pesce."""
    parole_da_eliminare = ["ATTREZZI", "PESCA", "USATI", "SCI", "AI", "ZONA", "FAO", "N.", "N°"]
    for p in parole_da_eliminare:
        testo = re.sub(rf'\b{p}\b', '', testo)
    return re.sub(r'\s+', ' ', testo).strip()

def estrai_tutto(file):
    """Analizza il PDF e trova tutti i prodotti basandosi sulla parola chiave LOTTO."""
    reader = PdfReader(file)
    # Uniamo il testo di tutte le pagine rendendolo maiuscolo
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    
    # Dividiamo il documento ogni volta che troviamo la dicitura LOTTO
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]   # Testo prima della parola LOTTO
        blocco_post = sezioni[i+1] # Testo dopo la parola LOTTO (contiene il codice lotto)
        
        # 1. Nome Scientifico (testo tra parentesi)
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        scientifico = sci_match.group(1) if sci_match else "N.D."
        
        # 2. Nome Commerciale (cerchiamo la riga che contiene il nome scientifico)
        linee = blocco_pre.strip().split('\n')
        nome_comm = "PESCE"
        for j, riga in enumerate(linee):
            if scientifico in riga:
                # Prendiamo il testo prima della parentesi
                nome_comm = riga.split('(')[0].strip()
                # Se la riga è vuota, prendiamo quella sopra
                if len(nome_comm) < 3 and j > 0:
                    nome_comm = linee[j-1].strip()
        
        # 3. LOTTO (Cattura tutto il codice, inclusi spazi e barre, fino a fine riga)
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        
        # 4. Zona FAO e Metodo di produzione
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

# --- INTERFACCIA APP ---
st.title("⚓ FishLabel Scanner PRO")
st.write("Carica la tua fattura PDF per generare le etichette per la Brother Wi-Fi.")

file = st.file_uploader("Carica Fattura", type="pdf")

if file:
    prodotti = estrai_tutto(file)
    
    if not prodotti:
        st.warning("Nessun lotto trovato nel PDF. Controlla il formato del file.")
    
    for p in prodotti:
        # Crea un box espandibile per ogni pesce trovato
        with st.expander(f"📦 {p['nome']} - Lotto: {p['lotto']}"):
            st.write(f"**Scientifico:** {p['sci']}")
            st.write(f"**Tracciabilità:** FAO {p['fao']} | {p['metodo']}")
            
            # Bottone di stampa con script JavaScript per apertura pop-up
            if st.button(f"Stampa {p['lotto']}", key=p['lotto']):
                st.components.v1.html(f"""
                    <script>
                    function printLabel() {{
                        const win = window.open('', '_blank', 'width=600,height=400');
                        if (!win) {{
                            alert("Pop-up bloccato! Per favore consenti i pop-up per questo sito.");
                            return;
                        }}
                        win.document.write('<html><body style="font-family:sans-serif; text-align:center; border:3px solid black; padding:15px;">');
                        win.document.write('<h1 style="font-size:38px; margin:0 auto;">{p['nome']}</h1>');
                        win.document.write('<p style="font-size:20px; margin:5px 0;"><i>({p['sci']})</i></p><hr>');
                        win.document.write('<p style="font-size:22px; margin:10px 0;">ZONA FAO: <b>{p['fao']}</b></p>');
                        win.document.write('<p style="font-size:22px; margin:10px 0;">METODO: <b>{p['metodo']}</b></p>');
                        win.document.write('<div style="font-size:34px; margin-top:15px; border:3px solid black; padding:10px; display:inline-block; font-weight:bold;">');
                        win.document.write('LOTTO: {p['lotto']}</div>');
                        win.document.write('<p style="font-size:14px; margin-top:15px;">Data Arrivo: 07/02/2026</p>');
                        win.document.write('</body></html>');
                        win.document.close();
                        // Piccolo ritardo per permettere al browser di caricare il contenuto prima della stampa
                        setTimeout(() => {{ win.print(); win.close(); }}, 500);
                    }}
                    printLabel();
                    </script>
                """, height=0)