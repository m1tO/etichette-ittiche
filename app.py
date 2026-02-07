import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

def pulisci_nome_chirurgico(testo: str) -> str:
    """Elimina codici, zone geografiche e termini tecnici dal nome commerciale."""
    if not testo:
        return ""
    testo = testo.upper().strip()

    # 1) Rimuove codici numerici all'inizio (es. 0258 o 46668255)
    testo = re.sub(r"^\d{3,10}\s+", "", testo)

    # 2) LISTA NERA: rimuovi SOLO parole intere (non pezzi di parole)
    lista_nera = [
        "GRECIA", "ITALIA", "SPAGNA", "FRANCIA", "NORVEGIA", "ACQUACOLTURA",
        "ALLEVATO", "FRESCO", "CONGELATO", "ZONA", "FAO", "PRODOTTO",
        "DESCRIZIONE", "TOTALE", "IMPONIBILE", "UM", "Q.TÀ", "PESCA"
    ]
    pattern = r"\b(" + "|".join(map(re.escape, lista_nera)) + r")\b"
    testo = re.sub(pattern, " ", testo)

    # 3) Taglia alle pezzature tipiche (es. 300-400, 6/7, U/10, 10/20)
    testo = re.split(r"\b(\d{1,4}\s*[-/]\s*\d{1,4}|U\s*/\s*\d{1,3})\b", testo)[0]

    # Pulizia finale da simboli e spazi doppi
    testo = re.sub(r"\s+", " ", testo).strip().strip("-").strip(",").strip(".")
    return testo


def disegna_etichetta(pdf: FPDF, p: dict) -> None:
    """Disegna l'etichetta 62x100mm per Brother in una sola pagina."""
    pdf.add_page()
    pdf.set_font("helvetica", "B", 8)
    # new_x e new_y per compatibilità Python 3.13 e fpdf2
    pdf.cell(
        w=pdf.epw,
        h=4,
        text="ITTICA CATANZARO - PALERMO",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)

    # Nome Pesce
    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p["nome"], align="C")

    # Scientifico (rimpicciolisce se troppo lungo)
    pdf.ln(1)
    f_sci = 9 if len(p["sci"]) < 25 else 7
    pdf.set_font("helvetica", "I", f_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align="C")

    # Tracciabilità
    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(
        w=pdf.epw,
        h=5,
        text=f"FAO {p['fao']} - {p['metodo']}",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    # Box Lotto
    pdf.set_y(38)
    l_txt = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_txt) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    # centra il box lotto
    pdf.set_x((pdf.w - 80) / 2)
    pdf.cell(w=80, h=11, text=l_txt, border=1, align="C")

    # Data
    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(
        w=pdf.epw,
        h=4,
        text=f"Data: {datetime.now().strftime('%d/%m/%Y')}",
        align="R",
    )


def estrai_dati_hermes(file_like) -> list[dict]:
    # importantissimo con Streamlit: rimetti il puntatore a inizio file
    try:
        file_like.seek(0)
    except Exception:
        pass

    reader = PdfReader(file_like)

    # Uniamo il testo in un'unica stringa (extract_text può tornare None)
    pages_text = []
    for p in reader.pages:
        t = p.extract_text() or ""
        pages_text.append(t)

    testo = " ".join(pages_text).upper()
    testo = testo.replace("ΑΙ", " AI ").replace("FA0", " FAO ")

    # Dividiamo per la parola LOTTO
    blocchi = re.split(r"LOTTO\s*N?\.?\s*:?[\s]*", testo)
    risultati = []

    for i in range(len(blocchi) - 1):
        testo_prima = blocchi[i]
        testo_dopo = blocchi[i + 1]

        # 1) Scientifico (l'ultimo tra parentesi)
        sci_match = re.findall(r"\(([^)]+)\)", testo_prima)
        if not sci_match:
            continue
        scientifico = sci_match[-1].strip()
        if any(x in scientifico for x in ["IVA", "KG", "EURO", "PA"]):
            continue

        # 2) Nome Commerciale (cerca prima delle parentesi dello scientifico)
        nome_sporco = testo_prima.split(f"({scientifico})")[0].strip()
        parti = re.split(r"\s{2,}|\n", nome_sporco)
        nome_grezzo = (parti[-1].strip() if parti else "").strip()

        # 3) Lotto (prende una stringa plausibile all'inizio del blocco dopo LOTTO)
        lotto_match = re.search(r"^\s*([A-Z0-9\-_/]{3,})", testo_dopo.strip())
        lotto = lotto_match.group(1) if lotto_match else "DA COMPILARE"
        lotto = re.sub(r"(CAS|KG|UM)$", "", lotto).strip()

        # 4) FAO e Metodo
        fao_m = re.search(r"FAO\s*N?°?\s*([\d\.]+)", testo_prima + " " + testo_dopo)
        metodo = (
            "ALLEVATO"
            if any(x in (testo_prima + " " + testo_dopo) for x in ["ALLEVATO", "ACQUACOLTURA"])
            else "PESCATO"
        )

        risultati.append(
            {
                "nome": pulisci_nome_chirurgico(nome_grezzo) or "DA COMPILARE",
                "sci": scientifico,
                "lotto": lotto,
                "fao": fao_m.group(1) if fao_m else "37.2.1",
                "metodo": metodo,
            }
        )

    return risultati


@st.cache_data(show_spinner=False)
def estrai_dati_hermes_cached(file_bytes: bytes) -> list[dict]:
    return estrai_dati_hermes(BytesIO(file_bytes))


# --- INTERFACCIA PRINCIPALE ---
st.title("⚓ FishLabel Scanner PRO")

# TASTO RESET ROSSO E GIGANTE
if st.button("🗑️ SVUOTA TUTTO E RICOMINCIA", type="primary"):
    st.session_state.clear()
    st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    file_bytes = file.getvalue()

    # Reset automatico se carichi un file diverso
    if "last_f" not in st.session_state or st.session_state.last_f != file.name:
        st.session_state.p_list = estrai_dati_hermes_cached(file_bytes)
        st.session_state.last_f = file.name

    if st.session_state.p_list:
        st.success(f"✅ Trovati {len(st.session_state.p_list)} prodotti.")

        # DOWNLOAD PDF UNICO
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

        # BOX MODIFICA MANUALE
        for i, p in enumerate(st.session_state.p_list):
            with st.expander(f"📦 {p['nome']} - {p['lotto']}"):
                c1, c2 = st.columns(2)
                p["nome"] = c1.text_input("Nome Pesce", p["nome"], key=f"nm_{i}")
                p["lotto"] = c2.text_input("Lotto", p["lotto"], key=f"lt_{i}")

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
    else:
        st.warning("⚠️ Non ho trovato prodotti. Prova con un PDF diverso o controlla il template.")
