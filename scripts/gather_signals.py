#!/usr/bin/env python3
"""
Daily signal gatherer for K Platform intelligence.
Sources: Arxiv, HuggingFace Daily Papers, RSS feeds, PubMed, Brave Search.
Synthesizes with Claude (claude-opus-4-7) into a structured PM briefing.
"""

import os
import sys
import json
import argparse
import datetime
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus

import requests
import feedparser
import anthropic

# ── CONFIG ────────────────────────────────────────────────────────────────────
TODAY = datetime.date.today().isoformat()
RUN_SLOT = os.environ.get("RUN_SLOT", "morning")

REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_FILE = REPORT_DIR / f"{TODAY}.md"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

# ── ARXIV ─────────────────────────────────────────────────────────────────────
ARXIV_QUERIES = [
    "agentic AI healthcare",
    "multimodal biology foundation model",
    "drug discovery large language model",
    "spatial transcriptomics deep learning",
    "LLM benchmark biomedical",
]
ARXIV_MAX_RESULTS = 5  # per query

# ── RSS FEEDS ─────────────────────────────────────────────────────────────────
RSS_FEEDS = {
    "Anthropic Blog": "https://www.anthropic.com/rss.xml",
    "OpenAI Blog": "https://openai.com/blog/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Nature Biotechnology": "https://www.nature.com/nbt.rss",
    "Nature Methods": "https://www.nature.com/nmeth.rss",
    "STAT News": "https://www.statnews.com/feed/",
    "Fierce Healthcare": "https://www.fiercehealthcare.com/rss/xml",
    "Drug Discovery News": "https://www.drugdiscoverynews.com/rss",
}
RSS_MAX_AGE_DAYS = 3

# ── PUBMED ────────────────────────────────────────────────────────────────────
PUBMED_QUERIES = [
    "artificial intelligence clinical trial",
    "large language model pharmaceutical",
    "foundation model pathology",
]
PUBMED_MAX_RESULTS = 5

# ── BRAVE SEARCH ──────────────────────────────────────────────────────────────
BRAVE_SEARCH_QUERIES = [
    "generative AI healthcare pharma 2026",
    "Owkin AI drug discovery",
    "AI pathology clinical deployment",
]
BRAVE_MAX_RESULTS = 5


# ── GATHERERS ─────────────────────────────────────────────────────────────────

def gather_arxiv() -> list[dict]:
    """Fetch recent papers from Arxiv."""
    results = []
    base_url = "http://export.arxiv.org/api/query"

    for query in ARXIV_QUERIES:
        try:
            params = {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": ARXIV_MAX_RESULTS,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            resp = requests.get(base_url, params=params, timeout=15)
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")[:300]
                link = entry.find("atom:id", ns).text.strip()
                published = entry.find("atom:published", ns).text[:10]

                results.append({
                    "source": "Arxiv",
                    "query": query,
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "date": published,
                })

            time.sleep(1)  # be polite to Arxiv API
        except Exception as e:
            print(f"[ARXIV] Error for query '{query}': {e}")

    print(f"[ARXIV] Gathered {len(results)} papers")
    return results


def gather_huggingface() -> list[dict]:
    """Fetch HuggingFace daily papers, filtered for healthcare/bio relevance."""
    results = []
    bio_keywords = [
        "health", "medical", "clinical", "biomedical", "pathology", "drug",
        "pharma", "genomic", "protein", "molecule", "biology", "cancer",
        "diagnosis", "radiology", "surgery", "patient", "hospital",
        "multimodal", "foundation model", "agent", "benchmark",
    ]

    try:
        resp = requests.get("https://huggingface.co/api/daily_papers", timeout=15)
        resp.raise_for_status()
        papers = resp.json()

        for paper in papers[:30]:  # check top 30
            title = paper.get("title", "")
            summary = paper.get("paper", {}).get("summary", "")[:300]
            paper_id = paper.get("paper", {}).get("id", "")

            text_lower = (title + " " + summary).lower()
            if any(kw in text_lower for kw in bio_keywords):
                results.append({
                    "source": "HuggingFace Daily Papers",
                    "title": title,
                    "summary": summary,
                    "url": f"https://huggingface.co/papers/{paper_id}" if paper_id else "",
                    "date": paper.get("publishedAt", TODAY)[:10],
                })

    except Exception as e:
        print(f"[HF] Error: {e}")

    print(f"[HF] Gathered {len(results)} relevant papers")
    return results


def gather_rss() -> list[dict]:
    """Fetch recent entries from RSS feeds."""
    results = []
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=RSS_MAX_AGE_DAYS)

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_dt = datetime.datetime(*published[:6], tzinfo=datetime.timezone.utc)
                    if pub_dt < cutoff:
                        continue
                    date_str = pub_dt.strftime("%Y-%m-%d")
                else:
                    date_str = TODAY

                title = entry.get("title", "Untitled")
                summary = entry.get("summary", "")[:300]
                link = entry.get("link", "")

                results.append({
                    "source": f"RSS: {name}",
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "date": date_str,
                })
        except Exception as e:
            print(f"[RSS] Error for '{name}': {e}")

    print(f"[RSS] Gathered {len(results)} entries")
    return results


