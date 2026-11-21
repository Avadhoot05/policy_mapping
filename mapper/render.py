"""HTML rendering with Jinja2 templates 
The page layout lives in mapper/templates/*.html, styles and browser code in mapper/static/. This module only
prepares the data and renders. CSS and JS are inlined into each page, so a saved report.html stays one
self-contained file. Autoescaping is on: every value from the sources is HTML-escaped.
"""
import os
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

HERE = os.path.dirname(os.path.abspath(__file__))

# labels and badge colours used by the templates
STATUS_CLASS = {"covered": "ok", "partial": "warn", "topic_only": "muted", "not_found": "bad"}
IMPL_CLASS = {"record_exists": "ok", "mixed": "warn", "open_or_planned": "warn", "unknown": "muted"}
RECORD_STATUS_CLASS = {"done": "ok", "open": "warn", "other": "muted"}
REL_LABEL = {"covers": "Covers", "partial": "Partial", "topic_only": "Topic only", "scope_mismatch": "Scope mismatch",
             "supporting": "Supporting record", "context": "Context", "excluded": "Other entity"}
FLAG_LABEL = {"translation_only": "Only in translation", "superseded": "Superseded version",
              "scope_mismatch": "Wrong-topic match", "entity_not_stated": "Entity not stated",
              "off_topic_policy": "In unrelated policy"}
DUE_FIELDS = ("Next due", "Next review", "naechste_frist")
SHOWN_ELSEWHERE = {"Status", *DUE_FIELDS}       # shown as the status badge / in the "Next due" column


# ---------------------------------------------------------------- helpers called from the templates

def source_url(slug, c):
    """Link to the source viewer with the cited lines, JSON path or CSV row/field highlighted."""
    loc = c["loc"]
    if "line_start" in loc:
        q = f"?ls={loc['line_start']}&le={loc['line_end']}"
    elif "json_path" in loc:
        q = f"?path={quote(loc['json_path'])}"
    else:
        q = f"?row={quote(loc['row_id'])}&field={quote(loc['field'])}"
    return f"/c/{quote(slug)}/source/{quote(c['source_id'])}{q}"


def line_label(loc):
    """'L24' or 'L24–25'."""
    a, b = loc["line_start"], loc["line_end"]
    return f"L{a}" if a == b else f"L{a}–{b}"


def record_view(c):
    """What the Evidence tab shows for one record: name, the register's own status, other cells, due dates."""
    st = c.get("record_status") or {}
    view = {"status": st.get("value", ""), "status_class": RECORD_STATUS_CLASS.get(st.get("signal"), "muted"),
            "name": None, "details": "", "due": []}
    cells = c.get("cells") or {}
    if cells:
        first = next(iter(cells))
        view["name"] = cells[first]
        view["details"] = " · ".join(f"{k}: {v}" for k, v in cells.items()
                                     if k != first and k not in SHOWN_ELSEWHERE and v not in ("", "-"))
    values = cells or {k: (v["value"] if isinstance(v, dict) else v) for k, v in c.get("record_fields", {}).items()}
    overdue = {o["field"]: o for o in c.get("overdue", [])}
    for k in DUE_FIELDS:
        if k in overdue:
            view["due"].append({"field": k, "date": overdue[k]["date"], "days_overdue": overdue[k]["days_overdue"],
                                "as_of": overdue[k]["as_of"]})
        elif values.get(k) not in (None, "", "-"):
            view["due"].append({"field": k, "date": values[k], "days_overdue": None})
    return view


def gate_reason(c, gate):
    return next((g["reason"] for g in c["gates"] if g["gate"] == gate), "")


def _static(name):
    """CSS / JS file content, marked safe so it is inlined as written."""
    with open(os.path.join(HERE, "static", name), encoding="utf-8") as f:
        return Markup(f.read())


env = Environment(loader=FileSystemLoader(os.path.join(HERE, "templates")), autoescape=True,
                  trim_blocks=True, lstrip_blocks=True, undefined=StrictUndefined)
env.globals.update(STATUS_CLASS=STATUS_CLASS, IMPL_CLASS=IMPL_CLASS, REL_LABEL=REL_LABEL, FLAG_LABEL=FLAG_LABEL,
                   source_url=source_url, line_label=line_label, record_view=record_view, gate_reason=gate_reason)
env.filters["basename"] = lambda p: p.split("/")[-1]


# ---------------------------------------------------------------- pages

def render_report(result):
    """The report of one run: Overview, Duty results, Version comparison."""
    company = result["company"]
    return env.get_template("report.html").render(
        result=result, company=company, legal=result["legal_input"], slug=company["slug"],
        duties=[du for du in result["duties"] if "elements" in du],
        run_info={"slug": company["slug"], "run_id": result["run_id"]},
        css=_static("report.css"), js=_static("report.js"))


def render_legal_duty(result, du):
    """Stand-alone page with the original German legal analysis of one duty."""
    return env.get_template("legal_duty.html").render(
        du=du, company=result["company"], legal=result["legal_input"], css=_static("report.css"))


def render_start(companies_info):
    return env.get_template("start.html").render(
        companies=companies_info, css=_static("report.css"), js=_static("start.js"))


def render_source(company_name, doc, ls=None, le=None, path=None, row=None, field=None):
    row_data = next((x for x in doc.get("rows", []) if x.get("id") == row), {}) if row is not None else {}
    return env.get_template("source.html").render(
        title=doc.get("title", doc["file"]), company_name=company_name, doc=doc, ls=ls, le=le,
        path=path, row_data=row_data, field=field, css=_static("report.css"))
