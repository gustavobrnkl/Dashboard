# Hosting the TV Dashboard on GitHub Pages (hourly auto-update)

This document describes how to make `support_tv.html` refresh itself every
hour without anyone manually re-running scripts, using GitHub Actions (to
regenerate the data) and GitHub Pages (to host the result). You run the
one-time setup steps below yourself; nothing here is automated by an
assistant.

## 1. What this is

Right now, updating the TV board means someone runs `python3
update_dashboard.py` on a laptop and reopens `support_tv.html` in Chrome.
This setup replaces that manual step with:

- A GitHub Actions workflow that runs **every hour**, pulls fresh data from
  Help Scout, and rebuilds `support_tv.html`.
- **GitHub Pages** serving that file at a stable URL.
- The page **reloading itself every 15 minutes**, so a fullscreen Chrome tab
  left open on the office TV picks up each new hourly build automatically.

## 2. Architecture at a glance

```
GitHub Actions (hourly cron)
        │
        ▼
  fresh, disposable runner
        │
        ├─ export_helpscout.py   → writes CSV (lives only on this runner)
        ├─ generate_tv_dashboard.py → reads CSV, writes support_tv.html
        │
        ▼
  upload ONLY support_tv.html as the Pages artifact
        │
        ▼
  GitHub Pages (public URL)
        │
        ▼
  Office TV's Chrome tab, open fullscreen, reloading every 15 min
```

The runner (and the CSV on it) is destroyed the moment the job finishes.
Nothing about the CSV persists across runs — each run starts from a clean
checkout and calls the Help Scout API fresh.

## 3. What's public vs. what never leaves the runner

**Published (public):** `support_tv.html` only. It contains case numbers,
ticket subjects, tag-derived issue/device labels, and durations — **no
customer names or emails appear anywhere in it.** The only mildly sensitive
thing exposed is ticket subject lines, since customers/agents write those in
free text.

**Never committed or published — must stay off GitHub entirely:**

| File | Why it's sensitive |
|---|---|
| `helpscout_conversations_last_30_days.csv` | Has `customer_name` and `customer_email` columns |
| `.env` | Help Scout API credentials |
| `dashboard.html` (the detailed analytics dashboard) | Has customer names/emails baked into its embedded data |

These three are excluded via `.gitignore` (see step 4) and the workflow
never uploads them anywhere — they only ever exist transiently on the
disposable Actions runner or on your local machine.

**Note on visibility:** this setup uses a **public** repo and **public**
GitHub Pages (free, no paid GitHub plan required). If you'd rather restrict
who can see the board, GitHub's *private* Pages requires a paid GitHub
Team/Enterprise plan — ask if you want that variant instead.

## 4. Step-by-step setup

Run these from the `Dashboard/` project folder (the repo root).

### 4.1 Initialize git and update `.gitignore`

```bash
cd /Users/gustavoborda/Documents/Dashboard
git init
```

Add these lines to `.gitignore` (it already ignores `.env`):

```
helpscout_conversations_last_30_days.csv
dashboard.html
```

### 4.2 Create the GitHub repo

Either via the `gh` CLI:

```bash
gh repo create brnkl-support-tv --public --source=. --remote=origin
```

or manually on github.com, then:

```bash
git remote add origin https://github.com/<your-username>/brnkl-support-tv.git
```

### 4.3 Commit and push (scripts only, never data)

```bash
git add export_helpscout.py \
        generate_tv_dashboard.py \
        update_dashboard.py \
        requirements.txt \
        .env.example \
        .gitignore
git commit -m "Add Help Scout TV dashboard pipeline"
git push -u origin main
```

Double-check what got staged before committing — `git status` should never
show the CSV, `.env`, or `dashboard.html`.

### 4.4 Add repository secrets

In GitHub: **Settings → Secrets and variables → Actions → New repository
secret**. Add two:

- `HELP_SCOUT_APP_ID`
- `HELP_SCOUT_APP_SECRET`

(same values as in your local `.env`)

### 4.5 Add the workflow file

Create `.github/workflows/update-tv-dashboard.yml`:

```yaml
name: Update TV Dashboard

on:
  schedule:
    - cron: "0 * * * *"   # every hour, on the hour (UTC)
  workflow_dispatch: {}    # allows manual "Run workflow" button

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Generate dashboard
        env:
          HELP_SCOUT_APP_ID: ${{ secrets.HELP_SCOUT_APP_ID }}
          HELP_SCOUT_APP_SECRET: ${{ secrets.HELP_SCOUT_APP_SECRET }}
        run: |
          python export_helpscout.py
          python generate_tv_dashboard.py

      - name: Prepare Pages artifact
        run: |
          mkdir -p _site
          cp support_tv.html _site/index.html

      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

      - id: deployment
        uses: actions/deploy-pages@v4
```

Commit and push this file the same way as step 4.3.

### 4.6 Enable Pages

In GitHub: **Settings → Pages → Build and deployment → Source →
"GitHub Actions"**.

### 4.7 Trigger the first run

Go to the **Actions** tab → "Update TV Dashboard" → **Run workflow**
(manual trigger via `workflow_dispatch`). Confirm it goes green, then open
the URL shown in the workflow's deployment step (something like
`https://<your-username>.github.io/brnkl-support-tv/`).

### 4.8 Point the TV at the Pages URL

On the machine driving the office TV, open that Pages URL in Chrome and go
fullscreen — instead of opening the local `support_tv.html` file. From now
on it refreshes itself.

## 5. Updating things later

- **Change the schedule:** edit the `cron` line in the workflow file.
- **Change which mailbox counts:** edit `SUPPORT_MAILBOX` in
  `generate_tv_dashboard.py`, commit, push.
- **Force an immediate refresh:** Actions tab → Run workflow.
- **Change how often the TV tab reloads:** edit the `setTimeout(...)`
  interval in `generate_tv_dashboard.py`'s HTML template.

## 6. Rolling back to fully local

Nothing about this setup removes the original local workflow. You can
always go back to the manual version at any time:

```bash
cd /Users/gustavoborda/Documents/Dashboard
python3 update_dashboard.py
```

then open the local `support_tv.html` in Chrome, same as before any of this
existed.
