"""
Pruebas de core.py sin red: JaaS y Groq se simulan.

Correr desde la carpeta del proyecto:
    python -m pip install pytest
    python -m pytest -q
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import core  # noqa: E402


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Cada prueba guarda correcciones y metricas en una carpeta temporal."""
    monkeypatch.setattr(core, "DATA_DIR", str(tmp_path))
    return tmp_path


class FakeGroq:
    """Imita el cliente de Groq y guarda el ultimo prompt de sistema que recibio."""

    def __init__(self, answer="texto generado"):
        self.answer = answer
        self.last_system = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, temperature, max_tokens, messages):
        self.last_system = messages[0]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))])


def _resp(status, data):
    return SimpleNamespace(status_code=status, json=lambda: data, text=json.dumps(data))


# Respuestas simuladas de createmeta para un proyecto tipo Madden (MAD)
ISSUETYPES = {"values": [
    {"id": "1", "name": "Bug", "subtask": False},
    {"id": "3", "name": "Task", "subtask": False},
    {"id": "5", "name": "Sub-task", "subtask": True},
]}
BUG_FIELDS = {"values": [
    {"fieldId": "summary", "name": "Summary", "required": True, "schema": {"type": "string"}},
    {"fieldId": "issuetype", "name": "Issue Type", "required": True, "schema": {"type": "issuetype"}},
    {"fieldId": "versions", "name": "Affects Version/s", "required": True,
     "schema": {"type": "array", "items": "version"}, "allowedValues": [{"id": "v1", "name": "1.0"}]},
    {"fieldId": "components", "name": "Component/s", "required": True,
     "schema": {"type": "array", "items": "component"}, "allowedValues": [{"id": "c1", "name": "Gameplay"}]},
    {"fieldId": "customfield_1", "name": "Severity", "required": True,
     "schema": {"type": "option"}, "allowedValues": [{"id": "s1", "value": "High"}, {"id": "s2", "value": "Low"}]},
    {"fieldId": "customfield_2", "name": "Area", "required": True, "schema": {"type": "option-with-child"},
     "allowedValues": [{"id": "a1", "value": "Franchise", "children": [{"id": "a11", "value": "Draft"}]}]},
    {"fieldId": "customfield_3", "name": "Owner", "required": False, "schema": {"type": "user"}},
    {"fieldId": "customfield_4", "name": "Changelist Found", "required": False, "schema": {"type": "number"}},
    {"fieldId": "customfield_5", "name": "Branch", "required": False, "schema": {"type": "array", "items": "string"}},
    {"fieldId": "customfield_6", "name": "Raro", "required": True, "schema": {"type": "any"}},
    {"fieldId": "customfield_7", "name": "Notas QA", "required": False, "schema": {"type": "string"}},
]}


def fake_get(url, headers=None, params=None, timeout=None):
    if url.endswith("/createmeta/MAD/issuetypes"):
        return _resp(200, ISSUETYPES)
    if url.endswith("/createmeta/MAD/issuetypes/1"):
        return _resp(200, BUG_FIELDS)
    if url.endswith("/createmeta/MAD/issuetypes/3"):
        return _resp(200, {"values": [BUG_FIELDS["values"][0]]})
    if url.endswith("/search"):
        jql = params["jql"]
        assert 'issuetype = "Bug"' in jql or 'issuetype = "Task"' in jql
        desc = "Linea 1\n*Repro Steps:*\n# Boot\n# Notice that X\n" + "detalle " * 30
        return _resp(200, {"issues": [{"fields": {"summary": "Franchise - Draft - Error al elegir", "description": desc}}]})
    return _resp(404, {})


# --- configuracion -----------------------------------------------------------

def test_repo_config_is_ea():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        config = json.load(f)
    assert config["jira_url"] == "https://api.jaas.ea.com"
    assert config["default_issue_type"] == "Bug"


def test_branch_suggestions_by_project(monkeypatch):
    monkeypatch.setitem(core.CONFIG, "branches", {"SK8": ["dingo-main"]})
    assert core.branch_suggestions("SK8") == ["dingo-main"]
    assert core.branch_suggestions("MAD") == []


