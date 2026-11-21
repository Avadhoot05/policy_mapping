"""Company discovery, source selection and the per-company parse cache.

Every path is derived from the company folder, so companies never share inputs,
cache, runs or reviews.
"""
import csv
import json
import os
import re
from datetime import datetime, timezone

from . import parsing
from .store import store_for

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANIES_DIR = os.path.join(APP_ROOT, "companies")
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
STRUCTURED = ("company_profile.json", "legal_entities.csv", "twin_questions.csv")


def load_app_config():
    with open(os.path.join(APP_ROOT, "config", "app.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg


class Company:
    def __init__(self, folder):
        self.folder = os.path.abspath(folder)
        self.slug = os.path.basename(self.folder)
        with open(os.path.join(self.folder, "company.json"), encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.name = self.cfg["name"]
        self.entity_id = self.cfg["entity_id"]
        self.entity_name = self.cfg["entity_name"]
        self.entity_codes = self.cfg.get("entity_codes", [])
        self.snapshot_date = self.cfg["snapshot_date"]
        self.input_dir = self._abs(self.cfg.get("input_dir", "input"))
        self.data_dir = os.path.join(self.input_dir, self.cfg.get("company_data_subdir", "company_data"))
        if self.cfg.get("duties_file"):          # company-specific legal input
            self.duties_file = self._abs(self.cfg["duties_file"])
        else:                                     # shared law-level legal input
            p = load_app_config()["legal_input"]
            self.duties_file = p if os.path.isabs(p) else os.path.normpath(os.path.join(APP_ROOT, p))
        self.runs_dir = os.path.join(self.folder, "runs")   # only used to print the report path in CLI mode
        self.store = store_for(self)                        # all persistent state goes through the store

    def _abs(self, p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(self.folder, p))

    # ------------------------------------------------------------ sources
    def source_list(self):
        """Documents in scope: the company's document_starters.csv if present, else its whole index."""
        index = self.read_index()
        starters = os.path.join(self.input_dir, "document_starters.csv")
        if os.path.exists(starters):
            with open(starters, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            scope = "starters"
        else:
            rows = [{"document_id": r["id"], "file": r["file"], "description": r.get("name", "")} for r in index]
            scope = "index"
        return rows, scope, index

    def read_index(self):
        p = os.path.join(self.data_dir, "documents_index.csv")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return list(csv.DictReader(f))


def discover_companies():
    out = []
    if not os.path.isdir(COMPANIES_DIR):
        return out
    for name in sorted(os.listdir(COMPANIES_DIR)):
        folder = os.path.join(COMPANIES_DIR, name)
        if SLUG.match(name) and os.path.exists(os.path.join(folder, "company.json")):
            out.append(Company(folder))
    return out


def get_company(slug):
    if not SLUG.match(slug or ""):
        return None
    folder = os.path.join(COMPANIES_DIR, slug)
    return Company(folder) if os.path.exists(os.path.join(folder, "company.json")) else None


# ---------------------------------------------------------------- cache

def load_sources(company):
    """Parse every source in scope, reusing the on-disk cache when content and parser are unchanged.

    Returns (docs_by_id, cache_report). A document is re-parsed ("dirty") when its sha256 or the
    parser version differs from the manifest. Content hashes are used instead of modification
    times alone, because copying or unzipping resets times.
    """
    store = company.store
    manifest = store.load_manifest()
    rows, scope, index = company.source_list()
    targets = [(r["document_id"], r["file"], os.path.join(company.data_dir, r["file"])) for r in rows]
    targets += [(name, name, os.path.join(company.data_dir, name)) for name in STRUCTURED]
    docs, report = {}, {"scope": scope, "reused": [], "parsed": [], "dirty": [], "missing": [], "removed": []}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen = set()
    for sid, rel, path in targets:
        seen.add(sid)
        if not os.path.exists(path):
            report["missing"].append({"source_id": sid, "file": rel})
            continue
        with open(path, "rb") as f:
            raw = f.read()
        digest = parsing.sha256_bytes(raw)
        entry = manifest.get(sid)
        cached = store.load_parsed(sid) if entry and entry["sha256"] == digest \
            and entry["parser_version"] == parsing.PARSER_VERSION else None
        if cached is not None:
            docs[sid] = cached
            report["reused"].append(sid)
            continue
        if sid == "company_profile.json":
            doc = parsing.parse_profile(raw)
        elif sid == "legal_entities.csv":
            doc = parsing.parse_entities(raw)
        elif sid == "twin_questions.csv":
            doc = parsing.parse_twin_questions(raw)
        else:
            doc = parsing.parse_document(sid, rel, raw)
        store.save_parsed(sid, doc)
        if entry:
            reason = "content changed" if entry["sha256"] != digest else "parser version changed"
            report["dirty"].append({"source_id": sid, "file": rel, "reason": reason,
                                    "previous_sha256": entry["sha256"], "sha256": digest})
        report["parsed"].append(sid)
        st = os.stat(path)
        manifest[sid] = {"file": rel, "sha256": digest, "size": len(raw), "mtime": int(st.st_mtime),
                         "parser_version": parsing.PARSER_VERSION, "parsed_at": now}
        docs[sid] = doc
    for sid in list(manifest):
        if sid not in seen:
            report["removed"].append({"source_id": sid, "file": manifest[sid]["file"]})
            del manifest[sid]
    store.save_manifest(manifest)
    return docs, report, rows, index
