"""Version and language comparison of policy documents (task section 6.3).

Two comparisons per policy family, when both documents are in the sources:
- version: superseded -> current, same language (does the body change? does coverage change?)
- language: master <-> translation, same version. Sentences are matched across languages by meaning with the
  multilingual model of the semantic search (no machine translation). A pair at or above the cut-off is "likely the same
  content"; a sentence without such a partner exists only in one language version. This is a proposal for the
  reviewer and never changes coverage (gate 4 still counts master-language text only).
"""
from .textutil import normalize


META_FIELDS = [
    ("Document number", "header", "doc_number"),
    ("Version", "header", "version"),
    ("Valid from (header)", "header", "valid_from"),
    ("Status (header)", "header", "status"),
    ("Version status", "version_block", "status"),
    ("Language", "version_block", "sprache"),
    ("Valid from", "version_block", "gueltig_ab"),
    ("Valid until", "version_block", "gueltig_bis"),
    ("Approval date", "version_block", "freigabe_datum"),
    ("Reason for change", "version_block", "aenderungsgrund"),
    ("Policy-level: current version", "policy_block", "aktuelle_version"),
    ("Policy-level: status", "policy_block", "status"),
    ("Policy-level: next review", "policy_block", "naechste_ueberpruefung"),
    ("Policy-level: master language", "policy_block", "master_sprache"),
]


def ref(doc):
    d = doc["derived"]
    return {"source_id": doc["document_id"], "file": doc["file"], "title": doc.get("title", ""),
            "doc_number": doc["header"].get("doc_number", {}).get("value", ""), "version": d["version"],
            "language": d["language"], "lifecycle": d["lifecycle"], "valid_from": d["valid_from"],
            "valid_until": d["valid_until"]}


def _meta(left, right):
    rows = []
    for label, block, key in META_FIELDS:
        lv = left.get(block, {}).get(key)
        rv = right.get(block, {}).get(key)
        if not lv and not rv:
            continue
        rows.append({"field": label, "block": block,
                     "left": {"value": lv["value"], "line": lv["line"]} if lv else None,
                     "right": {"value": rv["value"], "line": rv["line"]} if rv else None,
                     "changed": (lv or {}).get("value") != (rv or {}).get("value")})
    return rows


def _sections(doc):
    secs = []
    for s in doc["sections"]:
        sents = [u for u in doc["units"] if u["kind"] == "policy_sentence" and u.get("section") == s["heading"]]
        secs.append({"heading": s["heading"], "heading_line": s["heading_line"], "sentences": sents})
    return secs


def _side(sentences, other_norm):
    return [{"loc": u["loc"], "text": u["text"],
             "status": "same" if normalize(u["text"]) in other_norm else "only_here"} for u in sentences]


def _body(left, right):
    ls, rs = _sections(left), _sections(right)
    out, changed = [], False
    for i in range(max(len(ls), len(rs))):
        a = ls[i] if i < len(ls) else {"heading": "", "heading_line": None, "sentences": []}
        b = rs[i] if i < len(rs) else {"heading": "", "heading_line": None, "sentences": []}
        an = {normalize(u["text"]) for u in a["sentences"]}
        bn = {normalize(u["text"]) for u in b["sentences"]}
        if an != bn:
            changed = True
        out.append({"left_heading": a["heading"], "left_heading_line": a["heading_line"],
                    "right_heading": b["heading"], "right_heading_line": b["heading_line"],
                    "left": _side(a["sentences"], bn), "right": _side(b["sentences"], an)})
    return out, changed


def _vkey(v):
    try:
        return tuple(int(x) for x in (v or "").split("."))
    except ValueError:
        return (-1,)


def compare_versions(docs, similarity, cutoff=0.80):
    """similarity(texts_a, texts_b) -> matrix of cross-language similarities (the multilingual model)."""
    fams = {}
    for d in docs.values():
        if d.get("kind") == "policy" and d["derived"].get("policy_no"):
            fams.setdefault(d["derived"]["policy_no"], []).append(d)
    out = []
    for pno, members in sorted(fams.items()):
        members.sort(key=lambda d: (d["derived"]["language"], _vkey(d["derived"]["version"])))
        # version comparisons within one language
        by_lang = {}
        for d in members:
            by_lang.setdefault(d["derived"]["language"], []).append(d)
        for lang, ds in sorted(by_lang.items()):
            for a, b in zip(ds, ds[1:]):
                sections, changed = _body(a, b)
                out.append({
                    "kind": "version", "policy_no": pno, "title": b.get("title", ""), "language": lang,
                    "left": ref(a), "right": ref(b), "metadata": _meta(a, b), "sections": sections,
                    "body_changed": changed,
                })
        # language comparisons within one version (master vs translation)
        by_ver = {}
        for d in members:
            by_ver.setdefault(d["derived"]["version"], []).append(d)
        for ver, ds in sorted(by_ver.items(), key=lambda x: _vkey(x[0])):
            masters = [d for d in ds if d["derived"]["language"] == d["derived"]["master_language"]]
            others = [d for d in ds if d["derived"]["language"] != d["derived"]["master_language"]]
            for m in masters:
                for t in others:
                    out.append(_language(pno, ver, m, t, similarity, cutoff))
    return out


def _language(pno, ver, m, t, similarity, cutoff):
    """Align master and translation sentence by sentence (by meaning, across languages)."""
    entry = {"kind": "language", "policy_no": pno, "title": m.get("title", ""), "version": ver,
             "left": ref(m), "right": ref(t), "metadata": _meta(m, t), "cutoff": cutoff}
    ms = [u for u in m["units"] if u["kind"] == "policy_sentence"]
    ts = [u for u in t["units"] if u["kind"] == "policy_sentence"]
    sim = similarity([u["text"] for u in ms], [u["text"] for u in ts]) if ms and ts else []
    sent = lambda u: {"loc": u["loc"], "text": u["text"], "section": u.get("section", "")}
    rows, matched = [], set()
    for j, u in enumerate(ts):                      # each translation sentence -> its closest master sentence
        i = max(range(len(ms)), key=lambda k: sim[k][j]) if ms else None
        score = round(float(sim[i][j]), 2) if i is not None else 0.0
        if score >= cutoff:
            matched.add(i)
            rows.append({"master": sent(ms[i]), "translation": sent(u), "similarity": score, "status": "likely_same"})
        else:
            rows.append({"master": None, "translation": sent(u), "similarity": score, "status": "only_translation"})
    for i, u in enumerate(ms):                      # master sentences that no translation sentence matches
        if i not in matched:
            best = max((sim[i][j] for j in range(len(ts))), default=0.0)
            rows.append({"master": sent(u), "translation": None, "similarity": round(float(best), 2),
                         "status": "only_master"})
    order = lambda r: (r["master"] or r["translation"])["loc"]["line_start"]
    rows.sort(key=lambda r: (order(r), r["status"] != "likely_same"))
    n_t = sum(r["status"] == "only_translation" for r in rows)
    n_m = sum(r["status"] == "only_master" for r in rows)
    entry.update(rows=rows, only_in_master=n_m, only_in_translation=n_t, body_changed=bool(n_t or n_m))
    return entry
