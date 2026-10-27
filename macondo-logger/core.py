import os
import sys
import re
import json
import difflib
import requests
import keyring
from concurrent.futures import ThreadPoolExecutor

# Carpeta donde la app guarda lo que aprende (correcciones y metricas por proyecto).
# En Windows queda en %APPDATA%\MacondoLogger. Sobrevive a actualizaciones de la app.
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "MacondoLogger")
APP_DIR = os.path.dirname(os.path.abspath(__file__))

LEARNING_FILE_TEMPLATE = "buglogger_examples_{project}.json"
MAX_EXAMPLES = 3

KEYRING_SERVICE = "macondo-logger"
# Versiones anteriores guardaban las claves con otros nombres; se leen como respaldo
# para que nadie tenga que volver a pegar su token al actualizar.
LEGACY_SECRETS = {
    "jira_token": [("sk8-buglogger", "jaas_token")],
    "groq_key":   [("sk8-buglogger", "groq_key")],
}
SHARED_GROQ_KEY = os.environ.get("MACONDO_GROQ_KEY") or os.environ.get("SK8_BUGLOGGER_GROQ_KEY", "")


# ---------------------------------------------------------------------------
# configuracion (config.json)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "jira_url": "",
    "browse_url": "",
    "site_name": "Jira",
    "groq_model": "openai/gpt-oss-120b",
    "default_issue_type": "Bug",
    # sugerencias de branch por proyecto: {"SK8": ["dingo-main", ...]}
    "branches": {},
    # opciones de Bug Type cuando el proyecto lo tiene como texto libre
    "bug_types": ["In-Game", "UI", "Server"],
    # proyectos de prueba: no muestran la advertencia de "proyecto real"
    "test_projects": [],
    "fallback_projects": {},
    # nombre logico -> nombre del campo en Jira. Sirve para ordenar el formulario
    # y para pasarle a la IA el contexto del bug (pillar, severity, etc.).
    "field_names": {
        "changelist":    "Changelist Found",
        "branch":        "Branch",
        "bug_type":      "Bug Type",
        "pillar":        "Pillar",
        "game_spine":    "Game Spine",
        "platform":      "Platform",
        "repro_rate":    "Repro Rate",
        "player_impact": "Player Impact",
        "severity":      "Severity",
        "player_path":   "Player Path",
        "activity":      "Activity",
    },
}


def _config_candidates():
    if os.environ.get("MACONDO_CONFIG"):
        yield os.environ["MACONDO_CONFIG"]
    if getattr(sys, "frozen", False):          # corriendo como .exe
        yield os.path.join(os.path.dirname(sys.executable), "config.json")
    yield os.path.join(APP_DIR, "config.json")
    yield os.path.join(DATA_DIR, "config.json")


def load_config():
    """Lee el primer config.json que encuentre. Devuelve (config, ruta o None)."""
    for path in _config_candidates():
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
            config = {**DEFAULT_CONFIG, **user}
            config["field_names"] = {**DEFAULT_CONFIG["field_names"], **user.get("field_names", {})}
            return config, path
    return dict(DEFAULT_CONFIG), None


CONFIG, CONFIG_PATH = load_config()
JIRA_URL = CONFIG["jira_url"].rstrip("/")
SITE_NAME = CONFIG["site_name"]
GROQ_MODEL = CONFIG["groq_model"]
DEFAULT_ISSUE_TYPE = CONFIG["default_issue_type"]
BUG_TYPES = CONFIG["bug_types"]
TEST_PROJECTS = set(CONFIG["test_projects"])
FALLBACK_PROJECTS = CONFIG["fallback_projects"]
FIELD_NAMES = CONFIG["field_names"]


def branch_suggestions(project):
    """Branches sugeridas para un proyecto. Acepta una lista global o un dict por proyecto."""
    branches = CONFIG["branches"]
    if isinstance(branches, list):
        return branches
    return branches.get(project, [])


def browse_url(issue_key):
    """Link para abrir el ticket en el navegador."""
    return f"{(CONFIG.get('browse_url') or JIRA_URL).rstrip('/')}/browse/{issue_key}"


# ---------------------------------------------------------------------------
# credenciales: guardadas cifradas en el almacen del sistema (keyring;
# en Windows es el Credential Manager). Nunca en texto plano en disco.
# ---------------------------------------------------------------------------

def _get_secret(name):
    try:
        value = keyring.get_password(KEYRING_SERVICE, name)
        if value:
            return value
        for service, old_name in LEGACY_SECRETS.get(name, []):
            value = keyring.get_password(service, old_name)
            if value:
                keyring.set_password(KEYRING_SERVICE, name, value)  # se migra una sola vez
                return value
    except Exception:
        pass
    return None


