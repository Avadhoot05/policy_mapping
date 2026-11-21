"""Text normalisation and term matching.

The normalised text is used for search only and is never cited. Citations always use the raw lines.
"""
import re
import unicodedata

_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    """Lower-case, NFC, fold German umlauts (so 'ue' matches 'ü'), unify dashes and whitespace."""
    t = unicodedata.normalize("NFC", text).lower().translate(_FOLD)
    t = t.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> list:
    return _TOKEN.findall(normalize(text))


class Term:
    """A search term.

    'foo*' matches tokens starting with foo; '*foo*' matches tokens containing foo;
    'foo bar' or 'foo-bar' matches the phrase; otherwise the exact token is matched.
    """

    def __init__(self, raw: str):
        self.raw = raw
        n = normalize(raw)
        self.infix = n.startswith("*") and n.endswith("*") and len(n) > 2
        self.prefix = not self.infix and n.endswith("*")
        core = n.strip("*")
        self.phrase = bool(re.search(r"[\s\-/]", core))
        self.core = core
        self.phrase_tokens = _TOKEN.findall(core) if self.phrase else None

    def count(self, toks: list) -> int:
        """How often the term occurs in a unit (term frequency)."""
        if self.phrase:
            pt = self.phrase_tokens
            n = len(pt)
            hits = 0
            for i in range(len(toks) - n + 1):
                window = toks[i:i + n]
                if window[:-1] == pt[:-1] and (window[-1] == pt[-1] or (self.prefix and window[-1].startswith(pt[-1]))):
                    hits += 1
            return hits
        if self.infix:
            return sum(1 for t in toks if self.core in t)
        if self.prefix:
            return sum(1 for t in toks if t.startswith(self.core))
        return sum(1 for t in toks if t == self.core)
