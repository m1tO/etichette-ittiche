import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

# ----------------------------------
# PULIZIA NOME COMMERCIALE
# ----------------------------------

STOPWORDS = {
    "FRESCO", "ALLEVATO", "ACQUACOLTURA",
    "GRECIA", "MALTA", "NORVEGIA", "SPAGNA",
    "ZONA", "FAO", "KG", "UM", "SBG"
}

def pulisci_nome_chirurgico(testo: str) -> str:
    if not testo:
        return ""
    t = testo.upper().strip()

    # Rimuove codice iniziale numerico
    t = re.sub(r"^\d{3,5}\s+", "", t)

    # Taglia pezzature tipo 300/400 o 400-600
    t = re.split(r"\b\d{2,4}[/\-]\d{2,4}\b", t)[0]

    # Rimuove stopwords
    for w in STOPWORDS:
        t = re.sub(rf"\b{w}\b", "", t)

    t = re.sub(r"\s+", " ", t).strip(" -,.")
    return t


# ----------------------------------
# ESTRAZIONE TESTO PDF
# ----------------------------------

def estrai_testo_pdf(file_like):
    try:
        file_like.seek(0)
    except:
        pass

    reader = PdfReader(file_like)
    pages_text = []
    for p in reader.pages:
        pages_text.append(p.extract_text() or "")

    testo = "\n".join(pages_text)
    testo = testo.replace("FA0", "FAO").replace("ΑΙ", " AI ")
    return testo


# ----------------------------------
# DIVISIONE BLOCCHI PRODOTTO
# ----------------------------------

def estrai_blocchi_prodotti(testo):
    lines = [ln.strip() for ln in testo.splitlines() if ln.strip()]
    start_idxs = [i for i, ln in enumerate(lines) if re.match(r"^\d{3,5}\s+\S", ln)]

    blocchi = []
    for k, i in enumerate(start_idxs):
        j = start_idxs[k + 1] if k + 1 < len(start_idxs) else len(lines)
        blocchi.append("\n".join(lines[i:j]))

    return blocchi


# ----------------------------------
# SCIENTIFICO
# ----------------------------------

def estrai_scientifico(blocco_up):
    # 1) Tra parentesi
    m = re.search(r"\(([A-Z][A-Z\s\-]{4,})\)", blocco_up)
    if m:
        sci = m.group(1).strip()
        if len(sci.split()) >= 2:
            return sci

    # 2) Pattern binomiale maiuscolo
    cand = re.findall(r"\b([A-Z]{4,}\s+[A-Z]{4,})\b", blocco_up)
    for s in cand:
        if any(x in s for x in ["ZONA FAO", "LOTTO", "IMPONIBILE", "TOTALE"]):
            continue
        if len(s.split()) == 2:
            return s.strip()

    return "DA COMPILARE"


# ----------------------------------
# LOTTO ROBUSTO
# ----------------------------------

def estrai_lotto(blocco_up):
    # Pattern principale
    m = re.search(r"LOTTO\s*(?:N\.?|N°)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\/\-_\.]{2,})", blocco_up)
    if m:
        return m.group(1).strip()

    # Fallback
    m2 = re.search(r"\bLOTTO\s+([A-Z0-9][A-Z0-9\/\-_\.]{2,})\b", blocco_up)
    if m2:
        return m2.group(1).strip()

    return "DA COMPILARE"


# ----------------------------------
# ESTRAZIONE PRINCIPALE
# ----------------------------------

def estrai_dati(file_like):
    testo = estrai_testo_pdf(file_like)
    blocchi = estrai_blocchi_prodotti(testo)

    risultati = []

    for blocco in blocchi:
        b_up = blocco.upper()

        # Prima riga = descrizione
        first_line = blocco.splitlines()[0]
        nome = pulisci_nome_chirurgico(first_line) or "DA COMPILARE"

        lotto = estrai_lotto(b_up)

        # FAO
        fao_m = re.search(r"FAO\s*([0-9]{1,2}(?:\.[0-9]{1,2}){1,3})", b_up)
        fao = fao_m.group(1) if fao_m else "37.2.1"

        metodo = "ALLEVATO" if any(x in b_up for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"

        sci = estrai_scientifico(b_up)

        risultati.append({
            "nome": nome,
            "sci": sci,
            "lotto": lotto,
            "fao": fao,
            "metodo": metodo
        })

    return risultati


# ----------------------------------
# ETICHETTA PDF
# ----------------------------------

def disegna_etichetta(pdf, p):
    pdf.add_page()
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(w=pdf.epw, h=4, text="ITTICA CATANZARO - PALERMO",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p['nome'], align="C")

    pdf.ln(1)
    pdf.set_font("helvetica", "I", 9)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align="C")

    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5,
             text=f"FAO {p['fao']} - {p['metodo']}",
             align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((pdf.w - 80) / 2)
    pdf.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}",
             border=1, align="C")

    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4,
             text=f"Data: {datetime.now().strftime('%d/%m/%Y')}",
             align="R")


# ----------------------------------
# UI STREAMLIT
# ----------------------------------

st.title("⚓ FishLabel Scanner PRO")

if st.button("🗑️ SVUOTA TUTTO E RICOMINCIA", type="primary"):
    st.session_state.clear()
    st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if "last_f" not in st.session_state or st.session_state.last_f != file.name:
        st.session_state.p_list = estrai_dati(file)
        st.session_state.last_f = file.name

    if st.session_state.p_list:
        st.success(f"✅ Trovati {len(st.session_state.p_list)} prodotti.")

        pdf_tot = FPDF(orientation="L", unit="mm", format=(62, 100))
        pdf_tot.set_margins(4, 3, 4)
        pdf_tot.set_auto_page_break(False)

        for p in st.session_state.p_list:
            disegna_etichetta(pdf_tot, p)

        st.download_button(
            label="🖨️ SCARICA TUTTE LE ETICHETTE (PDF)",
            data=bytes(pdf_tot.output()),
            file_name="Rullino_Etichette.pdf",
            mime="application/pdf",
        )

        st.markdown("---")

        for i, p in enumerate(st.session_state.p_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                c1, c2 = st.columns(2)
                p['nome'] = c1.text_input("Nome Pesce", p['nome'], key=f"nm_{i}")
                p['lotto'] = c2.text_input("Lotto", p['lotto'], key=f"lt_{i}")

                pdf_s = FPDF(orientation="L", unit="mm", format=(62, 100))
                pdf_s.set_margins(4, 3, 4)
                pdf_s.set_auto_page_break(False)
                disegna_etichetta(pdf_s, p)

                st.download_button(
                    "Scarica PDF Singolo",
                    data=bytes(pdf_s.output()),
                    file_name=f"Etic_{i}.pdf",
                    key=f"btn_{i}",
                    mime="application/pdf",
                )
