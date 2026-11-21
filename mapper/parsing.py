"""Parse source files into a structured, citable form.

Line convention:
- the file is decoded as strict UTF-8 and split on '\n' only; nothing is stripped or merged
- line numbers start at 1 (index + 1), so they match `cat -n` and editors
- a text location is line_start/char_start .. line_end/char_end; lines include both ends,
  characters start at 0 and the end is exclusive (like a Python slice)
"""
import csv
import hashlib
import io
import json
import re

PARSER_VERSION = "1.0"

HEADER_LABELS = {
    "Dokumentnummer": "doc_number", "Document no.": "doc_number",
    "Version": "version",
    "Gültig ab": "valid_from", "Valid from": "valid_from",
    "Gesellschaft": "company", "Company": "company",
    "Status": "status",
    "Vertraulichkeit": "confidentiality", "Confidentiality": "confidentiality",
}
BODY_HEADINGS = {
    "Zweck und Geltungsbereich", "Purpose and scope",
    "Pflichten und Zuständigkeiten", "Obligations and responsibilities",
    "Angaben", "Details",
}
OBLIGATION_HEADINGS = {"Pflichten und Zuständigkeiten", "Obligations and responsibilities"}
POLICY_BLOCK = "Richtlinie"
VERSION_BLOCK = "Richtlinienversion"
RECORD_BLOCK = "Verpflichtung"
KV = re.compile(r"^([a-z_]+): ?(.*)$")
ENTITY_CODE = re.compile(r"\b[A-Z]{2,5}-[A-Z]{2}-\d{2}\b")  # e.g. CMS-DE-01

CURRENT_WORDS = {"approved", "gültig", "gueltig", "valid", "current", "freigegeben"}
SUPERSEDED_WORDS = {"superseded", "ersetzt", "obsolete", "withdrawn"}


# ---------------------------------------------------------------- basics

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def split_lines(raw: bytes) -> list:
    return raw.decode("utf-8").split("\n")


