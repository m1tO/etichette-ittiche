import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from fpdf import FPDF
import json
import os
from datetime import datetime
import base64

st.set_page_config(page_title="Ittica Catanzaro AI", layout="wide")

# --- 1. AUTOMAZIONE MEMORIA JSON ---
MEMORIA_FILE = "memoria_nomi.json"

def carica_memoria():
    if os.path.exists(MEMORIA_FILE):
        with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salva_memoria(memoria):
    with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=4)

if "learned_map" not in st.session_state:
    st.session_state.learned_map = carica_memoria()

# --- 2. AUTOMAZIONE API KEY ---
# Cerca la chiave nei secrets di Streamlit
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
else:
    st.error("⚠️ Chiave API non trovata nei Secrets! Inseriscila per continuare.")
    st.stop()

def chiedi_all_ai(testo_pdf):
    # Usiamo il modello 2.5/3 come dai tuoi screenshot
    model = genai.GenerativeModel('gemini-2.5-flash') 
    prompt = f"Analizza questa fattura ittica. Estrai i prodotti in JSON (nome, sci, lotto, fao, metodo). Testo: {testo_pdf}"
    response = model.generate_content(prompt)
    return json.loads(response.text.replace('```json', '').replace('```', '').strip())

# --- INTERFACCIA ---
st.title("⚓ Scanner Ittico Intelligente")

file = st.file_uploader("Trascina qui la fattura e basta", type="pdf")

if file:
    # Reset se file nuovo
    if "last_f" not in st.session_state or st.session_state.last_f != file.name:
        st.session_state.p_list = None
        st.session_state.last_f = file.name

    if st.button("🚀 ANALIZZA ORA", type="primary"):
        reader = PdfReader(file)
        testo = " ".join([p.extract_text() for p in reader.pages])
        prodotti_ai = chiedi_all_ai(testo)
        
        # Applica memoria storica
        for p in prodotti_ai:
            sci_key = p['sci'].upper().strip()
            if sci_key in st.session_state.learned_map:
                p['nome'] = st.session_state.learned_map[sci_key]
        
        st.session_state.p_list = prodotti_ai

    if st.session_state.get("p_list"):
        # Mostra i risultati e permetti modifiche che l'app "imparerà"
        for i, p in enumerate(st.session_state.p_list):
            with st.expander(f"🐟 {p['nome']}"):
                nuovo_nome = st.text_input("Nome", p['nome'], key=f"n_{i}")
                if nuovo_nome != p['nome']:
                    st.session_state.learned_map[p['sci'].upper().strip()] = nuovo_nome
                    salva_memoria(st.session_state.learned_map) # Salva subito su file!
                    p['nome'] = nuovo_nome
                
                # Anteprima e stampa qui sotto...