def save_jira_token(token):
    keyring.set_password(KEYRING_SERVICE, "jira_token", token)


def load_jira_token():
    return _get_secret("jira_token")


def delete_jira_token():
    for service, name in [(KEYRING_SERVICE, "jira_token")] + LEGACY_SECRETS["jira_token"]:
        try:
            keyring.delete_password(service, name)
        except Exception:
            pass


def delete_groq_key():
    for service, name in [(KEYRING_SERVICE, "groq_key")] + LEGACY_SECRETS["groq_key"]:
        try:
            keyring.delete_password(service, name)
        except Exception:
            pass


def get_groq_key():
    """Groq key guardada en este equipo, o la variable de entorno MACONDO_GROQ_KEY. "" si no hay."""
    return _get_secret("groq_key") or SHARED_GROQ_KEY


def save_groq_key(key):
    keyring.set_password(KEYRING_SERVICE, "groq_key", key)


# ---------------------------------------------------------------------------
# conexion y proyectos del usuario
# ---------------------------------------------------------------------------

def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_connection(token):
    res = requests.get(f"{JIRA_URL}/rest/api/2/myself", headers=_headers(token), timeout=30)
    if res.status_code == 200:
        data = res.json()
        return True, data.get("displayName", ""), data.get("name", "")
    return False, "", ""


