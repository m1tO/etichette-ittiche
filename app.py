import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime
from difflib import SequenceMatcher
import json

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

# ----------------------------------
# CONFIG
# ----------------------------------

DEFAULT_WHL = {"SALMONE", "ORATA", "SPIGOLA", "SEPPIA", "CALAMARO", "POLPO", "TRIGLIA"}

# parole “tecniche” che non vuoi nel nome etichetta
STOPWORDS = {
    "FRESCO", "ALLEVATO", "ACQUACOLTURA", "CONGELATO", "SURGELATO",
    "GRECIA", "MALTA", "NORVEGIA", "SPAGNA", "FRANCIA", "ITALIA",
    "ZONA", "FAO", "KG", "UM", "SBG", "LM", "MM", "CM",
    "IMPONIBILE", "TOTALE", "IVA", "EURO", "€",
    "INTERO", "INTERA", "FILETTO", "FILETTI", "TRANCIO", "TRANCE",
    "BUSTA", "SOTTOVUOTO", "FRES", "CONG"
}

# parole che indicano righe header/indirizzi (per evitare “PALERMO” come prodotto)
HEADER_NOISE = [
    "PALERMO", "VIA", "CORSO", "PIAZZA", "P.IVA", "PARTITA IVA", "CODICE FISCALE",
    "FATTURA", "DDT", "DOCUMENTO", "CLIENTE", "DESTINAZIONE",
    "TEL", "EMAIL", "CAP", "PROV", "(PA)", " IT ", " IT-"
]

# ----------------------------------
# FUZZY
# ----------------------------------

def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def best_fuzzy(candidate: str, whitelist: set[str]) -> tuple[str, float]:
    if not candidate or not whitelist:
        return "", 0.0
    c = candidate.upper().strip()
    best_name, best_score = "", 0.0
    for w in whitelist:
        if abs(len(w) - len(c)) > 12:
            continue
        s = sim(c, w)
        if s > best_score:
            best_score = s
            best_name = w
            if best_score > 0.93:
                break
    return best_name, best_score

# ----------------------------------
# NOME: PULIZIA + HARD WHITELIST
# ----------------------------------

def pulisci_nome_chirurgico(testo: str) -> str:
    if not testo:
        return ""
    t = testo.upper().strip()

    # togli codice articolo iniziale (3-6 cifre)
    t = re.sub(r"^\d{3,6}\s+", "", t)

    # taglia pezzature tipo 300/400 o 400-600
    t = re.split(r"\b\d{2,4}[/\-]\d{2,4}\b", t)[0]

    # rimuovi stopwords come parole intere
    for w in STOPWORDS:
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t)

    t = re.sub(r"\s+", " ", t).strip(" -,.")
    return t

def normalizza_nome_con_whitelist(nome_raw: str, whitelist: set[str]) -> str:
    """
    HARD MODE:
    se riconosce un nome presente in whitelist (anche fuzzy), ritorna SOLO quello.
    """
    base = pulisci_nome_chirurgico(nome_raw)
    if not base:
        return "DA COMPILARE"

    wl = set(w.upper().strip() for w in whitelist if w and str(w).strip())
    base_spaced = f" {base} "

    # 1) match diretto (frase o parola)
    for w in wl:
        if f" {w} " in base_spaced:
            return w

    # 2) fuzzy su token e su stringa intera
    words = base.split()
    best_name, best_score = "", 0.0
    for w in wl:
        s_full = sim(base, w)
        if s_full > best_score:
            best_score, best_name = s_full, w

        for token in words:
            s_tok = sim(token, w)
            if s_tok > best_score:
                best_score, best_name = s_tok, w

    if best_score >= 0.84:
        return best_name

    return base

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
    return testo.replace("FA0", "FAO").replace("ΑΙ", " AI ")

# ----------------------------------
# BLOCCO PRODOTTI: start per codice + validazione col blocco
# ----------------------------------

def is_probable_code_line(line: str) -> bool:
    """Candidata a inizio articolo: 3-6 cifre + testo, non header."""
    if not line:
        return False
    up = line.upper().strip()

    if not re.match(r"^\d{3,6}\s+\S", up):
        return False

    if any(x in up for x in HEADER_NOISE):
        return False

    return True

def block_has_scientific_or_lotto(block_up: str) -> bool:
    if "LOTTO" in block_up:
        return True
    if re.search(r"\(([A-Z][A-Z\s\-]{4,})\)", block_up):
        return True
    if re.search(r"\b[A-Z]{4,}\s+[A-Z]{4,}\b", block_up):
        return True
    return False

