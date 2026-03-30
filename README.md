# K Platform Daily Signal Intelligence

Automated daily PM intelligence briefing for K Platform at Owkin.  
Runs every weekday at 06:00 UTC (08:00 Paris) via GitHub Actions.

## What it does

1. **Gathers signals** from 5 source families:
   - **Arxiv** — latest papers on agentic AI, multimodal biology, drug discovery, spatial transcriptomics, LLM benchmarks
   - **HuggingFace Daily Papers** — curated ML papers, filtered for healthcare/bio relevance
   - **RSS feeds** — Anthropic blog, OpenAI blog, Google DeepMind, Nature Biotechnology, Nature Methods, STAT News, Fierce Healthcare, Drug Discovery News
   - **PubMed** — peer-reviewed clinical/pharma AI papers (last 7 days)
   - **Brave Search News** (optional) — real-time news on GenAI + healthcare

2. **Synthesizes with Claude** (`claude-opus-4-6`) using a PM-specific system prompt that:
   - Frames every signal through K Platform implications
   - Flags competitive threats (Biomni, Benchling, Phylo, OpenAI Health, etc.)
   - Surfaces regulatory signals affecting AZ/Sanofi deals
   - Outputs 3 concrete build signals for the backlog

3. **Commits the report** as `reports/YYYY-MM-DD.md` to this repo  
4. **Posts a Slack summary** (optional) with top signals + build items

## Setup

### 1. Fork or clone this repo into your GitHub org

```bash
git clone https://github.com/your-org/k-platform-signals
cd k-platform-signals
```

### 2. Set GitHub Secrets

Go to **Settings → Secrets and Variables → Actions** and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ Yes | Your Anthropic API key |
| `SENDGRID_API_KEY` | ✅ Yes | [SendGrid](https://sendgrid.com) free tier (100 emails/day) |
| `BRAVE_API_KEY` | Optional | [Brave Search API](https://brave.com/search/api/) — free: 2000 queries/month |
| `SLACK_WEBHOOK_URL` | Optional | Slack Incoming Webhook for channel summary |

**SendGrid one-time setup:**
1. Create free account at sendgrid.com
2. Verify a sender email (Settings → Sender Authentication)
3. Set `FROM_EMAIL` in `notify_email.py` to that verified address
4. Copy your API key → add as `SENDGRID_API_KEY` secret

**Email recipients** (hardcoded in `notify_email.py`):
- `REDACTED_EMAIL`
- `REDACTED_EMAIL`

### 3. Enable GitHub Actions

It triggers automatically **twice per weekday**:
- **07:30 Paris** (06:30 UTC) — morning briefing
- **17:00 Paris** (16:00 UTC) — end-of-day briefing

Each run emails both `REDACTED_EMAIL` and `REDACTED_EMAIL`.

To run manually: **Actions → Daily K Platform Signal Report → Run workflow**

### 4. Local testing

```bash
# Install dependencies
pip install -r scripts/requirements.txt

# Test signal gathering only (no API key needed)
python scripts/gather_signals.py --dry-run

# Test single source
python scripts/gather_signals.py --dry-run --source arxiv

# Full run (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/gather_signals.py
```

## Report Structure

Each daily report (`reports/YYYY-MM-DD.md`) contains:

1. **Top 3 Signals Today** — highest-impact items with direct K Platform implication
2. **Competitive Landscape Update** — moves by Biomni, Benchling, Phylo, OpenAI, DeepMind, NVIDIA
3. **Technical Frontier** — top Arxiv/HuggingFace papers relevant to K capabilities
4. **Regulatory & Enterprise Signals** — FDA, EU AI Act, GxP, HIPAA, pharma procurement
5. **Partnership & Ecosystem Signals** — Anthropic MCP ecosystem, ELN tools, clinical platforms
6. **Build Signals for K Platform** — 3 ranked backlog items

## Adding Signal Sources

Edit `scripts/gather_signals.py`:

- **New RSS feed**: Add to `RSS_FEEDS` dict
- **New Arxiv query**: Add to `ARXIV_QUERIES` list
- **New search query**: Add to `BRAVE_SEARCH_QUERIES` list
- **Custom scraper**: Add a new `gather_*()` function and call it in `main()`

## Cost estimate

| Component | Daily cost |
|-----------|-----------|
| Claude Opus 4.6 × 2 runs (~12K tokens each) | ~$0.40–0.60/day |
| SendGrid (free tier: 100 emails/day) | $0 |
| Brave Search API (free tier: 2000/month) | $0 |
| GitHub Actions (2000 min/month free) | $0 |
| **Total** | **~$8–13/month** |

## File structure

```
k-platform-signals/
├── .github/
│   └── workflows/
│       └── daily_signals.yml      # Runs 07:30 + 17:00 Paris weekdays
├── scripts/
│   ├── gather_signals.py          # Main pipeline (Arxiv, HF, RSS, PubMed, Brave)
│   ├── notify_email.py            # HTML email → REDACTED_EMAIL + @owkin.com
│   ├── notify_slack.py            # Slack channel summary (optional)
│   └── requirements.txt
├── reports/
│   ├── 2026-03-07.md              # Auto-committed by Actions
│   └── ...
└── README.md
```