def _has_create_permission(token, project_key):
    """True/False si Jira responde, None si no se pudo verificar."""
    try:
        res = requests.get(
            f"{JIRA_URL}/rest/api/2/mypermissions",
            headers=_headers(token),
            params={"projectKey": project_key, "permissions": "CREATE_ISSUES"},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if res.status_code != 200:
        return None
    perm = res.json().get("permissions", {}).get("CREATE_ISSUES", {})
    return bool(perm.get("havePermission"))


def _recent_project_keys(token):
    """Proyectos donde el usuario reporto hace poco, el mas reciente primero."""
    try:
        res = requests.get(
            f"{JIRA_URL}/rest/api/2/search",
            headers=_headers(token),
            params={"jql": "reporter = currentUser() ORDER BY created DESC", "fields": "project", "maxResults": 100},
            timeout=30,
        )
    except requests.RequestException:
        return []
    if res.status_code != 200:
        return []
    keys = []
    for issue in res.json().get("issues", []):
        key = issue.get("fields", {}).get("project", {}).get("key")
        if key and key not in keys:
            keys.append(key)
    return keys


def list_user_projects(token, username, workers=10):
    """
    Proyectos donde el usuario puede crear tickets, los recientes y los que lidera primero.
    Devuelve (lista, verificado). Si no se pudo verificar ningun permiso,
    devuelve todos los visibles con verificado=False para que la UI avise.
    """
    res = requests.get(f"{JIRA_URL}/rest/api/2/project", headers=_headers(token), params={"expand": "lead"}, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"no pude listar los proyectos ({res.status_code})")
    visible = res.json()
    recent = _recent_project_keys(token)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        permissions = list(pool.map(lambda p: _has_create_permission(token, p["key"]), visible))

    verified = any(p is not None for p in permissions)
    me = (username or "").lower()
    projects = []
    for project, can_create in zip(visible, permissions):
        if verified and not can_create:
            continue
        lead = project.get("lead") or {}
        lead_ids = {str(lead.get("name", "")).lower(), str(lead.get("key", "")).lower()}
        projects.append({
            "key": project["key"],
            "name": project.get("name", ""),
            "can_create": can_create,
            "is_lead": bool(me) and me in lead_ids,
            "recent": project["key"] in recent,
        })

    def order(p):
        rank = recent.index(p["key"]) if p["recent"] else 10_000
        return (not p["recent"], rank, not p["is_lead"], p["name"].lower())

    return sorted(projects, key=order), verified


# ---------------------------------------------------------------------------
# campos del proyecto: issue types y pantalla de creacion
# ---------------------------------------------------------------------------

# Campos que la app maneja aparte (o que Jira llena solo) y no van en el formulario.
STANDARD_FIELDS = {"summary", "description", "reporter", "project", "issuetype", "attachment"}


def _get_paged(token, path, page_size=200):
    """Junta todas las paginas de un endpoint paginado de Jira (campo 'values')."""
    items, start = [], 0
    while True:
        res = requests.get(
            f"{JIRA_URL}{path}",
            headers=_headers(token),
            params={"startAt": start, "maxResults": page_size},
            timeout=30,
        )
        if res.status_code != 200:
            return items or None
        data = res.json()
        if isinstance(data, list):
            return data
        page = data.get("values")
        if page is None:
            return data.get("fields") or data.get("issueTypes")  # forma alternativa, sin paginar
        items.extend(page)
        total = data.get("total")
        if data.get("isLast", True) or not page or (total is not None and len(items) >= total):
            return items
        start += len(page)


def _index_fields(raw):
    """Los campos pueden venir como lista o como dict; se normaliza a {fieldId: campo}."""
    if isinstance(raw, dict):
        out = {}
        for field_id, field in raw.items():
            field = dict(field)
            field.setdefault("fieldId", field_id)
            out[field_id] = field
        return out
    return {f["fieldId"]: f for f in (raw or []) if f.get("fieldId")}


def _label(value):
    return value.get("value") or value.get("name")


def _options(field):
    """{texto visible: id} de las opciones permitidas de un campo."""
    return {_label(v): v["id"] for v in field.get("allowedValues", []) if v.get("id") and _label(v)}


def _cascade_options(field):
    """Listas en cascada: {padre: {"id": id, "children": {hijo: id}}}."""
    out = {}
    for parent in field.get("allowedValues", []):
        if not parent.get("id") or not _label(parent):
            continue
        out[_label(parent)] = {
            "id": parent["id"],
            "children": {_label(c): c["id"] for c in parent.get("children", []) if c.get("id") and _label(c)},
        }
    return out


SELECTABLE = {"option", "version", "component", "priority", "securitylevel", "resolution"}


def field_kind(field):
    """
    Que control sabe dibujar la app para un campo de Jira. None si no lo soporta.
    text | number | date | datetime | select | multiselect | cascade | labels | user | users | group | groups
    """
    schema = field.get("schema", {})
    kind, items = schema.get("type"), schema.get("items")
    has_options = bool(field.get("allowedValues"))
    if kind == "string":
        return "select" if has_options else "text"
    if kind == "number":
        return "number"
    if kind == "date":
        return "date"
    if kind == "datetime":
        return "datetime"
    if kind == "option-with-child" and has_options:
        return "cascade"
    if kind in SELECTABLE and has_options:
        return "select"
    if kind == "user":
        return "user"
    if kind == "group":
        return "group"
    if kind == "array":
        if items in SELECTABLE | {"string"} and has_options:
            return "multiselect"
        if items == "string":
            return "labels"
        if items == "user":
            return "users"
        if items == "group":
            return "groups"
    return None


def fetch_issue_types(token, project):
    """Tipos de ticket que el usuario puede crear en el proyecto (sin subtareas). None si Jira no lo dice."""
    types = _get_paged(token, f"/rest/api/2/issue/createmeta/{project}/issuetypes")
    if not types:
        return None
    if isinstance(types, dict):
        types = list(types.values())
    return [{"id": t["id"], "name": t.get("name", "")} for t in types if not t.get("subtask") and t.get("id")]


def pick_default_issue_type(issuetypes):
    """El tipo 'Bug' (o el de config) si existe; si no, el primero."""
    wanted = DEFAULT_ISSUE_TYPE.strip().lower()
    for t in issuetypes:
        if t["name"].strip().lower() == wanted:
            return t
    return issuetypes[0] if issuetypes else None


def _build_meta(project, source, fields, issuetype, issuetypes, ref_ticket=None):
    """Arma todo lo que la UI necesita para dibujar el formulario y enviar el ticket."""
    by_name = {f.get("name", "").strip().lower(): fid for fid, f in fields.items()}
    logical_of = {}
    for logical, jira_name in FIELD_NAMES.items():
        fid = by_name.get(jira_name.lower())
        if fid and fid not in STANDARD_FIELDS:
            logical_of[fid] = logical

    form_fields, unsupported = [], []
    for fid, field in fields.items():
        if fid in STANDARD_FIELDS:
            continue
        kind = field_kind(field)
        required = bool(field.get("required")) and not field.get("hasDefaultValue")
        item = {
            "id": fid,
            "name": field.get("name", fid),
            "required": required,
            "logical": logical_of.get(fid),
            "kind": kind,
            "options": _cascade_options(field) if kind == "cascade" else _options(field),
        }
        (form_fields if kind else unsupported).append(item)

    # orden: primero los conocidos (en el orden de field_names), despues los obligatorios, despues el resto
    order = list(FIELD_NAMES)
    form_fields.sort(key=lambda f: (
        order.index(f["logical"]) if f["logical"] else len(order),
        not f["required"],
        f["name"].lower(),
    ))

    return {
        "project": project,
        "source": source,          # "createmeta" (pantalla de creacion real) o "editmeta" (ticket de referencia)
        "ref_ticket": ref_ticket,
        "issuetype_id": issuetype.get("id"),
        "issuetype_name": issuetype.get("name") or DEFAULT_ISSUE_TYPE,
        "issuetypes": issuetypes or ([issuetype] if issuetype.get("id") else []),
        "form_fields": form_fields,
        "unsupported_fields": unsupported,
        "field_names": {fid: f.get("name", fid) for fid, f in fields.items()},
    }


def fetch_create_meta(token, project, issuetype_id=None):
    """
    Campos de la pantalla de CREACION del proyecto para un tipo de ticket.
    Si no se indica el tipo, usa 'Bug'. Endpoints de Jira DC 8.4+.
    Devuelve None si no estan disponibles o si el usuario no puede crear ahi.
    """
    issuetypes = fetch_issue_types(token, project)
    if not issuetypes:
        return None
    issuetype = next((t for t in issuetypes if t["id"] == issuetype_id), None) or pick_default_issue_type(issuetypes)
    raw_fields = _get_paged(token, f"/rest/api/2/issue/createmeta/{project}/issuetypes/{issuetype['id']}")
    if not raw_fields:
        return None
    return _build_meta(project, "createmeta", _index_fields(raw_fields), issuetype, issuetypes)


def find_reference_ticket(token, reporter_username, project, issuetype_name):
    """Ticket reciente del proyecto para leer editmeta: primero uno del usuario, si no, cualquiera."""
    for jql in (
        f'project = "{project}" AND issuetype = "{issuetype_name}" AND reporter = "{reporter_username}" ORDER BY created DESC',
        f'project = "{project}" AND issuetype = "{issuetype_name}" ORDER BY created DESC',
        f'project = "{project}" ORDER BY created DESC',
    ):
        res = requests.get(
            f"{JIRA_URL}/rest/api/2/search",
            headers=_headers(token),
            params={"jql": jql, "maxResults": 1, "fields": "key"},
            timeout=30,
        )
        if res.status_code == 200 and res.json().get("issues"):
            return res.json()["issues"][0]["key"]
    return None


def fetch_edit_meta(token, project, issue_key):
    """Plan B: campos de un ticket existente. Puede incluir campos que no estan en la pantalla de creacion."""
    res = requests.get(f"{JIRA_URL}/rest/api/2/issue/{issue_key}?expand=editmeta", headers=_headers(token), timeout=30)
    if res.status_code != 200:
        return None
    issue = res.json()
    fields = _index_fields(issue.get("editmeta", {}).get("fields", {}))
    issuetype = issue.get("fields", {}).get("issuetype", {})
    return _build_meta(project, "editmeta", fields, issuetype, None, ref_ticket=issue_key)


def load_project_meta(token, reporter_username, project, issuetype_id=None):
    """
    Punto de entrada al elegir proyecto (o cambiar el tipo de ticket):
      1. pantalla de creacion real (createmeta)
      2. si no esta disponible, editmeta de un ticket de referencia
    Tambien trae los tickets reales del proyecto para aprender su estilo.
    Devuelve el dict meta, o None si no se pudo leer nada.
    """
    try:
        meta = fetch_create_meta(token, project, issuetype_id)
    except requests.RequestException:
        meta = None
    if not meta:
        try:
            ref = find_reference_ticket(token, reporter_username, project, DEFAULT_ISSUE_TYPE)
            meta = fetch_edit_meta(token, project, ref) if ref else None
        except requests.RequestException:
            meta = None
    if meta:
        meta["style"] = fetch_project_style(token, project, meta["issuetype_name"])
    return meta


def missing_required(meta, values):
    """Nombres de los campos obligatorios que siguen vacios."""
    return [f["name"] for f in meta["form_fields"] if f["required"] and _empty(values.get(f["id"]))]


# ---------------------------------------------------------------------------
# COMPONENTE DE APRENDIZAJE ("machine learning" de la app)
#
# No entrena un modelo propio. Aprende guardando ejemplos y pasandoselos a la
# IA cada vez que escribe un ticket (few-shot learning). Capas, de menor a mayor peso:
#   1. Plantilla base de Skate (SKATE_TEMPLATE): siempre va, define la estructura.
#   2. Tickets reales del proyecto: al abrir un proyecto se leen de Jira los
#      tickets recientes del usuario, o del equipo si el usuario no tiene
#      (fetch_project_style). No se guardan en disco.
#   3. Tus correcciones: si editas el summary/description antes de enviar, se
#      guardan en DATA_DIR/buglogger_examples_<PROYECTO>.json (save_example).
# Donde el proyecto o tus correcciones difieren de la plantilla, ganan ellos.
# ---------------------------------------------------------------------------

def fetch_project_style(token, project, issuetype_name="Bug", limit=20):
    """
    Estilo real del proyecto: summaries y descriptions de tickets recientes de ese tipo.
    Primero los del propio usuario; si no tiene, los de cualquiera en el proyecto.
    Nunca falla: si Jira no responde, devuelve listas vacias.
    """
    style = {"summaries": [], "descriptions": [], "source": None}
    for who, jql in (
        ("tuyos", f'project = "{project}" AND issuetype = "{issuetype_name}" AND reporter = currentUser() ORDER BY created DESC'),
        ("del proyecto", f'project = "{project}" AND issuetype = "{issuetype_name}" ORDER BY created DESC'),
    ):
        try:
            res = requests.get(
                f"{JIRA_URL}/rest/api/2/search",
                headers=_headers(token),
                params={"jql": jql, "maxResults": limit, "fields": "summary,description"},
                timeout=30,
            )
        except requests.RequestException:
            continue
        if res.status_code != 200:
            continue
        for issue in res.json().get("issues", []):
            fields = issue.get("fields", {})
            summary = (fields.get("summary") or "").strip()
            description = (fields.get("description") or "").strip()
            if summary and len(style["summaries"]) < 6:
                style["summaries"].append(summary)
            # solo descripciones con estructura (varias lineas), no tickets de una frase
            if len(description) >= 150 and description.count("\n") >= 3 and len(style["descriptions"]) < MAX_EXAMPLES:
                style["descriptions"].append(description[:2500])
        if style["descriptions"]:
            style["source"] = who
            break
    return style


def _examples_path(project):
    return os.path.join(DATA_DIR, LEARNING_FILE_TEMPLATE.format(project=project))


def load_examples(project):
    path = _examples_path(project)
    if not os.path.exists(path):
        legacy = LEARNING_FILE_TEMPLATE.format(project=project)  # versiones viejas lo guardaban junto a la app
        path = legacy if os.path.exists(legacy) else None
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_example(project, raw_bug, pillar, feature, description, summary=None):
    examples = load_examples(project)
    examples.append({
        "raw_bug": raw_bug,
        "pillar": pillar,
        "feature": feature,
        "summary": summary,
        "description": description,
    })
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_examples_path(project), "w", encoding="utf-8") as f:
        json.dump(examples, f, indent=2, ensure_ascii=False)


