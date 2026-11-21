"""The mapping pipeline: duties -> elements -> candidates -> gates -> proposal."""
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone

from . import compare
from .company import APP_ROOT, load_app_config, load_sources
from .gates import GateContext, evaluate
from .search import Index
from .semantic import SemanticIndex
from .textutil import normalize

STATUS_LABEL = {
    "covered": "Covered",
    "partial": "Partial",
    "topic_only": "Topic only – no rule stated",
    "not_found": "No supporting passage found",
}
DONE = {"erfuellt", "aktiv", "active", "done", "abgeschlossen", "umgesetzt", "yes"}
OPEN = {"offen", "in umsetzung", "in behandlung", "geplant", "open", "planned"}


def load_element_config():
    with open(os.path.join(APP_ROOT, "config", "duty_elements.json"), encoding="utf-8") as f:
        return json.load(f)


def load_duties(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _guidance_field(text, label):
    for ln in text.split("\n"):
        if ln.startswith(label):
            return ln[len(label):].strip()
    return ""


def sem_query(element):
    """The text semantic search compares passages with: element label plus its terms."""
    return element["label"] + ". " + " ".join(t.strip("*") for t in element["terms"])


def split_label(label):
    """'04-P02-1 · §30 Abs.2 Nr.1 BSIG · Risikoanalyse und IT-Sicherheitskonzept'
    -> title 'Risikoanalyse und IT-Sicherheitskonzept', legal_ref '§30 Abs.2 Nr.1 BSIG' (from the legal input)."""
    parts = [p.strip() for p in label.split("·")]
    return {"title": parts[-1] if len(parts) > 1 else label,
            "legal_ref": " · ".join(parts[1:-1]) if len(parts) > 2 else ""}


def _date(s):
    try:
        return date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- candidates

def _doc_meta(doc):
    d = doc.get("derived", {})
    h = doc.get("header", {})
    return {
        "title": doc.get("title", doc["file"]),
        "kind": doc["kind"],
        "doc_number": h.get("doc_number", {}).get("value", ""),
        "policy_no": d.get("policy_no", ""),
        "version": d.get("version", ""),
        "language": d.get("language", ""),
        "master_language": d.get("master_language", ""),
        "lifecycle": d.get("lifecycle", ""),
        "valid_from": d.get("valid_from", ""),
        "valid_until": d.get("valid_until", ""),
        "topic": d.get("topic", ""),
        "as_of": d.get("as_of", ""),
    }


def _locator_text(unit):
    loc = unit["loc"]
    if "line_start" in loc:
        if loc["line_start"] == loc["line_end"]:
            return f"L{loc['line_start']}"
        return f"L{loc['line_start']}–{loc['line_end']}"
    if "json_path" in loc:
        return loc["json_path"]
    return f"row {loc['row_id']}, field {loc['field']}"


def _overdue(cells_or_fields, as_of):
    """Due dates before `as_of`: the source's own date (a register's "As of"), else the data snapshot date.
    A register only shows the state on its own date, so an item can only be called overdue as of that date."""
    out = []
    for key in ("Next due", "Next review", "naechste_frist"):
        v = cells_or_fields.get(key)
        v = v["value"] if isinstance(v, dict) else v
        dt = _date(v) if v else None
        if dt and dt < as_of:
            out.append({"field": key, "date": v, "days_overdue": (as_of - dt).days, "as_of": as_of.isoformat()})
    return out


def _record_status(unit, doc):
    """Implementation signal of one supporting record: done / open / other, with the value used."""
    if unit["kind"] == "register_row":
        v = unit["cells"].get("Status", "")
    elif doc["kind"] == "evidence_record":
        v = doc.get("record_fields", {}).get("status", {}).get("value", "")
    else:
        return None, ""
    nv = normalize(v)
    if nv in DONE:
        return "done", v
    if nv in OPEN:
        return "open", v
    return "other", v


EXEC = re.compile(r"(\d+) runs?: (.*)")


def _executions(cells):
    v = cells.get("Executions", "")
    m = EXEC.match(v)
    if not m:
        return None
    counts = {}
    for part in m.group(2).split(","):
        part = part.strip()
        mm = re.match(r"(.+?) (\d+)$", part)
        if mm:
            counts[mm.group(1)] = int(mm.group(2))
    return {"runs": int(m.group(1)), "counts": counts, "raw": v}


def build_candidate(ctx, unit, doc, element, score, matched, snapshot):
    ev = evaluate(ctx, unit, doc, element)
    c = {
        "uid": unit["uid"], "source_id": unit["source_id"], "file": doc["file"], "sha256": doc["sha256"],
        "unit_kind": unit["kind"], "loc": unit["loc"], "location": _locator_text(unit), "quote": unit["text"],
        "section": unit.get("section", ""), "score": round(score, 3), "matched_terms": matched,
        "doc": _doc_meta(doc), **ev,
    }
    as_of = _date(c["doc"]["as_of"]) or snapshot      # the source's own date; the snapshot date if it has none
    if unit["kind"] == "register_row":
        c["cells"] = unit["cells"]
        c["overdue"] = _overdue(unit["cells"], as_of)
        ex = _executions(unit["cells"])
        if ex:
            c["executions"] = ex
    if doc["kind"] == "evidence_record":
        c["overdue"] = _overdue(doc.get("record_fields", {}), as_of)
    st, raw = _record_status(unit, doc)
    if st:
        c["record_status"] = {"signal": st, "value": raw}
    return c


# ---------------------------------------------------------------- element assessment

def assess_element(ctx, index, units, docs, element, snapshot, sem):
    hits = index.search(element["terms"])
    cands = [build_candidate(ctx, units[i], docs[units[i]["source_id"]], element, s, m, snapshot) for i, s, m in hits]
    for c in cands:
        c["found_by"] = "keyword"
    # semantic search proposes more policy sentences (same meaning, other wording); the same gates decide
    by_uid = {c["uid"]: c for c in cands}
    for i, sim in sem.search(sem_query(element), element["_key"]):
        u = units[i]
        if u["uid"] in by_uid:
            by_uid[u["uid"]]["found_by"] = "keyword+semantic"
            by_uid[u["uid"]]["similarity"] = round(sim, 3)
            continue
        c = build_candidate(ctx, u, docs[u["source_id"]], element, 0.0, [f"semantic similarity {sim:.2f}"], snapshot)
        c["found_by"], c["similarity"] = "semantic", round(sim, 3)
        cands.append(c)
    # record sources: every in-topic row of a matching register is a candidate
    if element.get("record_sources"):
        seen = {c["uid"] for c in cands}
        keys = [normalize(k) for k in element["record_sources"]]
        for u in units:
            d = docs[u["source_id"]]
            if u["uid"] in seen or u["kind"] != "register_row" or not any(k in normalize(d.get("title", "")) for k in keys):
                continue
            c = build_candidate(ctx, u, d, element, 0.0, [f"register: {d.get('title', '')}"], snapshot)
            c["found_by"] = "record source"
            if c["relation"] == "supporting":
                cands.append(c)
    def counts(c):
        lang = next(g["result"] for g in c["gates"] if g["gate"] == "4 language")
        return (c["relation"] in ("covers", "partial") and c["doc"]["lifecycle"] == "current"
                and lang in ("master", "also_in_master") and "entity_not_stated" not in c["qualifiers"])

    # a sentence found only by meaning counts only when the gates count it: close meaning alone is no reason to
    # list it as a passage (it would read as a match that the text does not support). The others are kept apart for
    # the audit trail ("Similar in meaning, not counted" in the Sources checked tab); they never affect the status.
    similar = [c for c in cands if c.get("found_by") == "semantic" and not counts(c)]
    for c in similar:
        c["why_not_counted"] = _why_not_counted(c)
    similar.sort(key=lambda c: -c["similarity"])
    cands = [c for c in cands if c not in similar]
    excluded = [c for c in cands if c["relation"] == "excluded"]
    policy = [c for c in cands if c["relation"] in ("covers", "partial", "topic_only", "scope_mismatch")
              and c["doc"]["kind"] == "policy"]

    counted = [c for c in policy if counts(c)]
    not_counted = [c for c in policy if not counts(c)]
    for c in not_counted:
        c["why_not_counted"] = _why_not_counted(c)
    if any(c["relation"] == "covers" for c in counted):
        status = "covered"
    elif counted:
        status = "partial"
    elif any(c["relation"] == "topic_only" and c["doc"]["lifecycle"] == "current"
             and "translation_only" not in c["qualifiers"] for c in not_counted):
        status = "topic_only"
    else:
        status = "not_found"
    supporting = [c for c in cands if c["relation"] == "supporting"]
    supp_mismatch = [c for c in cands if c["relation"] == "scope_mismatch" and c["doc"]["kind"] != "policy"]
    context = [c for c in cands if c["relation"] == "context"]
    impl = _implementation(supporting)
    eff = _effectiveness(supporting)
    # flags only for passages that would have counted, plus title/topic matches with the wrong scope
    flags = sorted({q for c in not_counted if c["relation"] in ("covers", "partial") for q in c["qualifiers"]} |
                   {"scope_mismatch" for c in not_counted if c["relation"] == "scope_mismatch"} |
                   {"off_topic_policy" for c in counted if "off_topic_policy" in c["qualifiers"]})
    return {
        "id": element["id"], "label": element["label"], "terms": element["terms"],
        "facets_required": element["facets_required"],
        "policy_status": status, "policy_status_label": STATUS_LABEL[status], "flags": flags,
        "passages": counted, "not_counted": not_counted, "supporting": supporting,
        "supporting_scope_mismatch": supp_mismatch, "context": context, "excluded": excluded,
        "similar_not_counted": similar, "implementation": impl, "effectiveness": eff,
    }


def _why_not_counted(c):
    reasons = []
    if c["relation"] == "excluded":
        reasons.append("concerns another legal entity")
    if c["relation"] == "scope_mismatch":
        reasons.append("topic of the document does not fit the duty")
    if c["relation"] == "topic_only":
        # a sentence found only by meaning does not name the subject (keyword search would have found it)
        reasons.append("states no rule" if c.get("found_by") == "semantic" else "names the subject but states no rule")
    if "superseded" in c["qualifiers"]:
        reasons.append("document version is superseded")
    if "translation_only" in c["qualifiers"]:
        reasons.append("text appears only in a translation, not in the master-language version")
    if "entity_not_stated" in c["qualifiers"]:
        reasons.append("entity not stated")
    lang = next(g["result"] for g in c["gates"] if g["gate"] == "4 language")
    if lang == "master_not_in_scope":
        reasons.append("master-language version not in the sources reviewed")
    return reasons


def _implementation(supporting):
    """Summarise implementation records honestly: done, open, or mixed, plus overdue counts."""
    # one signal per record: a register row, or a whole evidence document (not each of its fields)
    per_record = {}
    for c in supporting:
        if not c.get("record_status"):
            continue
        key = (c["source_id"], c["loc"].get("line_start")) if c["unit_kind"] == "register_row" else (c["source_id"], None)
        per_record[key] = (c["record_status"]["signal"], bool(c.get("overdue")))
    signals = [v[0] for v in per_record.values()]
    done, open_ = signals.count("done"), signals.count("open")
    overdue = sum(1 for v in per_record.values() if v[1])
    if done and open_:
        state, label = "mixed", f"Mixed: {done} record(s) done/active, {open_} open"
    elif done:
        state, label = "record_exists", f"Record of implementation exists ({done} done/active)"
    elif open_:
        state, label = "open_or_planned", f"Only open / planned records ({open_})"
    else:
        state, label = "unknown", "Unknown – no implementation record found"
    short = {"mixed": f"Mixed: {done} done, {open_} open", "record_exists": f"Records exist ({done})",
             "open_or_planned": f"Open only ({open_})", "unknown": "Unknown"}[state]
    if overdue:
        label += f"; {overdue} overdue as of the source's date"
    return {"state": state, "label": label, "short": short, "records": len(supporting), "done": done, "open": open_,
            "overdue_records": overdue}


def _effectiveness(supporting):
    """Per 17-AUS-17: missing proof -> 'not demonstrated'; only proven failure -> 'ineffective'.

    Register execution summaries are records, not test protocols, so they never prove
    effectiveness on their own. A recorded failed run is reported, not generalised.
    """
    runs = [c for c in supporting if c.get("executions")]
    failures = sum(c["executions"]["counts"].get("unwirksam", 0) for c in runs)
    partial = sum(c["executions"]["counts"].get("teilweise wirksam", 0) for c in runs)
    if not runs:
        return {"state": "not_demonstrated", "short": "Not demonstrated",
                "label": "Not demonstrated – no test or execution evidence in the sources",
                "controls_with_results": 0, "failed_runs": 0, "partly_effective_runs": 0}
    note = f"{len(runs)} control(s) with execution summaries"
    if failures:
        note += f"; {failures} run(s) recorded as ineffective"
    if partial:
        note += f"; {partial} run(s) partly effective"
    return {"state": "not_demonstrated", "short": "Not demonstrated (summaries only)",
            "label": "Not demonstrated – execution summaries only, no test protocol (" + note + ")",
            "controls_with_results": len(runs), "failed_runs": failures, "partly_effective_runs": partial}


# ---------------------------------------------------------------- company-derived helpers

def target_policy(ctx, docs):
    """Current, master-language policy whose topic fits the duties: where new sections should go."""
    best = None
    for d in docs.values():
        dv = d.get("derived", {})
        if d["kind"] != "policy" or dv.get("lifecycle") != "current":
            continue
        if dv.get("language") and dv.get("master_language") and dv["language"] != dv["master_language"]:
            continue
        if any(t in normalize(dv.get("topic", "")) for t in ctx.topics):
            sec = next((s["heading"] for s in d["sections"] if s["obligations"]), "")
            best = {"source_id": d["document_id"], "file": d["file"], "policy_no": dv["policy_no"],
                    "version": dv["version"], "language": dv["language"],
                    "doc_number": d["header"].get("doc_number", {}).get("value", ""),
                    "title": d.get("title", ""), "section": sec}
            break
    return best


def twin_questions_for(docs, keywords, topics):
    tq = docs.get("twin_questions.csv")
    if not tq:
        return []
    kws = [normalize(k) for k in keywords]
    out = []
    for r in tq["rows"]:
        nt = normalize(r.get("text", ""))
        if r.get("topic") in topics and any(k in nt for k in kws):
            out.append({"id": r["id"], "shortId": r.get("shortId", ""), "text": r.get("text", ""),
                        "topic": r.get("topic", ""), "status": r.get("status", ""),
                        "answer": r.get("answer", ""), "answerSource": r.get("answerSource", "")})
    return out


# ---------------------------------------------------------------- explanations

POLICY_UNITS = ("policy_sentence", "title")


def explain(el):
    parts = []
    s = el["policy_status"]
    label = el["label"][0].lower() + el["label"][1:] if el["label"][1:2].islower() else el["label"]
    if s == "covered":
        p = next(c for c in el["passages"] if c["relation"] == "covers")
        parts.append(f"{p['doc']['policy_no']} v{p['doc']['version']} ({p['doc']['language'].upper()} master, "
                     f"{p['location']}) states a rule with all required facets.")
    elif s == "partial":
        p = el["passages"][0]
        parts.append(f"{p['doc']['policy_no']} v{p['doc']['version']} ({p['doc']['language'].upper()} master, "
                     f"{p['location']}) states a rule, but these "
                     f"facets are not stated: {', '.join(f.lower() for f in p['facets_missing_labels']) or 'none'}.")
    elif s == "topic_only":
        opts = [c for c in el["not_counted"] if c["relation"] == "topic_only" and c["doc"]["lifecycle"] == "current"
                and "translation_only" not in c["qualifiers"]]
        p = sorted(opts, key=lambda c: (c["unit_kind"] == "title", c["loc"].get("line_start", 0)))[0]
        parts.append(f"{p['doc']['policy_no']} v{p['doc']['version']} ({p['doc']['language'].upper()} master, "
                     f"{p['location']}) only names the subject and states no rule for {label}.")
    else:
        parts.append(f"No current, master-language policy passage in the sources reviewed states a rule for {label}.")
    pol = lambda cs: [c for c in cs if c["unit_kind"] in POLICY_UNITS]
    found, counted = pol(el["passages"] + el["not_counted"]), pol(el["passages"])
    if found:
        mism = sum(1 for c in found if c["relation"] == "scope_mismatch")
        parts.append(f"{len(found)} policy passage{'s' if len(found) != 1 else ''} matched; {len(counted) or 'none'} "
                     f"counted, {len(found) - len(counted) or 'none'} not counted"
                     f"{f' ({mism} on an unrelated topic)' if mism else ''}.")
    off = [c for c in el["passages"] if "off_topic_policy" in c["qualifiers"]]
    if off:
        pols = ", ".join(dict.fromkeys(f"{c['doc']['policy_no']} v{c['doc']['version']} ({c['doc']['topic']})" for c in off))
        parts.append(f"The rule is placed in policies whose topic is unrelated ({pols}); it is counted because the sentence "
                     f"itself concerns information security, but it belongs in the information-security policy.")
    for c in el["not_counted"]:
        if "translation_only" in c["qualifiers"] and c["relation"] in ("covers", "partial"):
            lang, master = c['doc']['language'].upper(), c['doc']['master_language'].upper()
            where = f"The {lang} version {c['doc']['policy_no']} v{c['doc']['version']} ({c['doc']['doc_number']}, {c['location']})"
            if s in ("covered", "partial"):
                parts.append(f"{where} also contains a rule on this, but its text does not appear identically in the "
                             f"{master} master; only the master's own rule is counted.")
            else:
                parts.append(f"{where} contains a matching rule whose text does not appear in the {master} master. "
                             f"The master language is authoritative, so it is not counted; it is flagged as a language "
                             f"difference.")
    # wrong-topic matches, grouped per document
    groups = {}
    for c in el["not_counted"]:
        if c["relation"] == "scope_mismatch":
            groups.setdefault((c["doc"]["policy_no"], c["doc"]["title"], c["doc"]["topic"]), []).append(c)
    for (pno, title, topic), cs in groups.items():
        cur = [c["location"] for c in cs if c["doc"]["lifecycle"] == "current"]
        sup = [f"v{c['doc']['version']}" for c in cs if c["doc"]["lifecycle"] == "superseded"]
        where = ", ".join(cur) if cur else "superseded version only"
        parts.append(f"{pno} \u201c{title}\u201d ({where}{'; same text in superseded ' + sup[0] if sup and cur else ''}) "
                     f"matched the search terms, but its topic is {topic or 'different'}, not information security; "
                     f"not counted.")
    for c in el["not_counted"]:
        if "superseded" in c["qualifiers"] and c["relation"] in ("covers", "partial") and "translation_only" not in c["qualifiers"]:
            parts.append(f"A superseded version ({c['doc']['policy_no']} v{c['doc']['version']}) contains a matching "
                         f"passage; superseded text is not counted.")
    if el["supporting"]:
        parts.append(f"{len(el['supporting'])} supporting record entr{'y' if len(el['supporting']) == 1 else 'ies'} found "
                     f"(registers / evidence). They describe implementation, not policy text, and do not prove "
                     f"effectiveness on their own.")
    return " ".join(dict.fromkeys(parts))


# ---------------------------------------------------------------- fingerprint

def fingerprint(el):
    key = {
        "status": el["policy_status"], "impl": el["implementation"]["state"], "eff": el["effectiveness"]["state"],
        "passages": sorted((c["source_id"], c["sha256"], json.dumps(c["loc"], sort_keys=True)) for c in el["passages"]),
        "supporting": sorted((c["source_id"], c["sha256"], json.dumps(c["loc"], sort_keys=True)) for c in el["supporting"]),
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- run

def run_analysis(company, run_id=None):
    started = datetime.now(timezone.utc)
    run_id = run_id or started.strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = date.fromisoformat(company.snapshot_date)
    docs, cache_report, source_rows, index_rows = load_sources(company)
    cfg = load_element_config()
    app_cfg = load_app_config()
    duties_json = load_duties(company.duties_file)
    records = {r["source_id"]: r for r in duties_json["records"]}
    units = [u for d in docs.values() for u in d["units"]]
    index = Index(units)
    ctx = GateContext(company, docs, cfg)
    sem = SemanticIndex(units, company.store, app_cfg["semantic"])
    # each semantic-only sentence is offered only to the element it is closest to
    sem.assign({f"{d}/{e['id']}": sem_query(e) for d in duties_json["primary_ids"]
                for e in cfg["duties"].get(d, {}).get("elements", [])})
    target = target_policy(ctx, docs)

    duties_out = []
    for duty_id in duties_json["primary_ids"]:
        rec = records[duty_id]
        dcfg = cfg["duties"].get(duty_id)
        if not dcfg:
            duties_out.append({"duty_id": duty_id, "error": "No element configuration for this duty."})
            continue
        guidance = rec["evaluation_guidance_de"]
        elements = []
        for ecfg in dcfg["elements"]:
            el = assess_element(ctx, index, units, docs, dict(ecfg, _key=f"{duty_id}/{ecfg['id']}"), snapshot, sem)
            el["explanation"] = explain(el)
            tq = twin_questions_for(docs, ecfg["twin_keywords"], cfg.get("twin_topics", []))
            el["twin_questions"] = tq
            if el["policy_status"] == "covered":
                el["next_step"] = None
            elif el["policy_status"] == "partial":
                p0 = el["passages"][0]
                missing = ", ".join(f.lower() for f in p0["facets_missing_labels"])   # computed by gate 7
                el["next_step"] = {"target": target, "action": "complete",
                                   "text": f"Complete the rule in {p0['doc']['policy_no']} v{p0['doc']['version']} "
                                           f"({p0['doc']['language'].upper()} master, {p0['doc']['doc_number']}) "
                                           f"{p0['location']}, section \u201c{p0['section']}\u201d: also state {missing}."}
            else:
                el["next_step"] = {
                    "target": target, "action": ecfg["next_step"],
                    "text": (f"Add to {target['policy_no']} v{target['version']} ({target['language'].upper()} master, "
                             f"{target['doc_number']}), section \u201c{target['section']}\u201d: {ecfg['next_step']}.")
                    if target else f"Create a policy section: {ecfg['next_step']}."}
            el["sources_checked"] = sources_checked(docs, el)
            el["fingerprint"] = fingerprint(el)
            elements.append(el)
        statuses = [e["policy_status"] for e in elements]
        if all(s == "covered" for s in statuses):
            duty_status = "covered"
        elif any(s in ("covered", "partial") for s in statuses):
            duty_status = "partial"
        elif any(s == "topic_only" for s in statuses):
            duty_status = "topic_only"
        else:
            duty_status = "not_found"
        duties_out.append({
            "duty_id": duty_id, **split_label(rec["source_label_de"]), "label_de": rec["source_label_de"],
            "source_row": rec["source_row"], "addressees_de": rec["addressees_de"],
            "criterion_de": rec["criterion_and_questions_de"], "guidance_de": guidance,
            "evidence_question_de": _guidance_field(guidance, "Nachweisfrage:"),
            "expected_evidence_de": _guidance_field(guidance, "Antwort/Nachweis:"),
            "source_links": rec["source_links_raw"].split("\n"),
            "status": duty_status, "status_label": STATUS_LABEL[duty_status],
            "elements": elements,
        })

    result = {
        "schema_version": "1.1",
        "run_id": run_id,
        "generated_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "company": {"slug": company.slug, "name": company.name, "entity_id": company.entity_id,
                    "entity_name": company.entity_name, "entity_codes": company.entity_codes,
                    "snapshot_date": company.snapshot_date},
        "legal_input": {"file": os.path.basename(company.duties_file), "regulation": duties_json.get("regulation"),
                        "analysis_date": duties_json.get("analysis_date"),
                        "workbook": duties_json.get("source_workbook"),
                        "primary_ids": duties_json["primary_ids"]},
        "source_scope": cache_report["scope"],
        "search": {"mode": "keyword + semantic", "model": app_cfg["semantic"]["model"], "top_k": sem.top_k,
                   "min_similarity": sem.min_sim, "unit_kinds": app_cfg["semantic"].get("unit_kinds"),
                   "embedded_now": sem.embedded},
        "sources_reviewed_count": len(docs),
        "policy_documents_count": sum(d.get("kind") == "policy" for d in docs.values()),
        "cache": cache_report,
        "target_policy": target,
        "duties": duties_out,
        "comparisons": compare.compare_versions(docs, sem.similarity, app_cfg["semantic"]["language_match_cutoff"],
                                                app_cfg["language_detection"]),
    }
    return result, docs


def sources_checked(docs, el):
    hit_by_source = {}
    for bucket in ("passages", "not_counted", "supporting", "supporting_scope_mismatch", "context", "excluded"):
        for c in el[bucket]:
            hit_by_source.setdefault(c["source_id"], []).append(c["relation"])
    out = []
    for sid, d in docs.items():
        rel = hit_by_source.get(sid, [])
        out.append({"source_id": sid, "file": d["file"], "title": d.get("title", d["file"]), "kind": d["kind"],
                    "hits": len(rel), "relations": sorted(set(rel))})
    return sorted(out, key=lambda x: (-x["hits"], x["file"]))


def save_run(company, result, docs, report_html):
    """Persist one run through the company's store."""
    cited = {c["source_id"] for du in result["duties"] for e in du.get("elements", [])
             for b in ("passages", "not_counted", "supporting", "similar_not_counted") for c in e[b]}
    company.store.save_run(result["run_id"], {
        "mapping_result.json": json.dumps(result, ensure_ascii=False, indent=1),
        "report.html": report_html,
        "parsed_cited_documents.json": json.dumps(
            {sid: {k: v for k, v in docs[sid].items() if k != "data"} for sid in sorted(cited)}, ensure_ascii=False),
    })
