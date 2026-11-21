"""Local web UI: Python standard library only, bound to localhost.

Routes
  GET  /                                        start page (companies, Start analysis, earlier runs)
  POST /api/c/<slug>/runs                       run the analysis, returns the report link
  GET  /c/<slug>/runs/<run>/<file>              report.html, mapping_result.json, parsed_cited_documents.json
  GET  /api/c/<slug>/runs/<run>/reviews         reviewer decisions for that run (with re-review flags)
  POST /api/c/<slug>/runs/<run>/reviews         save a reviewer decision
  GET  /c/<slug>/runs/<run>/legal/<duty_id>     the original legal analysis of one duty
  GET  /c/<slug>/source/<source_id>?ls=&le=     source viewer with the cited lines highlighted
"""
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import review
from .analysis import run_analysis, save_run
from .company import discover_companies, get_company
from .render import render_legal_duty, render_report, render_source, render_start

CONTENT_TYPES = {"report.html": "text/html; charset=utf-8", "mapping_result.json": "application/json",
                 "parsed_cited_documents.json": "application/json"}
_run_locks = {}
_locks_guard = threading.Lock()


def _company_lock(slug):
    with _locks_guard:
        return _run_locks.setdefault(slug, threading.Lock())


def run_time(run_id):
    """A run id is its start time in UTC (e.g. 20261121T193115721023Z); shown in local time, or as is if not."""
    try:
        t = datetime.strptime(run_id, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return run_id
    return t.strftime("%d %b %Y, %H:%M:%S")


def list_runs(company):
    return [{"run_id": r, "time": run_time(r), "url": f"/c/{company.slug}/runs/{r}/report.html"}
            for r in company.store.list_runs()]


def execute_run(company):
    with _company_lock(company.slug):
        t0 = time.time()
        result, docs = run_analysis(company)
        save_run(company, result, docs, render_report(result))
        return {"run_id": result["run_id"], "report_url": f"/c/{company.slug}/runs/{result['run_id']}/report.html",
                "seconds": round(time.time() - t0, 2)}


def _load_run(company, run_id):
    return company.store.load_result(run_id)


def reviews_for_run(company, result):
    decisions = review.load(company)
    out = {}
    for du in result["duties"]:
        for el in du.get("elements", []):
            cur, hist = review.current(decisions, du["duty_id"], el["id"], el["fingerprint"])
            out[f"{du['duty_id']}/{el['id']}"] = {"current": cur, "history": hist}
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "PolicyMapping/1.0"

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _parts(self):
        u = urlparse(self.path)
        return [unquote(p) for p in u.path.split("/") if p], parse_qs(u.query)

    def do_GET(self):
        parts, q = self._parts()
        try:
            if not parts:
                info = [{"slug": c.slug, "name": c.name, "entity_name": c.entity_name, "entity_codes": c.entity_codes,
                         "snapshot_date": c.snapshot_date, "input_dir": c.input_dir, "runs": list_runs(c)}
                        for c in discover_companies()]
                return self._send(200, render_start(info))
            if len(parts) == 5 and parts[0] == "c" and parts[2] == "runs" and parts[4] in CONTENT_TYPES:
                comp = get_company(parts[1])
                data = comp.store.read_run_file(parts[3], parts[4]) if comp else None
                if data is not None:
                    return self._send(200, data, CONTENT_TYPES[parts[4]])
            if len(parts) == 6 and parts[0] == "c" and parts[2] == "runs" and parts[4] == "legal":
                comp = get_company(parts[1])
                res = _load_run(comp, parts[3]) if comp else None
                du = next((d for d in res["duties"] if d["duty_id"] == parts[5] and "elements" in d), None) if res else None
                if du:
                    return self._send(200, render_legal_duty(res, du))
            if len(parts) == 6 and parts[:1] == ["api"] and parts[1] == "c" and parts[3] == "runs" and parts[5] == "reviews":
                comp = get_company(parts[2])
                res = _load_run(comp, parts[4]) if comp else None
                if res:
                    return self._json(200, reviews_for_run(comp, res))
            if len(parts) == 4 and parts[0] == "c" and parts[2] == "source":
                comp = get_company(parts[1])
                if comp:
                    doc = _cached_doc(comp, parts[3])
                    if doc:
                        num = lambda k: int(q[k][0]) if k in q and q[k][0].isdigit() else None
                        return self._send(200, render_source(comp.name, doc, num("ls"), num("le"),
                                                             q.get("path", [None])[0], q.get("row", [None])[0],
                                                             q.get("field", [None])[0]))
            self._send(404, "<h1>Not found</h1>")
        except Exception as ex:  # keep the server alive, report the error
            self._send(500, f"<h1>Error</h1><pre>{ex}</pre>")

    def do_POST(self):
        parts, _ = self._parts()
        try:
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "c" and parts[3] == "runs":
                comp = get_company(parts[2])
                if not comp:
                    return self._json(404, {"error": "unknown company"})
                return self._json(200, execute_run(comp))
            if len(parts) == 6 and parts[0] == "api" and parts[1] == "c" and parts[3] == "runs" and parts[5] == "reviews":
                comp = get_company(parts[2])
                res = _load_run(comp, parts[4]) if comp else None
                if not res:
                    return self._json(404, {"error": "unknown company or run"})
                n = int(self.headers.get("Content-Length", "0"))
                if n > 20000:
                    return self._json(413, {"error": "request too large"})
                payload = json.loads(self.rfile.read(n) or b"{}")
                try:
                    rec = review.add(comp, res, payload)
                except ValueError as ve:
                    return self._json(400, {"error": str(ve)})
                return self._json(200, rec)
            self._json(404, {"error": "not found"})
        except Exception as ex:
            self._json(500, {"error": str(ex)})


def _cached_doc(company, source_id):
    """Only documents parsed for this company (listed in its own manifest) can be viewed."""
    if source_id not in company.store.load_manifest():
        return None
    return company.store.load_parsed(source_id)


def serve(host="127.0.0.1", port=8000):
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Policy mapping UI running at http://{host}:{port}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