def recent_examples_block(project):
    examples = load_examples(project)[-MAX_EXAMPLES:]
    if not examples:
        return ""
    block = "\n=== THE TESTER'S OWN CORRECTIONS IN THIS PROJECT (highest priority: match these) ===\n"
    for i, ex in enumerate(examples, 1):
        block += f"\n--- CORRECTION {i} (Pillar: {ex.get('pillar') or 'N/A'}, Feature: {ex.get('feature') or 'N/A'}) ---\n"
        block += ex["description"] + "\n"
    return block


def project_style_block(style):
    descriptions = (style or {}).get("descriptions") or []
    if not descriptions:
        return ""
    block = "\n=== REAL TICKETS FROM THIS PROJECT (adapt the base template to their section names and markup) ===\n"
    for i, description in enumerate(descriptions, 1):
        block += f"\n--- PROJECT EXAMPLE {i} ---\n{description}\n"
    return block


def learning_status(project, style):
    """Para mostrar en la UI de donde esta aprendiendo la app en este proyecto."""
    return {
        "corrections": len(load_examples(project)),
        "real_tickets": len((style or {}).get("descriptions") or []),
        "real_source": (style or {}).get("source"),
    }


# ---------------------------------------------------------------------------
# metricas de uso: de aqui sale la accuracy REAL, medida con el uso.
#   generated      -> borradores generados con IA
#   sent           -> tickets enviados
#   corrected      -> enviados despues de editarlos
#   similarity_sum -> suma del parecido (0..1) entre borrador y lo enviado
# accuracy = enviados SIN reescribir / enviados.
# ---------------------------------------------------------------------------

