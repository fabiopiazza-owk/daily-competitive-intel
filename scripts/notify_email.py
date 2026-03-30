#!/usr/bin/env python3
"""
Send daily signal report by email to Fabio via SendGrid.
Uses SendGrid free tier (100 emails/day).
"""

import os
import json
import datetime
import requests
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
TODAY = datetime.date.today().isoformat()
RUN_SLOT_LABEL = os.environ.get("RUN_SLOT_LABEL", "📊 Daily Briefing")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "your-org/k-platform-signals")
GITHUB_REF = os.environ.get("GITHUB_REF_NAME", "main")

RECIPIENTS = [
    {"email": "REDACTED_EMAIL", "name": "REDACTED"},
    {"email": "REDACTED_EMAIL",   "name": "REDACTED"},
]
FROM_EMAIL = "REDACTED_EMAIL"   # Must be a verified sender in SendGrid
FROM_NAME  = "K Platform Intelligence"

REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_FILE = REPORT_DIR / f"{TODAY}.md"


# ── MARKDOWN → HTML ───────────────────────────────────────────────────────────
def md_to_html(text: str) -> str:
    """Minimal markdown-to-HTML for email rendering."""
    import re
    lines = text.split("\n")
    html_lines = []
    in_table = False
    in_ul = False

    for line in lines:
        # Table rows
        if line.startswith("|"):
            if not in_table:
                html_lines.append('<table style="border-collapse:collapse;width:100%;font-size:13px;">')
                in_table = True
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Detect separator row
            if all(set(c) <= set("-: ") for c in cells):
                continue
            tag = "th" if html_lines and "<th" not in "\n".join(html_lines[-5:]) else "td"
            style = 'style="border:1px solid #ddd;padding:6px 10px;text-align:left;"'
            row = "".join(f"<{tag} {style}>{c}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
            continue
        else:
            if in_table:
                html_lines.append("</table>")
                in_table = False

        # Headings
        if line.startswith("### "):
            html_lines.append(f'<h3 style="color:#2d3748;margin:20px 0 8px;">{line[4:]}</h3>')
        elif line.startswith("## "):
            html_lines.append(f'<h2 style="color:#1a202c;border-bottom:2px solid #667eea;padding-bottom:6px;margin:28px 0 12px;">{line[3:]}</h2>')
        elif line.startswith("# "):
            html_lines.append(f'<h1 style="color:#1a202c;margin:0 0 4px;">{line[2:]}</h1>')
        # Horizontal rule
        elif line.startswith("---"):
            html_lines.append('<hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">')
        # Bullet points
        elif line.startswith("- ") or line.startswith("* "):
            if not in_ul:
                html_lines.append('<ul style="padding-left:20px;margin:8px 0;">')
                in_ul = True
            content = line[2:]
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" style="color:#667eea;">\1</a>', content)
            html_lines.append(f'<li style="margin:4px 0;">{content}</li>')
            continue
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if not line.strip():
                html_lines.append("<br>")
            else:
                # Inline formatting
                formatted = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                formatted = re.sub(r'\*(.+?)\*', r'<em>\1</em>', formatted)
                formatted = re.sub(r'`(.+?)`', r'<code style="background:#f7fafc;padding:2px 5px;border-radius:3px;font-size:12px;">\1</code>', formatted)
                formatted = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" style="color:#667eea;">\1</a>', formatted)
                html_lines.append(f'<p style="margin:6px 0;line-height:1.6;">{formatted}</p>')

    if in_table:
        html_lines.append("</table>")
    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def build_html_email(report_text: str, report_url: str) -> str:
    body_html = md_to_html(report_text)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f7fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:760px;margin:32px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:28px 36px;">
      <div style="font-size:11px;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">
        Owkin · K Platform Intelligence
      </div>
      <div style="font-size:22px;font-weight:700;color:#ffffff;">
        {RUN_SLOT_LABEL}
      </div>
      <div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:4px;">
        {TODAY}
      </div>
    </div>

    <!-- Body -->
    <div style="padding:32px 36px;color:#2d3748;font-size:14px;line-height:1.7;">
      {body_html}
    </div>

    <!-- Footer -->
    <div style="background:#f7fafc;padding:20px 36px;border-top:1px solid #e2e8f0;">
      <a href="{report_url}"
         style="display:inline-block;background:#667eea;color:#ffffff;padding:10px 20px;
                border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;">
        📄 View Full Report on GitHub
      </a>
      <p style="margin:12px 0 0;font-size:11px;color:#a0aec0;">
        Automated by K Platform Signal Intelligence · Powered by Claude Opus 4.6
        · <a href="https://github.com/{GITHUB_REPO}" style="color:#a0aec0;">View repo</a>
      </p>
    </div>

  </div>
</body>
</html>"""


def extract_preview_text(report_text: str) -> str:
    """Extract first ~200 chars of analysis for email preview."""
    lines = [l.strip() for l in report_text.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("**Date")]
    return " ".join(lines[:3])[:200]


def send_email(html_body: str, preview_text: str, report_url: str):
    if not SENDGRID_API_KEY:
        print("[EMAIL] SENDGRID_API_KEY not set — skipping email")
        return

    subject = f"K Platform Signals · {RUN_SLOT_LABEL} · {TODAY}"

    payload = {
        "personalizations": [
            {
                "to": RECIPIENTS,
                "subject": subject,
            }
        ],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": subject,
        "content": [
            {
                "type": "text/plain",
                "value": f"{preview_text}\n\nFull report: {report_url}",
            },
            {
                "type": "text/html",
                "value": html_body,
            },
        ],
    }

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=15,
    )

    if resp.status_code in (200, 202):
        print(f"[EMAIL] Sent to {[r['email'] for r in RECIPIENTS]} ✓")
    else:
        print(f"[EMAIL] Error {resp.status_code}: {resp.text}")


def main():
    if not REPORT_FILE.exists():
        print(f"[EMAIL] Report not found: {REPORT_FILE}")
        return

    report_text = REPORT_FILE.read_text(encoding="utf-8")
    report_url = f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_REF}/reports/{TODAY}.md"

    html_body = build_html_email(report_text, report_url)
    preview = extract_preview_text(report_text)

    send_email(html_body, preview, report_url)


if __name__ == "__main__":
    main()
