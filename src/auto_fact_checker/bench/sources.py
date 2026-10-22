"""Source passages about AI research for the Exp08 error-injection benchmark: Wikipedia leads and arXiv abstracts.

Local: download a Wikipedia article's lead section as plain text (MediaWiki API `prop=extracts&exintro&explaintext`)
or an arXiv abstract (arXiv API Atom feed), normalise whitespace and trim to whole sentences under a word budget.
Global context: bench/ai_errors.py:build() turns these passages into the frozen benchmark
benchmarks/ai_errors_v1/dataset.jsonl. APIs: https://www.mediawiki.org/wiki/Extension:TextExtracts ,
https://info.arxiv.org/help/api/user-manual.html ; Wikipedia text is CC BY-SA 4.0; arXiv dedicates its metadata to
CC0 1.0 (https://info.arxiv.org/help/license/index.html#metadata-license). Abstract is explicitly a metadata field
(https://info.arxiv.org/help/prep.html); each item retains its URL for the separate full-paper licence. API terms ask for >= 3 s between
requests (https://info.arxiv.org/help/api/tou.html), hence ARXIV_DELAY_S.
"""

import json
import re
import time
import urllib.parse
import urllib.request

UA = "auto-fact-checker/0.1 (research benchmark; https://github.com/BurnyCoder/auto-fact-checker)"  # Wikimedia UA policy
ARXIV_DELAY_S = 3  # arXiv API terms: one connection, >= 3 s between requests
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")  # split after . ! ? followed by an uppercase/digit start


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT.split(" ".join(text.split())) if s.strip()]


def trim_sentences(text: str, max_words: int = 180, min_sentences: int = 3) -> str:
    """Whole sentences from the start until the word budget would be exceeded (at least min_sentences)."""
    out, words = [], 0
    for s in split_sentences(text):
        n = len(s.split())
        if out and len(out) >= min_sentences and words + n > max_words:
            break
        out.append(s)
        words += n
    return " ".join(out)


def fetch_wikipedia_lead(title: str) -> dict:
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1, "titles": title,
         "format": "json"})
    page = next(iter(json.loads(_get(url))["query"]["pages"].values()))
    return {"source": "wikipedia", "title": page["title"], "text": " ".join(page["extract"].split()),
            "url": "https://en.wikipedia.org/wiki/" + page["title"].replace(" ", "_"), "license": "CC BY-SA 4.0"}


def fetch_arxiv_abstract(arxiv_id: str) -> dict:
    time.sleep(ARXIV_DELAY_S)
    xml = _get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}")
    title, summary = re.search(r"<entry>.*?<title>(.*?)</title>.*?<summary>(.*?)</summary>", xml, re.S).groups()
    return {"source": "arxiv", "title": " ".join(title.split()), "text": " ".join(summary.split()),
            "url": f"https://arxiv.org/abs/{arxiv_id}", "license": "arXiv metadata (CC0 1.0); paper licence at url"}