STATS_FILE_TEMPLATE = "buglogger_stats_{project}.json"
_STATS_DEFAULT = {"generated": 0, "sent": 0, "corrected": 0, "similarity_sum": 0.0}


def _stats_path(project):
    return os.path.join(DATA_DIR, STATS_FILE_TEMPLATE.format(project=project))


def load_stats(project):
    path = _stats_path(project)
    stats = dict(_STATS_DEFAULT)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            for key in stats:
                stats[key] = saved.get(key, stats[key])
        except (OSError, ValueError):
            pass
    return stats


def _save_stats(project, stats):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_stats_path(project), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


def record_generation(project):
    stats = load_stats(project)
    stats["generated"] += 1
    _save_stats(project, stats)


def record_submission(project, was_corrected, generated_text, final_text):
    stats = load_stats(project)
    stats["sent"] += 1
    if was_corrected:
        stats["corrected"] += 1
    stats["similarity_sum"] += difflib.SequenceMatcher(None, generated_text or "", final_text or "").ratio()
    _save_stats(project, stats)


def accuracy_report(project):
    stats = load_stats(project)
    sent = stats["sent"]
    unedited = sent - stats["corrected"]
    return {
        "generated": stats["generated"],
        "sent": sent,
        "unedited": unedited,
        "corrected": stats["corrected"],
        "accuracy_pct": (unedited / sent * 100) if sent else None,
        "avg_similarity_pct": (stats["similarity_sum"] / sent * 100) if sent else None,
    }


