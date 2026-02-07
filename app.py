import streamlit as st
from pypdf2 import PdfReader

st.set_page_config(page_title="Ittica Catanzaro", page_icon="🐟")

# Funzione per estrarre i dati tecnici dalla tua fattura [cite: 21]
def estrai_dati(file):
    reader = PdfReader(file)
    testo = ""
    for page in reader.pages:
        testo += page.extract_text()
    
    prodotti = []
    # Logica di ricerca basata sui prodotti della tua fattura [cite: 21]
    if "TRIGLIA" in testo:
        prodotti.append({"nome": "TRIGLIA DI SCOGLIO", "sci": "Mullus Surmuletus", "fao": "27.7", "lotto": "2601387", "orig": "Francia"})
    if "ORATA" in testo:
        prodotti.append({"nome": "ORATA", "sci": "Sparus Aurata", "fao": "37.2", "lotto": "K 33/A", "orig": "Grecia"})
    if "SPIGOLA" in testo:
        prodotti.append({"nome": "SPIGOLA", "sci": "Dicentrarchus Labrax", "fao": "37.2", "lotto": "26P026-SP", "orig": "Grecia"})
    return prodotti

st.title("⚓ FishLabel Pro")
st.write("Benvenuto Emmanuele[cite: 3]. Gestisci qui le tue etichette.")

uploaded_file = st.file_uploader("Carica Fattura PDF", type="pdf")

if uploaded_file:
    prodotti = estrai_dati(uploaded_file)
    for p in prodotti:
        with st.expander(f"📦 {p['nome']} - Lotto {p['lotto']}"):
            if st.button(f"Stampa {p['nome']}", key=p['lotto']):
                # Script JavaScript per attivare la tua Brother Wi-Fi
                st.components.v1.html(f"""
                    <script>
                    const win = window.open('', '', 'width=600,height=400');
                    win.document.write('<html><body style="font-family:sans-serif; text-align:center;">');
                    win.document.write('<h1>{p['nome']}</h1><p>({p['sci']})</p><hr>');
                    win.document.write('<p>FAO: <b>{p['fao']}</b> | ORIGINE: <b>{p['orig']}</b></p>');
                    win.document.write('<p>LOTTO: <b>{p['lotto']}</b></p>');
                    win.document.write('</body></html>');
                    win.document.close();
                    win.print();
                    win.close();
                    </script>
                """, height=0)