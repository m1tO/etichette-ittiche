import streamlit as st
from PyPDF2 import PdfReader
from fpdf import FPDF
import re
from datetime import datetime
from io import BytesIO
import json
from difflib import SequenceMatcher

st.set_page_config(page_title="Ittica Catanzaro PRO", page_icon="🐟")

# -----------------------------
# UTIL: pulizia + scoring nomi
# -----------------------------

STOPWORDS = {
    "GRECIA", "ITALIA", "SPAGNA", "FRANCIA", "NORVEGIA",
    "ACQUACOLTURA", "ALLEVATO", "FRESCO", "CONGELATO",
    "ZONA", "FAO", "PRODOTTO", "DESCRIZIONE", "TOTALE",
    "IMPONIBILE", "UM", "Q.TÀ", "QTA", "PESCA",
    "EURO", "€", "IVA", "KG", "CAS", "LOTTO", "N°", "N.",
}

def pulisci_nome_chirurgico(testo: str) -> str:
    if not testo:
        return ""
    t = testo.upper().strip()

    # rimuove codici numerici all'inizio
    t = re.sub(r"^\d{3,10}\s+", "", t)

    # rimuovi solo parole intere stopwords
    pattern = r"\b(" + "|".join(map(re.escape, sorted(STOPWORDS, key=len, reverse=True))) + r")\b"
    t = re.sub(pattern, " ", t)

    # taglia pezzature tipiche (300-400, 6/7, U/10, 10/20)
    t = re.split(r"\b(\d{1,4}\s*[-/]\s*\d{1,4}|U\s*/\s*\d{1,3})\b", t)[0]

    # togli “PN / PS / SP” da fine se è un tag tecnico
    t = re.sub(r"\b(PN|PS|SP)\b", " ", t)

    # pulizia finale
    t = re.sub(r"[•·]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -,.")
    return t


def is_probably_code(s: str) -> bool:
    """Vero se sembra un codice (molte cifre/simboli) tipo 26P026-SP30, N°37.2, ecc."""
    if not s:
        return True
    s = s.strip().upper()
    # se contiene € o kg ecc non è un nome
    if any(x in s for x in ["€", "EURO", "IVA", "IMPONIBILE", "TOTALE"]):
        return True
    # troppe cifre
    digits = sum(ch.isdigit() for ch in s)
    if digits >= 3:
        return True
    # pattern codici tipici
    if re.search(r"\bN\s*[°\.]?\s*\d", s):
        return True
    if re.search(r"[A-Z]\d{2,}", s):
        return True
    if re.search(r"\d{2,}[A-Z]", s):
        return True
    if re.search(r"\d+\.\d+", s):  # 37.2
        return True
    if re.search(r"[A-Z]{1,5}\-\d{2,}", s):
        return True
    if re.search(r"\d{2,}\-[A-Z]{1,5}", s):
        return True
    return False


def score_candidate_name(raw: str, known_names: set[str]) -> int:
    """
    Punteggio euristico: più alto = più probabile nome pesce.
    """
    if not raw:
        return -10

    s = raw.strip().upper()
    s_clean = pulisci_nome_chirurgico(s)

    if not s_clean:
        return -10
    if is_probably_code(s_clean):
        return -10
    if any(w in s_clean for w in ["FAO", "LOTTO", "UM", "QTA", "Q.TÀ", "IMPONIBILE", "TOTALE", "IVA", "EURO", "€", "KG"]):
        return -10

    # base
    score = 0

    # premio se è tutto lettere/spazi (pochi simboli)
    if re.fullmatch(r"[A-ZÀ-Ü' ]+", s_clean):
        score += 10

    # numero parole ideale 1-4
    words = [w for w in s_clean.split() if w]
    if 1 <= len(words) <= 4:
        score += 12
    elif len(words) == 5:
        score += 6
    else:
        score -= 5

    # lunghezza ragionevole
    L = len(s_clean)
    if 4 <= L <= 22:
        score += 10
    elif 23 <= L <= 35:
        score += 5
    else:
        score -= 5

    # penalizza parole stopwords rimaste
    if any(w in STOPWORDS for w in words):
        score -= 8

    # premio se appare nella lista di nomi conosciuti (opzionale)
    if s_clean in known_names:
        score += 25

    return score


