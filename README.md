# New grad job tracker

A pipeline that keeps a Google Sheet continuously topped up with US new grad
software engineering, tech consulting, and rotational program roles. It pulls
from community GitHub feeds, company career boards, and a jobs API, filters out
internships and senior roles, and adds only jobs that are not already in your
sheet. Nothing is ever deleted or overwritten, so your own notes stay put.

It runs itself on GitHub Actions every 6 hours. No server to babysit.

## How it works

```
  GitHub new grad feeds  \
  Greenhouse boards       >  normalize  ->  filter          ->  dedupe          ->  append new rows
  Lever boards           /                 (US, new grad,       (against keys        to your sheet
  Adzuna keyword API    /                   no internships)      already in sheet)
```

The sheet is the single source of truth for what you have already seen. Each
row carries a hidden `key` (a cleaned version of the job URL). A job whose key
is already present is skipped, so the same posting reached through three
different links still lands once.

## One time setup (about 15 minutes)

### 1. Make the Google Sheet
Create a blank Google Sheet. From its URL, copy the id (the long string between
`/d/` and `/edit`). That is your `SHEET_ID`.

### 2. Create a Google service account
This is a robot Google account the script logs in as. No OAuth popups.

1. Go to https://console.cloud.google.com/ and create a project (any name).
2. In "APIs and Services > Library", enable the **Google Sheets API**.
3. In "APIs and Services > Credentials", click **Create credentials >
   Service account**. Name it, click through, done.
4. Open the new service account, go to the **Keys** tab, **Add key > Create
   new key > JSON**. A `.json` file downloads. Keep it safe.
5. Open that JSON file, find the `client_email` value (looks like
   `something@project.iam.gserviceaccount.com`).
6. Back in your Google Sheet, click **Share** and share it with that
   `client_email` as an **Editor**.

### 3. Put it on GitHub
1. Create a new **private** GitHub repo and upload these files.
2. In the repo, go to **Settings > Secrets and variables > Actions > New
   repository secret** and add:
   - `SHEET_ID` = your sheet id
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = the entire contents of the JSON key file
     (open it, select all, paste)
   - `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` = optional, see below

### 4. (Optional but recommended) Adzuna key
Adzuna is what catches the big consulting and rotational employers (Deloitte,
Accenture, EY, Capital One, and similar) that do not publish a clean board API.
Get a free key at https://developer.adzuna.com/, then add the two secrets above.
Leave them empty and the pipeline just skips Adzuna.

### 5. Run it
Go to the **Actions** tab, pick **Update job tracker**, click **Run workflow**.
Watch the log. On the first run it fills the sheet; after that it adds only new
jobs. From then on it runs on its own every 6 hours.

## Running locally to test
```bash
pip install -r requirements.txt
cp .env.example .env          # fill in the values
export $(grep -v '^#' .env | xargs)
python main.py
```

## Tuning it (edit config.yaml, not the code)
- **Add companies**: drop a Greenhouse token or Lever site into the lists. Find
  the token from the careers URL, for example `boards.greenhouse.io/COMPANY`.
- **Change how often it runs**: edit the `cron` line in
  `.github/workflows/update.yml`. `0 */6 * * *` is every 6 hours.
- **Widen or narrow roles**: edit the `include_title_any` and
  `exclude_title_any` lists in `config.yaml`.
- **Tighten Adzuna freshness**: `max_days_old` controls how far back it looks.

## Your columns
`status` is yours. Put `Applied`, `Interested`, or `Skip` there. The pipeline
never touches rows that already exist, so your status survives every run. Sort
or filter the sheet by `first_seen` to see what showed up today.
