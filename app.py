import streamlit as st
from PyPDF2 import PdfReader
import re

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

# CSS per gestire la stampa senza pop-up
st.markdown("""
    <style>
    @media print {
        /* Nasconde tutto ciò che non è l'etichetta */
        header, footer, .stButton, .stFileUploader, .stExpander, .stMarkdown, [data-testid="stSidebar"] {
            display: none !important;
        }
        .print-only {
            display: block !important;
            width: 100%;
            border: 2px solid black;
            padding: 20px;
            text-align: center;
        }
    }
    .print-only { display: none; }
    </style>
""", unsafe_allow_html=True)

def pulisci_testo(testo):
    parole_da_eliminare = ["ATTREZZI", "PESCA", "USATI", "SCI", "AI", "ZONA", "FAO", "N.", "N°"]
    for p in parole_da_eliminare:
        testo = re.sub(rf'\b{p}\b', '', testo)
    return re.sub(r'\s+', ' ', testo).strip()

def estrai_tutto(file):
    reader = PdfReader(file)
    testo = "\n".join([page.extract_text().upper() for page in reader.pages])
    sezioni = re.split(r'LOTTO\s*N?\.?\s*', testo)
    prodotti = []
    for i in range(len(sezioni) - 1):
        blocco_pre = sezioni[i]
        blocco_post = sezioni[i+1]
        sci_match = re.search(r'\((.*?)\)', blocco_pre)
        scientifico = sci_match.group(1) if sci_match else "N.D."
        linee = blocco_pre.strip().split('\n')
        nome_comm = "PESCE"
        for j, riga in enumerate(linee):
            if scientifico in riga:
                nome_comm = riga.split('(')[0].strip()
                if len(nome_comm) < 3 and j > 0: nome_comm = linee[j-1].strip()
        lotto_match = re.search(r'^([A-Z0-9\s/\\-]+)', blocco_post)
        lotto = lotto_match.group(1).strip() if lotto_match else "N.D."
        fao_match = re.search(r'FAO\s*([\d\.]+)', blocco_pre)
        fao = fao_match.group(1) if fao_match else "37.2.1"
        metodo = "ALLEVATO" if "ALLEVATO" in blocco_pre else "PESCATO"
        prodotti.append({"nome": pulisci_testo(nome_comm), "sci": scientifico, "lotto": lotto, "fao": fao, "metodo": metodo})
    return prodotti

st.title("⚓ FishLabel Scanner PRO")
file = st.file_uploader("Carica Fattura", type="pdf")

if file:
    prodotti = estrai_tutto(file)
    for p in prodotti:
        with st.expander(f"📦 {p['nome']} - Lotto: {p['lotto']}"):
            # HTML dell'etichetta che sarà visibile solo in stampa
            label_html = f"""
                <div class="print-only">
                    <h1 style="font-size:40px;">{p['nome']}</h1>
                    <p style="font-size:22px;"><i>({p['sci']})</i></p>
                    <hr>
                    <p style="font-size:24px;">ZONA FAO: <b>{p['fao']}</b></p>
                    <p style="font-size:24px;">METODO: <b>{p['metodo']}</b></p>
                    <div style="font-size:36px; border:3px solid black; padding:10px; margin-top:15px; font-weight:bold;">
                        LOTTO: {p['lotto']}
                    </div>
                </div>
            """
            st.markdown(label_html, unsafe_allow_html=True)
            
            if st.button(f"Prepara Stampa {p['lotto']}", key=f"btn_{p['lotto']}"):
                # Questo script forza il browser ad aprire la finestra di stampa della pagina stessa
                st.components.v1.html("<script>window.print();</script>", height=0)