# --- campos del proyecto e issue type -------------------------------------------

def test_meta_defaults_to_bug_and_lists_issue_types(data_dir):
    with patch.object(core.requests, "get", fake_get):
        meta = core.load_project_meta("t", "u", "MAD")
    assert meta["issuetype_name"] == "Bug" and meta["issuetype_id"] == "1"
    assert [t["name"] for t in meta["issuetypes"]] == ["Bug", "Task"]  # sin subtareas


def test_meta_with_other_issue_type(data_dir):
    with patch.object(core.requests, "get", fake_get):
        meta = core.load_project_meta("t", "u", "MAD", issuetype_id="3")
    assert meta["issuetype_name"] == "Task"


def test_all_required_fields_are_in_the_form(data_dir):
    with patch.object(core.requests, "get", fake_get):
        meta = core.load_project_meta("t", "u", "MAD")
    form = {f["name"]: f for f in meta["form_fields"]}
    for name in ("Affects Version/s", "Component/s", "Severity", "Area"):
        assert form[name]["required"], name
    assert form["Area"]["kind"] == "cascade"
    assert form["Component/s"]["kind"] == "multiselect"
    assert form["Owner"]["kind"] == "user"
    assert form["Severity"]["logical"] == "severity"
    # el campo de tipo desconocido no se pierde: se reporta como no soportado
    assert [f["name"] for f in meta["unsupported_fields"]] == ["Raro"]
    # summary e issuetype los maneja la app, no aparecen en el formulario
    assert "Summary" not in form and "Issue Type" not in form


def test_missing_required(data_dir):
    with patch.object(core.requests, "get", fake_get):
        meta = core.load_project_meta("t", "u", "MAD")
    ids = {f["name"]: f["id"] for f in meta["form_fields"]}
    values = {ids["Severity"]: "High", ids["Component/s"]: []}
    assert set(core.missing_required(meta, values)) == {"Affects Version/s", "Component/s", "Area"}


# --- aprendizaje -------------------------------------------------------------------

def test_corrections_are_saved_per_project(data_dir):
    core.save_example("SK8", "boton roto", "UI", "Menu", "desc corregida", summary="Boton roto")
    core.save_example("MAD", "otro bug", None, None, "otra desc")
    assert len(core.load_examples("SK8")) == 1 and len(core.load_examples("MAD")) == 1
    assert (data_dir / "buglogger_examples_MAD.json").exists()


def test_description_always_has_skate_template_plus_project_and_corrections(data_dir):
    core.save_example("MAD", "bug", None, None, "MI CORRECCION")
    style = {"descriptions": ["TICKET REAL DE MADDEN " * 10], "summaries": []}
    client = FakeGroq()
    core.generate_description(client, "MAD", "bug", {"CL": "123"}, style)
    system = client.last_system
    assert "BASE TEMPLATE (Skate)" in system and "OwnTheLot" in system
    assert "TICKET REAL DE MADDEN" in system and "MI CORRECCION" in system
    assert system.index("BASE TEMPLATE") < system.index("TICKET REAL") < system.index("MI CORRECCION")


def test_description_without_project_tickets_uses_skate_template(data_dir):
    client = FakeGroq()
    core.generate_description(client, "NEW", "bug", {}, None)
    assert "OwnTheLot" in client.last_system


def test_summary_with_skate_prefix(data_dir):
    client = FakeGroq(answer='"Boton de salir no responde"\n')
    assert core.generate_summary(client, "bug", "SK8", None, ["UI", "Menus"]) == "UI - Menus - Boton de salir no responde"


def test_summary_without_prefix_copies_project_format(data_dir):
    client = FakeGroq(answer="Franchise - Draft - Error al elegir jugador")
    style = {"summaries": ["Franchise - Draft - Algo", "Play - Online - Otro", "Franchise - Trade - X"]}
    summary = core.generate_summary(client, "bug", "MAD", style, [None, ""])
    assert summary == "Franchise - Draft - Error al elegir jugador"
    assert "including any prefix" in client.last_system