# ---------------------------------------------------------------------------
# groq: escribir summary y description
# ---------------------------------------------------------------------------

def make_groq_client(api_key):
    from groq import Groq
    return Groq(api_key=api_key)


def ask_groq(client, system_prompt, user_prompt):
    res = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.2,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return res.choices[0].message.content.strip()


DESCRIPTION_RULES = (
    "You are a QA engineer at EA writing bug reports in JaaS (Jira).\n"
    "Write the description following the BASE TEMPLATE below. It is the standard used across EA titles.\n"
    "If this project's real tickets or the tester's corrections use different section names, extra sections, "
    "fields or markup, follow them instead: corrections > project tickets > base template.\n\n"
    "=== DEFAULT STRUCTURE OF THE BASE TEMPLATE ===\n"
    "- Description paragraph: 2-3 sentences max. What is wrong, where, and the consequence.\n"
    "- Repro Rate.\n"
    "- Repro Steps: 5-8 steps. Start with Boot. End with 'Notice that [what is wrong]'.\n"
    "- Player Impact: 1-2 sentences, focus on player experience.\n"
    "- Note: include Pillar Team and Feature exactly as given, only when they are provided. "
    "Add Expected/Actual only when there are specific values. Add Prerequisite only if mentioned. "
    "Add a likely cause line only if it's obvious from the description.\n"
    "- Jira wiki markup: # for steps, * for note bullets, *bold* section titles.\n\n"
    "=== ALWAYS ===\n"
    "- Do not invent details that aren't in the bug description (no item names, values, CLs or steps the user did not give).\n"
    "- Do not copy facts from any example: examples show format only.\n"
    "- No headers before the description paragraph.\n"
    "- Return only the description text."
)

# Plantilla base: tickets reales de Skate. Es la estructura por defecto para
# cualquier proyecto; los tickets reales de cada proyecto la ajustan.
SKATE_TEMPLATE = (
    "\n=== EXAMPLE 1 ===\n"
    "The challenge OTL S04-OwnTheLot-001 does not display the pre-challenge countdown timer when played in Co-op. "
    "Before the challenge begins, the expected countdown is absent, causing the challenge to start without providing "
    "players with the proper visual indication and preparation time.\n\n"
    "*Repro Rate:*\n5/5 (Always)\n\n"
    "*Repro Steps:*\n"
    "# Boot the title: - CL 28452329 (Staging Blue Retail)\n"
    "# Purchase the Skate Pass to gain access to San Van Open Stadium\n"
    "# Create or join a Co-op session\n"
    "# Enter San Van Open Stadium\n"
    "# Navigate to OTL S04-OwnTheLot-001 \"X Marks the Lot\"\n"
    "# Start the challenge in Co-op mode\n"
    "# Observe the UI before the challenge begins\n"
    "# Notice that the pre-challenge countdown timer is not displayed\n\n"
    "*Player Impact:*\n"
    "Players do not receive the expected visual cue before the challenge starts, reducing coordination "
    "and negatively impacting the Co-op gameplay experience.\n\n"
    "*Note:*\n"
    "* Pillar Team: Events\n"
    "* Feature: Challenges\n"
    "* Prerequisite: Purchase the Skate Pass to access San Van Open Stadium\n"
    "* Expected behavior: A countdown timer should be displayed before the challenge starts in Co-op mode\n"
    "* Actual behavior: No pre-challenge countdown timer appears\n"
    "* Likely issue with Co-op HUD synchronization or challenge initialization logic.\n\n"
    "=== EXAMPLE 2 ===\n"
    "The Zone Entrance progress indicator is displaying an incorrect total count. "
    "The UI currently shows 1/11, while the expected value should be 1/7. "
    "This results in inaccurate progression information being presented to the player.\n\n"
    "*Repro Rate:*\n5/5 (Always)\n\n"
    "*Repro Steps:*\n"
    "# Boot the title: - CL 28371079 (Staging Blue)\n"
    "# Enter the Stadium area\n"
    "# Navigate to or trigger the Zone Entrance objective/progression UI\n"
    "# Observe the displayed progress counter\n"
    "# Notice that the UI shows 1/11\n"
    "# Verify that the correct count should be 1/7\n\n"
    "*Player Impact:*\n"
    "Players receive incorrect progression information, which may cause confusion regarding "
    "objective completion and overall zone progress.\n\n"
    "*Note:*\n"
    "* Pillar Team: Stadium\n"
    "* Feature: Zone Progression/UI\n"
    "* Expected display: 1/7\n"
    "* Actual display: 1/11\n"
    "* Likely incorrect objective count or UI data configuration.\n\n"
    "=== EXAMPLE 3 ===\n"
    "The player can unexpectedly be dropped beneath the world geometry, causing the character to fall below "
    "the playable area. Once below the world, the player is unable to interact with the environment as intended "
    "and may become stuck in an invalid gameplay state.\n\n"
    "*Repro Rate:*\n1/5 (Observed Once)\n\n"
    "*Repro Steps:*\n"
    "# Boot the title: - CL 28371079 (Staging Blue)\n"
    "# Navigate to the affected location\n"
    "# Perform the actions shown in the attached video/logs\n"
    "# Observe the player position relative to the world geometry\n"
    "# Notice that the player is dropped below the world and begins falling underneath the map\n\n"
    "*Player Impact:*\n"
    "Players can become trapped outside the playable area, potentially requiring a respawn, "
    "fast travel, or game restart to recover.\n\n"
    "*Note:*\n"
    "* Pillar Team: Worlds\n"
    "* Feature: Layout\n"
    "* Issue results in the player leaving the intended playable space\n"
    "* Likely related to missing collision, streaming issue, or invalid player spawn/teleport location.\n"
)

