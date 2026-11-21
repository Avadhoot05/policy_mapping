"""Entry point.

  python3 app.py                 start the local UI at http://127.0.0.1:8000/
  python3 app.py --port 8080     use another port
  python3 app.py --run marenthal run one analysis from the command line (no server) and print the report path
  python3 app.py --check         check that every company's input files and the legal input are in place
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mapper import company as company_mod  # noqa: E402
from mapper.company import STRUCTURED, discover_companies, get_company, load_app_config  # noqa: E402
from mapper.server import execute_run, serve  # noqa: E402


def check_inputs():
    """Return a list of problems (empty if everything needed to run is in place)."""
    problems = []
    companies = discover_companies()
    if not companies:
        problems.append("No company found in companies/ (each needs a company.json).")
    for c in companies:
        if not os.path.exists(c.duties_file):
            problems.append(f"[{c.slug}] legal input not found: {c.duties_file}")
        if not os.path.isdir(c.data_dir):
            problems.append(f"[{c.slug}] company data folder not found: {c.data_dir}")
            continue
        rows, _, index = c.source_list()
        if not index:
            problems.append(f"[{c.slug}] documents_index.csv missing or empty in {c.data_dir}")
        missing = [r["file"] for r in rows if not os.path.exists(os.path.join(c.data_dir, r["file"]))]
        missing += [n for n in STRUCTURED if not os.path.exists(os.path.join(c.data_dir, n))]
        if missing:
            problems.append(f"[{c.slug}] {len(missing)} source file(s) missing, e.g. {missing[0]}")
    return problems


def main():
    cfg = load_app_config()
    ap = argparse.ArgumentParser(description="NIS2 duty-to-policy mapping")
    ap.add_argument("--host", default=cfg.get("host", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=cfg.get("port", 8000))
    ap.add_argument("--run", metavar="COMPANY", help="run one analysis for companies/<COMPANY> and exit")
    ap.add_argument("--check", action="store_true", help="check the input files and exit")
    ap.add_argument("--search-mode", choices=["keyword", "hybrid"], default=cfg.get("search_mode", "keyword"),
                    help="keyword (default, standard library) or hybrid (keyword + semantic; needs ./run.sh --semantic)")
    args = ap.parse_args()
    company_mod.OVERRIDES["search_mode"] = args.search_mode
    if args.check:
        problems = check_inputs()
        for p in problems:
            print("  ✗", p)
        if problems:
            sys.exit("Input check failed. Place COBACK_Marenthal_Inputs next to this folder, or edit the paths in "
                     "companies/<slug>/company.json (input_dir) and config/app.json (legal_input).")
        print("Input check passed: " + ", ".join(c.slug for c in discover_companies()))
        return
    if args.run:
        comp = get_company(args.run)
        if not comp:
            sys.exit(f"Unknown company '{args.run}' (expected companies/{args.run}/company.json)")
        info = execute_run(comp)
        print(f"Analysis finished in {info['seconds']} s")
        print("Report:", os.path.join(comp.runs_dir, info["run_id"], "report.html"))
        return
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
