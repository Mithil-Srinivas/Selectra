"""Spell-tolerant detection of catalogue brand and product-line names in shopper text.

Shoppers misspell and split invented names ("krida" -> Kridaa, "ripple flex" -> RippleFlex). We fuzzy-match each
word and each adjacent word pair against the brand / line-name vocabulary. The result is a list of *hints*
handed to the LLM; the text itself is not rewritten, so a wrong hint can be ignored rather than silently applied.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz, process

# Hinglish / question filler that must never be "corrected" into a name.
STOPWORDS = set("""ka ki ke hai hain kya kitne kitna kitni price rate stock me mein dikhao chahiye wala wali wale with
and pack set ya or the for kaunsa konsa sabse sasta mehenga""".split())


@dataclass(frozen=True)
class NameHint:
    text: str        # as the shopper wrote it
    canonical: str   # catalogue spelling
    kind: Literal["brand", "line"]
    score: float


class NameMatcher:
    def __init__(self, brands: list[str], line_names: list[str], pair_cutoff: float = 85, word_cutoff: float = 80):
        self.vocab = {b.lower(): (b, "brand") for b in brands}
        self.vocab.update({l.lower(): (l, "line") for l in line_names if l.lower() not in self.vocab})
        self.keys = list(self.vocab)
        self.pair_cutoff, self.word_cutoff = pair_cutoff, word_cutoff

    def _match(self, s: str, cutoff: float):
        return process.extractOne(s, self.keys, scorer=fuzz.ratio, score_cutoff=cutoff)

    def find(self, text: str) -> list[NameHint]:
        toks = re.findall(r"[a-z0-9]+", text.lower())
        hints: list[NameHint] = []
        i = 0
        while i < len(toks):
            a = toks[i]
            b = toks[i + 1] if i + 1 < len(toks) else None
            if b and a not in STOPWORDS and b not in STOPWORDS and (m := self._match(a + b, self.pair_cutoff)):
                canon, kind = self.vocab[m[0]]
                hints.append(NameHint(f"{a} {b}", canon, kind, m[1]))
                i += 2
                continue
            if len(a) >= 4 and a not in STOPWORDS and (m := self._match(a, self.word_cutoff)):
                canon, kind = self.vocab[m[0]]
                hints.append(NameHint(a, canon, kind, m[1]))
            i += 1
        return hints
