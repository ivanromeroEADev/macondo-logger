"""
Macondo Logger - logueo de bugs en JaaS con ayuda de IA.

Punto de entrada de la app. Junta tres piezas:
  - el tema Macondo (macondo_theme)
  - la conexion a JaaS + Groq (macondo_login)
  - la pantalla del Bug Logger (bug_logger_ui)

Para correrla en modo desarrollo:  python -m streamlit run macondo_app.py
"""

import streamlit as st

import macondo_theme
import macondo_login
import bug_logger_ui

macondo_theme.apply("Macondo Logger")
macondo_theme.header("Macondo Logger")

# El Bug Logger usa IA, asi que la conexion pide tambien la Groq API Key.
if not macondo_login.login_gate(need_groq=True):
    st.stop()

macondo_login.session_panel()
bug_logger_ui.render()
