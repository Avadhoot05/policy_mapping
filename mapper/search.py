"""Candidate retrieval: term matching over natural units plus BM25 ranking (D-17, D-30, D-40).

BM25 only orders candidates for display. It never decides whether a passage covers a duty;
the gates and the reviewer do.
"""
import math

from .textutil import Term, tokens

K1 = 1.5
B = 0.75


class Index:
    def __init__(self, units):
        self.units = units
        self.toks = [tokens(u["text"]) for u in units]
        self.n = len(units)
        self.avg_len = (sum(len(t) for t in self.toks) / self.n) if self.n else 0.0

    def term_frequencies(self, term):
        return [term.count(t) for t in self.toks]

    def search(self, raw_terms):
        """Return [(unit_index, score, matched_terms)] for units matching any term, best first."""
        terms = [Term(t) for t in raw_terms]
        tf_table = [self.term_frequencies(t) for t in terms]
        scores = {}
        matched = {}
        for term, tfs in zip(terms, tf_table):
            df = sum(1 for x in tfs if x)
            if not df:
                continue
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(tfs):
                if not tf:
                    continue
                dl = len(self.toks[i])
                s = idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / self.avg_len))
                scores[i] = scores.get(i, 0.0) + s
                matched.setdefault(i, []).append(term.raw)
        return sorted(((i, scores[i], matched[i]) for i in scores), key=lambda x: (-x[1], x[0]))


def bm25_score(tf, df, n, dl, avg_len):
    """Single-term BM25 contribution (exposed for tests)."""
    idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
    return idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / avg_len))
