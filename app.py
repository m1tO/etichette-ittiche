import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime
import json

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

# ----------------------------------
# CONFIG
# ----------------------------------

DEFAULT_WHL = {"SALMONE", "ORATA", "SPIGOLA", "SEPPIA", "CALAMARO", "POLPO", "TRIGLIA"}

STOPWORDS = {
    "FRESCO", "ALLEVATO", "ACQUACOLTURA", "CONGELATO", "SURGELATO",
    "GRECIA", "MALTA", "NORVEGIA", "SPAGNA", "FRANCIA", "ITALIA",
    "ZONA", "FAO", "KG", "UM", "SBG", "LM", "MM", "CM",
    "IMPONIBILE", "TOTALE", "IVA", "EURO", "€",
    "INTERO", "INTERA", "FILETTO", "FILETTI", "TRANCIO", "TRANCE",
    "BUSTA", "SOTTOVUOTO", "FRES", "CONG"
}

HEADER_NOISE = [
    "PALERMO", "VIA", "CORSO", "PIAZZA", "P.IVA", "PARTITA IVA", "CODICE FISCALE",
    "FATTURA", "DDT", "DOCUMENTO", "CLIENTE", "DESTINAZIONE",
    "TEL", "EMAIL", "CAP", "PROV", "(PA)", " IT ", " IT-",
    "AGENZIA", "ENTRATE", "FATTURE E CORRISPETTIVI", "TERMINI DI PAGAMENTO",
    "IMPONIBILE", "IMPOSTA", "TOTALE", "SCADENZE", "PEC", "SPETTABILE"
]

# ----------------------------------
# PDF TEXT
# ----------------------------------

def estrai_testo_pdf(file_like):
    try:
        file_like.seek(0)
    except Exception:
        pass

    reader = PdfReader(file_like)
    pages_text = []
    for p in reader.pages:
        pages_text.append(p.extract_text() or "")

    testo = "\n".join(pages_text)
    testo = testo.replace("FA0", "FAO").replace("ΑΙ", " AI ")
    return testo

# ----------------------------------
# NOME: PULIZIA (solo come fallback)
# ----------------------------------

def pulisci_nome_chirurgico(testo: str) -> str:
    if not testo:
        return ""
    t = testo.upper().strip()
    t = re.sub(r"^\d{3,6}\s+", "", t)
    t = re.split(r"\b\d{2,4}[/\-]\d{2,4}\b", t)[0]
    for w in STOPWORDS:
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -,.")
    return t

# ----------------------------------
# WHITELIST: LOAD + MATCHER
# ----------------------------------

def load_whitelist_from_json_bytes(raw: bytes) -> set[str]:
    obj = json.loads(raw.decode("utf-8"))

    if isinstance(obj, list):
        names = obj
    elif isinstance(obj, dict) and "names" in obj and isinstance(obj["names"], list):
        names = obj["names"]
    else:
        raise ValueError("Formato JSON non valido")

    wl = set()
    for x in names:
        s = str(x).upper().strip()
        s = re.sub(r"\s+", " ", s)
        if not s:
            continue
        # evita voci troppo corte tipo "IN"
        if len(s) < 4 and " " not in s:
            continue
        wl.add(s)
    return wl

def build_whitelist_regex(whitelist: set[str]) -> re.Pattern:
    if not whitelist:
        return re.compile(r"(?!)")

    ordered = sorted(whitelist, key=len, reverse=True)
    parts = [re.escape(x) for x in ordered]
    pattern = r"\b(?:%s)\b" % "|".join(parts)
    return re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)

def find_name_from_whitelist(text: str, wl_regex: re.Pattern) -> str:
    if not text:
        return ""
    m = wl_regex.search(text.upper())
    return m.group(0).upper().strip() if m else ""

# ----------------------------------
# LOTTO / SCIENTIFICO / FAO / METODO
# ----------------------------------

