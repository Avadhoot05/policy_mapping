"""Tests: run with  python3 -m unittest discover -s tests -v   (from the project folder).

All runs happen in temporary company folders, so the real companies/ cache, runs and reviews
are never touched. The synthetic "Testfirma GmbH" fixture is a labelled test variant.
"""
import json
import math
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mapper import company as company_mod, parsing, review  # noqa: E402
from mapper.analysis import run_analysis  # noqa: E402
from mapper.company import Company, load_sources  # noqa: E402
from mapper.store import FileStore, Store  # noqa: E402
from mapper.search import Index, bm25_score  # noqa: E402
from mapper.textutil import Term, tokens  # noqa: E402

INPUTS = os.path.normpath(os.path.join(ROOT, "..", "COBACK_Marenthal_Inputs"))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "testco_input")
EN_V2 = "7b10774b-53cf-47cf-9d3e-1307061f33c0"
DE_V2 = "90daa5ae-2259-4edb-a856-5c3dc4c0e050"
DE_V11 = "1ecfcb5c-707a-43b9-a526-f448fbfa00e7"


def make_company(tmp, slug, cfg):
    folder = os.path.join(tmp, slug)
    os.makedirs(folder)
    with open(os.path.join(folder, "company.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return Company(folder)


def marenthal(tmp):
    return make_company(tmp, "marenthal", {
        "name": "Marenthal Chemie AG", "entity_id": "1764010d-db68-42e2-8aa2-db89242548ad",
        "entity_name": "Marenthal Chemie AG", "entity_codes": ["CMS-DE-01"], "snapshot_date": "2026-11-18",
        "input_dir": INPUTS})


def testco(tmp, input_dir=FIXTURE):
    return make_company(tmp, "testco", {
        "name": "Testfirma GmbH (SYNTHETIC TEST)", "entity_id": "e0000001-0000-0000-0000-000000000001",
        "entity_name": "Testfirma GmbH", "entity_codes": ["TST-DE-01"], "snapshot_date": "2026-11-18",
        "input_dir": input_dir})


def citations(result, buckets=("passages", "not_counted", "supporting", "supporting_scope_mismatch", "context")):
    return [c for du in result["duties"] for e in du["elements"] for b in buckets for c in e[b]]


def json_at(data, path):
    for key, idx in re.findall(r"\.([^.\[]+)|\[(\d+)\]", path):
        data = data[int(idx)] if idx else data[key]
    return data


def assert_citations_verbatim(test, docs, result):
    """Every cited quote is exactly the text at its stated location, in the file version that was parsed."""
    for c in citations(result):
        d = docs[c["source_id"]]
        test.assertEqual(d["sha256"], c["sha256"], c["uid"])
        loc = c["loc"]
        if "line_start" in loc:
            got = parsing.extract(d["lines"], loc)
        elif "json_path" in loc:
            got = json_at(d["data"], loc["json_path"])
        else:
            got = next(r for r in d["rows"] if r["id"] == loc["row_id"])[loc["field"]]
        test.assertEqual(got, c["quote"], c["uid"])


def assert_no_other_entity_used(test, result):
    for c in citations(result, ("passages", "supporting")):
        test.assertNotEqual(next(g["result"] for g in c["gates"] if g["gate"] == "1 entity"), "other_entity", c["uid"])


def element(result, duty, el):
    d = next(x for x in result["duties"] if x["duty_id"] == duty)
    return next(e for e in d["elements"] if e["id"] == el)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pm-test-")
        cls.m = marenthal(cls.tmp)
        cls.result, cls.docs = run_analysis(cls.m)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestParsing(Base):
    def test_line_numbers_match_editor(self):
        d = self.docs[EN_V2]
        self.assertEqual(d["lines"][0], "")  # PDF-derived files start with two blank lines
        self.assertTrue(d["lines"][21].startswith("Notfall- und Wiederanlaufübung der IT durchführen"))  # L22

    def test_every_unit_quote_is_exact(self):
        for d in self.docs.values():
            for u in d["units"]:
                if "line_start" in u["loc"]:
                    self.assertEqual(parsing.extract(d["lines"], u["loc"]), u["text"], u["uid"])

    def test_sentence_spanning_two_lines(self):
        u = next(u for u in self.docs[EN_V2]["units"] if u["loc"]["line_start"] == 22)
        self.assertEqual((u["loc"]["line_end"], u["loc"]["char_start"]), (23, 0))
        self.assertIn("\nProzessleitsystem) üben und Ergebnisse dokumentieren.", u["text"])

    def test_document_status_beats_policy_metadata(self):
        d = self.docs[DE_V11]["derived"]
        self.assertEqual(d["lifecycle"], "superseded")          # header L14 + version block L37
        self.assertEqual(self.docs[DE_V11]["policy_block"]["aktuelle_version"]["value"], "2.0")  # the trap
        self.assertTrue(any("describes the policy family" in n for n in d["notes"]))

    def test_register_and_evidence_record(self):
        reg = next(d for d in self.docs.values() if d["file"].endswith("REG_Internal_Controls_CMS-DE-01.txt"))
        row = next(r for r in reg["register"]["rows"] if r["line"] == 35)
        self.assertEqual(row["cells"]["Control"], "Offline-Datensicherung und Wiederherstellungstest")
        rec = next(d for d in self.docs.values() if d["file"].endswith("DMS-00001406_V000074_Nachweis.txt"))
        self.assertEqual(rec["record_fields"]["beschreibung"]["line_end"], 22)  # continuation line joined


class TestSearch(unittest.TestCase):
    def test_terms(self):
        toks = tokens("Notfall- und Wiederanlaufübung der IT; Offline-Datensicherung")
        self.assertEqual(Term("wiederanlauf*").count(toks), 1)        # prefix over a compound
        self.assertEqual(Term("*uebung*").count(toks), 1)             # umlaut folded, infix
        self.assertEqual(Term("*datensicherung*").count(toks), 1)
        self.assertEqual(Term("security incident*").count(tokens("A security incidents list")), 1)
        self.assertEqual(Term("restore*").count(toks), 0)

    def test_bm25_hand_computed(self):
        # 3 units; term in 1 unit, tf=2, dl=4, avg=4: idf=ln(1+(3-1+.5)/(1+.5)) ; tf part = 2*2.5/(2+1.5)
        expected = math.log(1 + 2.5 / 1.5) * (2 * 2.5) / (2 + 1.5)
        self.assertAlmostEqual(bm25_score(2, 1, 3, 4, 4), expected, places=9)

    def test_bm25_properties(self):
        units = [{"text": t} for t in ["backup backup server", "backup policy text here", "unrelated words only", "rare term"]]
        idx = Index(units)
        ranked = [i for i, _, _ in idx.search(["backup"])]
        self.assertEqual(ranked[0], 0)                                     # higher tf wins
        self.assertLess(bm25_score(10, 1, 4, 4, 4), 10 * bm25_score(1, 1, 4, 4, 4))  # saturation
        self.assertGreater(bm25_score(1, 1, 10, 4, 4), bm25_score(1, 5, 10, 4, 4))   # rare > common


class TestGatesAndResults(Base):
    def test_four_duties(self):
        self.assertEqual([d["duty_id"] for d in self.result["duties"]], ["04-P02-1", "04-P02-2", "04-P02-3", "04-P02-6"])

    def test_translation_only_not_counted(self):
        el = element(self.result, "04-P02-3", "recovery")
        self.assertEqual(el["policy_status"], "not_found")                # German master is authoritative
        self.assertIn("translation_only", el["flags"])
        c = next(c for c in el["not_counted"] if c["source_id"] == EN_V2)
        self.assertEqual(c["location"], "L22–23")
        self.assertIn("translation_only", c["qualifiers"])

    def test_kr017_scope_mismatch(self):
        el = element(self.result, "04-P02-3", "crisis_management")
        self.assertTrue(el["not_counted"])
        self.assertTrue(all(c["relation"] == "scope_mismatch" for c in el["not_counted"]))
        self.assertEqual(el["policy_status"], "not_found")

    def test_topic_only_cites_german_master(self):
        el = element(self.result, "04-P02-1", "security_concept")
        self.assertEqual(el["policy_status"], "topic_only")
        self.assertIn("DE master, L18–19", el["explanation"])

    def test_superseded_never_counted(self):
        for du in self.result["duties"]:
            for el in du["elements"]:
                self.assertFalse(any(c["doc"]["lifecycle"] == "superseded" for c in el["passages"]))

    def test_backup_control_is_evidence_with_overdue(self):
        el = element(self.result, "04-P02-3", "backup")
        c = next(c for c in el["supporting"] if c.get("cells", {}).get("Control") == "Offline-Datensicherung und Wiederherstellungstest")
        self.assertEqual(c["overdue"][0]["date"], "2026-01-21")

    def test_all_sources_parsed_and_citations_verbatim(self):
        self.assertEqual(self.result["cache"]["missing"], [])
        assert_citations_verbatim(self, self.docs, self.result)
        assert_no_other_entity_used(self, self.result)

    def test_one_current_version_per_policy_and_language(self):
        families = {}
        for d in self.docs.values():
            if d["kind"] == "policy":
                families.setdefault((d["derived"]["policy_no"], d["derived"]["language"]), []).append(d["derived"])
        for key, versions in families.items():
            self.assertEqual(sum(v["lifecycle"] == "current" for v in versions), 1, key)
            for v in versions:
                self.assertEqual(v["lifecycle"] == "superseded", bool(v["valid_until"]), (key, v["version"]))

    def test_version_comparison(self):
        ver = next(c for c in self.result["comparisons"] if c["kind"] == "version" and c["policy_no"] == "KR-009")
        self.assertFalse(ver["body_changed"])                         # v1.1 -> v2.0: same body text


class TestMultiCompany(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pm-iso-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_isolation_and_covered_path(self):
        m, t = marenthal(self.tmp), testco(self.tmp)
        rm, dm = run_analysis(m)
        rt, dt = run_analysis(t)
        ids_m, ids_t = set(dm), set(dt)
        structured = {"company_profile.json", "legal_entities.csv", "twin_questions.csv"}
        self.assertFalse((ids_m & ids_t) - structured)                    # no shared documents
        self.assertNotIn("Marenthal", json.dumps(rt, ensure_ascii=False))  # no Marenthal data in the other report
        self.assertNotEqual(m.store.cache_dir, t.store.cache_dir)
        el = element(rt, "04-P02-3", "backup")
        self.assertEqual(el["policy_status"], "covered")                  # positive path works
        self.assertNotIn("No current", el["explanation"])                 # no contradicting sentence
        self.assertIsNone(el["next_step"])
        excluded = [c["file"] for c in el["excluded"]]
        self.assertTrue(any("TST-FR-01" in f for f in excluded))         # other entity dropped (gate 1)
        self.assertFalse(any("TST-FR-01" in c["file"] for c in el["supporting"]))
        self.assertEqual(element(rt, "04-P02-3", "backup")["effectiveness"]["failed_runs"], 1)
        assert_citations_verbatim(self, dt, rt)
        assert_no_other_entity_used(self, rt)
        # sentence-level scope: IT rule inside an EHS policy counts, flagged; evacuation drill does not
        rec = element(rt, "04-P02-3", "recovery")
        self.assertEqual(rec["policy_status"], "partial")
        self.assertNotIn("No current", rec["explanation"])
        self.assertTrue(rec["next_step"]["text"].startswith("Complete the rule in"))
        self.assertIn("off_topic_policy", rec["flags"])
        self.assertTrue(all("off_topic_policy" in c["qualifiers"] for c in rec["passages"]))
        # incident-reporting rule worded without any search term: found only by meaning, then counted by the gates
        det = element(rt, "04-P02-2", "detection_reporting")
        self.assertEqual(det["policy_status"], "covered")
        self.assertEqual([(c["found_by"], c["location"]) for c in det["passages"]], [("semantic", "L22")])
        test_el = element(rt, "04-P02-2", "incident_test")
        evac = [c for c in test_el["not_counted"] if c["quote"].startswith("Evakuierungsübung")]
        self.assertTrue(evac and all(c["relation"] == "scope_mismatch" for c in evac))


class TestStoreContract(unittest.TestCase):
    """Behaviour every Store implementation must have (FileStore today; a database store would reuse this)."""

    def make_store(self, tmp):
        return FileStore(tmp, "contract")

    def test_contract(self):
        tmp = tempfile.mkdtemp(prefix="pm-store-")
        try:
            st = self.make_store(tmp)
            self.assertIsInstance(st, Store)
            self.assertEqual((st.load_manifest(), st.load_parsed("x"), st.load_decisions(), st.list_runs()), ({}, None, [], []))
            st.save_manifest({"a": {"sha256": "1"}})
            st.save_parsed("company_profile.json", {"k": "ä"})
            self.assertEqual(st.load_manifest(), {"a": {"sha256": "1"}})
            self.assertEqual(st.load_parsed("company_profile.json"), {"k": "ä"})
            st.save_run("20261120T000000000000Z", {"report.html": "<p>r</p>", "mapping_result.json": '{"run_id": "x"}'})
            self.assertEqual(st.list_runs(), ["20261120T000000000000Z"])
            self.assertEqual(st.load_result("20261120T000000000000Z"), {"run_id": "x"})
            self.assertIsNone(st.read_run_file("../etc", "report.html"))          # invalid run id
            self.assertIsNone(st.read_run_file("20261120T000000000000Z", "x.py"))  # unknown file name
            with self.assertRaises(ValueError):
                st.save_run("bad", {"report.html": ""})
            st.save_embeddings("m/x", {"k": "AAAA"})
            self.assertEqual(st.load_embeddings("m/x"), {"k": "AAAA"})
            self.assertEqual(st.load_embeddings("other"), {})
            st.append_decision({"d": 1})
            st.append_decision({"d": 2})
            self.assertEqual([d["d"] for d in st.load_decisions()], [1, 2])     # append-only, ordered
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSemantic(Base):
    """Semantic search runs next to keyword search: it may propose more passages, but the gates decide."""

    def test_embeddings_cached(self):
        self.assertGreater(self.result["search"]["embedded_now"], 0)
        again, _ = run_analysis(self.m)                               # embeddings now come from the cache
        self.assertEqual(again["search"]["embedded_now"], 0)

    def test_meaning_only_matches_reported_only_when_counted(self):
        for du in self.result["duties"]:
            for el in du["elements"]:
                for c in el["not_counted"] + el["supporting"] + el["context"] + el["excluded"]:
                    self.assertNotEqual(c.get("found_by"), "semantic", c["uid"])

    def test_language_versions_matched_by_meaning(self):
        lang = next(c for c in self.result["comparisons"] if c["kind"] == "language" and c["policy_no"] == "KR-009")
        by = lambda st, side: sorted(r[side]["loc"]["line_start"] for r in lang["rows"] if r["status"] == st)
        self.assertEqual(by("likely_same", "master"), [18, 19, 20])  # the three purpose/scope sentences (DE L18-20)
        self.assertEqual(by("only_translation", "translation"), [22, 24])  # recovery rule + rack inspection
        self.assertEqual(by("only_master", "master"), [22])          # "Dieses Dokument wird ... verbindlich"
        self.assertTrue(all(r["similarity"] >= lang["cutoff"] for r in lang["rows"] if r["status"] == "likely_same"))
        # whole German sentences in the EN version are flagged; no master sentence is
        wrong = [r["translation"]["loc"]["line_start"] for r in lang["rows"]
                 if r["translation"] and r["translation"]["wrong_language"] == "DE"]
        self.assertEqual(wrong, [22, 24])
        self.assertFalse(any(r["master"]["wrong_language"] for r in lang["rows"] if r["master"]))
        self.assertEqual(lang["wrong_language"], 2)

    def test_sentence_language_needs_a_whole_sentence(self):
        from mapper.compare import sentence_language
        detect = lambda t: sentence_language(t, min_words=6, min_confidence=0.9)
        self.assertEqual(detect("Die IT-Sicherheit wird jährlich durch den ISB geprüft."), "de")
        self.assertEqual(detect("The officer reviews the IT backup plan every year."), "en")
        # a quoted German term in an English sentence, or a short phrase, is not a German sentence
        self.assertEqual(detect("This policy sets binding rules on “Informationssicherheit” for Marenthal Chemie AG."), "en")
        self.assertIsNone(detect("Wiederherstellung kritischer Systeme"))


class TestCache(unittest.TestCase):
    def test_reuse_and_dirty(self):
        tmp = tempfile.mkdtemp(prefix="pm-cache-")
        try:
            inp = os.path.join(tmp, "input")
            shutil.copytree(FIXTURE, inp)
            t = testco(tmp, inp)
            _, r1, _, _ = load_sources(t)
            self.assertEqual(len(r1["parsed"]), 8)
            _, r2, _, _ = load_sources(t)
            self.assertEqual((len(r2["reused"]), len(r2["parsed"])), (8, 0))
            p = os.path.join(inp, "company_data", "documents", "REG_Risk_Register_TST-DE-01.txt")
            with open(p, "a", encoding="utf-8") as f:
                f.write("| Neues Risiko | Informationssicherheit | - | x | 1 | 1 | 1 | offen | - | - |\n")
            _, r3, _, _ = load_sources(t)
            self.assertEqual([d["file"] for d in r3["dirty"]], ["documents/REG_Risk_Register_TST-DE-01.txt"])
            self.assertEqual(r3["dirty"][0]["reason"], "content changed")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestReviewAndServer(unittest.TestCase):
    def test_review_stale_and_server(self):
        tmp = tempfile.mkdtemp(prefix="pm-srv-")
        old = company_mod.COMPANIES_DIR
        company_mod.COMPANIES_DIR = tmp
        try:
            t = testco(tmp)
            from mapper import server
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            port = httpd.server_address[1]
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{port}"
            self.assertIn("Testfirma", urllib.request.urlopen(base + "/").read().decode())
            req = urllib.request.Request(base + "/api/c/testco/runs", method="POST")
            info = json.loads(urllib.request.urlopen(req).read())
            html = urllib.request.urlopen(base + info["report_url"]).read().decode()
            for tab in ('data-main="overview"', 'data-main="duties"', 'data-main="comparison"'):
                self.assertIn(tab, html)
            self.assertIn('data-key="04-P02-3/backup"', html)
            legal = urllib.request.urlopen(base + info["report_url"].replace("report.html", "legal/04-P02-3")).read().decode()
            self.assertIn("Betriebsaufrechterhaltung", legal)
            body = json.dumps({"duty_id": "04-P02-3", "element_id": "backup", "decision": "confirmed",
                               "reviewer": "Test", "comment": "ok"}).encode()
            req = urllib.request.Request(f"{base}/api/c/testco/runs/{info['run_id']}/reviews", data=body,
                                         method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req)
            got = json.loads(urllib.request.urlopen(f"{base}/api/c/testco/runs/{info['run_id']}/reviews").read())
            self.assertFalse(got["04-P02-3/backup"]["current"]["stale"])
            # a different proposal fingerprint marks the decision for re-review
            cur, _ = review.current(review.load(t), "04-P02-3", "backup", "different")
            self.assertTrue(cur["stale"])
            # unknown company / traversal is rejected
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/c/..%2Fmarenthal/source/x")
            httpd.shutdown()
            httpd.server_close()
        finally:
            company_mod.COMPANIES_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