def best_name_from_window(window: str, known_names: set[str]) -> str:
    """
    Estrae candidati dal testo (finestra) e sceglie il migliore in base al punteggio.
    """
    up = (window or "").upper()

    # spezza in chunk su separatori tipici
    chunks = re.split(r"\n|\r|\t|\s{2,}|[|]|—|–|•|·|:", up)

    candidates = []
    for ch in chunks:
        ch = ch.strip(" -\u00a0")
        if not ch:
            continue

        # scarta chunk chiaramente tecnici
        if any(x in ch for x in ["IMPONIBILE", "TOTALE", "IVA", "EURO", "€", "PAGAMENTO", "DATA", "FATTURA", "CLIENTE"]):
            continue

        # pulisci
        ch2 = pulisci_nome_chirurgico(ch)

        # scarta se vuoto / codice
        if not ch2 or is_probably_code(ch2):
            continue

        sc = score_candidate_name(ch2, known_names)
        if sc > -5:
            candidates.append((sc, ch2))

    if not candidates:
        return ""

    # scegli il migliore; a parità, quello più corto (spesso più “nome puro”)
    candidates.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
    return candidates[0][1]


def find_scientific_names(text: str) -> list[str]:
    """
    Estrae possibili nomi scientifici:
    - preferisce quelli tra parentesi (come Hermes)
    - fallback su pattern binomiale (Genus species)
    """
    up = (text or "").upper()

    # 1) parentesi
    par = re.findall(r"\(([^)]+)\)", up)
    scis = []
    for p in par:
        p = p.strip()
        # scarta roba non scientifica
        if any(x in p for x in ["IVA", "EURO", "KG", "FAO", "IMPONIBILE", "TOTALE", "UM", "QTA", "Q.TÀ"]):
            continue
        # deve contenere almeno una lettera
        if not re.search(r"[A-Z]", p):
            continue
        # spesso lo scientifico è due parole o più (ma qui teniamo generico)
        # scarta se è tutto numeri/simboli
        if re.fullmatch(r"[\d\W_]+", p):
            continue
        scis.append(p)

    # 2) fallback pattern binomiale classico (non tutto maiuscolo, ma nel testo uppato lo perdiamo)
    # usiamo un pattern più permissivo: DUE PAROLE con 3+ lettere
    # (rischia falsi positivi, quindi lo usiamo solo se non troviamo nulla tra parentesi)
    if not scis:
        # qui lavoriamo sul testo originale (non upper) per preservare maiuscole/minuscole
        binom = re.findall(r"\b([A-Z][a-z]{2,}\s+[a-z]{3,})\b", text or "")
        scis = [b.strip() for b in binom]

    # dedup mantenendo ordine
    seen = set()
    out = []
    for s in scis:
        k = s.strip().upper()
        if k not in seen:
            seen.add(k)
            out.append(s.strip())
    return out


# -----------------------------
# PDF label
# -----------------------------

def disegna_etichetta(pdf: FPDF, p: dict) -> None:
    pdf.add_page()
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(
        w=pdf.epw,
        h=4,
        text="ITTICA CATANZARO - PALERMO",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)

    pdf.set_font("helvetica", "B", 15)
    pdf.multi_cell(w=pdf.epw, h=7, text=p["nome"], align="C")

    pdf.ln(1)
    f_sci = 9 if len(p["sci"]) < 25 else 7
    pdf.set_font("helvetica", "I", f_sci)
    pdf.multi_cell(w=pdf.epw, h=4, text=f"({p['sci']})", align="C")

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

    pdf.set_y(38)
    l_txt = f"LOTTO: {p['lotto']}"
    f_l = 12 if len(l_txt) < 20 else 10
    pdf.set_font("helvetica", "B", f_l)
    pdf.set_x((pdf.w - 80) / 2)
    pdf.cell(w=80, h=11, text=l_txt, border=1, align="C")

    pdf.set_y(54)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(w=pdf.epw, h=4, text=f"Data: {datetime.now().strftime('%d/%m/%Y')}", align="R")


