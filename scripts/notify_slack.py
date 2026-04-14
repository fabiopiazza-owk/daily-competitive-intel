#!/usr/bin/env python3
"""
Post a curated summary of the daily signal report to Slack via Workflow Builder webhook.
Extracts Top 3 Signals (§1) and Build Signals (§6), formats as Slack mrkdwn text,
and posts variables to the Workflow Builder trigger. Gracefully skips if SLACK_WEBHOOK_URL is unset.
"""

import os
import re
import json
import datetime
import requests
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
TODAY = datetime.date.today().isoformat()
RUN_SLOT_LABEL = os.environ.get("RUN_SLOT_LABEL", "Daily Briefing")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "your-org/k-platform-signals")
GITHUB_REF = os.environ.get("GITHUB_REF_NAME", "main")

REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_FILE = REPORT_DIR / f"{TODAY}.md"


# ── SECTION EXTRACTION ────────────────────────────────────────────────────────
def extract_section(text: str, section_num: int) -> str:
    """Extract a numbered section (e.g. '## 1. ...') from the report markdown."""
    pattern = rf"^## {section_num}\. .+$"
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            start = i
        elif start is not None and re.match(r"^## \d+\. ", line):
            return "\n".join(lines[start:i]).strip()
    if start is not None:
        return "\n".join(lines[start:]).rstrip().rstrip("-").strip()
    return ""


def parse_top_signals(section: str) -> list[dict]:
    """Parse section 1 into a list of {emoji, title, summary, link}."""
    signals = []
    current = None
    # Match emoji-prefixed headings (### 🔴 Title) or numbered headings (### 1. Title)
    heading_re = re.compile(r"^###\s+(?:(🔴|🟠|🟡|🟢)\s+|(\d+)\.\s*)(.+)$")
    fallback_emojis = ["🔴", "🟠", "🟡", "🟢"]

    for line in section.split("\n"):
        m = heading_re.match(line)
        if m:
            if current:
                signals.append(current)
            emoji = m.group(1) or fallback_emojis[min(len(signals), len(fallback_emojis) - 1)]
            title = m.group(3)
            current = {"emoji": emoji, "title": title, "summary": "", "link": ""}
        elif current:
            link_match = re.search(r"\[.+?\]\((.+?)\)", line)
            if "**K implication:**" in line:
                current["summary"] += line.split("**K implication:**")[-1].strip() + " "
            elif link_match and not current["link"]:
                current["link"] = link_match.group(1)
            elif not line.startswith("---") and not line.startswith("## ") and line.strip():
                current["summary"] += line.strip() + " "
    if current:
        signals.append(current)

    # Last-resort fallback: extract bold items as signals if no headings matched
    if not signals:
        bold_re = re.compile(r"^\s*[-*\d.]+\s*\*\*(.+?)\*\*[:\s]*(.*)$")
        for line in section.split("\n"):
            bm = bold_re.match(line)
            if bm:
                link_match = re.search(r"\[.+?\]\((.+?)\)", line)
                signals.append({
                    "emoji": fallback_emojis[min(len(signals), len(fallback_emojis) - 1)],
                    "title": bm.group(1),
                    "summary": bm.group(2).strip(),
                    "link": link_match.group(1) if link_match else "",
                })
            if len(signals) >= 3:
                break

    return signals


def parse_build_signals(section: str) -> list[dict]:
    """Parse section 6 into a list of {rank, title, rationale}."""
    signals = []
    # Try markdown table format first (| Rank | Item | Rationale |)
    table_rows = re.findall(r"^\|\s*\*\*(\d+)\*\*\s*\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|$", section, re.MULTILINE)
    if table_rows:
        rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}
        for rank_str, title, rationale in table_rows:
            rank_num = int(rank_str)
            signals.append({
                "rank": rank_emojis.get(rank_num, f"#{rank_num}"),
                "title": title.strip(),
                "rationale": rationale.strip(),
            })
        return signals

    # Fallback: heading format (### 🥇 Title)
    current = None
    for line in section.split("\n"):
        m = re.match(r"^### (🥇|🥈|🥉)\s+(.+)$", line)
        if m:
            if current:
                signals.append(current)
            current = {"rank": m.group(1), "title": m.group(2), "rationale": ""}
        elif current:
            if line.startswith("**Rationale:**"):
                current["rationale"] = line.replace("**Rationale:**", "").strip()
            elif line.startswith("**Effort:**"):
                current["rationale"] += f" | {line.strip()}"
    if current:
        signals.append(current)
    return signals


# ── SLACK MRKDWN FORMATTING ──────────────────────────────────────────────────
def format_top_signals(signals: list[dict]) -> str:
    """Format top signals as Slack mrkdwn text."""
    parts = []
    for sig in signals[:3]:
        # First sentence of summary for brevity
        summary = sig["summary"].strip()
        sentences = re.split(r"(?<=[.!?])\s+", summary)
        short_summary = sentences[0] if sentences else summary
        if len(short_summary) > 300:
            short_summary = short_summary[:297] + "..."

        line = f"{sig['emoji']}  *{sig['title']}*\n{short_summary}"
        if sig["link"]:
            line += f"\n<{sig['link']}|Read more>"
        parts.append(line)

    return "\n\n".join(parts)


def format_build_signals(signals: list[dict]) -> str:
    """Format build signals as Slack mrkdwn text."""
    parts = []
    for sig in signals[:3]:
        rationale = sig["rationale"].strip()
        # Keep rationale concise
        sentences = re.split(r"(?<=[.!?])\s+", rationale)
        short_rationale = " ".join(sentences[:2]) if len(sentences) > 2 else rationale
        if len(short_rationale) > 300:
            short_rationale = short_rationale[:297] + "..."

        parts.append(f"{sig['rank']}  *{sig['title']}*\n{short_rationale}")

    return "\n\n".join(parts)


# ── SEND ──────────────────────────────────────────────────────────────────────
def send_slack(payload: dict):
    resp = requests.post(
        SLACK_WEBHOOK_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=15,
    )
    if resp.status_code in (200, 201, 202):
        print("[SLACK] Workflow triggered ✓")
    else:
        print(f"[SLACK] Error {resp.status_code}: {resp.text}")


def main():
    if not SLACK_WEBHOOK_URL:
        print("[SLACK] SLACK_WEBHOOK_URL not set — skipping Slack notification")
        return

    if not REPORT_FILE.exists():
        print(f"[SLACK] Report not found: {REPORT_FILE}")
        return

    report_text = REPORT_FILE.read_text(encoding="utf-8")
    report_url = f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_REF}/reports/{TODAY}.md"

    section1 = extract_section(report_text, 1)
    section6 = extract_section(report_text, 6)

    top_signals = parse_top_signals(section1)
    build_signals = parse_build_signals(section6)

    if not top_signals:
        print("[SLACK] Could not parse top signals from report — skipping")
        return

    # Workflow Builder expects flat variables matching the trigger definition
    payload = {
        "date": TODAY,
        "slot_label": RUN_SLOT_LABEL,
        "top_signals": format_top_signals(top_signals),
        "build_signals": format_build_signals(build_signals),
        "report_url": report_url,
    }

    send_slack(payload)


if __name__ == "__main__":
    main()