SKATE_SUMMARY_EXAMPLES = [
    'Pre-challenge countdown timer is missing in Co-op for OTL S04-OwnTheLot-001 "X Marks the Lot"',
    'Handplants are counted multiple times in OTL S04-OwnTheLot-001 "X Marks the Lot"',
    '"Let The Games Begin!" news item is not displayed first in the News feed order',
    "Zone Entrance counter displays incorrect value (1/11 instead of 1/7)",
    "Player can fall below the world geometry",
]


def generate_summary(client, raw_bug, project=None, style=None, prefix_parts=None):
    """
    Una linea de summary. Si el proyecto tiene Pillar / Game Spine (convencion Skate),
    el prefijo 'Pillar - Game Spine - ' lo arma la app con lo que elegiste.
    Si no, la IA copia el formato completo de los summaries del proyecto, prefijo incluido.
    """
    prefix_parts = [p for p in (prefix_parts or []) if p]
    corrected = [ex["summary"] for ex in load_examples(project)[-MAX_EXAMPLES:] if ex.get("summary")] if project else []
    real = (style or {}).get("summaries") or []
    examples = (corrected + real)[:8]
    if len(examples) < 3:
        examples += SKATE_SUMMARY_EXAMPLES[: 5 - len(examples)]

    if prefix_parts:
        format_rule = (
            "If the examples start with a 'Pillar - Area -' style prefix, leave that prefix out: "
            "write only the bug part, it is added later."
        )
    else:
        format_rule = "Follow the exact format of the examples, including any prefix or tags they use."

    system = (
        "You are a QA engineer writing JaaS (Jira) ticket summaries.\n"
        "Given a bug description, write a short specific one-line summary of the issue. " + format_rule + "\n\n"
        "Real summaries from this project, for wording and level of detail:\n"
        + "".join(f"- {e}\n" for e in examples)
        + "\nBe specific, include item names and values when mentioned. One line, no quotes around it. "
        "Return only that line."
    )
    line = ask_groq(client, system, f"Bug: {raw_bug}")
    line = re.sub(r"[\x00-\x1f\x7f]", " ", line).strip().strip('"')
    return " - ".join(prefix_parts + [line])


def generate_description(client, project, raw_bug, context, style=None):
    """
    context: {etiqueta: valor} con lo que se lleno en el formulario
    (CL, Branch, Pillar Team, Feature, Repro Rate, Severity...).
    """
    lines = [f"Bug: {raw_bug}"]
    lines += [f"{label}: {value}" for label, value in context.items() if value]
    system = (
        DESCRIPTION_RULES
        + "\n\n=== BASE TEMPLATE (Skate) ===\n" + SKATE_TEMPLATE
        + project_style_block(style)
        + recent_examples_block(project)
    )
    return ask_groq(client, system, "\n".join(lines))


# ---------------------------------------------------------------------------
# envio
# ---------------------------------------------------------------------------

def match(value, options):
    """Busca la opcion que corresponde a un texto, sin importar mayusculas. None si no hay."""
    if not value or not options:
        return None
    value_lower = str(value).lower()
    for key in options:
        if key.lower() == value_lower:
            return key
    for key in options:
        if value_lower in key.lower() or key.lower() in value_lower:
            return key
    return None


