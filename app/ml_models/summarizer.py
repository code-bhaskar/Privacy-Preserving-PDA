import re
from collections import Counter

_STOPWORDS = set("""
a an the and or but if while of to in on at for with without from by is are was were
be been being do does did have has had i you he she it we they me my your his her our
their this that these those as so than then too very can will just not no yes about
""".split())


class LocalSummarizer:
    """
    Extractive frequency-based summarizer.
    Deliberately local + dependency-free: no text ever crosses a network
    boundary, satisfying FR-10 by construction rather than by policy.
    """

    def summarize(self, texts: list[str], max_sentences: int = 3) -> str:
        blob = " ".join(t.strip() for t in texts if t and t.strip())
        if not blob:
            return ""

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", blob) if s.strip()]
        if len(sentences) <= max_sentences:
            return " ".join(sentences)

        words = [w.lower() for w in re.findall(r"[A-Za-z']+", blob)]
        freq = Counter(w for w in words if w not in _STOPWORDS and len(w) > 2)
        if not freq:
            return " ".join(sentences[:max_sentences])
        peak = max(freq.values())

        scored = []
        for pos, s in enumerate(sentences):
            toks = [w.lower() for w in re.findall(r"[A-Za-z']+", s)]
            if not toks:
                continue
            score = sum(freq.get(w, 0) / peak for w in toks) / (len(toks) ** 0.5)
            score *= 1.0 + (0.15 if pos == 0 else 0.0)   # mild lead bias
            scored.append((score, pos, s))

        top = sorted(scored, key=lambda x: -x[0])[:max_sentences]
        return " ".join(s for _, _, s in sorted(top, key=lambda x: x[1]))


local_summarizer = LocalSummarizer()
