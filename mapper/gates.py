"""The seven gates applied to every candidate passage.

Gates 1-5 read metadata from the files (deterministic). Gates 6-7 interpret wording with
patterns and only propose. Every gate records its result, the reason and, where possible,
the line it relied on. Only gate 1 removes a candidate; the others add labels.
"""
import re

from .textutil import normalize

POLICY_UNIT_KINDS = {"policy_sentence", "title"}


class GateContext:
    """Company-level facts the gates need, built once per run from the company's own sources."""

    def __init__(self, company, docs, cfg):
        self.company = company
        self.docs = docs
        self.topics = [normalize(t) for t in cfg["topics"]]
        self.facets = {k: [re.compile(p) for p in v["patterns"]] for k, v in cfg["facets"].items()}
        self.facet_labels = {k: v["label"] for k, v in cfg["facets"].items()}
        self.normative_res = [re.compile(p) for p in cfg["normative_patterns"]]
        # case-sensitive patterns on the raw sentence: does the sentence itself concern the topic?
        self.sentence_topic_res = [re.compile(p) for p in cfg.get("sentence_topic_patterns", [])]
        self.entity_name = normalize(company.entity_name)
        self.codes = [c for c in company.entity_codes]
        # lookups for controls whose topic comes from the risk / obligation they cover
        self.risk_topic, self.duty_topic = {}, {}
        for d in docs.values():
            for row in d.get("register", {}).get("rows", []):
                c = row["cells"]
                if "Risk" in c and "Category" in c:
                    self.risk_topic[c["Risk"]] = (c["Category"], d["document_id"], row["line"])
                if "Obligation" in c and "Legal area" in c:
                    self.duty_topic[c["Obligation"]] = (c["Legal area"], d["document_id"], row["line"])
        # master-language policy text, for the language gate
        self.master_text = {}
        for d in docs.values():
            dv = d.get("derived", {})
            if d.get("kind") == "policy" and dv.get("language") and dv.get("language") == dv.get("master_language"):
                key = (dv["policy_no"], dv["version"])
                self.master_text[key] = (d["document_id"], {normalize(u["text"]) for u in d["units"]})

    # ------------------------------------------------------------ gate 1
    def entity(self, unit, doc):
        hint = unit.get("entity_hint") or doc.get("derived", {}).get("entity", "")
        text = hint if hint else (unit["text"] if doc["kind"] == "profile" else "")
        nt = normalize(text)
        if not nt:
            return "not_stated", "No entity stated for this source or value."
        if self.entity_name in nt or any(c.lower() in nt for c in self.codes):
            line = doc.get("derived", {}).get("entity_line")
            return "match", f"Entity '{hint or self.company.entity_name}'" + (f" (L{line})" if line else "")
        if re.search(r"\b[a-z]{2,5}-[a-z]{2}-\d{2}\b", nt) or hint:
            return "other_entity", f"Belongs to another entity: '{hint or text[:80]}'"
        return "not_stated", "No entity stated for this value."

    # ------------------------------------------------------------ gate 2
    @staticmethod
    def kind(unit, doc):
        if doc["kind"] == "policy" and unit["kind"] in POLICY_UNIT_KINDS:
            return "policy_text", "Internal policy text (Soll)."
        if doc["kind"] in ("register", "evidence_record", "twin", "profile", "entities", "twin_questions"):
            return "supporting_record", f"{doc['kind'].replace('_', ' ').capitalize()}: a record, not policy text."
        return "other_document", "Other document; context only."

    # ------------------------------------------------------------ gate 3
    @staticmethod
    def lifecycle(doc):
        d = doc.get("derived", {})
        lc = d.get("lifecycle", "not_applicable")
        h = doc.get("header", {}).get("status", {})
        v = doc.get("version_block", {}).get("status", {})
        bits = []
        if h:
            bits.append(f"Status '{h['value']}' (L{h['line']})")
        if v:
            bits.append(f"version status '{v['value']}' (L{v['line']})")
        return lc, ", ".join(bits) or "No lifecycle (record or structured file)."

    # ------------------------------------------------------------ gate 4
    def language(self, unit, doc):
        d = doc.get("derived", {})
        if doc["kind"] != "policy":
            return "not_applicable", ""
        lang, master = d.get("language"), d.get("master_language")
        if not master or lang == master:
            return "master", f"Master-language version ({lang or 'unknown'})."
        key = (d["policy_no"], d["version"])
        if key not in self.master_text:
            return "master_not_in_scope", f"Translation ({lang}); the {master} master of {key[0]} v{key[1]} is not in the sources."
        _, texts = self.master_text[key]
        if normalize(unit["text"]) in texts:
            return "also_in_master", f"Same text also appears in the {master} master."
        return "translation_only", (f"Appears only in the {lang} version; the {master} master "
                                    f"({key[0]} v{key[1]}) does not contain it.")

    # ------------------------------------------------------------ gate 5
    def topic_of(self, unit, doc):
        """Return (topic, how) or (None, why-unknown)."""
        if doc["kind"] == "policy":
            pb = doc.get("policy_block", {}).get("thema")
            if pb:
                return pb["value"], f"thema: {pb['value']} (L{pb['line']})"
        if unit["kind"] == "register_row":
            c = unit["cells"]
            for col in ("Category", "Legal area", "Area"):
                if c.get(col):
                    return c[col], f"column '{col}' = {c[col]}"
            # controls have no topic column: use the risk or obligation they cover
            if c.get("Risk covered") in self.risk_topic:
                t, sid, line = self.risk_topic[c["Risk covered"]]
                return t, f"via risk '{c['Risk covered']}' (risk register L{line}): {t}"
            if c.get("Legal duty covered") in self.duty_topic:
                t, sid, line = self.duty_topic[c["Legal duty covered"]]
                return t, f"via obligation (obligations register L{line}): {t}"
            # 'Type' is a topic only in registers without a control-type column (e.g. incidents)
            if c.get("Type") and "Risk covered" not in c:
                return c["Type"], f"column 'Type' = {c['Type']}"
        if doc["kind"] == "evidence_record":
            q = doc.get("record_fields", {}).get("quelle")
            if q:
                return q["value"], f"quelle: {q['value']} (L{q['line']})"
        return None, "No topic field for this source."

    def scope(self, unit, doc):
        topic, how = self.topic_of(unit, doc)
        if topic is None:
            if any(t in normalize(unit["text"]) for t in self.topics):
                return "fit", "Text names the topic."
            return "unknown", how
        if any(t in normalize(topic) for t in self.topics):
            return "fit", how
        # sentence-level scope: a sentence about the topic inside an unrelated document still
        # concerns the duty (e.g. an IT rule in an anti-corruption policy); an evacuation drill does not
        if unit["kind"] in ("policy_sentence", "text_sentence"):
            hits = [m.group(0) for p in self.sentence_topic_res for m in [p.search(unit["text"])] if m]
            if hits:
                return "fit_sentence", (f"Document topic does not fit ({how}), but the sentence itself concerns the "
                                        f"topic ({', '.join(dict.fromkeys(hits))}).")
        return "mismatch", f"Topic does not fit the duty: {how}"

    # ------------------------------------------------------------ gate 6
    def normative(self, unit):
        if unit["kind"] == "title":
            return "title_only", "Document title only; states no rule."
        if unit["kind"] not in ("policy_sentence", "text_sentence"):
            return "record", "Record entry, not a rule statement."
        nt = normalize(unit["text"])
        hits = [p.pattern for p in self.normative_res if p.search(nt)]
        if hits:
            return "rule", "States a rule (" + ", ".join(h.strip("\\b") for h in hits[:3]) + ")."
        return "topic_only", "Names the subject but states no rule."

    # ------------------------------------------------------------ gate 7
    def facets_found(self, unit):
        nt = normalize(unit["text"])
        return sorted(k for k, pats in self.facets.items() if any(p.search(nt) for p in pats))