def _empty(value):
    if isinstance(value, (list, tuple)):
        return not any(v not in (None, "") for v in value)
    return value is None or value == ""


def _split(value):
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [x for x in re.split(r"[,\s]+", str(value)) if x]


def format_value(kind, value, options):
    """Convierte lo que se lleno en la UI al formato que espera la API de Jira."""
    if kind == "text":
        return str(value)
    if kind == "number":
        return float(str(value).strip())
    if kind == "date":
        return str(value)
    if kind == "datetime":
        return f"{value}T00:00:00.000+0000" if len(str(value)) == 10 else str(value)
    if kind == "select":
        key = match(value, options)
        if key is None:
            raise ValueError(f"'{value}' no es una opcion valida")
        return {"id": options[key]}
    if kind == "multiselect":
        ids = []
        for v in (value if isinstance(value, (list, tuple)) else [value]):
            key = match(v, options)
            if key is None:
                raise ValueError(f"'{v}' no es una opcion valida")
            ids.append({"id": options[key]})
        return ids
    if kind == "cascade":
        parent, child = (list(value) + [None, None])[:2] if isinstance(value, (list, tuple)) else (value, None)
        entry = options[parent]
        out = {"id": entry["id"]}
        if child:
            out["child"] = {"id": entry["children"][child]}
        return out
    if kind == "labels":
        return _split(value)
    if kind in ("user", "group"):
        return {"name": str(value).strip()}
    if kind in ("users", "groups"):
        return [{"name": v} for v in _split(value)]
    raise ValueError(f"tipo de campo no soportado: {kind}")


def _error_map(res):
    try:
        return res.json().get("errors") or {}
    except ValueError:
        return {}


def explain_error(res, meta):
    """Convierte el error de Jira en lineas legibles, con el nombre del campo."""
    try:
        data = res.json()
    except ValueError:
        return res.text
    lines = list(data.get("errorMessages", []))
    names = meta.get("field_names", {})
    for field_id, message in (data.get("errors") or {}).items():
        label = names.get(field_id)
        lines.append(f"{label} ({field_id}): {message}" if label else f"{field_id}: {message}")
    return "\n".join(lines) or res.text


def submit_ticket(token, ticket, meta):
    """
    Crea el ticket en UNA llamada, con los campos del formulario que tienen valor.
    El reporter no se manda: Jira usa al dueno del token.
    Si Jira rechaza campos OPCIONALES, se quitan y se reintenta una vez; quedan como warnings.
    Devuelve (respuesta_de_jira, warnings).
    """
    warnings = []
    fields = {
        "project": {"key": meta["project"]},
        "issuetype": {"id": meta["issuetype_id"]} if meta.get("issuetype_id") else {"name": meta["issuetype_name"]},
        "summary": ticket["summary"],
        "description": ticket["description"],
    }
    values = ticket.get("values") or {}
    for field in meta["form_fields"]:
        value = values.get(field["id"])
        if _empty(value):
            continue
        try:
            fields[field["id"]] = format_value(field["kind"], value, field["options"])
        except (ValueError, KeyError) as error:
            warnings.append(f"{field['name']}: {error}")

    headers = {**_headers(token), "Content-Type": "application/json"}
    url = f"{JIRA_URL}/rest/api/2/issue"
    res = requests.post(url, headers=headers, json={"fields": fields})

    if res.status_code == 400:
        errors = _error_map(res)
        required = {f["id"] for f in meta["form_fields"] if f["required"]}
        keep = required | {"summary", "description", "project", "issuetype"}
        droppable = [fid for fid in errors if fid in fields and fid not in keep]
        if droppable:
            for field_id in droppable:
                label = meta.get("field_names", {}).get(field_id, field_id)
                warnings.append(f"{label}: {errors[field_id]}")
                fields.pop(field_id)
            res = requests.post(url, headers=headers, json={"fields": fields})

    return res, warnings


def attach_files(token, issue_key, files):
    """
    Sube archivos a un ticket ya creado.
    files: lista de tuplas (filename, bytes, content_type)
    Devuelve lista de (filename, ok, error_msg)
    """
    headers = {**_headers(token), "X-Atlassian-Token": "no-check"}  # requerido por Jira para adjuntos
    results = []
    for filename, filebytes, content_type in files:
        res = requests.post(
            f"{JIRA_URL}/rest/api/2/issue/{issue_key}/attachments",
            headers=headers,
            files={"file": (filename, filebytes, content_type or "application/octet-stream")},
        )
        results.append((filename, True, None) if res.status_code in (200, 201) else (filename, False, res.text))
    return results