def block_has_whitelist_match(first_line: str, whitelist: set[str]) -> bool:
    base = pulisci_nome_chirurgico(first_line)
    if not base:
        return False

    base_spaced = f" {base} "
    for w in whitelist:
        w = str(w).upper().strip()
        if not w:
            continue
        if f" {w} " in base_spaced:
            return True

    # fuzzy leggero sulle singole parole
    words = base.split()
    for token in words:
        for w in whitelist:
            w = str(w).upper().strip()
            if not w:
                continue
            if abs(len(w) - len(token)) > 10:
                continue
            if sim(token, w) >= 0.88:
                return True
    return False

def estrai_blocchi_prodotti(testo: str, whitelist: set[str]) -> list[str]:
    """
    1) prende tutte le righe che iniziano con codice (3-6 cifre)
    2) crea blocchi fino al prossimo codice
    3) filtra i blocchi: devono contenere LOTTO/scientifico oppure match whitelist
    """
    lines = [ln.strip() for ln in testo.splitlines() if ln.strip()]
    start_idxs = [i for i, ln in enumerate(lines) if is_probable_code_line(ln)]

    blocchi = []
    for k, i in enumerate(start_idxs):
        j = start_idxs[k + 1] if k + 1 < len(start_idxs) else len(lines)
        block_lines = lines[i:j]
        if not block_lines:
            continue

        blocco = "\n".join(block_lines)
        b_up = blocco.upper()

        first_line = block_lines[0]

        if block_has_scientific_or_lotto(b_up) or block_has_whitelist_match(first_line, whitelist):
            blocchi.append(blocco)

    return blocchi

# ----------------------------------
# SCIENTIFICO / LOTTO / FAO / METODO
# ----------------------------------

def estrai_scientifico(blocco_up: str) -> str:
    m = re.search(r"\(([A-Z][A-Z\s\-]{4,})\)", blocco_up)
    if m:
        sci = m.group(1).strip()
        if len(sci.split()) >= 2:
            return sci

    cand = re.findall(r"\b([A-Z]{4,}\s+[A-Z]{4,})\b", blocco_up)
    for s in cand:
        if any(x in s for x in ["ZONA FAO", "LOTTO", "IMPONIBILE", "TOTALE", "PALERMO", "FATTURA"]):
            continue
        if len(s.split()) == 2:
            return s.strip()

    return "DA COMPILARE"

def estrai_lotto(blocco_up: str) -> str:
    m = re.search(r"LOTTO\s*(?:N\.?|N°)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\/\-_\.]{2,})", blocco_up)
    if m:
        return m.group(1).strip()

    m2 = re.search(r"\bLOTTO\s+([A-Z0-9][A-Z0-9\/\-_\.]{2,})\b", blocco_up)
    if m2:
        return m2.group(1).strip()

    return "DA COMPILARE"

# ----------------------------------
# ESTRAZIONE DATI
# ----------------------------------

def estrai_dati(file_like, whitelist: set[str]):
    testo = estrai_testo_pdf(file_like)
    blocchi = estrai_blocchi_prodotti(testo, whitelist)

    risultati = []
    for blocco in blocchi:
        b_up = blocco.upper()

        first_line = blocco.splitlines()[0]
        nome = normalizza_nome_con_whitelist(first_line, whitelist)

        # extra safety: se ancora sembra header, scarta
        if any(x in nome for x in ["PALERMO", "VIA", "FATTURA", "CLIENTE"]):
            continue

        lotto = estrai_lotto(b_up)

        fao_m = re.search(r"FAO\s*([0-9]{1,2}(?:\.[0-9]{1,2}){1,3})", b_up)
        fao = fao_m.group(1) if fao_m else "37.2.1"

        metodo = "ALLEVATO" if any(x in b_up for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"

        sci = estrai_scientifico(b_up)

        risultati.append({"nome": nome, "sci": sci, "lotto": lotto, "fao": fao, "metodo": metodo})

    # dedup per evitare doppioni
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
            obj = json.loads(wl_file.getvalue().decode("utf-8"))
            if isinstance(obj, list):
                whitelist = set(str(x).upper().strip() for x in obj if str(x).strip())
            elif isinstance(obj, dict) and "names" in obj and isinstance(obj["names"], list):
                whitelist = set(str(x).upper().strip() for x in obj["names"] if str(x).strip())
            st.success(f"Whitelist caricata ✅ ({len(whitelist)} nomi)")
        except Exception:
            st.error("JSON non valido.")

if st.button("🗑️ SVUOTA TUTTO E RICOMINCIA", type="primary"):
    st.session_state.clear()
    st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    if "last_f" not in st.session_state or st.session_state.last_f != file.name:
        st.session_state.p_list = estrai_dati(file, whitelist)
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
