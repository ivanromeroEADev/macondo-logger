"""
Tema visual compartido de Macondo.

La paleta (amarillo Macondo, marron, beige), la tipografia y la cabecera con el
logo viven aqui, en un solo lugar.

Uso en cada app (apply primero, como primera llamada a Streamlit; luego header):
    import macondo_theme
    macondo_theme.apply("Macondo Logger")
    macondo_theme.header("Macondo Logger")
"""

import os
import sys

import streamlit as st

# --- Colores -----------------------------------------------------------------
# Amarillo Macondo. MOSTAZA_OSCURO es el mismo tono mas oscuro
# para hovers y bordes.
MOSTAZA = "#f0b802"
MOSTAZA_OSCURO = "#c28f00"
MARRON = "#3B2F1E"
BEIGE = "#F5E6C8"
FONDO = "#FFFDF7"

# --- Tipografia --------------------------------------------------------------
# Fuentes de Google Fonts. Estan en una variable para cambiarlas facil
# (alternativas: "Baloo 2", "Exo 2", "Chakra Petch").
FUENTE_TITULO = "Fredoka"      # titulos y el nombre de la app
FUENTE_TEXTO = "Inter"         # cuerpo: limpia y legible

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family={FUENTE_TITULO.replace(' ', '+')}:wght@400;500;600;700&family={FUENTE_TEXTO.replace(' ', '+')}:wght@400;500;600&display=swap');

:root {{
    --macondo-mostaza: {MOSTAZA};
    --macondo-mostaza-oscuro: {MOSTAZA_OSCURO};
    --macondo-marron: {MARRON};
    --macondo-beige: {BEIGE};
}}

/* Tipografia del cuerpo. Se aplica a los contenedores de texto, no con '*',
   para no romper los iconos (que usan su propia fuente de iconos). */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stSidebar"],
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] .stMarkdown,
div[data-baseweb="select"], input, textarea, button {{
    font-family: '{FUENTE_TEXTO}', 'Segoe UI', system-ui, sans-serif;
}}

/* Titulos y encabezados. */
h1, h2, h3, h4, .macondo-title {{
    font-family: '{FUENTE_TITULO}', '{FUENTE_TEXTO}', sans-serif !important;
    letter-spacing: 0.3px;
}}

/* El nombre de la app, al lado del logo. */
.macondo-title {{
    color: var(--macondo-mostaza-oscuro);
    font-weight: 700;
    font-size: 2.1rem;
    margin: 0;
    line-height: 1.1;
}}

/* Botones primarios (Conectar, Generar con IA, Confirmar y enviar). */
div.stButton > button[kind="primary"] {{
    background-color: var(--macondo-mostaza);
    border-color: var(--macondo-mostaza-oscuro);
    color: var(--macondo-marron);
    font-weight: 600;
}}
div.stButton > button[kind="primary"]:hover {{
    background-color: var(--macondo-mostaza-oscuro);
    border-color: var(--macondo-mostaza-oscuro);
    color: #FFFDF7;
}}

/* Botones secundarios: mismo tono pero solo el contorno. */
div.stButton > button[kind="secondary"] {{
    border-color: var(--macondo-mostaza-oscuro);
    color: var(--macondo-marron);
}}
div.stButton > button[kind="secondary"]:hover {{
    background-color: var(--macondo-beige);
    border-color: var(--macondo-mostaza-oscuro);
}}

/* Mensajes de estado en tonos calidos, en vez del rojo/verde/azul de Streamlit. */
div[data-testid="stAlertContainer"] {{ border-radius: 6px; }}
div[data-testid="stAlertContainer"][class*="success"],
div[data-baseweb="notification"][kind="positive"] {{
    background-color: #EFE6C8; color: var(--macondo-marron);
}}
div[data-testid="stAlertContainer"][class*="warning"] {{
    background-color: #F5DDA0; color: var(--macondo-marron);
}}
div[data-testid="stAlertContainer"][class*="error"] {{
    background-color: #E8C9A0; color: var(--macondo-marron);
}}

/* Spinner en amarillo. */
div[data-testid="stSpinner"] > div {{ border-top-color: var(--macondo-mostaza) !important; }}

/* Pestañas: la activa en amarillo. */
button[data-baseweb="tab"][aria-selected="true"] {{ color: var(--macondo-mostaza-oscuro); }}
div[data-baseweb="tab-highlight"] {{ background-color: var(--macondo-mostaza) !important; }}

/* El logo de la cabecera, con esquinas redondeadas. */
.macondo-logo img {{ border-radius: 12px; }}
</style>
"""


def apply(page_title, page_icon="🦋"):
    """
    Configura la pagina e inyecta el CSS de Macondo.
    Debe ser la PRIMERA llamada a Streamlit de la app (set_page_config solo se
    puede usar una vez y tiene que ir antes que cualquier otro elemento).
    """
    st.set_page_config(page_title=page_title, page_icon=page_icon, layout="centered", initial_sidebar_state="expanded")
    st.markdown(_CSS, unsafe_allow_html=True)


def _logo_path():
    """Ruta al logo, funcione desde el codigo o desde el .exe (carpeta de PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "macondo_logo.jpg")


def header(title):
    """Dibuja la cabecera: la mariposa de logo a la izquierda y el nombre de la app."""
    logo = _logo_path()
    col_logo, col_title = st.columns([1, 5], vertical_alignment="center")
    if os.path.exists(logo):
        col_logo.markdown('<div class="macondo-logo">', unsafe_allow_html=True)
        col_logo.image(logo)
        col_logo.markdown("</div>", unsafe_allow_html=True)
    col_title.markdown(f"<h1 class='macondo-title'>{title}</h1>", unsafe_allow_html=True)