def doc_kind(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if re.search(r"_KR-\d+_", base):
        return "policy"
    if base.startswith("REG_"):
        return "register"
    if "_Nachweis" in base or re.search(r"_[VM]\d{6}_", base):
        return "evidence_record"
    if base.startswith("Zwilling"):
        return "twin"
    return "other"


def lifecycle_of(*status_values) -> str:
    vals = [v.strip().lower() for v in status_values if v]
    kinds = set()
    for v in vals:
        if v in CURRENT_WORDS:
            kinds.add("current")
        elif v in SUPERSEDED_WORDS:
            kinds.add("superseded")
        else:
            kinds.add("unknown")
    if not kinds:
        return "unknown"
    if len(kinds - {"unknown"}) > 1:
        return "conflict"
    known = kinds - {"unknown"}
    return known.pop() if known else "unknown"


# ---------------------------------------------------------------- locations

def offset_to_pos(line_starts, offset):
    """Map an offset in a joined block to (line_index_in_block, column)."""
    lo, hi = 0, len(line_starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if line_starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo, offset - line_starts[lo]


def extract(lines, loc) -> str:
    """Rebuild the exact text at a location (used for quote verification)."""
    ls, cs, le, ce = loc["line_start"], loc["char_start"], loc["line_end"], loc["char_end"]
    if ls == le:
        return lines[ls - 1][cs:ce]
    parts = [lines[ls - 1][cs:]] + lines[ls:le - 1] + [lines[le - 1][:ce]]
    return "\n".join(parts)


def line_loc(lines, start, end=None):
    end = end or start
    return {"line_start": start, "char_start": 0, "line_end": end, "char_end": len(lines[end - 1])}


def split_sentences(lines, start, end):
    """Split lines[start..end] (1-based, inclusive) into sentences with exact locations.

    A sentence ends at '.', '!' or '?' followed by a line break, the end of the block,
    or a space and an upper-case letter. PDF-extracted text wraps mid-sentence, so a
    sentence may span several lines.
    """
    block = lines[start - 1:end]
    joined = "\n".join(block)
    starts, pos = [], 0
    for ln in block:
        starts.append(pos)
        pos += len(ln) + 1
    spans, s = [], 0
    n = len(joined)
    for i, ch in enumerate(joined):
        if ch in ".!?":
            nxt = joined[i + 1] if i + 1 < n else ""
            nxt2 = joined[i + 2] if i + 2 < n else ""
            if nxt in ("", "\n") or (nxt == " " and nxt2[:1].isupper()):
                spans.append((s, i + 1))
                s = i + 1
    if s < n:
        spans.append((s, n))
    out = []
    for a, b in spans:
        while a < b and joined[a] in " \n\t":
            a += 1
        while b > a and joined[b - 1] in " \n\t":
            b -= 1
        if a >= b:
            continue
        la, ca = offset_to_pos(starts, a)
        lb, cb = offset_to_pos(starts, b)
        loc = {"line_start": start + la, "char_start": ca, "line_end": start + lb, "char_end": cb}
        out.append((loc, joined[a:b]))
    return out


# ---------------------------------------------------------------- documents

def _unit(units, doc_id, kind, loc, text, **extra):
    u = {"uid": f"{doc_id}#{len(units)}", "source_id": doc_id, "kind": kind, "loc": loc, "text": text}
    u.update(extra)
    units.append(u)


def _parse_kv_block(lines, start, end):
    """Parse 'key: value' lines; lines without a key continue the previous value."""
    fields, order, last = {}, [], None
    for i in range(start, end + 1):
        ln = lines[i - 1]
        if not ln.strip():
            continue
        m = KV.match(ln)
        if m:
            last = m.group(1)
            fields[last] = {"value": m.group(2), "line": i, "line_end": i}
            order.append(last)
        elif last:
            fields[last]["value"] += " " + ln.strip()
            fields[last]["line_end"] = i
    return fields, order


def parse_structured_doc(doc_id, file, raw):
    """Policies, evidence records and other DMS-style documents."""
    lines = split_lines(raw)
    kind = doc_kind(file)
    doc = {"document_id": doc_id, "file": file, "sha256": sha256_bytes(raw), "size": len(raw),
           "kind": kind, "parser_version": PARSER_VERSION, "lines": lines,
           "header": {}, "policy_block": {}, "version_block": {}, "record_fields": {},
           "sections": [], "units": []}
    n = len(lines)
    # title lines: non-empty lines before the first header label
    i, pre = 1, []
    while i <= n and lines[i - 1].strip() not in HEADER_LABELS:
        if lines[i - 1].strip():
            pre.append(i)
        i += 1
    if len(pre) >= 2:
        doc["title"] = " ".join(lines[j - 1].strip() for j in pre[:-1])
        doc["title_lines"] = [pre[0], pre[-2]]
        doc["doc_type"] = lines[pre[-1] - 1].strip()
    elif pre:
        doc["title"] = lines[pre[0] - 1].strip()
        doc["title_lines"] = [pre[0], pre[0]]
        doc["doc_type"] = ""
    # header: label line followed by value line
    while i <= n:
        s = lines[i - 1].strip()
        if s in HEADER_LABELS and i + 1 <= n:
            doc["header"][HEADER_LABELS[s]] = {"value": lines[i].strip(), "line": i + 1, "label": s, "label_line": i}
            i += 2
            continue
        if not s:
            i += 1
            continue
        break
    # sections and blocks
    marks = []
    for j in range(i, n + 1):
        s = lines[j - 1].strip()
        if s in BODY_HEADINGS or s in (POLICY_BLOCK, VERSION_BLOCK, RECORD_BLOCK):
            marks.append((j, s))
    for k, (j, s) in enumerate(marks):
        end = (marks[k + 1][0] - 1) if k + 1 < len(marks) else n
        if s == POLICY_BLOCK:
            doc["policy_block"], _ = _parse_kv_block(lines, j + 1, end)
        elif s == VERSION_BLOCK:
            doc["version_block"], _ = _parse_kv_block(lines, j + 1, end)
        elif s == RECORD_BLOCK:
            doc["record_fields"], order = _parse_kv_block(lines, j + 1, end)
            for key in order:
                f = doc["record_fields"][key]
                loc = {"line_start": f["line"], "char_start": 0, "line_end": f["line_end"],
                       "char_end": len(lines[f["line_end"] - 1])}
                _unit(doc["units"], doc_id, "record_field", loc, extract(lines, loc), section=s, field=key)
        else:
            doc["sections"].append({"heading": s, "heading_line": j, "start": j + 1, "end": end,
                                    "obligations": s in OBLIGATION_HEADINGS})
            if end >= j + 1:
                for loc, text in split_sentences(lines, j + 1, end):
                    _unit(doc["units"], doc_id, "policy_sentence" if kind == "policy" else "text_sentence",
                          loc, text, section=s)
    if not marks:  # unstructured text (e.g. safety data sheet): sentences over the whole body
        body_start = i
        if body_start <= n:
            for loc, text in split_sentences(lines, body_start, n):
                _unit(doc["units"], doc_id, "text_sentence", loc, text, section="")
    if doc.get("title_lines"):
        a, b = doc["title_lines"]
        loc = {"line_start": a, "char_start": 0, "line_end": b, "char_end": len(lines[b - 1])}
        _unit(doc["units"], doc_id, "title", loc, extract(lines, loc), section="(title)")
    # derived metadata
    h, vb, pb = doc["header"], doc["version_block"], doc["policy_block"]
    hv = lambda d, k: d.get(k, {}).get("value", "")
    m = re.search(r"_(KR-\d+)_", file)
    doc["derived"] = {
        "policy_no": hv(pb, "nummer") or (m.group(1) if m else ""),
        "version": hv(vb, "version") or hv(h, "version"),
        "language": hv(vb, "sprache") or _lang_from_name(file),
        "master_language": hv(pb, "master_sprache"),
        "topic": hv(pb, "thema"),
        "valid_from": hv(vb, "gueltig_ab") or hv(h, "valid_from"),
        "valid_until": hv(vb, "gueltig_bis"),
        "approved_on": hv(vb, "freigabe_datum"),
        "header_status": hv(h, "status"),
        "version_status": hv(vb, "status"),
        "lifecycle": lifecycle_of(hv(h, "status"), hv(vb, "status")),
        "entity": hv(h, "company") or _code_from_name(file),
        "entity_line": h.get("company", {}).get("line"),
        "notes": [],
    }
    d = doc["derived"]
    if pb.get("aktuelle_version") and d["version"] and pb["aktuelle_version"]["value"] != d["version"]:
        d["notes"].append(
            f"Policy-level field aktuelle_version: {pb['aktuelle_version']['value']} (L{pb['aktuelle_version']['line']}) "
            f"describes the policy family, not this document. This document is version {d['version']} with its own "
            f"status '{d['header_status']}' (L{h.get('status', {}).get('line')}) / '{d['version_status']}' "
            f"(L{vb.get('status', {}).get('line')}).")
    if d["lifecycle"] == "conflict":
        d["notes"].append("Header status and version-block status contradict each other.")
    return doc


def _lang_from_name(file):
    m = re.search(r"_(de|en|fr|zh)(?:_|\.)", file)
    return m.group(1) if m else ""


def _code_from_name(file):
    m = ENTITY_CODE.search(file)
    return m.group(0) if m else ""


def parse_register(doc_id, file, raw):
    lines = split_lines(raw)
    doc = {"document_id": doc_id, "file": file, "sha256": sha256_bytes(raw), "size": len(raw),
           "kind": "register", "parser_version": PARSER_VERSION, "lines": lines, "units": [],
           "register": {"columns": [], "rows": []}}
    reg = doc["register"]
    table_lines = []
    for i, ln in enumerate(lines, 1):
        if ln.startswith("# ") and "title" not in doc:
            doc["title"] = ln[2:].strip()
            doc["title_lines"] = [i, i]
        m = re.match(r"^Company: (.+?) \((\w{2})\)\. As of (\d{4}-\d{2}-\d{2})\.", ln)
        if m:
            reg.update({"company": m.group(1), "country": m.group(2), "as_of": m.group(3), "company_line": i})
        if ln.startswith("|"):
            table_lines.append(i)
    if table_lines:
        cells = lambda ln: [c.strip() for c in ln.strip().strip("|").split("|")]
        reg["columns"] = cells(lines[table_lines[0] - 1])
        reg["header_line"] = table_lines[0]
        for i in table_lines[1:]:
            row = cells(lines[i - 1])
            if all(set(c) <= {"-", ":", " "} for c in row):
                continue
            rec = dict(zip(reg["columns"], row))
            reg["rows"].append({"line": i, "cells": rec})
            _unit(doc["units"], doc_id, "register_row", line_loc(lines, i), lines[i - 1], cells=rec)
    doc["derived"] = {"policy_no": "", "version": "", "language": "", "master_language": "", "topic": "",
                      "lifecycle": "not_applicable", "entity": reg.get("company", "") or _code_from_name(file),
                      "entity_line": reg.get("company_line"), "as_of": reg.get("as_of", ""), "notes": []}
    return doc


def parse_twin(doc_id, file, raw):
    lines = split_lines(raw)
    doc = {"document_id": doc_id, "file": file, "sha256": sha256_bytes(raw), "size": len(raw),
           "kind": "twin", "parser_version": PARSER_VERSION, "lines": lines, "units": [], "records": []}
    cur = None
    for i, ln in enumerate(lines, 1):
        if ln.startswith("# ") and "title" not in doc:
            doc["title"] = ln[2:].strip()
        if ln.startswith("## "):
            code = ENTITY_CODE.search(ln)
            cur = {"heading": ln[3:].strip(), "line": i, "code": code.group(0) if code else "", "fields": {}}
            doc["records"].append(cur)
            continue
        m = re.match(r"^- \*\*(.+?):\*\* ?(.*)$", ln)
        if m and cur is not None:
            cur["fields"][m.group(1)] = {"value": m.group(2), "line": i}
    for rec in doc["records"]:
        ent = rec["fields"].get("Gesellschaft", {}).get("value", "") or rec["code"]
        rec["entity"] = ent
        for key, f in rec["fields"].items():
            _unit(doc["units"], doc_id, "twin_field", line_loc(lines, f["line"]), lines[f["line"] - 1],
                  section=rec["heading"], field=key, entity_hint=ent)
    doc["derived"] = {"policy_no": "", "version": "", "language": "", "master_language": "", "topic": "",
                      "lifecycle": "not_applicable", "entity": "", "entity_line": None, "notes": []}
    return doc


def parse_document(doc_id, file, raw):
    kind = doc_kind(file)
    if kind == "register":
        return parse_register(doc_id, file, raw)
    if kind == "twin":
        return parse_twin(doc_id, file, raw)
    return parse_structured_doc(doc_id, file, raw)


# ---------------------------------------------------------------- structured company files

def _flatten(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{path}.{k}")
    elif isinstance(obj, list):
        if not obj:
            yield path, None
        for i, v in enumerate(obj):
            yield from _flatten(v, f"{path}[{i}]")
    else:
        yield path, obj


def parse_profile(raw):
    data = json.loads(raw.decode("utf-8"))
    sid = "company_profile.json"
    doc = {"document_id": sid, "file": sid, "sha256": sha256_bytes(raw), "size": len(raw), "kind": "profile",
           "parser_version": PARSER_VERSION, "units": [], "empty_paths": [], "data": data}
    for path, val in _flatten(data):
        if val is None:
            doc["empty_paths"].append(path)
        elif isinstance(val, str) and val.strip():
            _unit(doc["units"], sid, "profile_value", {"json_path": path}, val)
    doc["derived"] = {"lifecycle": "not_applicable", "entity": "", "notes": [], "language": "", "topic": ""}
    return doc


def parse_csv_rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))


def parse_entities(raw):
    sid = "legal_entities.csv"
    rows = parse_csv_rows(raw)
    doc = {"document_id": sid, "file": sid, "sha256": sha256_bytes(raw), "size": len(raw), "kind": "entities",
           "parser_version": PARSER_VERSION, "units": [], "rows": rows}
    for r in rows:
        for f, v in r.items():
            if v and f not in ("id", "parentId"):
                _unit(doc["units"], sid, "csv_field", {"row_id": r["id"], "field": f}, v, entity_hint=r.get("name", ""))
    doc["derived"] = {"lifecycle": "not_applicable", "entity": "", "notes": [], "language": "", "topic": ""}
    return doc


def parse_twin_questions(raw):
    sid = "twin_questions.csv"
    rows = parse_csv_rows(raw)
    doc = {"document_id": sid, "file": sid, "sha256": sha256_bytes(raw), "size": len(raw),
           "kind": "twin_questions", "parser_version": PARSER_VERSION, "units": [], "rows": rows}
    for r in rows:  # only answered rows can be evidence; a question is not an answer
        if r.get("answer", "").strip():
            _unit(doc["units"], sid, "csv_field", {"row_id": r["id"], "field": "answer"}, r["answer"],
                  question=r.get("text", ""), answer_source=r.get("answerSource", ""))
    doc["derived"] = {"lifecycle": "not_applicable", "entity": "", "notes": [], "language": "", "topic": ""}
    return doc