def gather_pubmed() -> list[dict]:
    """Fetch recent PubMed articles."""
    results = []
    base_search = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    base_fetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    for query in PUBMED_QUERIES:
        try:
            search_resp = requests.get(base_search, params={
                "db": "pubmed",
                "term": f"{query} AND (\"last 7 days\"[dp])",
                "retmax": PUBMED_MAX_RESULTS,
                "retmode": "json",
                "sort": "date",
            }, timeout=15)
            search_resp.raise_for_status()
            ids = search_resp.json().get("esearchresult", {}).get("idlist", [])

            if not ids:
                continue

            time.sleep(0.4)  # respect PubMed rate limit (3 req/sec unauthenticated)

            fetch_resp = requests.get(base_fetch, params={
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json",
            }, timeout=15)
            fetch_resp.raise_for_status()
            docs = fetch_resp.json().get("result", {})

            for pmid in ids:
                doc = docs.get(pmid, {})
                if not isinstance(doc, dict):
                    continue
                title = doc.get("title", "Untitled")
                pub_date = doc.get("pubdate", TODAY)[:10]

                results.append({
                    "source": "PubMed",
                    "query": query,
                    "title": title,
                    "summary": "",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "date": pub_date,
                })

            time.sleep(0.5)
        except Exception as e:
            print(f"[PUBMED] Error for query '{query}': {e}")

    print(f"[PUBMED] Gathered {len(results)} articles")
    return results


