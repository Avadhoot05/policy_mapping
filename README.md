# Policy mapping: NIS2 duties → internal policy passages

This is a local tool that maps four NIS2 duties (§30 Abs. 2 Nr. 1, 2, 3, 6 BSIG) to the exact internal policy passages
of a company. It shows coverage, version and language, the supporting records, and what is missing or needs an
update. It is built for Marenthal Chemie AG and works for any company folder added later.

## Run it

Requirements: Python 3.10+ (developed on 3.12), Linux or macOS. Place the unzipped COBACK input package next to this
folder:

```
some-folder/
├── coback_policy_mapping/        ← this solution
└── COBACK_Marenthal_Inputs/      ← COBACK's input package, as supplied
```

```bash
cd coback_policy_mapping
./setup.sh               # 1. creates .venv, installs requirements.txt (Jinja2) and checks the inputs
./start.sh               # 2. starts http://127.0.0.1:8000/
./test.sh                # 3. optional: runs the 26 tests
```

1. On the start page, press **Start analysis**. A run takes well under a second.
2. Open the report. It has three tabs: **Overview**, **Duty results** and **Version comparison**.
3. In Duty results, each element has **Confirm / Reject / Needs clarification**. Decisions are saved per company with
   your name and the time.

| Script | Options |
|---|---|
| `./setup.sh` | `--semantic`: also installs CPU-only PyTorch and sentence-transformers and downloads the model (~0.8 GB, once) |
| `./start.sh` | `--semantic`: hybrid search (needs `./setup.sh --semantic`) · `--port 8080`: another port |
| `./test.sh` | Runs all tests, verbose (24; the 3 hybrid tests are skipped without the semantic packages) |

The scripts are safe to run again: steps that are already done are skipped. If the inputs are elsewhere, edit
`input_dir` in `companies/marenthal/company.json` and `legal_input` / `legal_input_txt` in `config/app.json`;
`./setup.sh` and `./start.sh` report what they cannot find.

Without the script, the default mode also runs directly with `python3 app.py`. Use `python3 app.py --run marenthal`
for one analysis without the UI, and `python3 app.py --check` to check the inputs.

## Results for Marenthal Chemie AG (sources reviewed: 15 starter files + 3 structured company files)

| Duty | Policy text (Soll) | Key findings |
|---|---|---|
| **04-P02-1** Risk analysis & IT security concept | **Topic only** | KR-009 v2.0 DE (DMS-00000420, L18–19) only names the topic "Informationssicherheit" and states no rule. The obligations register shows the annual risk analysis as *offen*, due 2026-01-01 (overdue). Both IT risks in the risk register have overdue reviews. |
| **04-P02-2** Incident handling | **No supporting passage found** | KR-017 matches words such as "Alarmierung" and "Übung", but its topic is **EHS** (evacuation, alarm chains), so it is not counted. No IT incident procedure and no test protocol were found. |
| **04-P02-3** Continuity, backups, recovery, crisis | **No supporting passage found**, with a language difference flagged | The IT recovery-exercise rule exists **only in the EN translation** (DMS-00000443, L22–23), not in the DE master (`master_sprache: de`). The master is authoritative, so the rule is not counted. Records exist (backup/restore control, restart exercise, evidence record DMS-00001406), but there is no restore protocol and no measured recovery time. |
| **04-P02-6** Effectiveness assessment | **No supporting passage found** | Four IT controls have execution summaries (one run "teilweise wirksam"). Summaries are not test protocols, so effectiveness is **not demonstrated** (17-AUS-17). |

