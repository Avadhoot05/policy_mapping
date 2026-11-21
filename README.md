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
./setup.sh               # 1. creates .venv, installs the packages and the model (~1 GB, once), checks the inputs
./start.sh               # 2. starts http://127.0.0.1:8000/
./test.sh                # 3. optional: runs the 25 tests
```

1. On the start page, press **Start analysis**. A run takes about 2 seconds (the model loads once per server start).
2. Open the report. It has three tabs: **Overview**, **Duty results** and **Version comparison**.
3. In Duty results, each element has **Confirm / Reject / Needs clarification**. Decisions are saved per company with
   your name and the time.


The scripts are safe to run again: steps that are already done are skipped.

> [!IMPORTANT]
> **Inputs in another folder?** Edit `input_dir` in `companies/marenthal/company.json` and `legal_input` in
> `config/app.json`. `./setup.sh` and `./start.sh` report what they cannot find.

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


## How candidates are found: keyword + semantic search

Every run uses both searches, and **the same seven gates decide** for both:

| Search | What it finds |
|---|---|
| Keyword | DE/EN term matches over all units (policy sentences, register rows, company data), ranked with BM25 |
| Semantic | The 5 policy sentences closest in meaning per element ( similarity ≥ 0.30), with a free local multilingual model (`paraphrase-multilingual-MiniLM-L12-v2`, no API) |

Semantic search catches rules worded without any of our search terms. The test company has one ("Verdächtige
Aktivitäten in der IT … sind der IT-Leitung zu melden"): only the semantic search finds it, and the gates count it as
*Covered* for incident reporting. Its limits are handled by the rules below:
- **Close meaning is not a match.** On the Marenthal data, real rules scored 0.37–0.48 but KR-017's EHS evacuation
  sentences scored 0.40–0.52. So a sentence found only by meaning is reported **only when the gates count it**;
  otherwise it is neither listed nor explained. It can also never create *Topic only*.
- **One element per sentence:** a meaning-only sentence is offered only to the element it is closest to.
- **Only policy sentences** are searched by meaning; over register rows and company data it was mostly noise.

`mapping_result.json` records how each candidate was found (`found_by`, `similarity`). Embeddings are cached per
company (keyed by text hash), so later runs only embed changed text. On the Marenthal data the semantic search adds
no counted passage: the four duty results are the same as with keyword search alone, so the "no supporting passage
found" claims do not depend only on the keyword lists.

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
(`config/duty_elements.json`) and the legal input are shared.

## Outputs per run (`companies/<slug>/runs/<run_id>/`)

| File | Content |
|---|---|
| `report.html` | One page with three tabs: **Overview** (summary table), **Duty results** (per duty: Mapping, Evidence, Missing information, Sources checked, with review buttons) and **Version comparison** (incl. the language-difference box). |
| `mapping_result.json` | The full result with a stable schema (the pages are a view of it) |
| `parsed_cited_documents.json` | The parsed form of every cited document, for inspection |


## Project layout

```
app.py                  entry point (UI server or --run)
mapper/parsing.py       source parsing with exact line/character locations
mapper/company.py       company discovery, source scope, parse cache logic (via the store)
mapper/store.py         storage interface (Store) and its file implementation (FileStore)
mapper/search.py        term matching + BM25
mapper/semantic.py      semantic search and cross-language sentence matching
mapper/gates.py         the 7 gates
mapper/analysis.py      pipeline: elements, dimensions, explanations, questions, next steps
mapper/compare.py       version and language comparison
mapper/review.py        reviewer decisions and re-review detection
mapper/render.py        prepares data and renders the pages with Jinja2
mapper/templates/       page layout as HTML templates (report, duty tabs, comparison, legal duty, start, source)
mapper/static/          report.css, report.js, start.js (inlined, so each report.html is self-contained)
mapper/server.py        local web server (Python standard library)
config/duty_elements.json  law-level configuration (elements, terms, facets, questions)
companies/marenthal/company.json
tests/                  unit and integration tests, synthetic test company
```