def estrai_scientifico(text_up: str) -> str:
    m = re.search(r"\(([A-Z][A-Z\s\-]{4,})\)", text_up)
    if m:
        sci = m.group(1).strip()
        if len(sci.split()) >= 2:
            return sci

    cand = re.findall(r"\b([A-Z]{4,}\s+[A-Z]{4,})\b", text_up)
    for s in cand:
        if any(x in s for x in ["ZONA FAO", "LOTTO", "IMPONIBILE", "TOTALE", "PALERMO", "FATTURA"]):
            continue
        if len(s.split()) == 2:
            return s.strip()

    return "DA COMPILARE"

def estrai_fao(text_up: str) -> str:
    m = re.search(r"FAO\s*N?°?\s*([0-9]{1,2}(?:\.[0-9]{1,2}){1,3})", text_up)
    return m.group(1) if m else "37.2.1"

def estrai_metodo(text_up: str) -> str:
    return "ALLEVATO" if any(x in text_up for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"

def estrai_lotto_da_blocco(text_up: str) -> str:
    m = re.search(r"LOTTO\s*(?:N\.?|N°)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\/\-_\.]{2,})", text_up)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"\bLOTTO\s+([A-Z0-9][A-Z0-9\/\-_\.]{2,})\b", text_up)
    if m2:
        return m2.group(1).strip()
    return "DA COMPILARE"

# ----------------------------------
# STRATEGIA A: FATTURE CON CODICI ARTICOLO
# ----------------------------------

def is_probable_code_line(line: str) -> bool:
    if not line:
        return False
    up = line.upper().strip()
    if not re.match(r"^\d{3,6}\s+\S", up):
        return False
    if any(x in up for x in HEADER_NOISE):
        return False
    return True

def estrai_blocchi_prodotti_da_codici(testo: str) -> list[str]:
    lines = [ln.strip() for ln in testo.splitlines() if ln.strip()]
    start_idxs = [i for i, ln in enumerate(lines) if is_probable_code_line(ln)]

    blocchi = []
    for k, i in enumerate(start_idxs):
        j = start_idxs[k + 1] if k + 1 < len(start_idxs) else len(lines)
        block_lines = lines[i:j]
        if block_lines:
            blocchi.append("\n".join(block_lines))
    return blocchi

def estrai_dati_da_blocchi_codici(testo: str, wl_regex: re.Pattern) -> list[dict]:
    blocchi = estrai_blocchi_prodotti_da_codici(testo)
    risultati = []

    for blocco in blocchi:
        b_up = blocco.upper()

        # Nome: cerca nel blocco intero usando whitelist (vincente)
        nome = find_name_from_whitelist(blocco, wl_regex)

        # fallback: pulisci prima riga
        if not nome:
            first_line = blocco.splitlines()[0]
            nome = pulisci_nome_chirurgico(first_line)

        if not nome or any(x in nome for x in ["PALERMO", "VIA", "FATTURA", "CLIENTE"]):
            continue

        lotto = estrai_lotto_da_blocco(b_up)
        sci = estrai_scientifico(b_up)
        fao = estrai_fao(b_up)
        metodo = estrai_metodo(b_up)

        risultati.append({"nome": nome, "sci": sci, "lotto": lotto, "fao": fao, "metodo": metodo})

    return risultati

# ----------------------------------
# STRATEGIA B: FATTURE SENZA CODICI (TABELLARE) - FIX LOTTI CON SPAZI
# ----------------------------------