Each "not found" is backed by a "Sources checked" list (every source, the search terms, hit or no hit). Each gap
has a next step: which section to add to **KR-009 v2.0 DE, section "Pflichten und Zuständigkeiten"**, linked open twin
questions (#195, #196, #197, #174, #200, …).

**Version comparison:** KR-009 v1.1 → v2.0 (DE) has an identical body, so coverage does not change, and validity is
continuous (until 2024-07-08 / from 2024-07-09). The superseded v1.1 still contains the policy-level field
`aktuelle_version: 2.0`; the document's own status (*Superseded*, L14/L37) is what counts. The DE↔EN comparison of
v2.0 is a compact *language difference* box: it lists only text in the EN file that is written in German but does not
exist in the German master (L22–23 recovery rule, L24 rack inspection). Translated sentences are not compared word
for word, and no translation or AI is used. KR-017 v1.1 → v2.0 is shown as well.

## Full-corpus cross-check (not part of the report's scope)

The report uses the bounded source set allowed by START_HERE.txt (15 starters + 3 structured files). As a check,
the same pipeline was also run over **all 1,426 documents**. The policy result for KR-009 does not change: no version
of the information-security policy states a concrete rule. These additional findings are outside the report's scope
and are documented here only:

| Finding | Source | Effect if the full corpus were in scope |
|---|---|---|
| The IT recovery-exercise rule (*"Notfall- und Wiederanlaufübung der IT durchführen – Wiederherstellung kritischer Systeme (ERP, Prozessleitsystem) üben und Ergebnisse dokumentieren."*) appears in German in **12 current, approved policies on other topics**: KR-002 v2.0, KR-003 v2.0, KR-004 v1.1, KR-005 v2.0, KR-006 v1.1, KR-007 v2.0, KR-010 v2.0, KR-011 v1.1, KR-012 v1.1, KR-015 v1.1, KR-016 v1.1, KR-018 v1.1 (usually L32–33). Never in KR-009 DE. | e.g. DMS-00000362 (KR-002 v2.0) L32–33 | 04-P02-3 *recovery* and 04-P02-2 *incident test* become **Partial, in unrelated policy**. The rule has no owner, interval or recovery-time target, and it belongs in KR-009. Those policies' obligation sections repeat the same group-wide list (code of conduct, partner checks, alarm chains, …), so this looks like a copied catalogue rather than a deliberate IT rule. |
| Internal IT-security (ISMS) audit of Marenthal Chemie AG, 4–6 Nov 2025, covering access, patch and backup management. Finding 3: *"Wiederherstellungstest der Datensicherung wurde nicht dokumentiert"* (closed); a corrective measure is recorded in REG_Corrective_Measures_CMS-DE-01 L27. | DMS-00001370 L23–41 | Evidence that an effectiveness check took place (04-P02-6) and that restore-test documentation was missing (04-P02-3). |
| ISO/IEC 27001 certificate IS-FRA-48211: `gueltig_bis: 2026-06-16`, `status: läuft ab`. | DMS-00000276 L28–29 | **Expired** at the 2026-11-18 snapshot, while company_profile.json `.certifications[13]` still lists it as a certificate. |
| Mandatory annual information-security and phishing e-learning, referring to KR-009. | DMS-00000087 / DMS-00000092 | Awareness training only; not an incident procedure. |

To repeat the check, point a company's `input_dir` to a copy of the inputs **without** `document_starters.csv`;
the tool then uses the whole catalogue. Known limits of that mode:
- French and Chinese header labels are not parsed.
- Audit reports, certificates and training records are shown as context, not yet as structured evidence records.

## How a duty is related to a passage

```
duty → elements (from the duty text and its Nachweisfrage, e.g. 04-P02-3 → continuity, backup, recovery, crisis)
     → search: DE/EN terms over natural units (policy sentences, register rows, record fields), ranked by BM25
     → 7 gates per candidate:
         1 entity     only the assessed entity (other group companies are dropped)
         2 kind       policy text (Soll) vs. record (implementation evidence)
         3 lifecycle  the document's own status; superseded text is never counted
         4 language   master language is authoritative; translation-only text is flagged, not counted
         5 scope      the topic must fit (EHS ≠ information security); an IT sentence inside an unrelated
                      policy still counts, flagged "in unrelated policy"
         6 rule?      does it state a rule, or only name the topic?
         7 facets     which required facets are stated (what, action, owner, interval, target, documentation)
     → proposal: Covered / Partial / Topic only / No supporting passage found  (+ flags)
     → reviewer confirms, rejects or asks for clarification
```

- **Three dimensions are kept separate**, as 17-AUS-17 requires: policy text, implementation records and effectiveness.
  A register saying "erfüllt" or "wirksam" is a record, not proof. Missing proof means "not demonstrated", never
  "ineffective".
- **No scores or percentages.** BM25 only orders candidates for display.
- **Every quote is verbatim**, with `document_id`, file and a line/character location (lines start at 1 and match
  `cat -n`). The test suite re-checks every quote against the files (validation check CIT-1).
- **Blank is not "no".** Empty profile lists, blank CSV fields and open twin questions are reported as unknown.

## Search modes: keyword (default) and hybrid

Set `"search_mode"` in `config/app.json`, or use `./start.sh --semantic` (after `./setup.sh --semantic`).

| Mode | How candidates are found | Needs |
|---|---|---|
| `keyword` (default) | DE/EN term matching over all units, ranked with BM25 | Jinja2 only (requirements.txt) |
| `hybrid` | Keyword as above, **plus** a free local multilingual embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) that proposes the 5 most similar **policy sentences** per element (cosine similarity ≥ 0.30) | `./setup.sh --semantic` (CPU PyTorch + sentence-transformers + model, ~0.8 GB once) |