def gather_brave() -> list[dict]:
    """Fetch news via Brave Search API (optional)."""
    if not BRAVE_API_KEY:
        print("[BRAVE] No API key — skipping")
        return []

    results = []
    for query in BRAVE_SEARCH_QUERIES:
        try:
            resp = requests.get(
                "https://api.search.brave.com/res/v1/news/search",
                headers={"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"},
                params={"q": query, "count": BRAVE_MAX_RESULTS, "freshness": "pw"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("results", []):
                results.append({
                    "source": "Brave Search",
                    "query": query,
                    "title": item.get("title", ""),
                    "summary": item.get("description", "")[:300],
                    "url": item.get("url", ""),
                    "date": item.get("age", TODAY)[:10] if item.get("age") else TODAY,
                })
        except Exception as e:
            print(f"[BRAVE] Error for query '{query}': {e}")

    print(f"[BRAVE] Gathered {len(results)} results")
    return results


# ── SYNTHESIS ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior Product Manager intelligence analyst for K Platform at Owkin.
K Platform is Owkin's enterprise AI platform for pharmaceutical R&D — it provides drug discovery,
clinical trial optimization, and biomarker identification capabilities using multimodal AI
(pathology, genomics, clinical data).

Your job: synthesize raw signals into a structured daily briefing. For every signal, think:
- What does this mean for K Platform's roadmap?
- Is this a competitive threat (Biomni, Benchling, Phylo, OpenAI Health, NVIDIA Clara)?
- Does this affect enterprise deals (AstraZeneca, Sanofi)?
- Is there a regulatory implication (FDA, EU AI Act, GxP, HIPAA)?

Output a markdown report with these sections:
## 1. Top 3 Signals Today
For each signal use a level-3 heading with a colored circle emoji indicating urgency, then the title:
### 🔴 <title>   (highest urgency)
### 🟠 <title>   (high urgency)
### 🟡 <title>   (moderate urgency)
Under each, include a bullet `- **K implication:** <one-sentence implication>` and a markdown link to the source.

## 2. Competitive Landscape Update — moves by competitors
## 3. Technical Frontier — top papers relevant to K capabilities
## 4. Regulatory & Enterprise Signals — FDA, EU AI Act, GxP, HIPAA, pharma procurement
## 5. Partnership & Ecosystem Signals — Anthropic MCP, ELN tools, clinical platforms
## 6. Build Signals for K Platform
Exactly 3 ranked backlog items. Use level-3 headings with medal emojis:
### 🥇 <title>
**Rationale:** <why this matters>
**Effort:** <estimated effort>
### 🥈 <title>
### 🥉 <title>

Be concise, opinionated, and actionable. Each section should have 3-5 bullet points max.
Use markdown links where URLs are available."""

def synthesize_report(all_signals: list[dict]) -> str:
    """Send gathered signals to Claude for synthesis."""
    if not ANTHROPIC_API_KEY:
        print("[SYNTH] No ANTHROPIC_API_KEY — cannot synthesize")
        sys.exit(1)

    # Format signals for the prompt
    signal_text = ""
    for i, s in enumerate(all_signals, 1):
        signal_text += f"\n{i}. [{s['source']}] {s['title']}"
        if s.get("summary"):
            signal_text += f"\n   Summary: {s['summary']}"
        if s.get("url"):
            signal_text += f"\n   URL: {s['url']}"
        if s.get("date"):
            signal_text += f"\n   Date: {s['date']}"
        signal_text += "\n"

    user_prompt = f"""Here are today's raw signals ({TODAY}, {RUN_SLOT} run).
Total signals gathered: {len(all_signals)}

{signal_text}

Synthesize these into the daily K Platform intelligence briefing.
Start with a top-level heading: # K Platform Signal Report — {TODAY}
Include **Date:** {TODAY} and **Run:** {RUN_SLOT} at the top."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"[SYNTH] Sending {len(all_signals)} signals to Claude for synthesis...")
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    if not message.content:
        print(f"[SYNTH] ERROR: Empty response from Claude (stop_reason={message.stop_reason})")
        raise RuntimeError(f"Claude returned empty content (stop_reason={message.stop_reason})")

    report = message.content[0].text
    print(f"[SYNTH] Report generated ({len(report)} chars)")
    return report


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gather daily signals for K Platform")
    parser.add_argument("--dry-run", action="store_true", help="Gather signals only, no Claude synthesis")
    parser.add_argument("--source", type=str, help="Run a single source (arxiv, hf, rss, pubmed, brave)")
    args = parser.parse_args()

    source_map = {
        "arxiv": gather_arxiv,
        "hf": gather_huggingface,
        "rss": gather_rss,
        "pubmed": gather_pubmed,
        "brave": gather_brave,
    }

    # Gather signals
    all_signals = []
    if args.source:
        if args.source not in source_map:
            print(f"Unknown source: {args.source}. Choose from: {', '.join(source_map.keys())}")
            sys.exit(1)
        all_signals = source_map[args.source]()
    else:
        for name, gatherer in source_map.items():
            print(f"\n{'='*60}\n Gathering: {name}\n{'='*60}")
            all_signals.extend(gatherer())

    print(f"\n[TOTAL] {len(all_signals)} signals gathered")

    if args.dry_run:
        print("\n[DRY RUN] Skipping synthesis. Sample signals:")
        for s in all_signals[:10]:
            print(f"  - [{s['source']}] {s['title']}")
        return

    if not all_signals:
        print("[WARN] No signals gathered — writing minimal report")
        report = f"# K Platform Signal Report — {TODAY}\n\n**Date:** {TODAY}\n**Run:** {RUN_SLOT}\n\nNo signals gathered in this run. Check source availability."
    else:
        report = synthesize_report(all_signals)

    # Write report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"[DONE] Report written to {REPORT_FILE}")


if __name__ == "__main__":
    main()
