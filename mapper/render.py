"""HTML rendering: the report (one self-contained file per run), the start page and the source viewer."""
import json
from html import escape as _esc
from urllib.parse import quote

STATUS_CLASS = {"covered": "ok", "partial": "warn", "topic_only": "muted", "not_found": "bad"}
IMPL_CLASS = {"record_exists": "ok", "mixed": "warn", "open_or_planned": "warn", "unknown": "muted"}
REL_LABEL = {"covers": "Covers", "partial": "Partial", "topic_only": "Topic only", "scope_mismatch": "Scope mismatch",
             "supporting": "Supporting record", "context": "Context", "excluded": "Other entity"}
FLAG_LABEL = {"translation_only": "Only in translation", "superseded": "Superseded version",
              "scope_mismatch": "Wrong-topic match", "entity_not_stated": "Entity not stated",
              "off_topic_policy": "In unrelated policy"}


def e(x):
    return _esc("" if x is None else str(x))


def badge(text, cls):
    return f'<span class="badge {cls}">{e(text)}</span>'


def chip(text, cls=""):
    return f'<span class="chip {cls}">{e(text)}</span>'


CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--muted:#6b6a66;--line:#e2e0da;--accent:#2f4f6f;
--ok:#2e6b3f;--ok-bg:#e5f1e8;--warn:#8a5a00;--warn-bg:#fbf0d9;--bad:#9b2c2c;--bad-bg:#f8e3e1;
--muted-bg:#eeede9;--info:#2f4f8f;--info-bg:#e4ebf7;--mis:#6a3d8a;--mis-bg:#efe6f5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:19px;margin:32px 0 12px}h3{font-size:16px;margin:0}h4{font-size:14px;margin:16px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
a{color:var(--accent)}.muted{color:var(--muted)}small{color:var(--muted)}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
.actions{display:flex;gap:8px;flex-wrap:wrap}
button,.btn{font:inherit;border:1px solid var(--line);background:var(--card);padding:6px 12px;border-radius:6px;cursor:pointer;color:var(--ink);text-decoration:none;display:inline-block}
button.primary,.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button:disabled{opacity:.5;cursor:default}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px 24px;margin:16px 0;font-size:14px}
.meta div span{display:block;color:var(--muted);font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{font-size:12px;color:var(--muted);font-weight:600}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.bad{background:var(--bad-bg);color:var(--bad)}
.badge.muted{background:var(--muted-bg);color:var(--muted)}.badge.info{background:var(--info-bg);color:var(--info)}.badge.mis{background:var(--mis-bg);color:var(--mis)}
.chip{display:inline-block;border:1px solid var(--line);border-radius:4px;padding:0 6px;font-size:12px;margin:0 4px 4px 0;background:#faf9f7}
.chip.info{border-color:#b9c7e6;background:var(--info-bg)}.chip.mis{border-color:#d4c0e2;background:var(--mis-bg)}.chip.sup{border-color:#ccc;background:var(--muted-bg)}
.proposal{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);border:1px dashed var(--muted);border-radius:4px;padding:0 5px}
.quote{white-space:pre-wrap;background:#fbfaf7;border-left:3px solid var(--accent);margin:6px 0;padding:8px 10px;font-size:14px;font-family:ui-serif,Georgia,serif}
.quote.nc{border-left-color:#b9b6ae}
.qcard{padding:10px 0}.qcard+.qcard{border-top:1px solid var(--line)}
.duty.collapsed .dbody{display:none}
.toggle{margin-left:auto;border:1px solid var(--line);background:none;border-radius:6px;width:30px;height:30px;font-size:16px;line-height:1;cursor:pointer;transition:transform .15s}.duty.collapsed .toggle{transform:rotate(-90deg)}
.qhead{font-size:13px;color:var(--muted)}
.el{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}.el:first-child{border-top:0;margin-top:0;padding-top:0}
.elhead{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.next{background:var(--warn-bg);border-radius:6px;padding:8px 12px;font-size:14px;margin-top:8px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:12px 0 0;flex-wrap:wrap}
.tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:none;padding:6px 10px;color:var(--muted)}
.tabs button.on{border-bottom-color:var(--accent);color:var(--ink);font-weight:600}
.panel{display:none;padding-top:12px}.panel.on{display:block}
.mtabs{display:flex;gap:4px;border-bottom:2px solid var(--line);margin:20px 0 4px;position:sticky;top:0;background:var(--bg);z-index:5}
.mtabs button{border:0;border-bottom:3px solid transparent;border-radius:0;background:none;padding:10px 16px;font-size:15px;color:var(--muted);margin-bottom:-2px}
.mtabs button.on{border-bottom-color:var(--accent);color:var(--ink);font-weight:600}
.mpanel{display:none}.mpanel.on{display:block}
.card,.el{scroll-margin-top:64px}
details summary{cursor:pointer;color:var(--accent);font-size:13px}
.review{background:#fafafa;border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin-top:10px;font-size:13px}
.review input,.review textarea{font:inherit;border:1px solid var(--line);border-radius:4px;padding:4px 6px;width:100%}
.review .row{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}.review .cur{margin-bottom:6px}
.stale{color:var(--bad);font-weight:600}
.side{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.sent{white-space:pre-wrap;padding:4px 6px;border-radius:4px;margin:3px 0;font-size:13px;font-family:ui-serif,Georgia,serif}
.sent.only_here{background:var(--warn-bg);outline:1px solid #e7cf9b}.sent.same{background:#f4f3ef}
tr.changed td{background:var(--warn-bg)}
.kv{display:grid;grid-template-columns:200px 1fr;gap:4px 12px;font-size:14px}.kv>div:nth-child(odd){color:var(--muted)}
pre.de{white-space:pre-wrap;font-size:13px;background:#fbfaf7;padding:8px;border-radius:4px}
footer{margin:40px 0 20px;font-size:13px;color:var(--muted)}
"""


def _loc_link(slug, c, text="View source"):
    loc = c["loc"]
    if "line_start" in loc:
        q = f"?ls={loc['line_start']}&le={loc['line_end']}"
    elif "json_path" in loc:
        q = f"?path={quote(loc['json_path'])}"
    else:
        q = f"?row={quote(loc['row_id'])}&field={quote(loc['field'])}"
    return f'<a href="/c/{quote(slug)}/source/{quote(c["source_id"])}{e(q)}" target="_blank" title="Open the source with this location highlighted">{e(text)}</a>'


def _doc_chips(c):
    d = c["doc"]
    bits = []
    lc = d.get("lifecycle")
    if lc == "current":
        bits.append(chip("Current"))
    elif lc == "superseded":
        bits.append(chip("Superseded", "sup"))
    for q in c.get("qualifiers", []):
        if q in FLAG_LABEL and q != "superseded":
            bits.append(chip(FLAG_LABEL[q], "info"))
    return "".join(bits)


def _quote_card(slug, c, counted):
    rel = REL_LABEL.get(c["relation"], c["relation"])
    why = ""
    if c.get("why_not_counted"):
        why = '<div class="qhead">Not counted: ' + e("; ".join(c["why_not_counted"])) + "</div>"
    facets = ""
    if c["doc"]["kind"] == "policy" and c["relation"] in ("covers", "partial"):
        facets = (f'<div class="qhead">Facets present: {e(", ".join(c["facets_present_labels"]) or "none")} · '
                  f'missing: {e(", ".join(c["facets_missing_labels"]) or "none")}</div>')
    return (f'<div class="qcard"><div class="qhead">{badge(rel, "ok" if counted else ("mis" if c["relation"] == "scope_mismatch" else "muted"))} '
            f'<b>{e(c["doc"]["title"])}</b> · {e(c["file"])} · <b>{e(c["location"])}</b> · {_loc_link(slug, c)}</div>'
            f'<div>{_doc_chips(c)}</div>'
            # counted passages keep the verbatim quote (task: exact quote); not-counted ones link to the source
            + (f'<div class="quote">{e(c["quote"])}</div>' if counted else "")
            + f'{facets}{why}<div class="qhead">document_id {e(c["source_id"])}</div></div>')


def _review_box(duty_id, el):
    key = f"{duty_id}/{el['id']}"
    return (f'<div class="review" data-key="{e(key)}" data-duty="{e(duty_id)}" data-element="{e(el["id"])}">'
            f'<div class="cur"><b>Reviewer decision:</b> <span class="curtxt muted">not reviewed yet</span></div>'
            f'<textarea rows="2" placeholder="Comment / rationale (optional)"></textarea>'
            f'<div class="row"><button data-d="confirmed">Confirm</button><button data-d="rejected">Reject</button>'
            f'<button data-d="needs_clarification">Needs clarification</button></div>'
            f'<details class="hist"><summary>History</summary><div class="histbody muted">No decisions yet.</div></details></div>')


def _mapping_panel(slug, du):
    out = []
    for el in du["elements"]:
        flags = "".join(chip(FLAG_LABEL.get(f, f), "mis" if f == "scope_mismatch" else "info") for f in el["flags"])
        out.append(f'<div class="el" id="el-{e(du["duty_id"])}-{e(el["id"])}"><div class="elhead"><h3>{e(el["label"])}</h3>'
                   f'{badge(el["policy_status_label"], STATUS_CLASS[el["policy_status"]])}'
                   f'<span class="proposal" data-key="{e(du["duty_id"])}/{e(el["id"])}" title="Generated by the tool; not yet reviewed">System proposal</span>{flags}</div>'
                   f'<p>{e(el["explanation"])}</p>')
        if el["passages"]:
            out.append("<h4>Supporting passages (counted)</h4>" + "".join(_quote_card(slug, c, True) for c in el["passages"]))
        if el["not_counted"]:
            out.append(f'<details><summary>Checked but not counted ({len(el["not_counted"])})</summary>'
                       + "".join(_quote_card(slug, c, False) for c in el["not_counted"]) + "</details>")
        if el.get("next_step"):
            out.append(f'<div class="next"><b>Next step:</b> {e(el["next_step"]["text"])}</div>')
        out.append(_review_box(du["duty_id"], el) + "</div>")
    return "".join(out)


RECORD_STATUS_CLASS = {"done": "ok", "open": "warn", "other": "muted"}
SHOWN_ELSEWHERE = {"Status", "Next due", "Next review", "naechste_frist"}   # status badge / Overdue column


def _record_summary(c):
    """Record name with its status badge (the register's own wording, e.g. "aktiv"), then the other cells."""
    st = c.get("record_status") or {}
    sb = (" " + badge(st["value"], RECORD_STATUS_CLASS.get(st.get("signal"), "muted"))) if st.get("value") else ""
    if c.get("cells"):
        keys = list(c["cells"].keys())
        main = c["cells"].get(keys[0], "")
        rest = [f"{k}: {v}" for k, v in c["cells"].items()
                if k != keys[0] and k not in SHOWN_ELSEWHERE and v not in ("", "-")]
        return f"<b>{e(main)}</b>{sb}<br><small>{e(' · '.join(rest))}</small>"
    return f'{sb.strip()}<span class="quote" style="display:block">{e(c["quote"])}</span>'


def _due(c):
    """Next due / next review date of a record; overdue ones (before the snapshot date) in red with the day count."""
    over = {o["field"]: o for o in c.get("overdue", [])}
    src = c.get("cells") or {k: (v["value"] if isinstance(v, dict) else v) for k, v in c.get("record_fields", {}).items()}
    out = []
    for k in ("Next due", "Next review", "naechste_frist"):
        if k in over:
            out.append(f'{e(k)} {e(over[k]["date"])} <span class="stale">({over[k]["days_overdue"]} days overdue)</span>')
        elif src.get(k) not in (None, "", "-"):
            out.append(f"{e(k)} {e(src[k])}")
    return "<br>".join(out)


def _evidence_panel(slug, du):
    out = []
    for el in du["elements"]:
        rows = []
        for c in el["supporting"]:
            od = _due(c)
            rows.append(f"<tr><td>{_loc_link(slug, c, c['doc']['title'])}<br><small>{e(c['location'])}</small></td>"
                        f"<td>{_record_summary(c)}"
                        + ("".join(chip(FLAG_LABEL[q], "info") for q in c["qualifiers"] if q in FLAG_LABEL))
                        + f"</td><td>{od or '–'}</td></tr>")
        mism = el["supporting_scope_mismatch"]
        out.append(f'<div class="el"><div class="elhead"><h3>{e(el["label"])}</h3></div>'
                   f'<div class="kv"><div>Implementation</div><div>{badge(el["implementation"]["label"], IMPL_CLASS[el["implementation"]["state"]])}</div>'
                   f'<div>Effectiveness</div><div>{badge(el["effectiveness"]["label"], "muted")}</div></div>')
        if rows:
            out.append('<table><tr><th>Source</th><th>Record</th><th>Next due</th></tr>' + "".join(rows) + "</table>")
        else:
            out.append('<p class="muted">No supporting record found in the sources reviewed.</p>')
        if mism:
            out.append(f'<details><summary>Records matched by terms but with another topic ({len(mism)}, not used)</summary><ul>'
                       + "".join(f"<li>{e(c['file'])} {e(c['location'])}: {e(c['quote'][:140])} "
                                 f"<small>({e(next(g['reason'] for g in c['gates'] if g['gate'] == '5 scope'))})</small></li>" for c in mism)
                       + "</ul></details>")
        out.append("</div>")
    out.append('<p class="muted"><small>Records describe implementation, not policy text. Per 17-AUS-17, register '
               'summaries such as “erfüllt” or “wirksam” are source metadata and do not prove effectiveness of the duty; '
               'missing proof means “not demonstrated”, only a proven failure means “ineffective”.</small></p>')
    return "".join(out)


def _missing_panel(du):
    """Missing information: expected evidence verbatim from the legal input, missing facets of partial
    passages (computed), and the company's own open twin questions. No hand-written text."""
    out = [f'<div class="el"><p class="muted" title="Verbatim from the legal input ({e(du["duty_id"])})"><small>'
           f'<b>Expected evidence:</b> {e(du["expected_evidence_de"])}<br>'
           f'<b>Evidence question:</b> {e(du["evidence_question_de"])}</small></p></div>']
    for el in du["elements"]:
        if el["policy_status"] == "covered":
            line = '<span class="muted">Covered – nothing missing in the policy text.</span>'
        elif el["policy_status"] == "partial":
            p0 = el["passages"][0]
            line = (f'The rule at {e(p0["doc"]["policy_no"])} v{e(p0["doc"]["version"])} {e(p0["location"])} does not state: '
                    f'<b>{e(", ".join(p0["facets_missing_labels"]))}</b>.')
        else:
            line = f'No policy rule found ({e(el["policy_status_label"])}).'
        tq = "".join(f"<li><b>#{e(q['shortId'])}</b> {e(q['text'])} <small>({e(q['topic'])}, status: {e(q['status'])}, "
                     f"answer: {e(q['answer']) or 'none – unknown, not “no”'})</small></li>" for q in el["twin_questions"])
        out.append(f'<div class="el"><h3>{e(el["label"])}</h3><p>{line}</p>'
                   + (f"<h4>Related open questions in the company's digital twin</h4><ul>{tq}</ul>" if tq else "")
                   + "</div>")
    return "".join(out)


def _sources_panel(du):
    out = []
    for el in du["elements"]:
        # sources with hits in the table; the others in one line, so "not found" stays about all sources reviewed
        hit = [s for s in el["sources_checked"] if s["hits"]]
        nohit = [s for s in el["sources_checked"] if not s["hits"]]
        body = ""
        if hit:
            rows = "".join(f"<tr><td>{e(s['title'])}<br><small>{e(s['file'])}</small></td><td>{e(s['kind'])}</td>"
                           f"<td>{s['hits']}</td><td>{e(', '.join(REL_LABEL.get(r, r) for r in s['relations']))}</td></tr>"
                           for s in hit)
            body += f'<table><tr><th>Source</th><th>Kind</th><th>Hits</th><th>Outcome</th></tr>{rows}</table>'
        if nohit and not hit:
            body += f'<p class="muted"><small>No hits in any of the {len(nohit)} sources reviewed.</small></p>'
        elif nohit:
            body += (f'<details><summary class="muted"><small>{len(nohit)} other source{"s" if len(nohit) != 1 else ""} '
                     f'without hits</small></summary><p class="muted"><small>'
                     + e("; ".join(s["file"].split("/")[-1] for s in nohit)) + '</small></p></details>')
        out.append(f'<details><summary>{e(el["label"])} – search terms: {e(", ".join(el["terms"]))}'
                   f' <span class="muted"><small>({len(hit)} of {len(el["sources_checked"])} sources with hits)</small></span></summary>'
                   f'{body}</details>')
    return "".join(out)


def _duty_section(slug, du):
    did = du["duty_id"]
    tabs = [("map", "Mapping", _mapping_panel(slug, du)), ("ev", "Evidence", _evidence_panel(slug, du)),
            ("q", "Missing information", _missing_panel(du)),
            ("src", "Sources checked", _sources_panel(du))]
    tb = "".join(f'<button class="{"on" if i == 0 else ""}" data-tab="{did}-{k}">{e(t)}</button>' for i, (k, t, _) in enumerate(tabs))
    pn = "".join(f'<div class="panel{" on" if i == 0 else ""}" id="{did}-{k}">{body}</div>'
                 for i, (k, t, body) in enumerate(tabs))
    return (f'<section class="card duty" id="duty-{e(did)}"><div class="elhead"><h2 style="margin:0"><a href="legal/{quote(did)}" target="_blank" title="Open the legal duty">{e(did)} · {e(du["title"])}</a></h2>'
            f'{badge(du["status_label"], STATUS_CLASS[du["status"]])}'
            f'<button class="toggle" aria-expanded="true" aria-label="Collapse" title="Collapse">▾</button></div>'
            f'<div class="dbody">'
            f'<div class="tabs">{tb}</div>{pn}</div></section>')


def _overview(result):
    rows = []
    for du in result["duties"]:
        els = du.get("elements", [])
        for i, el in enumerate(els):
            first = f'<td rowspan="{len(els)}"><a href="#duty-{e(du["duty_id"])}"><b>{e(du["duty_id"])}</b></a><br>{e(du["title"])}</td>' if i == 0 else ""
            rows.append(f'<tr>{first}<td><a href="#el-{e(du["duty_id"])}-{e(el["id"])}">{e(el["label"])}</a></td>'
                        f'<td>{badge(el["policy_status_label"], STATUS_CLASS[el["policy_status"]])} '
                        + "".join(chip(FLAG_LABEL.get(f, f), "mis" if f == "scope_mismatch" else "info") for f in el["flags"])
                        + f'</td><td>{badge(el["implementation"]["short"], IMPL_CLASS[el["implementation"]["state"]])}'
                        + (f' {chip(str(el["implementation"]["overdue_records"]) + " overdue")}' if el["implementation"]["overdue_records"] else "")
                        + f'</td><td><small>{e(el["effectiveness"]["short"])}</small></td>'
                        f'<td class="ovrev" data-key="{e(du["duty_id"])}/{e(el["id"])}"><small class="muted">not reviewed</small></td></tr>')
    return ('<table><tr><th>Duty</th><th>Element</th><th>Policy text (Soll)</th><th>Implementation records</th>'
            '<th>Effectiveness</th><th>Review</th></tr>' + "".join(rows) + "</table>")


def _comparisons(result):
    out = []
    slug = result["company"]["slug"]
    for cmp_ in result["comparisons"]:
        L, R = cmp_["left"], cmp_["right"]
        if cmp_["kind"] == "language":
            out.append(_language_box(slug, cmp_))
            continue
        kind = "Version comparison" if cmp_["kind"] == "version" else "Language comparison"
        meta = "".join(
            f'<tr class="{"changed" if m["changed"] else ""}"><td>{e(m["field"])}</td>'
            f'<td>{e(m["left"]["value"]) if m["left"] else "–"} <small>{("L" + str(m["left"]["line"])) if m["left"] else ""}</small></td>'
            f'<td>{e(m["right"]["value"]) if m["right"] else "–"} <small>{("L" + str(m["right"]["line"])) if m["right"] else ""}</small></td></tr>'
            for m in cmp_["metadata"])
        secs = []
        for s in cmp_["sections"]:
            def col(items, head, hl):
                return (f'<div><div class="qhead"><b>{e(head)}</b> {("(L" + str(hl) + ")") if hl else ""}</div>'
                        + "".join(f'<div class="sent {it["status"]}"><small>L{it["loc"]["line_start"]}'
                                  f'{("–" + str(it["loc"]["line_end"])) if it["loc"]["line_end"] != it["loc"]["line_start"] else ""}</small> '
                                  f'{e(it["text"])}</div>' for it in items) + "</div>")
            secs.append(f'<div class="side">{col(s["left"], s["left_heading"], s["left_heading_line"])}'
                        f'{col(s["right"], s["right_heading"], s["right_heading_line"])}</div>')
        notes = "".join(f"<li>{e(n)}</li>" for n in L["notes"] + R["notes"])
        title = f'{cmp_["policy_no"]} {e(cmp_["title"])}'
        sub = (f'{L["doc_number"]} v{L["version"]} {L["language"].upper()} ({L["lifecycle"]}) → '
               f'{R["doc_number"]} v{R["version"]} {R["language"].upper()} ({R["lifecycle"]})')
        out.append(f'<section class="card"><div class="elhead"><h3>{e(kind)}: {title}</h3>'
                   f'{badge("Body changed" if cmp_["body_changed"] else "Body identical", "warn" if cmp_["body_changed"] else "ok")}</div>'
                   f'<div class="muted">{e(sub)}</div><p>{e(cmp_["coverage_change"])}</p>'
                   + (f'<p class="muted">{e(cmp_["validity_note"])}</p>' if cmp_["validity_note"] else "")
                   + (f"<h4>Version notes</h4><ul>{notes}</ul>" if notes else "")
                   + f'<h4>Metadata</h4><table><tr><th>Field</th><th>{e(L["doc_number"])} <small>{e(L["file"])}</small></th>'
                   f'<th>{e(R["doc_number"])} <small>{e(R["file"])}</small></th></tr>{meta}</table>'
                   f'<h4>Body text, side by side</h4><p class="muted"><small>Highlighted sentences have no identical counterpart on the other side.</small></p>'
                   + "".join(secs) + "</section>")
    return "".join(out) or '<p class="muted">No policy family with two versions in the sources.</p>'


def _language_box(slug, cmp_):
    L, R = cmp_["left"], cmp_["right"]
    items = "".join(
        f'<div class="qcard"><div class="qhead"><b>{e(R["doc_number"])}</b> · {e(R["file"])} · '
        f'<b>L{s["loc"]["line_start"]}{("–" + str(s["loc"]["line_end"])) if s["loc"]["line_end"] != s["loc"]["line_start"] else ""}</b>'
        f' · section \u201c{e(s["section"])}\u201d · {_loc_link(slug, {"source_id": R["source_id"], "loc": s["loc"]})}</div>'
        f'<div class="quote nc">{e(s["text"])}</div></div>' for s in cmp_["extra_in_translation"])
    return (f'<section class="card"><div class="elhead"><h3>Language difference: {e(cmp_["policy_no"])} v{e(cmp_["version"])} '
            f'{e(L["language"].upper())} (master) ↔ {e(R["language"].upper())}</h3>'
            f'{badge("Content differs" if cmp_["extra_in_translation"] else "No missing passage", "warn" if cmp_["extra_in_translation"] else "ok")}</div>'
            f'<div class="kv"><div>Master</div><div>{e(L["doc_number"])} · {e(L["file"])} · valid from {e(L["valid_from"])}</div>'
            f'<div>Translation</div><div>{e(R["doc_number"])} · {e(R["file"])} · valid from {e(R["valid_from"])}</div></div>'
            f'<p>{e(cmp_["coverage_change"])}</p>'
            + (f'<h4>Only in the {e(R["language"].upper())} version (text in {e(L["language"].upper())}, not in the master)</h4>{items}' if items else "")
            + '<p class="muted"><small>Language versions are kept separate and never combined. Only identical text is '
              'compared; no translation or AI is used.</small></p></section>')


JS = r"""
const RUN=%RUN%;
function mainTab(id){document.querySelectorAll('.mtabs button').forEach(b=>b.classList.toggle('on',b.dataset.main===id));
 document.querySelectorAll('.mpanel').forEach(p=>p.classList.toggle('on',p.id===id));}
document.querySelectorAll('.mtabs button').forEach(b=>b.onclick=()=>{mainTab(b.dataset.main);history.replaceState(null,'','#'+b.dataset.main);});
function followHash(){const h=decodeURIComponent(location.hash.slice(1));if(!h)return;const el=document.getElementById(h);if(!el)return;
 const p=el.closest('.mpanel');if(p)mainTab(p.id);const card=el.closest('.duty');if(card)setCard(card,true);if(el===p)window.scrollTo(0,0);else el.scrollIntoView();}
window.addEventListener('hashchange',followHash);
function setCard(card,open){card.classList.toggle('collapsed',!open);const b=card.querySelector('.toggle');
 const l=open?'Collapse':'Expand';b.title=l;b.setAttribute('aria-label',l);b.setAttribute('aria-expanded',open);}
document.querySelectorAll('.duty .toggle').forEach(b=>b.onclick=()=>{const c=b.closest('.duty');setCard(c,c.classList.contains('collapsed'));});
document.querySelectorAll('.tabs').forEach(t=>t.addEventListener('click',ev=>{const b=ev.target.closest('button');if(!b)return;
 const sec=t.parentElement;t.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
 sec.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id===b.dataset.tab));}));
const api=`/api/c/${RUN.slug}/runs/${RUN.run_id}/reviews`;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function show(data){
 Object.entries(data).forEach(([k,d])=>{const c=d&&d.current;if(!c)return;
  const ov=document.querySelector(`.ovrev[data-key="${k}"]`);
  if(ov)ov.innerHTML=`<small><b>${esc(c.label)}</b><br>${esc(c.reviewer)}${c.stale?'<br><span class="stale">Re-review needed</span>':''}</small>`;
  const pb=document.querySelector(`.proposal[data-key="${k}"]`);
  if(pb){pb.className='badge '+(c.stale?'bad':({confirmed:'ok',rejected:'bad',needs_clarification:'warn'}[c.decision]||'muted'));
   pb.textContent=c.stale?`Re-review needed (was: ${c.label})`:`${c.label} by ${c.reviewer} · ${String(c.at).slice(0,10)}`;
   pb.title=c.stale?'The system proposal changed after this decision':(c.comment||'Reviewer decision');}
  const box=document.querySelector(`.review[data-key="${k}"]`);if(!box)return;
  const st=c.stale?' <span class="stale">Re-review needed – the proposal changed since this decision</span>':'';
  const txt=`<b>${esc(c.label)}</b> by ${esc(c.reviewer)} on ${esc(c.at)}${c.comment?': “'+esc(c.comment)+'”':''}${st}`;
  const cur=box.querySelector('.curtxt');cur.innerHTML=txt;cur.classList.remove('muted');
  box.querySelector('.histbody').innerHTML=d.history.map(h=>`<div>${esc(h.at)} · ${esc(h.reviewer)} · <b>${esc(h.decision)}</b> ${esc(h.comment)} <small>(run ${esc(h.run_id)})</small></div>`).join('');});}
function load(){fetch(api).then(r=>r.json()).then(show).catch(()=>{document.querySelectorAll('.ovrev').forEach(x=>x.innerHTML='<small class="muted">needs the local server</small>');document.querySelectorAll('.review .curtxt').forEach(x=>x.textContent='Reviews need the local server (python3 app.py).');
 document.querySelectorAll('.review button').forEach(b=>b.disabled=true);});}
document.querySelectorAll('.review').forEach(box=>box.addEventListener('click',ev=>{const b=ev.target.closest('button[data-d]');if(!b)return;
 let name=localStorage.getItem('reviewer')||prompt('Your name (stored with the decision):');if(!name)return;localStorage.setItem('reviewer',name);
 fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({duty_id:box.dataset.duty,element_id:box.dataset.element,
  decision:b.dataset.d,comment:box.querySelector('textarea').value,reviewer:name})}).then(r=>r.json().then(j=>{if(!r.ok)throw new Error(j.error);return j;}))
  .then(()=>{box.querySelector('textarea').value='';load();}).catch(err=>alert('Could not save: '+err.message));}));
load();followHash();window.addEventListener('load',()=>setTimeout(followHash,0));
"""


def _page(result, title, body, nav):
    c = result["company"]
    li = result["legal_input"]
    run = json.dumps({"slug": c["slug"], "run_id": result["run_id"]})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} – {e(c['name'])} – {e(result['run_id'])}</title><style>{CSS}</style></head><body><main>
<div class="top"><div><h1>{e(title)}</h1><div class="muted">Run {e(result['run_id'])}</div></div>
<div class="actions">{nav}<a class="btn" href="/">Start page</a></div></div>
<div class="meta"><div><span>Assessed entity</span>{e(c['entity_name'])} ({e(', '.join(c['entity_codes']))})<br><small>{e(c['entity_id'])}</small></div>
<div><span>Data snapshot</span>{e(c['snapshot_date'])}</div><div><span>Legal input</span>{e(li['file'])} · {e(li['workbook'])}<br><small>analysis dated {e(li['analysis_date'])}</small></div>
<div><span>Generated</span>{e(result['generated_at'])}</div></div>
{body}
</main><script>{JS.replace('%RUN%', run)}</script></body></html>"""


def render_report(result):
    """One page with three tabs: Overview, Duty results, Version comparison."""
    slug = result["company"]["slug"]
    duties = "".join(_duty_section(slug, du) for du in result["duties"] if "elements" in du)
    tabs = [("overview", "Overview", f'<div class="card">{_overview(result)}</div>'),
            ("duties", "Duty results", duties),
            ("comparison", "Version comparison", _comparisons(result))]
    bar = "".join(f'<button class="{"on" if i == 0 else ""}" data-main="{k}">{e(t)}</button>' for i, (k, t, _) in enumerate(tabs))
    panels = "".join(f'<div class="mpanel{" on" if i == 0 else ""}" id="{k}">{body}</div>'
                     for i, (k, t, body) in enumerate(tabs))
    return _page(result, "Policy mapping · NIS2 / BSIG §30", f'<div class="mtabs">{bar}</div>{panels}', "")


def render_legal_duty(result, du):
    """Stand-alone page with the original German legal analysis of one duty."""
    c = result["company"]
    li = result["legal_input"]
    links = "".join(f'<li><a href="{e(u.split(" ")[0])}" target="_blank">{e(u)}</a></li>' for u in du["source_links"] if u.strip())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(du['duty_id'])} – legal duty</title><style>{CSS}</style></head><body><main>
<h1>{e(du['duty_id'])} · {e(du['title'])}</h1>
<div class="muted">{e(du['label_de'])}</div>
<div class="meta"><div><span>Legal input</span>{e(li['file'])}</div><div><span>Workbook</span>{e(li['workbook'])}, row {e(du['source_row'])}</div>
<div><span>Analysis dated</span>{e(li['analysis_date'])}</div><div><span>Assessed entity</span>{e(c['entity_name'])}</div></div>
<div class="card"><div class="kv"><div>Addressees</div><div>{e(du['addressees_de'])}</div>
<div>Criterion</div><div>{e(du['criterion_de'])}</div>
<div>Evidence question</div><div>{e(du['evidence_question_de'])}</div>
<div>Expected evidence</div><div>{e(du['expected_evidence_de'])}</div></div>
<h4>Duties / evaluation guidance (original)</h4><pre class="de">{e(du['guidance_de'])}</pre>
<h4>Source links</h4><ul>{links}</ul></div>
</main></body></html>"""


# ---------------------------------------------------------------- start page and source viewer

def render_start(companies_info):
    cards = []
    for ci in companies_info:
        runs = "".join(f'<li><a href="{e(r["url"])}">{e(r["run_id"])}</a></li>' for r in ci["runs"][:10])
        latest = (f'<a class="btn" href="{e(ci["runs"][0]["url"])}">Open latest report</a>' if ci["runs"] else "")
        cards.append(f'<section class="card" data-slug="{e(ci["slug"])}"><div class="top"><div><h2 style="margin:0">{e(ci["name"])}</h2>'
                     f'<div class="muted">Entity {e(ci["entity_name"])} ({e(", ".join(ci["entity_codes"]))}) · snapshot {e(ci["snapshot_date"])}</div>'
                     f'<div class="muted"><small>{e(ci["slug"])} · inputs: {e(ci["input_dir"])}</small></div></div>'
                     f'<div class="actions"><button class="primary run">Start analysis</button>{latest}</div></div>'
                     f'<div class="status muted" style="margin-top:8px"></div>'
                     + (f'<details><summary>Earlier runs ({len(ci["runs"])})</summary><ul>{runs}</ul></details>' if ci["runs"] else "")
                     + "</section>")
    body = "".join(cards) or '<p>No companies found. Add a folder with a company.json to <code>companies/</code>.</p>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Policy mapping</title><style>{CSS}</style></head>
<body><main><h1>Policy mapping · NIS2 duties → internal policies</h1>
<p class="muted">Each company is analysed separately from its own folder in <code>companies/</code>. Start an analysis to generate a new report; earlier reports are kept.</p>
{body}</main><script>
document.querySelectorAll('section[data-slug]').forEach(s=>s.querySelector('.run').onclick=ev=>{{
 const b=ev.target,st=s.querySelector('.status');b.disabled=true;st.textContent='Running analysis…';
 fetch(`/api/c/${{s.dataset.slug}}/runs`,{{method:'POST'}}).then(r=>r.json().then(j=>{{if(!r.ok)throw new Error(j.error);return j;}}))
 .then(j=>{{st.innerHTML=`Done in ${{j.seconds}} s · <a href="${{j.report_url}}"><b>Open report</b></a>`;b.disabled=false;}})
 .catch(err=>{{st.textContent='Failed: '+err.message;b.disabled=false;}});}});
</script></body></html>"""


def render_source(company_name, doc, ls=None, le=None, path=None, row=None, field=None):
    title = doc.get("title", doc["file"])
    if "lines" in doc:
        rows = []
        for i, ln in enumerate(doc["lines"], 1):
            hl = ls is not None and ls <= i <= (le or ls)
            rows.append(f'<tr id="L{i}" style="{"background:#fbf0d9" if hl else ""}"><td class="muted" style="text-align:right;width:48px">{i}</td>'
                        f'<td style="white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:13px">{e(ln)}</td></tr>')
        body = f'<table>{"".join(rows)}</table>'
        anchor = f"<script>location.hash='L{max(1, (ls or 1) - 3)}'</script>" if ls else ""
    elif path is not None:
        body = f'<p><b>{e(path)}</b></p>' + "".join(
            f'<div class="quote">{e(u["text"])}</div>' for u in doc["units"] if u["loc"].get("json_path") == path)
        anchor = ""
    else:
        r = next((x for x in doc.get("rows", []) if x.get("id") == row), {})
        body = '<table>' + "".join(f'<tr style="{"background:#fbf0d9" if k == field else ""}"><td>{e(k)}</td><td>{e(v)}</td></tr>'
                                   for k, v in r.items()) + '</table>'
        anchor = ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(title)}</title><style>{CSS}</style></head>
<body><main><h1>{e(title)}</h1><p class="muted">{e(company_name)} · {e(doc['file'])} · document_id {e(doc['document_id'])} · sha256 {e(doc['sha256'])}</p>
<div class="card">{body}</div></main>{anchor}</body></html>"""
