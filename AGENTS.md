# AGENTS.md

## What this is
A local prototype that maps four NIS2 duties (04-P02-1, -2, -3, -6) to exact passages in Marenthal Chemie AG's
internal policies. For each duty element it reports Covered / Partial / Topic only / No supporting passage found,
with document ID, file, quote and line, plus the policy section to add or complete. A reviewer confirms or rejects
each proposal in a local web UI.

## Setup and run
Python 3.10+, Linux or macOS. The COBACK input package must sit next to this folder:
```
<parent>/coback_policy_mapping/      ← this repo
<parent>/COBACK_Marenthal_Inputs/    ← input data (not in the repo)
```
```bash
./setup.sh                    # creates .venv, installs requirements.txt (jinja2), checks inputs
./start.sh                    # web UI at http://127.0.0.1:8000/  (--port N to change)
./test.sh                     # unit + integration tests, all must pass
.venv/bin/python app.py --run marenthal   # one analysis without the UI; prints the report path
.venv/bin/python app.py --check           # input check only
```
Optional semantic search: `./setup.sh --semantic` (≈1 GB download), then `./start.sh --semantic`.

## Layout
- `mapper/` pipeline: `parsing` → `search` (BM25) / `semantic` (optional) → `gates` (7 checks) → `analysis` →
  `render` (Jinja2, `templates/`, `static/`) · `server` (stdlib HTTP) · `store` (all persistence) · `review`
- `config/duty_elements.json` duty elements, search terms, required facets (law-level, shared by all companies)
- `config/app.json` legal input path, search mode, semantic settings
- `companies/<slug>/company.json` one folder per company; `cache/`, `runs/`, `review/` are generated (gitignored)
- `tests/` tests and a synthetic test company (`tests/fixtures/testco_input/`)

## Rules
- Never modify files in `COBACK_Marenthal_Inputs/`. Use a labelled test variant instead.
- Search scope: the 15 files in `document_starters.csv` plus `company_profile.json`, `legal_entities.csv`,
  `twin_questions.csv`.
- German master version is authoritative; text found only in a translation is flagged, not counted.
- Register rows are implementation records, never policy coverage.
- All persistence goes through `mapper/store.py`; never write paths directly.
- Run `./test.sh` after every change.
