"""
Pantalla de conexion (login).

Pide el token de JaaS y, solo cuando hace falta IA (el Bug Logger), la Groq API
Key. Los guarda cifrados en este equipo con keyring, verifica la conexion y deja
los datos de la sesion listos para el resto de la app.

login_gate(need_groq) dibuja la pantalla de conexion si todavia no hay sesion y
devuelve True cuando ya esta conectado, para que la app siga su curso:

    if not macondo_login.login_gate(need_groq=True):
        st.stop()
"""

import streamlit as st
import core  # nucleo compartido: token, Groq key y verificacion de conexion


def _connect(jira_token, remember, need_groq, groq_key):
    """Verifica el token contra Jira y, si es valido, guarda la sesion. Devuelve True/False."""
    if not jira_token:
        st.error(f"Falta el PAT Token de {core.SITE_NAME}.")
        return False

    with st.spinner(f"Conectando a {core.SITE_NAME}..."):
        ok, display_name, username = core.test_connection(jira_token)

    if not ok:
        st.error("Token invalido. Revisa que lo copiaste completo y que no haya expirado.")
        return False

    if remember:
        core.save_jira_token(jira_token)

    # Datos que el resto de la app usa para hablar con Jira y mostrar quien eres.
    st.session_state.jira_token = jira_token
    st.session_state.reporter = username
    st.session_state.user_display_name = display_name
    if need_groq:
        st.session_state.groq_client = core.make_groq_client(groq_key)
    st.session_state.connected = True
    return True


def logout(forget_groq=False):
    """
    Cierra la sesion: borra el token guardado en este equipo (y la Groq key si se pide)
    y limpia todo lo de la sesion, para volver a la pantalla de conexion.
    """
    core.delete_jira_token()
    if forget_groq:
        core.delete_groq_key()
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def session_panel():
    """Barra lateral con quien esta conectado y el boton para cerrar sesion."""
    with st.sidebar:
        st.markdown("**Sesión**")
        st.caption(f"Conectado como **{st.session_state.get('user_display_name') or st.session_state.get('reporter')}**")
        st.caption(f"{core.SITE_NAME}: {core.JIRA_URL}")
        forget_groq = st.checkbox("Olvidar también la Groq API Key", key="logout_forget_groq",
                                  help="Útil si este computador lo usa otra persona.")
        if st.button("Cerrar sesión", key="btn_logout", use_container_width=True):
            logout(forget_groq)
            st.rerun()
        st.caption(f"Al cerrar sesión se borra tu token de {core.SITE_NAME} de este equipo. "
                   "Lo que Macondo aprendió de tus proyectos se conserva.")


def login_gate(need_groq):
    """
    Dibuja la conexion si no hay sesion. Devuelve True cuando ya esta conectado.
    'need_groq' es True cuando la app usa IA (el Bug Logger).
    """
    # Si ya nos conectamos en esta sesion, no mostramos nada: seguimos de largo.
    if st.session_state.get("connected"):
        return True

    st.subheader("Conectar")

    if not core.JIRA_URL:
        st.error(
            "Falta config.json, o no tiene \"jira_url\". Debe estar en la misma carpeta que "
            "macondo_app.py (o junto al .exe). Descarga de nuevo el repo: ya viene incluido."
        )
        return False

    saved_token = core.load_jira_token()

    # --- Groq API Key (solo si la app usa IA) -----------------------------
    groq_key = core.get_groq_key() if need_groq else None
    if need_groq and not groq_key:
        st.info("Primera vez en este equipo: pega tu Groq API Key una sola vez, queda guardada cifrada.")
        groq_key_input = st.text_input("Groq API Key", type="password", key="groq_key_input")
        if st.button("Guardar Groq API Key", key="btn_save_groq"):
            if groq_key_input:
                core.save_groq_key(groq_key_input)
                st.rerun()
            else:
                st.error("Pega una key antes de guardar.")

    # --- Token de Jira ----------------------------------------------------
    if saved_token:
        st.success(f"Token de {core.SITE_NAME} guardado en este equipo: no hace falta pegarlo de nuevo.")
        if st.button("Olvidar token", key="btn_forget"):
            core.delete_jira_token()
            st.rerun()
        jira_token = saved_token
        remember = False  # ya esta guardado, no hay nada que volver a guardar
    else:
        jira_token = st.text_input(f"{core.SITE_NAME} PAT Token", type="password", key="jira_token_input")
        remember = st.checkbox(
            "Recordar en este equipo (queda cifrado)", value=True
        )

    # El boton Conectar se bloquea si falta la Groq key en una app que la necesita.
    disabled = need_groq and not groq_key
    if st.button("Conectar", type="primary", disabled=disabled, key="btn_connect"):
        if _connect(jira_token, remember, need_groq, groq_key):
            st.rerun()

    return st.session_state.get("connected", False)
