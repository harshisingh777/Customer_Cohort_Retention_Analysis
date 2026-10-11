# Presentation deployment

A free, online copy of the app for demos. Nothing runs on the presenter's laptop: it only needs a
browser. This is **not** a production setup (see `runbook.md` for that):

| | Production (`infra/render.yaml`) | Presentation (`infra/render-demo.yaml`) |
|---|---|---|
| Cost | paid, always on | free |
| Sign-in | invite-only email links / Google | one-click demo account |
| Data | refreshed daily by the worker | loaded once by the `demo-db` workflow |
| Wake-up | instant | about a minute after 15 idle minutes |

Pieces: **Neon** (Postgres, free, 1 GB, never expires), **Render** (API and web app, free), and a
**GitHub Actions** workflow that loads Online Retail II into Neon.

## One-time setup (about 30 minutes)

### 1. Database: Neon

1. Sign up at <https://neon.com> (Continue with GitHub is fine). No card needed.
2. Create a project: any name, Postgres 17, the region nearest the audience.
3. On the project dashboard click **Connect**, turn **Connection pooling off**, and copy the
   connection string. It looks like
   `postgresql://neondb_owner:...@ep-....neon.tech/neondb?sslmode=require&channel_binding=require`.

### 2. Secrets for the loader

In the repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Value |
|---|---|
| `DEMO_ADMIN_DATABASE_URL` | the Neon connection string from step 1 |
| `DEMO_ROLE_PASSWORD` | any long random string of letters and digits |
| `DEMO_PII_KEY` | another long random string of letters and digits |

Or from a terminal with the GitHub CLI (each command asks for the value):

```bash
gh secret set DEMO_ADMIN_DATABASE_URL
gh secret set DEMO_ROLE_PASSWORD     # e.g. paste the output of: openssl rand -hex 24
gh secret set DEMO_PII_KEY           # e.g. paste the output of: openssl rand -hex 24
```

Keep `DEMO_ROLE_PASSWORD` somewhere: step 4 needs it.

### 3. Load the data

**Actions → demo-db → Run workflow** (leave both boxes unticked). It creates the database roles,
runs the migrations, downloads Online Retail II, builds and publishes the marts and fits the CLV
model, then prints the database size (about 485 MB). Around 10 minutes. Re-running it reloads
everything.

### 4. API and web app: Render

1. Sign up at <https://render.com> with GitHub and allow it to see this repository.
2. **New → Blueprint**, pick the repository, and set **Blueprint Path** to `infra/render-demo.yaml`.
3. Render asks for the values marked `sync: false`. The three database URLs are the Neon string
   with the user and password swapped for an app role. Print them with:

   ```bash
   DEMO_ADMIN_DATABASE_URL='<neon string>' DEMO_ROLE_PASSWORD='<role password>' \
     uv run python scripts/demo_db.py --print-env
   ```

   | Service | Variable | Value |
   |---|---|---|
   | `retention-demo-api` | `API_DATABASE_URL` | the `api_ro` URL |
   | | `API_OPS_DATABASE_URL` | the `api_ops` URL |
   | | `CORS_ALLOWED_ORIGINS` | `https://retention-demo-web.onrender.com` |
   | `retention-demo-web` | `WEB_DATABASE_URL` | the `web_auth` URL |
   | | `API_BASE_URL` | `https://retention-demo-api.onrender.com` |
   | | `PUBLIC_API_URL` | `https://retention-demo-api.onrender.com` |

4. **Apply**. The first build takes 5–10 minutes.
5. Check each service's URL at the top of its Render page. If Render added a suffix (because the
   name was taken), put the real URLs into `CORS_ALLOWED_ORIGINS`, `API_BASE_URL` and
   `PUBLIC_API_URL` (**Environment → Save, rebuild and deploy**).

Open the web URL and click **Sign in to the demo**.

## On presentation day

- Open the web URL **two minutes before** you start and sign in. Free services sleep after 15
  idle minutes; the first request wakes them (about a minute each, web then API).
- Keep a tab open during the talk; clicking around keeps everything awake.
- `admin@example.com` sees everything, including Settings. To show the read-only view with masked
  emails, sign out and sign in as `viewer@example.com`.

## What doesn't run in the demo

There is no background worker, so jobs are queued but never picked up:

- **Refresh now** on the Data page and **Export PDF**: avoid clicking them. **Export CSV** works.
- Settings changes are saved but only take effect on the next data load (re-run `demo-db`).

## Limits

- Neon free: 1 GB storage, 100 compute-hours a month; the database sleeps after 5 idle minutes and
  wakes in about a second.
- Render free: 750 instance-hours a month across both services; spun-down time doesn't count.