def estrai_dati_tabella_senza_codici(testo: str, wl_regex: re.Pattern) -> list[dict]:
    lines = [ln.strip() for ln in (testo or "").splitlines() if ln.strip()]
    results = []

    def extract_lotto_from_line(line_up: str) -> str:
        # cattura anche lotti con spazio tipo "K 33/A"
        m = re.search(
            r"LOTTO\s*(?:N\.?|N°)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\/\-_\. ]{1,25})",
            line_up
        )
        if not m:
            return ""
        raw = m.group(1)
        raw = re.split(r"\b(IVA|TOTALE|IMPORTO|QUANTITÀ|QUANTITA|€)\b", raw)[0]
        raw = re.sub(r"\s+", " ", raw).strip(" -,:;.")
        return raw

    for i, ln in enumerate(lines):
        up = ln.upper()
        if "LOTTO" not in up:
            continue

        lotto = extract_lotto_from_line(up)
        if not lotto:
            continue

        # cerca nome nelle righe sopra (finestra ampia)
        nome = ""
        for j in range(i, max(-1, i - 8), -1):
            cand = lines[j]
            cand_up = cand.upper()
            if any(x in cand_up for x in HEADER_NOISE):
                continue
            nome = find_name_from_whitelist(cand, wl_regex)
            if nome:
                break

        # se non trovato sopra, prova sotto
        if not nome:
            for j in range(i + 1, min(len(lines), i + 6)):
                cand = lines[j]
                cand_up = cand.upper()
                if any(x in cand_up for x in HEADER_NOISE):
                    continue
                nome = find_name_from_whitelist(cand, wl_regex)
                if nome:
                    break

        # finestra attorno per scientifico/FAO/metodo
        around = " ".join(lines[max(0, i - 6): min(len(lines), i + 6)])
        around_up = around.upper()

        sci = estrai_scientifico(around_up)
        fao = estrai_fao(around_up)
        metodo = estrai_metodo(around_up)

        if not nome:
            nome = "DA COMPILARE"

        results.append({"nome": nome, "sci": sci, "lotto": lotto, "fao": fao, "metodo": metodo})

    # dedup per lotto
    seen = set()
    out = []
    for r in results:
        k = r["lotto"].upper().strip()
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out

# ----------------------------------
# ESTRAZIONE UNIFICATA
# ----------------------------------

def estrai_dati(file_like, wl_regex: re.Pattern) -> list[dict]:
    testo = estrai_testo_pdf(file_like)

    risultati = estrai_dati_da_blocchi_codici(testo, wl_regex)

    if not risultati:
        risultati = estrai_dati_tabella_senza_codici(testo, wl_regex)

    # dedup finale (nome, lotto, sci)
    seen = set()
    out = []
    for r in risultati:
        k = (r["nome"], r["lotto"], r["sci"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out

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
    pdf.multi_cell(w=pdf.epw, h=7, text=p["nome"], align="C")

    pdf.ln(1)
    f_sci = 9 if len(p["sci"]) < 25 else 7
    pdf.set_font("helvetica", "I", f_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align="C")

    pdf.ln(1)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(w=pdf.epw, h=5, text=f"FAO {p['fao']} - {p['metodo']}",
             align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(38)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_x((pdf.w - 80) / 2)
    pdf.cell(w=80, h=11, text=f"LOTTO: {p['lotto']}", border=1, align="C")

    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align="R")

# ----------------------------------
# UI
# ----------------------------------

st.title("⚓ FishLabel Scanner PRO")

with st.expander("📚 Carica whitelist nomi pesce (JSON)"):
    st.caption('Accetta lista ["ORATA", ...] oppure oggetto {"names":[...]}')
    wl_file = st.file_uploader("Carica JSON whitelist", type=["json"], key="wl_json")

    whitelist = set(DEFAULT_WHL)
    if wl_file is not None:
        try:
            whitelist = load_whitelist_from_json_bytes(wl_file.getvalue())
            st.success(f"Whitelist caricata ✅ ({len(whitelist)} nomi)")
        except Exception:
            st.error("JSON non valido o formato non supportato.")

wl_regex = build_whitelist_regex(whitelist)

if st.button("🗑️ SVUOTA TUTTO E RICOMINCIA", type="primary"):
    st.session_state.clear()
    st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if "last_f" not in st.session_state or st.session_state.last_f != file.name:
        st.session_state.p_list = estrai_dati(file, wl_regex)
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
        st.warning("⚠️ Non ho trovato prodotti (template strano o testo non estraibile).")
