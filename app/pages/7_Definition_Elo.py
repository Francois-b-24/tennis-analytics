"""Page Définition Elo : affiche le PDF de définition du rating Elo."""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
_ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")
os.environ.setdefault("ROOT_PATH", str(_ROOT))

_SRC = _ROOT / "src"
for path in (_APP_DIR, _ROOT, _SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import streamlit as st

from components.widgets import inject_global_css, page_info

st.set_page_config(page_title="Définition Elo — Tennis Analytics", layout="wide")
inject_global_css()

st.title("Définition du rating Elo")
page_info(
    "Document de référence détaillant le système de notation Elo appliqué au tennis : "
    "principes mathématiques, ajustements par surface, facteur K adaptatif et décroissance d'inactivité."
)

PDF_PATH = _ROOT / "docs" / "elo_tennis_definition.pdf"

if not PDF_PATH.exists():
    st.error(
        "Le document PDF est introuvable. "
        "Vérifiez la présence du fichier `docs/elo_tennis_definition.pdf`."
    )
    st.stop()

# Lecture du PDF en base64 pour affichage inline
with PDF_PATH.open("rb") as f:
    pdf_bytes = f.read()

pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

# Affichage embarqué (visionneuse navigateur)
st.markdown(
    f"""
    <iframe
        src="data:application/pdf;base64,{pdf_b64}"
        width="100%"
        height="800"
        style="border: 1px solid #d0d0d0; border-radius: 8px;"
        type="application/pdf">
    </iframe>
    """,
    unsafe_allow_html=True,
)

# Bouton de téléchargement
st.download_button(
    label="📄 Télécharger le PDF",
    data=pdf_bytes,
    file_name="elo_tennis_definition.pdf",
    mime="application/pdf",
)
