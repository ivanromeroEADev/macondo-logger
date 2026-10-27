"""
Bug Logger - interfaz (la pantalla para loguear tickets en JaaS con ayuda de IA).

Todo vive en una funcion render() que llama macondo_app.py. La conexion
(token + Groq key) la resuelve macondo_login ANTES de llamar a render().

El flujo tiene cuatro etapas, guardadas en st.session_state["bl_stage"]:
  project  -> elegir el proyecto
  form     -> elegir el tipo de ticket y llenar los campos del proyecto
  preview  -> revisar y editar el summary/description antes de enviar
  done     -> ticket creado, con adjuntos y avisos
"""

import streamlit as st

import core

SITE = core.SITE_NAME

# Etiqueta con la que cada dato conocido se le pasa a la IA.
CONTEXT_LABELS = {
    "changelist": "CL",
    "branch": "Branch",
    "pillar": "Pillar Team",
    "game_spine": "Game Spine",
    "platform": "Platform",
    "repro_rate": "Repro Rate",
    "player_impact": "Player Impact level",
    "severity": "Severity",
    "player_path": "Player Path",
    "activity": "Activity",
    "bug_type": "Bug Type",
}
OTHER_BRANCH = "Otra (escribirla)"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _project_label(project):
    tags = [tag for tag, on in (("reciente", project["recent"]), ("lead", project["is_lead"])) if on]
    return f"{project['key']} — {project['name']}" + (f"   [{', '.join(tags)}]" if tags else "")


def _load_projects():
    """Proyectos donde puedes crear tickets. Si JaaS no deja listarlos, usa la lista de respaldo."""
    try:
        projects, verified = core.list_user_projects(st.session_state.jira_token, st.session_state.reporter)
    except Exception:
        projects = [
            {"key": k, "name": n, "can_create": None, "is_lead": False, "recent": False}
            for k, n in core.FALLBACK_PROJECTS.items()
        ]
        verified = False
    st.session_state.bl_projects = projects
    st.session_state.bl_projects_verified = verified


def _open_project(project_key, issuetype_id=None):
    """Lee los campos del proyecto (para ese tipo de ticket) y pasa al formulario."""
    with st.spinner(f"Leyendo los campos de {project_key}..."):
        meta = core.load_project_meta(st.session_state.jira_token, st.session_state.reporter, project_key, issuetype_id)
    if meta is None:
        st.error(
            f"No pude leer los campos de {project_key}. Puede que no tengas permiso para crear tickets ahí "
            "o que el proyecto no tenga ningún ticket para tomar como referencia."
        )
        return False
    st.session_state.bl_meta = meta
    st.session_state.bl_stage = "form"
    return True


