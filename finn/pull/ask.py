"""Free-form questions over a company's own documents. Retrieval is plain TF-IDF -
the corpus per company is a few hundred chunks, so a vector DB would be ceremony."""

import math
import re
from collections import Counter

from .. import llm

STOP = set("the a an and or of to in for on at by with from is are was were be been this that it as we our "
           "you your they their has have had will would can could should do does did not no yes so if "
           "than then there what which who how when where why about into over under also more less".split())

ASK_PROMPT = """Answer the question about {company} using ONLY the excerpts below from its own annual report
and earnings calls. Be concise (max 120 words) and specific. Cite excerpts inline like [2].
If the excerpts don't answer it, say so plainly - do not guess.

QUESTION: {q}

EXCERPTS:
{ctx}"""


def _tokens(s):
    return [w for w in re.findall(r"[a-z0-9%]+", s.lower()) if w not in STOP and len(w) > 1]


def rank(chunks, question, k=8):
    docs = [Counter(_tokens(c["text"])) for c in chunks]
    df = Counter(w for d in docs for w in d)
    n = len(docs)
    q = _tokens(question)
    scored = []
    for i, d in enumerate(docs):
        length = sum(d.values()) or 1
        s = sum((d[w] / length) * math.log(1 + n / (1 + df[w])) for w in q if w in d)
        scored.append((s, i))
    scored.sort(reverse=True)
    return [chunks[i] for s, i in scored[:k] if s > 0]


def answer(company, chunks, question):
    top = rank(chunks, question)
    if not top:
        return {"answer": "Nothing in the annual report or recent calls addresses that.", "sources": []}
    ctx = "\n\n".join(f"[{i + 1}] ({c['source']}{', p.' + c['page'] if c.get('page') else ''})\n{c['text']}"
                      for i, c in enumerate(top))
    text = llm.call(ASK_PROMPT.format(company=company, q=question, ctx=ctx), task="ask")
    return {"answer": text.strip(),
            "sources": [{"n": i + 1, "source": c["source"], "page": c.get("page")} for i, c in enumerate(top)]}