In both modes **the same seven gates decide**. Semantic search only widens the net:
- **What it can do:** a passage found only by similarity can make an element *Covered* or *Partial*.
- **What it can't do:** create a *Topic only* status, because being close in meaning is not the same as naming the subject.

The search mode and similarity of each candidate are recorded in `mapping_result.json` (`search`, `found_by`, `similarity`); the report does not show them. Embeddings are cached per
company (keyed by text hash), so later runs only embed changed text.

**Why only policy sentences:** calibration on the Marenthal data showed that similarity alone cannot separate relevant
rules (0.37–0.48) from KR-017's EHS alarm and evacuation sentences (0.40–0.52). Over register rows and twin fields it
was mostly noise (e.g. a safety data sheet's "Stabilität und Reaktivität" for business continuity).

**One element per sentence:** a sentence found only by semantic search is offered only to the element it is
closest to. Otherwise one IT rule would be proposed to, and could be counted for, elements it is not about.

**Result on the Marenthal data:** hybrid mode proposed 15 additional policy passages. The gates rejected or
discounted all of them, and all four duty results are **identical** in both modes. The "no supporting passage found"
claims therefore don't depend only on the keyword lists. A test (`TestSemanticHybrid`) checks this; it is skipped
when the semantic packages are not installed.

## Multiple companies

Each company is a folder `companies/<slug>/` with a `company.json`:

```json
{ "name": "…", "entity_id": "…", "entity_name": "…", "entity_codes": ["XX-DE-01"],
  "snapshot_date": "YYYY-MM-DD", "input_dir": "path/to/inputs", "company_data_subdir": "company_data" }
```

The input folder has the same layout as the Marenthal package: `company_data/` with `documents_index.csv`,
`documents/`, `company_profile.json`, `legal_entities.csv`, `twin_questions.csv`, plus an optional
`document_starters.csv`. If the starters file is missing, all indexed documents are used. The new company appears on
the start page.

Companies are fully isolated. Each one has its own inputs, parse cache (`cache/`), runs (`runs/<run_id>/`) and
reviewer decisions (`review/`). Nothing company-specific is hard-coded; only the law-level configuration
(`config/duty_elements.json`) and the legal input are shared. A test runs Marenthal and a **synthetic** test company
(`tests/fixtures`, clearly labeled) and checks that no data crosses over.

## Caching and change detection

Parsed documents are stored in `companies/<slug>/cache/parsed/` with a `manifest.json` (sha256, size, mtime, parser
version). Later runs reuse them. A file is re-parsed when its **content hash** or the **parser version** changes;
the hash is used because copying or unzipping resets modification times. Changed files are listed in the report.
Reviewer decisions store a fingerprint of the proposal; if a later run proposes something different, the decision
is shown as **"Re-review needed"**.

## Outputs per run (`companies/<slug>/runs/<run_id>/`)

| File | Content |
|---|---|
| `report.html` | One page with three tabs: **Overview** (summary table), **Duty results** (per duty: Mapping, Evidence, Missing information, Sources checked, with review buttons) and **Version comparison** (incl. the language-difference box). |
| `mapping_result.json` | The full result with a stable schema (the pages are a view of it) |
| `parsed_cited_documents.json` | The parsed form of every cited document, for inspection |

## Scope, assumptions and limits

- **Sources:** the 15 files in `document_starters.csv` plus the 3 structured company files, as allowed by
  START_HERE.txt. "Not found" always means "not found in these sources".
- **Exercise assumption:** the four duties are assumed applicable. This is a mapping proposal, not a legal finding.
- **Master language authoritative:** text found only in a translation is flagged as a language difference and not
  counted. (Asked COBACK to confirm.)
- **Registers are evidence, not policy text**, even when they name a group policy as their source.
- **Overdue** is computed against the snapshot date 2026-11-18; the register's own as-of date is shown as well.
- **Known limits:**
  - Keyword search can miss synonyms. The search terms are listed in the report so the "not found" claims can be checked.
  - Gates 6–7 (rule detection, facets) are pattern-based proposals for the reviewer, not decisions.
- **Out of scope:** relevance assessment, a full compliance verdict, a knowledge graph, task planning and management,
  reminders, PDF export, MCP and deployment.

## Production architecture

This prototype is deliberately local and standard-library only (*"A local prototype is sufficient"*). Its **concepts**
are the ones a production system needs. Its **storage and runtime** are not.

**Storage is already behind an interface.** Everything persistent goes through `mapper/store.py`: the parse cache
(manifest and parsed documents), the run outputs and the reviewer decisions. The pipeline, server and review logic
never touch file paths. `FileStore` is the only implementation (one folder per company). A `PostgresStore` would
implement the same methods (`load_manifest`, `save_parsed`, `save_run`, `list_runs`, `read_run_file`,
`load_decisions`, `append_decision`, …) and be selected with `"store": "postgres"` in `company.json`. The test
`TestStoreContract` defines the behaviour any implementation must have.

**Carries over unchanged**
- Change detection by content hash plus parser version.
- Immutable, versioned documents: every citation is bound to document ID, version and hash.
- Exact, re-verifiable citation anchors.
- Deterministic gates for entity, kind, lifecycle, language and scope, kept separate from interpretation.
- System proposal → human decision, with a fingerprint and "Re-review needed".
- Strict per-company isolation and a stable JSON result schema.

**Must change**

| Area | Prototype | Production |
|---|---|---|
| Storage | One JSON file per parsed document on local disk | Postgres (EU) with transactions, backups and row-level security per workspace; raw files in EU object storage, keyed by sha256 |
| Search | In-memory index rebuilt every run; keywords + BM25 | Persistent, incremental index: German full-text (`tsvector`) + multilingual embeddings (`pgvector`) for synonyms and cross-language recall |
| Parsing | Parsers for this dump's TXT layout | Versioned extraction for PDF/DOCX/scans (incl. OCR), anchors on the **original** document (page, paragraph, character offsets) instead of TXT line numbers |
| Re-evaluation | Whole analysis on every run | Only duties whose cited document versions changed (dependency graph citation → document version) |
| Execution | Synchronous in the web request, stdlib server | Job queue + workers for ingestion, extraction and mapping; API stays responsive |
| Reviews | JSON file, free-text reviewer name | Append-only `review_decision` table, SSO identity, permissions, audit log |
| Interpretation | Pattern-based rule and facet detection | LLM facet extraction quoting exact passages, labeled "Model estimate"; gates 1–5 stay deterministic |

**Target flow**

```
Connectors (SharePoint, Drive, …)  ──►  Object storage (EU): raw files, immutable, keyed by sha256
                                             │  change event (etag / hash differs)
                                             ▼
                                  Job queue ──► Extraction workers (versioned parsers, OCR)
                                             │  text + structure + stable anchors (page, paragraph, offsets)
                                             ▼
          Postgres (EU, row-level security per workspace)
            document · document_version · passage (text, anchor, hash, parser_version)
            passage search: German full-text (tsvector) + embeddings (pgvector)
                                             │
                                             ▼
          Mapping workers: retrieve (BM25 + embeddings) → gates 1–5 (deterministic)
                           → LLM facet extraction, quoting exact passages ("Model estimate")
                           → proposal + fingerprint, only for duties affected by the change
                                             │
                                             ▼
          mapping_proposal · citation · review_decision (append-only, SSO user) · audit log
                                             │
                                             ▼
          API / MCP (read-only)  ──►  UI renders the report live from the database
```

**Design choices**
- **One store first.** Postgres + pgvector keeps documents, passages, search, results and reviews transactional in one place. A separate search engine (e.g. OpenSearch with a German compound-word splitter) is worth adding only when one database is no longer enough.
- **Stable anchors.** Citations point to the original file (page, paragraph, offsets), plus the extraction version. They survive a re-extraction, and the quote can always be re-verified.
- **Incremental and auditable.** A changed document triggers re-extraction and re-evaluation of only the affected proposals. Their review decisions become "Re-review needed" instead of being overwritten (no silent changes).
- **The model proposes, the gates and the person decide.** Entity, version, language and scope are never left to the model.

## Project layout

```
app.py                  entry point (UI server or --run)
mapper/parsing.py       source parsing with exact line/character locations
mapper/company.py       company discovery, source scope, parse cache logic (via the store)
mapper/store.py         storage interface (Store) and its file implementation (FileStore)
mapper/search.py        term matching + BM25
mapper/semantic.py      optional semantic search (hybrid mode)
mapper/gates.py         the 7 gates
mapper/analysis.py      pipeline: elements, dimensions, explanations, questions, next steps
mapper/compare.py       version and language comparison
mapper/validate.py      10 data and result checks, run by the test suite (nothing stored)
mapper/review.py        reviewer decisions and re-review detection
mapper/render.py        prepares data and renders the pages with Jinja2
mapper/templates/       page layout as HTML templates (report, duty tabs, comparison, legal duty, start, source)
mapper/static/          report.css, report.js, start.js (inlined, so each report.html is self-contained)
mapper/server.py        local web server (Python standard library)
config/duty_elements.json  law-level configuration (elements, terms, facets, questions)
companies/marenthal/company.json
tests/                  unit and integration tests, synthetic test company
```
