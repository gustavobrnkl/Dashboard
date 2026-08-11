# Help Scout Support TV Dashboard

Pulls conversations from Help Scout, and turns them into two things:

- `dashboard.html` — a detailed analytics dashboard (filters, charts, a sortable ticket table).
- `support_tv.html` — a glanceable, full-screen operations board meant for an office TV, auto-deployed hourly via GitHub Actions + GitHub Pages.

No server, no framework — plain Python (stdlib + `requests` + `python-dotenv`) generating static HTML.

## ⚠️ Known issue — action needed before your next commit

`dashboard.html` is currently tracked in this repo's git history from before `.gitignore` existed, and it embeds real customer names and emails in its data. Since this repo needs to be public for free GitHub Pages, **those emails are currently visible in the commit history on GitHub.**

Before pushing anything else, you should:
1. Stop tracking it going forward: `git rm --cached dashboard.html support_tv.html`
2. Decide whether to also purge it from past history (it will still be visible in old commits otherwise). The tool GitHub recommends for this is [`git-filter-repo`](https://github.com/newren/git-filter-repo):
   ```bash
   pip install git-filter-repo
   git filter-repo --path dashboard.html --invert-paths
   git push --force origin main
   ```
   This rewrites history, so only do it if you're sure no one else has cloned this repo.

`support_tv.html` doesn't contain any customer PII (no names or emails anywhere in it — see "Privacy" below), so untracking it is just cleanup, not a security fix; it's regenerated fresh by the Actions workflow every hour anyway and was never meant to live in git.

## Files

| File | Purpose |
|---|---|
| `export_helpscout.py` | Authenticates with Help Scout (OAuth client credentials), pulls the last 30 days of conversations plus all currently-open BRNKL Support tickets regardless of age, writes `helpscout_conversations_last_30_days.csv`. |
| `generate_tv_dashboard.py` | Reads that CSV, computes TV-board metrics (open/new/closed counts, time-to-close, top issues, device breakdown, oldest open cases), writes `support_tv.html`. |
| `update_dashboard.py` | Convenience wrapper — runs the two scripts above in sequence. |
| `requirements.txt` | `requests`, `python-dotenv` — that's it. |
| `.env.example` | Template for the two required Help Scout credentials. |
| `.github/workflows/update-tv-dashboard.yml` | Runs `update_dashboard.py` hourly and deploys `support_tv.html` to GitHub Pages. |
| `support_dashboard_mockup.html` | Original visual reference used when designing the TV board — not part of the pipeline. |

Never committed (see `.gitignore`): `.env`, `helpscout_conversations_last_30_days.csv`, `dashboard.html`, `support_tv.html`, `__pycache__/`, `.DS_Store`.

## Setup

```bash
cp .env.example .env
# then edit .env with your real Help Scout App ID / Secret
pip3 install -r requirements.txt
```

## Running locally

```bash
python3 update_dashboard.py
```

This fetches fresh data and regenerates both `support_tv.html`. Open it directly in a browser — it's fully self-contained, no server needed.

## Automatic hourly updates (GitHub Actions + Pages)

The workflow at `.github/workflows/update-tv-dashboard.yml`:

- Runs on a schedule (`cron: "17 * * * *"`, hourly) and can also be triggered manually from the **Actions** tab.
- Installs dependencies, runs `update_dashboard.py` with `HELP_SCOUT_APP_ID` / `HELP_SCOUT_APP_SECRET` injected from **repo secrets** (Settings → Secrets and variables → Actions) — never stored in the repo.
- Copies only `support_tv.html` into a `_site/index.html` publishing folder and deploys it via `actions/upload-pages-artifact` + `actions/deploy-pages`.
- The CSV and everything else the scripts produce stay on that run's disposable GitHub-hosted runner and are discarded when the job ends — they're never committed or uploaded anywhere.

Live at: **https://gustavobrnkl.github.io/Dashboard/**

Pages source is set to "GitHub Actions" under Settings → Pages.

## Privacy — what's actually public

`support_tv.html` (the only thing served by Pages) shows case numbers, ticket subjects, tag-derived issue/device labels, and durations. **It does not render customer names or emails anywhere.** The only mildly sensitive thing on it is ticket subject text, since that's free-form and written by customers/agents.

`dashboard.html` is the opposite — it has full customer names and emails baked into its data — which is exactly why the issue at the top of this README needs to be resolved.

## Displaying on the office TV

Open `https://gustavobrnkl.github.io/Dashboard/` in Chrome on whatever machine drives the TV, go fullscreen, and leave it open. Recommended:

- Disable sleep/screen-lock on that machine.
- Fullscreen/kiosk mode in Chrome.

**Not yet implemented:** the page doesn't currently auto-reload itself, so an already-open tab will keep showing whatever it loaded until someone manually refreshes it — even though the underlying data is updating hourly on the server. Worth adding a small `setTimeout(() => location.reload(), 15 * 60 * 1000)` to `generate_tv_dashboard.py`'s HTML template so the open tab picks up new builds on its own.

## Configuration

- `SUPPORT_MAILBOX` in `generate_tv_dashboard.py` — which Help Scout mailbox counts toward the TV board (currently `"BRNKL Support"`; the general `Ahoy` inbox is excluded from all TV metrics).
- `LOCAL_TZ` in the same file — all "today" boundaries (new/closed counts, time-to-close) are computed in `America/Vancouver`, not UTC.