def _init_state():
    defaults = {
        "bl_stage": "project",
        "bl_meta": None,
        "bl_ticket": None,
        "bl_was_corrected": False,
        "bl_projects": None,
        "bl_projects_verified": True,
        "bl_pending_files": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    if st.session_state.bl_projects is None:
        with st.spinner("Buscando tus proyectos..."):
            _load_projects()


def _show(value):
    """Valor de un campo como texto, para el preview y para la IA."""
    if isinstance(value, tuple):        # lista en cascada: (padre, hijo)
        return " / ".join(str(v) for v in value if v)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------
# etapa: elegir proyecto
# ---------------------------------------------------------------------------

def _stage_project():
    st.subheader("Elige el proyecto")

    if not st.session_state.bl_projects_verified:
        st.warning(
            f"No pude verificar en cuáles proyectos tienes permiso para crear tickets, así que aparecen todos los que "
            f"{SITE} me deja ver. Si eliges uno donde no puedes crear, te aviso al abrirlo."
        )

    text_filter = st.text_input("Filtrar por clave o nombre", key="bl_project_filter").strip().lower()
    visible = [p for p in st.session_state.bl_projects if text_filter in f"{p['key']} {p['name']}".lower()]
    st.caption(f"{len(visible)} de {len(st.session_state.bl_projects)} proyectos · los recientes y los que lideras van primero")

    if visible:
        keys_by_label = {_project_label(p): p["key"] for p in visible}
        choice = keys_by_label[st.selectbox("Proyecto", list(keys_by_label), key="bl_project_choice")]
    else:
        choice = None
        st.info("Ningún proyecto coincide con el filtro.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Usar este proyecto", type="primary", disabled=not choice, key="bl_btn_use_project"):
            if _open_project(choice):
                st.rerun()
    with col_b:
        if st.button("Actualizar lista", key="bl_btn_reload_projects"):
            with st.spinner("Buscando tus proyectos..."):
                _load_projects()
            st.rerun()

    with st.expander("¿No ves tu proyecto? Escribe la clave"):
        manual = st.text_input("Clave del proyecto (ej. SK8)", key="bl_manual_project").strip().upper()
        if st.button("Abrir por clave", disabled=not manual, key="bl_btn_manual_project"):
            if _open_project(manual):
                st.rerun()


# ---------------------------------------------------------------------------
# etapa: formulario
# ---------------------------------------------------------------------------

def _render_field(field, box, project, key_prefix):
    """Dibuja un campo de JaaS segun su tipo y devuelve lo que se lleno."""
    label = field["name"] + (" *" if field["required"] else "")
    key = f"{key_prefix}_{field['id']}"
    kind, options = field["kind"], field["options"]
    blank = [] if field["required"] else ["(sin especificar)"]

    # Branch: sugerencias por proyecto desde config.json, o texto libre
    if field["logical"] == "branch" and kind in ("labels", "text"):
        suggestions = core.branch_suggestions(project)
        if suggestions:
            picked = box.selectbox(label, blank + suggestions + [OTHER_BRANCH], key=key)
            if picked == OTHER_BRANCH:
                return box.text_input("Branch (escríbela)", key=key + "_free")
            return None if picked == "(sin especificar)" else picked
        return box.text_input(label, key=key, placeholder="ej. main")

    # Bug Type como texto libre: opciones desde config.json
    if field["logical"] == "bug_type" and kind in ("labels", "text") and core.BUG_TYPES:
        picked = box.selectbox(label, blank + core.BUG_TYPES, key=key)
        return None if picked == "(sin especificar)" else picked

    if field["logical"] == "changelist":
        return box.text_input(label, key=key, placeholder="ej. 28452329").strip() or None

    if kind == "text":
        return box.text_input(label, key=key) or None
    if kind == "number":
        return box.number_input(label, value=None, key=key)
    if kind in ("date", "datetime"):
        picked = box.date_input(label, value=None, key=key)
        return picked.isoformat() if picked else None
    if kind == "select":
        picked = box.selectbox(label, (blank or [""]) + sorted(options), key=key, index=0)
        return None if picked in ("", "(sin especificar)") else picked
    if kind == "multiselect":
        return box.multiselect(label, sorted(options), key=key)
    if kind == "cascade":
        parent = box.selectbox(label, [""] + sorted(options), key=key)
        if not parent:
            return None
        children = sorted(options[parent]["children"])
        child = box.selectbox(f"{field['name']} (detalle)", [""] + children, key=key + "_child") if children else ""
        return (parent, child or None)
    if kind == "labels":
        return box.text_input(label, key=key, help="Separadas por coma") or None
    if kind in ("user", "group"):
        return box.text_input(label, key=key, help="Usuario de JaaS (ej. el correo antes de @ o el username)") or None
    if kind in ("users", "groups"):
        return box.text_input(label, key=key, help="Usuarios separados por coma") or None
    return None


def _stage_form():
    meta = st.session_state.bl_meta
    project = meta["project"]

    # --- barra superior ---
    top_a, top_b, top_c = st.columns([3, 1.4, 1.6])
    top_a.caption(f"conectado como {st.session_state.user_display_name}")
    if top_b.button("Cambiar proyecto", key="bl_btn_change_project"):
        st.session_state.bl_stage = "project"
        st.rerun()
    if top_c.button("🔄 Refrescar campos", key="bl_btn_refresh"):
        if _open_project(project, meta["issuetype_id"]):
            st.rerun()

    st.markdown(f"### {project}")

    # --- tipo de ticket (Bug por defecto) ---
    issuetypes = meta.get("issuetypes") or []
    if len(issuetypes) > 1:
        names = [t["name"] for t in issuetypes]
        current = names.index(meta["issuetype_name"]) if meta["issuetype_name"] in names else 0
        picked = st.selectbox("Issue Type", names, index=current, key=f"bl_{project}_issuetype")
        picked_id = issuetypes[names.index(picked)]["id"]
        if picked_id != meta["issuetype_id"]:
            if _open_project(project, picked_id):
                st.rerun()
    else:
        st.caption(f"Issue Type: **{meta['issuetype_name']}**")

    if meta["source"] != "createmeta":
        st.warning(
            f"No pude leer la pantalla de creación de {project}; usé el ticket {meta['ref_ticket']} como referencia. "
            f"Si {SITE} rechaza algún campo opcional, se omite y te aviso."
        )

    # --- de donde esta aprendiendo ---
    learning = core.learning_status(project, meta.get("style"))
    parts = ["plantilla Skate"]
    if learning["real_tickets"]:
        parts.append(f"{learning['real_tickets']} ticket(s) reales {learning['real_source']}")
    if learning["corrections"]:
        parts.append(f"{learning['corrections']} corrección(es) tuyas")
    st.caption(f"🦋 Escribe con: " + " + ".join(parts))

    acc = core.accuracy_report(project)
    if acc["sent"]:
        st.caption(
            f"📊 Accuracy en {project}: {acc['accuracy_pct']:.0f}% "
            f"({acc['unedited']} de {acc['sent']} enviados sin reescribir) · "
            f"parecido promedio al borrador: {acc['avg_similarity_pct']:.0f}%"
        )

    blocking = [f["name"] for f in meta["unsupported_fields"] if f["required"]]
    if blocking:
        st.error(
            "Este proyecto exige campos que la app todavía no sabe llenar: " + ", ".join(blocking) +
            f". Es probable que {SITE} rechace el ticket; créalo desde {SITE} o avísale a quien mantiene Macondo."
        )

    # --- campos del proyecto ---
    key_prefix = f"bl_{project}_{meta['issuetype_id']}"
    main = [f for f in meta["form_fields"] if f["required"] or f["logical"]]
    others = [f for f in meta["form_fields"] if not (f["required"] or f["logical"])]
    values = {}

    st.subheader("Campos")
    st.caption("Los marcados con * son obligatorios en este proyecto.")
    cols = st.columns(2)
    for i, field in enumerate(main):
        values[field["id"]] = _render_field(field, cols[i % 2], project, key_prefix)
    feature = cols[len(main) % 2].text_input(
        "Feature (opcional)", key=f"{key_prefix}_feature",
        placeholder="ej. Challenges", help="No es un campo de JaaS: va en la nota de la descripción.",
    )

    if others:
        with st.expander(f"Otros campos de {project} ({len(others)})"):
            for field in others:
                values[field["id"]] = _render_field(field, st, project, key_prefix)

    missing = core.missing_required(meta, values)
    cl_field = next((f for f in meta["form_fields"] if f["logical"] == "changelist"), None)
    cl_value = values.get(cl_field["id"]) if cl_field else None
    if cl_field and cl_field["kind"] == "number" and cl_value:
        try:
            float(cl_value)
        except ValueError:
            missing.append(f"{cl_field['name']} (debe ser un número)")

    # --- descripcion libre + adjuntos ---
    st.subheader("Describe el bug")
    raw_bug = st.text_area("Bug", height=120, key="bl_raw_bug", placeholder="Qué está pasando, dónde, y qué esperabas en cambio")

    st.markdown("**Adjuntos** (opcional: logs, videos, imágenes)")
    uploaded = st.file_uploader("Arrastra archivos o haz clic para elegir", accept_multiple_files=True,
                                label_visibility="collapsed", key="bl_file_uploader")
    pasted = st.file_uploader("O pega un screenshot (Ctrl+V): haz clic aquí primero y después pega",
                              accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="bl_paste_uploader")
    all_files = list(uploaded or []) + list(pasted or [])
    if all_files:
        st.caption(f"{len(all_files)} archivo(s) listos: " + ", ".join(f.name for f in all_files))

    if missing:
        st.caption("Faltan campos obligatorios: " + ", ".join(missing))

    # --- generar con IA ---
    if st.button("Generar con IA", type="primary", disabled=not (raw_bug and not missing), key="bl_btn_generate"):
        by_logical = {f["logical"]: values.get(f["id"]) for f in meta["form_fields"] if f["logical"]}
        context = {CONTEXT_LABELS[k]: _show(v) for k, v in by_logical.items() if k in CONTEXT_LABELS and v}
        if feature:
            context["Feature"] = feature
        style = meta.get("style")
        with st.spinner("Escribiendo summary y description..."):
            summary = core.generate_summary(
                st.session_state.groq_client, raw_bug, project, style,
                prefix_parts=[_show(by_logical.get("pillar")), _show(by_logical.get("game_spine"))],
            )
            description = core.generate_description(st.session_state.groq_client, project, raw_bug, context, style)
        core.record_generation(project)

        st.session_state.bl_pending_files = [(f.name, f.getvalue(), f.type) for f in all_files]
        st.session_state.bl_ticket = {
            "raw_bug": raw_bug,
            "feature": feature,
            "pillar": _show(by_logical.get("pillar")) or None,
            "values": {fid: v for fid, v in values.items() if not core._empty(v)},
            "summary": summary,
            "description": description,
            "generated_summary": summary,
            "generated_description": description,
        }
        st.session_state.bl_was_corrected = False
        st.session_state.bl_stage = "preview"
        st.rerun()


# ---------------------------------------------------------------------------
# etapa: preview editable
# ---------------------------------------------------------------------------

def _stage_preview():
    ticket = st.session_state.bl_ticket
    meta = st.session_state.bl_meta
    project = meta["project"]

    if project in core.TEST_PROJECTS:
        st.info(f"Enviando a **{project}** (proyecto de pruebas) · {meta['issuetype_name']}")
    else:
        st.warning(f"Enviando a **{project}** · {meta['issuetype_name']}. Revisa bien antes de confirmar.")

    st.subheader("Preview")
    edited_summary = st.text_input("Summary", value=ticket["summary"], key="bl_edit_summary")
    edited_description = st.text_area("Description", value=ticket["description"], height=350, key="bl_edit_description")

    if edited_summary != ticket["summary"] or edited_description != ticket["description"]:
        st.session_state.bl_was_corrected = True

    with st.expander("Campos"):
        names = {f["id"]: f["name"] for f in meta["form_fields"]}
        shown = [(names.get(fid, fid), _show(v)) for fid, v in ticket["values"].items()]
        if ticket.get("feature"):
            shown.append(("Feature (en la nota)", ticket["feature"]))
        cols = st.columns(2)
        for i, (label, value) in enumerate(shown):
            cols[i % 2].markdown(f"**{label}:** {value}")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("↩️ Volver al formulario", key="bl_btn_restart"):
            st.session_state.bl_stage = "form"
            st.session_state.bl_ticket = None
            st.rerun()

    with col2:
        if st.button("✅ Confirmar y enviar", type="primary", key="bl_btn_submit"):
            ticket["summary"] = edited_summary
            ticket["description"] = edited_description
            with st.spinner(f"Enviando a {SITE}..."):
                res, warnings = core.submit_ticket(st.session_state.jira_token, ticket, meta)

            if res.status_code == 201:
                key = res.json().get("key")
                st.session_state.bl_last_key = key
                st.session_state.bl_last_warnings = warnings
                pending = st.session_state.get("bl_pending_files", [])
                st.session_state.bl_attach_results = core.attach_files(st.session_state.jira_token, key, pending) if pending else []

                # Solo se guarda como ejemplo cuando corregiste algo: eso es lo que enseña.
                if st.session_state.bl_was_corrected:
                    core.save_example(project, ticket["raw_bug"], ticket["pillar"], ticket["feature"],
                                      edited_description, summary=edited_summary)
                core.record_submission(project, st.session_state.bl_was_corrected,
                                       ticket.get("generated_description", ""), edited_description)
                st.session_state.bl_stage = "done"
                st.rerun()
            else:
                st.error("Falló el envío:")
                st.code(core.explain_error(res, meta))

    with col3:
        st.caption("Si corriges el Summary o la Description, la corrección se guarda para que los próximos borradores salgan mejor.")


# ---------------------------------------------------------------------------
# etapa: listo
# ---------------------------------------------------------------------------

def _stage_done():
    key = st.session_state.bl_last_key
    st.success(f"**{key}** creado")
    st.markdown(f"[Abrir en {SITE}]({core.browse_url(key)})")

    warnings = st.session_state.get("bl_last_warnings", [])
    if warnings:
        with st.expander(f"⚠️ {len(warnings)} campo(s) no se pudieron aplicar", expanded=True):
            st.caption("El ticket se creó igual, sin estos campos:")
            for warning in warnings:
                st.text(warning)

    attach_results = st.session_state.get("bl_attach_results", [])
    if attach_results:
        ok_count = sum(1 for _, ok, _ in attach_results if ok)
        fail_count = len(attach_results) - ok_count
        if fail_count == 0:
            st.caption(f"📎 {ok_count} adjunto(s) subido(s) correctamente.")
        else:
            with st.expander(f"📎 {ok_count} adjunto(s) OK, {fail_count} fallaron", expanded=True):
                for filename, ok, error in attach_results:
                    st.caption(f"✅ {filename}" if ok else f"❌ {filename}: {error}")

    col1, col2 = st.columns(2)
    if col1.button("Loguear otro bug", key="bl_btn_another"):
        st.session_state.bl_stage = "form"
        st.session_state.bl_ticket = None
        st.session_state.bl_pending_files = []
        st.rerun()
    if col2.button("Cambiar proyecto", key="bl_btn_done_change_project"):
        st.session_state.bl_stage = "project"
        st.session_state.bl_ticket = None
        st.session_state.bl_pending_files = []
        st.rerun()


def render():
    """Dibuja el Bug Logger. Da por hecho que ya hay sesion (ver macondo_login)."""
    _init_state()
    stage = st.session_state.bl_stage
    if stage == "project":
        _stage_project()
    elif stage == "form":
        _stage_form()
    elif stage == "preview":
        _stage_preview()
    elif stage == "done":
        _stage_done()