# -----------------------------
# ESTRAZIONE "INTELLIGENTE"
# -----------------------------

def estrai_testo_pdf(file_like) -> str:
    try:
        file_like.seek(0)
    except Exception:
        pass

    reader = PdfReader(file_like)
    pages_text = []
    for p in reader.pages:
        pages_text.append((p.extract_text() or ""))
    testo = "\n".join(pages_text)

    # normalizzazioni comuni Hermes
    testo = testo.replace("FA0", "FAO")
    testo = testo.replace("ΑΙ", " AI ")
    return testo


def estrai_dati_multi_template(file_like, learned_map: dict[str, str]) -> list[dict]:
    testo_originale = estrai_testo_pdf(file_like)
    testo = testo_originale.upper()

    # lista nomi "conosciuti": quelli imparati + (se vuoi) puoi aggiungerne altri fissi
    known_names = set(n.upper() for n in learned_map.values() if n)

    risultati = []

    # Strategy A: split per LOTTO (quando c'è)
    blocchi = re.split(r"LOTTO\s*N?\.?\s*:?[\s]*", testo)
    has_lotto = len(blocchi) > 1

    if has_lotto:
        for i in range(len(blocchi) - 1):
            prima = blocchi[i]
            dopo = blocchi[i + 1]

            # lotto (prima cosa plausibile nel "dopo")
            lotto_match = re.search(r"^\s*([A-Z0-9\-_/]{3,})", dopo.strip())
            lotto = lotto_match.group(1) if lotto_match else "DA COMPILARE"
            lotto = re.sub(r"(CAS|KG|UM)$", "", lotto).strip()

            # scientifico: ultimo tra parentesi nel "prima"
            sci_match = re.findall(r"\(([^)]+)\)", prima)
            if not sci_match:
                continue
            sci = sci_match[-1].strip()
            if any(x in sci for x in ["IVA", "EURO", "KG", "FAO", "IMPONIBILE", "TOTALE", "UM", "QTA", "Q.TÀ"]):
                continue

            sci_key = sci.upper()

            # FAO
            fao_m = re.search(r"FAO\s*N?°?\s*([\d\.]+)", prima + " " + dopo)
            fao = fao_m.group(1) if fao_m else "37.2.1"

            # metodo
            metodo = "ALLEVATO" if any(x in (prima + " " + dopo) for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"

            # NOME:
            # 1) se l'abbiamo già imparato, usa quello
            if sci_key in learned_map and learned_map[sci_key].strip():
                nome = learned_map[sci_key].strip().upper()
            else:
                # 2) finestra robusta: prendi parte finale di "prima" + inizio di "dopo"
                window = (prima[-260:] + " " + dopo[:120]).upper()
                nome = best_name_from_window(window, known_names) or "DA COMPILARE"

            risultati.append({"nome": nome, "sci": sci, "lotto": lotto, "fao": fao, "metodo": metodo})

    # Strategy B: se LOTTO non c'è o qualcosa sfugge, prova per scientifico in generale
    if not risultati:
        scis = find_scientific_names(testo_originale)  # qui preferisce parentesi, fallback binomiale
        for sci in scis:
            sci_key = sci.upper()
            # trova occorrenza nel testo uppercase
            token = f"({sci_key})"
            idx = testo.find(token)
            if idx == -1:
                # fallback: prova senza parentesi (binomiale)
                idx = testo.find(sci_key)
            if idx == -1:
                continue

            # finestra
            window = testo[max(0, idx - 260): idx + 160]

            # lotto vicino
            lotto_m = re.search(r"LOTTO\s*N?\.?\s*:?[\s]*([A-Z0-9\-_/]{3,})", window)
            lotto = lotto_m.group(1) if lotto_m else "DA COMPILARE"
            lotto = re.sub(r"(CAS|KG|UM)$", "", lotto).strip()

            fao_m = re.search(r"FAO\s*N?°?\s*([\d\.]+)", window)
            fao = fao_m.group(1) if fao_m else "37.2.1"

            metodo = "ALLEVATO" if any(x in window for x in ["ALLEVATO", "ACQUACOLTURA"]) else "PESCATO"

            if sci_key in learned_map and learned_map[sci_key].strip():
                nome = learned_map[sci_key].strip().upper()
            else:
                nome = best_name_from_window(window, known_names) or "DA COMPILARE"

            risultati.append({"nome": nome, "sci": sci, "lotto": lotto, "fao": fao, "metodo": metodo})

    # dedup (stesso sci+lotto)
    seen = set()
    out = []
    for r in risultati:
        k = (r["sci"].upper(), r["lotto"].upper())
        if k not in seen:
            seen.add(k)
            out.append(r)

    return out


@st.cache_data(show_spinner=False)
def estrai_cached(file_bytes: bytes, learned_json: str) -> list[dict]:
    learned_map = json.loads(learned_json) if learned_json else {}
    return estrai_dati_multi_template(BytesIO(file_bytes), learned_map)


# -----------------------------
# UI
# -----------------------------

st.title("⚓ FishLabel Scanner PRO")

# init memoria "imparata"
if "learned_map" not in st.session_state:
    st.session_state.learned_map = {}  # chiave: SCI (upper) -> nome commerciale

with st.expander("🧠 Memoria Nomi (opzionale)"):
    cA, cB = st.columns([1, 1])

    # export
    learned_export = json.dumps(st.session_state.learned_map, ensure_ascii=False, indent=2)
    cA.download_button(
        "⬇️ Scarica memoria nomi (JSON)",
        data=learned_export.encode("utf-8"),
        file_name="memoria_nomi_pesci.json",
        mime="application/json",
    )

    # import
    up = cB.file_uploader("⬆️ Carica memoria nomi (JSON)", type=["json"], key="mem_up")
    if up is not None:
        try:
            loaded = json.loads(up.getvalue().decode("utf-8"))
            if isinstance(loaded, dict):
                # normalizza chiavi SCI
                norm = {k.upper().strip(): str(v).upper().strip() for k, v in loaded.items()}
                st.session_state.learned_map.update(norm)
                st.success("Memoria importata ✅")
        except Exception as e:
            st.error("JSON non valido.")

# reset
if st.button("🗑️ SVUOTA TUTTO E RICOMINCIA", type="primary"):
    st.session_state.pop("p_list", None)
    st.session_state.pop("last_f", None)
    st.rerun()

file = st.file_uploader("Carica Fattura PDF", type="pdf")

if file:
    file_bytes = file.getvalue()
    learned_json = json.dumps(st.session_state.learned_map, ensure_ascii=False)

    # ricalcola se cambia file
    if "last_f" not in st.session_state or st.session_state.last_f != file.name:
        st.session_state.p_list = estrai_cached(file_bytes, learned_json)
        st.session_state.last_f = file.name

    if st.session_state.p_list:
        st.success(f"✅ Trovati {len(st.session_state.p_list)} prodotti.")

        # PDF unico
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

        # edit + apprendimento
        for i, p in enumerate(st.session_state.p_list):
            header = f"📦 {p['nome']} - {p['lotto']}"
            with st.expander(header):
                c1, c2 = st.columns(2)
                new_nome = c1.text_input("Nome Pesce", p["nome"], key=f"nm_{i}")
                new_lotto = c2.text_input("Lotto", p["lotto"], key=f"lt_{i}")

                # salva update
                p["nome"] = new_nome.upper().strip() if new_nome else p["nome"]
                p["lotto"] = new_lotto.upper().strip() if new_lotto else p["lotto"]

                # "impara" sullo scientifico
                sci_key = p["sci"].upper().strip()
                if p["nome"] and p["nome"] != "DA COMPILARE":
                    st.session_state.learned_map[sci_key] = p["nome"]

                # PDF singolo
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
        st.warning("⚠️ Non ho trovato prodotti. Prova con un PDF diverso o template troppo diverso.")