def evaluate(ctx, unit, doc, element):
    """Run all gates on one candidate and propose a relation level."""
    gates = []
    ent, why = ctx.entity(unit, doc)
    gates.append({"gate": "1 entity", "result": ent, "reason": why})
    kind, why = ctx.kind(unit, doc)
    gates.append({"gate": "2 kind", "result": kind, "reason": why})
    lc, why = ctx.lifecycle(doc)
    gates.append({"gate": "3 lifecycle", "result": lc, "reason": why})
    lang, why = ctx.language(unit, doc)
    gates.append({"gate": "4 language", "result": lang, "reason": why})
    sc, why = ctx.scope(unit, doc)
    gates.append({"gate": "5 scope", "result": sc, "reason": why})
    norm, why = ctx.normative(unit)
    gates.append({"gate": "6 normative", "result": norm, "reason": why})
    found = ctx.facets_found(unit)
    req = element["facets_required"]
    present = [f for f in req if f in found]
    missing = [f for f in req if f not in found]
    gates.append({"gate": "7 facets", "result": f"{len(present)}/{len(req)}",
                  "reason": "Present: " + (", ".join(present) or "none") + "; missing: " + (", ".join(missing) or "none")})

    if ent == "other_entity":
        relation = "excluded"
    elif kind == "policy_text":
        if sc == "mismatch":
            relation = "scope_mismatch"
        elif norm in ("title_only", "topic_only"):
            relation = "topic_only"
        else:
            relation = "covers" if not missing else "partial"
    elif kind == "supporting_record":
        relation = "scope_mismatch" if sc == "mismatch" else "supporting"
    else:
        relation = "scope_mismatch" if sc == "mismatch" else "context"
    qualifiers = []
    if lc == "superseded":
        qualifiers.append("superseded")
    if lang == "translation_only":
        qualifiers.append("translation_only")
    if ent == "not_stated":
        qualifiers.append("entity_not_stated")
    if sc == "fit_sentence" and kind == "policy_text":
        qualifiers.append("off_topic_policy")
    return {"relation": relation, "qualifiers": qualifiers, "gates": gates,
            "facets_present": present, "facets_missing": missing,
            "facets_present_labels": [ctx.facet_labels[f] for f in present],
            "facets_missing_labels": [ctx.facet_labels[f] for f in missing]}