def test_accuracy_report(data_dir):
    core.record_generation("SK8")
    core.record_submission("SK8", False, "igual", "igual")
    core.record_submission("SK8", True, "borrador", "texto distinto")
    report = core.accuracy_report("SK8")
    assert report["sent"] == 2 and report["accuracy_pct"] == 50


# --- envio ---------------------------------------------------------------------------

def test_submit_formats_every_kind(data_dir):
    with patch.object(core.requests, "get", fake_get):
        meta = core.load_project_meta("t", "u", "MAD")
    ids = {f["name"]: f["id"] for f in meta["form_fields"]}
    ticket = {"summary": "S", "description": "D", "values": {
        ids["Affects Version/s"]: ["1.0"],
        ids["Component/s"]: ["Gameplay"],
        ids["Severity"]: "high",
        ids["Area"]: ("Franchise", "Draft"),
        ids["Owner"]: "jdoe",
        ids["Changelist Found"]: "28452329",
        ids["Branch"]: "dingo-main",
    }}
    sent = {}

    def fake_post(url, headers, json):
        sent.update(json["fields"])
        return _resp(201, {"key": "MAD-1"})

    with patch.object(core.requests, "post", fake_post):
        res, warnings = core.submit_ticket("t", ticket, meta)
    assert res.status_code == 201 and warnings == []
    assert sent["issuetype"] == {"id": "1"}
    assert sent["versions"] == [{"id": "v1"}]
    assert sent["components"] == [{"id": "c1"}]
    assert sent["customfield_1"] == {"id": "s1"}
    assert sent["customfield_2"] == {"id": "a1", "child": {"id": "a11"}}
    assert sent["customfield_3"] == {"name": "jdoe"}
    assert sent["customfield_4"] == 28452329.0
    assert sent["customfield_5"] == ["dingo-main"]


def test_submit_drops_rejected_optional_field_and_retries(data_dir):
    with patch.object(core.requests, "get", fake_get):
        meta = core.load_project_meta("t", "u", "MAD")
    ids = {f["name"]: f["id"] for f in meta["form_fields"]}
    ticket = {"summary": "S", "description": "D", "values": {ids["Severity"]: "High", ids["Notas QA"]: "x"}}
    calls = []

    def fake_post(url, headers, json):
        calls.append(dict(json["fields"]))
        if len(calls) == 1:
            return _resp(400, {"errors": {ids["Notas QA"]: "no esta en la pantalla", ids["Severity"]: "invalido"}})
        return _resp(201, {"key": "MAD-2"})

    with patch.object(core.requests, "post", fake_post):
        res, warnings = core.submit_ticket("t", ticket, meta)
    assert res.status_code == 201
    assert ids["Notas QA"] not in calls[1]          # opcional: se quita
    assert ids["Severity"] in calls[1]              # obligatorio: se conserva
    assert warnings == ["Notas QA: no esta en la pantalla"]


# --- cerrar sesion -----------------------------------------------------------------

def test_logout_forgets_new_and_old_saved_keys(monkeypatch):
    store = {("macondo-logger", "jira_token"): "nuevo", ("sk8-buglogger", "jaas_token"): "viejo",
             ("macondo-logger", "groq_key"): "g"}

    def delete(service, name):
        if (service, name) not in store:
            raise KeyError(name)
        del store[(service, name)]

    fake = SimpleNamespace(get_password=lambda s, n: store.get((s, n)), delete_password=delete,
                           set_password=lambda s, n, v: store.__setitem__((s, n), v))
    monkeypatch.setattr(core, "keyring", fake)
    core.delete_jira_token()
    assert core.load_jira_token() is None          # ni el nuevo ni el de la version vieja
    assert core.get_groq_key() == "g"               # la Groq key se queda si no se pide
    core.delete_groq_key()
    assert ("macondo-logger", "groq_key") not in store


# --- la app arranca ------------------------------------------------------------------

def test_app_starts_without_errors():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "macondo_app.py"), default_timeout=30).run()
    assert not at.exception
