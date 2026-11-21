"""Data and result validation checks (IMPLEMENTATION.md D-33, D-52).

Run by the test suite only; nothing is stored. They verify every quote, the version invariants,
the legal input and the entity gate against the real data.
"""
import json
import os
from datetime import date, timedelta

from .company import load_app_config, APP_ROOT
from .compare import _vkey
from .parsing import extract


def _check(cid, title, ok, detail, warn=False):
    return {"id": cid, "title": title, "status": "pass" if ok else ("warn" if warn else "fail"), "detail": detail}


def _resolve_json_path(data, path):
    cur = data
    import re
    for part in re.findall(r"\.([^.\[]+)|\[(\d+)\]", path):
        key, idx = part
        cur = cur[int(idx)] if idx else cur[key]
    return cur


def run_checks(company, docs, result, source_rows, index_rows):
    checks = []
    idx = {r["id"]: r for r in index_rows}
    # 1 starters <-> catalogue
    bad = [r["document_id"] for r in source_rows if r["document_id"] not in idx or idx[r["document_id"]]["file"] != r["file"]]
    checks.append(_check("SRC-1", "Every source in scope exists in the document catalogue with the same file", not bad,
                         f"{len(source_rows)} sources checked" + (f"; mismatches: {bad}" if bad else "")))
    # 2 files present and parsed
    missing = result["cache"]["missing"]
    checks.append(_check("SRC-2", "Every source file exists and was parsed", not missing,
                         f"{len(docs)} sources parsed" + (f"; missing: {missing}" if missing else "")))
    # 3 catalogue chars column matches the parsed text length
    wrong = []
    for r in source_rows:
        d = docs.get(r["document_id"])
        if d and idx.get(r["document_id"], {}).get("chars"):
            n = len("\n".join(d["lines"]))
            if str(n) != idx[r["document_id"]]["chars"]:
                wrong.append(f"{r['file']}: catalogue {idx[r['document_id']]['chars']} vs actual {n}")
    checks.append(_check("SRC-3", "Catalogue character counts match the files", not wrong,
                         "all match" if not wrong else "; ".join(wrong[:5]), warn=True))
    # 4 every cited quote is verbatim at its location, and the file hash matches
    n, bad = 0, []
    for du in result["duties"]:
        for e in du.get("elements", []):
            for b in ("passages", "not_counted", "supporting", "supporting_scope_mismatch", "context"):
                for c in e[b]:
                    n += 1
                    d = docs[c["source_id"]]
                    if d["sha256"] != c["sha256"]:
                        bad.append(f"{c['uid']}: hash")
                        continue
                    loc = c["loc"]
                    if "line_start" in loc:
                        ok = extract(d["lines"], loc) == c["quote"]
                    elif "json_path" in loc:
                        ok = _resolve_json_path(d["data"], loc["json_path"]) == c["quote"]
                    else:
                        row = next((r for r in d["rows"] if r["id"] == loc["row_id"]), None)
                        ok = bool(row) and row.get(loc["field"]) == c["quote"]
                    if not ok:
                        bad.append(c["uid"])
    checks.append(_check("CIT-1", "Every cited quote is verbatim at its stated location (and the file hash matches)",
                         not bad, f"{n} citations verified" + (f"; failures: {bad[:10]}" if bad else "")))
    # 5 version invariants per policy family and language
    fams = {}
    for d in docs.values():
        if d.get("kind") == "policy":
            dv = d["derived"]
            fams.setdefault((dv["policy_no"], dv["language"]), []).append(d)
    problems, info = [], []
    for (pno, lang), ds in sorted(fams.items()):
        unread = [d["file"] for d in ds if not d["derived"]["version"]]
        if unread:
            problems.append(f"{pno} {lang}: version not readable in {', '.join(unread)}")
            ds = [d for d in ds if d["derived"]["version"]]
        ds.sort(key=lambda d: _vkey(d["derived"]["version"]))
        cur = [d for d in ds if d["derived"]["lifecycle"] == "current"]
        if len(cur) > 1:
            problems.append(f"{pno} {lang}: {len(cur)} current versions")
        for d in ds:
            dv = d["derived"]
            if dv["lifecycle"] == "superseded" and not dv["valid_until"]:
                problems.append(f"{pno} v{dv['version']} {lang}: superseded without valid-until date")
            if dv["lifecycle"] == "current" and dv["valid_until"]:
                problems.append(f"{pno} v{dv['version']} {lang}: current but has a valid-until date")
            if dv["lifecycle"] == "conflict":
                problems.append(f"{pno} v{dv['version']} {lang}: header and version status contradict")
        for a, b in zip(ds, ds[1:]):
            try:
                if date.fromisoformat(a["derived"]["valid_until"]) + timedelta(days=1) != \
                        date.fromisoformat(b["derived"]["valid_from"]):
                    problems.append(f"{pno} {lang}: validity gap/overlap between v{a['derived']['version']} and "
                                    f"v{b['derived']['version']}")
            except ValueError:
                problems.append(f"{pno} {lang}: unreadable validity dates")
        info.append(f"{pno} {lang}: " + ", ".join(f"v{d['derived']['version']} {d['derived']['lifecycle']}" for d in ds))
    checks.append(_check("VER-1", "Policy version invariants (one current version, continuous validity, statuses agree)",
                         not problems, "; ".join(problems or info)))
    # 6 duties JSON <-> TXT parity
    cfg = load_app_config()
    txt_path = cfg.get("legal_input_txt")
    if txt_path and not os.path.isabs(txt_path):
        txt_path = os.path.normpath(os.path.join(APP_ROOT, txt_path))
    if txt_path and os.path.exists(txt_path) and not company.cfg.get("duties_file"):
        with open(company.duties_file, encoding="utf-8") as f:
            dj = json.load(f)
        with open(txt_path, encoding="utf-8") as f:
            txt = f.read()
        miss = [r["source_id"] for r in dj["records"]
                if r["source_label_de"] not in txt or f"row {r['source_row']}" not in txt
                or any(line.strip() and line.strip() not in txt for line in r["evaluation_guidance_de"].split("\n"))]
        checks.append(_check("LEG-1", "Legal input: JSON and TXT contain the same records, rows and guidance",
                             not miss, f"{len(dj['records'])} records compared" + (f"; differences: {miss}" if miss else "")))
    # 7 every primary duty has a result
    ids = [d["duty_id"] for d in result["duties"] if "elements" in d]
    want = result["legal_input"]["primary_ids"]
    checks.append(_check("RES-1", "Every primary duty has a mapping result", ids == want,
                         f"{len(ids)} of {len(want)}: {', '.join(ids)}"))
    # 8 assessed entity exists in legal_entities.csv
    ent = docs.get("legal_entities.csv")
    row = next((r for r in ent["rows"] if r["id"] == company.entity_id), None) if ent else None
    checks.append(_check("ENT-1", "Assessed entity exists in legal_entities.csv with the configured name",
                         bool(row) and row["name"] == company.entity_name,
                         f"{company.entity_id} → {row['name'] if row else 'not found'}"))
    # 9 twin questions: answered rows carry an answer source; linked questions exist
    tq = docs.get("twin_questions.csv")
    if tq:
        no_src = [r["shortId"] for r in tq["rows"] if r.get("answer", "").strip() and not r.get("answerSource")]
        ids_all = {r["id"] for r in tq["rows"]}
        linked = {q["id"] for du in result["duties"] for e in du.get("elements", []) for q in e["twin_questions"]}
        checks.append(_check("TWQ-1", "Twin questions: answered rows have an answer source; linked questions exist",
                             not no_src and linked <= ids_all,
                             f"{len(tq['rows'])} questions, {sum(1 for r in tq['rows'] if r.get('answer','').strip())} "
                             f"answered, {len(linked)} linked"))
    # 10 entity gate: no candidate from another entity is used
    leaked = [c["uid"] for du in result["duties"] for e in du.get("elements", [])
              for b in ("passages", "supporting") for c in e[b]
              if next(g["result"] for g in c["gates"] if g["gate"] == "1 entity") == "other_entity"]
    checks.append(_check("ENT-2", "No passage or record from another entity is used as coverage or evidence",
                         not leaked, "none" if not leaked else str(leaked)))
    return {"checks": checks, "passed": sum(c["status"] == "pass" for c in checks),
            "failed": sum(c["status"] == "fail" for c in checks), "warnings": sum(c["status"] == "warn" for c in checks)}
