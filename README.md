# New grad job tracker

Keeps a Google Sheet topped up with US new grad software engineering, tech
consulting and rotational roles. Pulls from community GitHub feeds, company
career boards and a jobs API, drops internships and senior roles, and appends
only jobs the sheet has not seen. Existing rows are never edited, so your notes
survive every run.

Runs itself on GitHub Actions every 6 hours. No server.

Hunting in a different field? See **[ADAPTING.md](ADAPTING.md)**.

```
GitHub new grad feeds \
Greenhouse boards      >  normalize -> filter -> dedupe -> append new rows
Lever boards          /   (US, new grad, no interns, posted this cycle)
Adzuna keyword API   /
```

The sheet is the source of truth for dedup: each row carries a hidden `key`
(the cleaned job URL), and a job whose key is already present is skipped. The
same posting reached through three links lands once.

## Setup (~15 min)

**1. Sheet.** Create a blank Google Sheet. Its id is the long string between
`/d/` and `/edit` in the URL.

**2. Service account.** A robot Google account, no OAuth popups.
1. At [console.cloud.google.com](https://console.cloud.google.com/), create a
   project and enable the **Google Sheets API**.
2. **Credentials > Create credentials > Service account**, then **Keys > Add
   key > JSON**. Keep the downloaded file safe.
3. Copy `client_email` from that file and share your sheet with it as
   **Editor**.

**3. GitHub.** Push to a repo, then add under **Settings > Secrets and
variables > Actions**:

| Secret | Value |
| --- | --- |
| `SHEET_ID` | the sheet id from step 1 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | entire contents of the JSON key file |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | optional, see below |

**4. Adzuna (optional).** Free key at
[developer.adzuna.com](https://developer.adzuna.com/). Catches the big
consulting and rotational employers (Deloitte, Accenture, EY, Capital One TDP)
that have no clean board API. Leave the secrets empty to skip it.

**5. Run.** Actions tab > **Update job tracker** > **Run workflow**. The first
run fills the sheet; after that it adds only what is new.

## Local testing
```bash
pip install -r requirements.txt
cp .env.example .env      # fill in
export $(grep -v '^#' .env | xargs)
python main.py
```

## Styling
`format_sheet.py` applies the header bar, widths, striping, hidden `key`
column, Status dropdown and per-status row colours. Formatting lives on the
sheet, so new rows inherit it. Rerun only when changing colours or the status
list; it clears its own previous rules first, so nothing stacks up.

```bash
export $(grep -v '^#' .env | xargs)   &&   python format_sheet.py
```

Rows sort newest first after each update, moving as a unit so a Status stays
attached to its job.

## Tuning (edit `config.yaml`, not the code)
- **Companies**: add a Greenhouse token or Lever site. From the careers URL,
  `boards.greenhouse.io/COMPANY` means the token is `COMPANY`. Tokens rotate;
  a dead one is skipped, not fatal.
- **Frequency**: the `cron` in `.github/workflows/update.yml`. Running less
  often risks missing roles outright, since feeds drop a posting once it
  closes.
- **Roles**: `include_title_any` / `exclude_title_any`.
- **Freshness**: `min_date_posted` drops prior-cycle listings; Adzuna's
  `max_days_old` controls its own lookback.

### Two location traps
- **Never add `remote` to `us_location_hints`** — it makes "Remote in UK" look
  US based. A bare "Remote" is already treated as US when no
  `non_us_location_any` marker is present.
- **Never add state codes `in`, `or`, `me`, `hi`, `de`, `la`, `ok`** — they are
  English words that match foreign strings. Add the city name instead.

Foreign markers match whole words, so `india` cannot swallow `Indianapolis`. US
markers are checked first, so "Toronto, ON, Canada, Dallas, TX" is kept.

## Your columns
`Status` is yours (dropdown: Interested, Applied, Interviewing, Offer,
Rejected, Skip). Filter `First Seen` by today to triage only what is new;
today's untouched rows are highlighted.

## Limits
- Community feeds are volunteer curated, so a new posting can lag a few hours.
  Company boards shorten that for employers you list explicitly.
- Adzuna is only as clean as the aggregators it indexes; the title filters do
  real work there.
- Closed roles are not re-checked. A closed job stops reappearing but stays in
  your sheet, which is what protects your notes.
- GitHub disables scheduled workflows after **60 days without a commit**. Push
  something occasionally or the tracker quietly stops.
