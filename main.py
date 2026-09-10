#!/usr/bin/env python3
"""
New grad job tracker.

Pulls US new grad SWE, tech consulting and rotational roles from community
GitHub feeds, company ATS boards (Greenhouse, Lever) and the Adzuna API,
filters out internships and senior roles, dedupes against what is already in
your Google Sheet, and appends only the genuinely new rows.

The Google Sheet is the single source of truth for dedup. Nothing is ever
deleted or overwritten, so your own Status edits are safe.

Run locally:   python main.py
On a schedule: GitHub Actions (see .github/workflows/update.yml)
"""

import os
import re
import sys
import json
import time
import datetime as dt
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml
# gspread and google.oauth2 are imported lazily inside open_worksheet so the
# rest of the pipeline can run (and be tested) without the Google libraries.

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.yaml")

# Order of columns written to the sheet. "key" must stay last, it is the
# dedup fingerprint. "status" is yours to edit and is never touched again.
COLUMNS = [
    "status", "company", "title", "location", "category",
    "source", "date_posted", "first_seen", "url", "key",
]

# What the header row actually displays. These are only labels: every check
# normalizes them back to COLUMNS, so renaming one here does not move a
# column or break dedup. Keep the order identical to COLUMNS.
HEADER_LABELS = [
    "Status", "Company", "Role", "Location", "Category",
    "Source", "Posted", "First Seen", "Link", "key",
]


def normalize_header(cells):
    """'Date Posted' -> 'date_posted', so a prettied up header still matches."""
    return [re.sub(r"\s+", "_", (c or "").strip().lower()) for c in cells]


def header_is_valid(cells):
    """True for the current display labels and for the older all lowercase
    header, so a sheet written by an earlier version is left alone instead of
    having a second header inserted above it."""
    seen = normalize_header(cells)
    return seen in (COLUMNS, normalize_header(HEADER_LABELS))

USER_AGENT = "newgrad-job-tracker/1.0 (personal job search)"
TIMEOUT = 30


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def log(msg):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def http_get(url, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", USER_AGENT)
    return requests.get(url, headers=headers, timeout=TIMEOUT, **kwargs)


def clean_url(url):
    """Strip query string, fragment and trailing slash so the same posting
    reached through different tracking links collapses to one key."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", "")).lower()
    except Exception:
        return url.strip().lower()


def make_key(company, title, url):
    """Dedup fingerprint. Prefer the cleaned URL, fall back to company+title."""
    cu = clean_url(url)
    if cu:
        return cu
    return f"{(company or '').strip().lower()}|{(title or '').strip().lower()}"


def ts_to_date(value):
    """Accept a unix timestamp (int/str) or an ISO string, return YYYY-MM-DD."""
    if not value:
        return ""
    try:
        n = float(value)
        if n > 1e12:      # milliseconds
            n = n / 1000.0
        return dt.datetime.fromtimestamp(n, dt.timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    s = str(value)
    return s[:10] if len(s) >= 10 else s


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ----------------------------------------------------------------------------
# filtering
# ----------------------------------------------------------------------------
def title_ok(title, f):
    t = norm(title)
    if not t:
        return False
    padded = f" {t} "
    for bad in f["exclude_title_any"]:
        b = bad.lower()
        if b.startswith(" ") or b.endswith(" "):
            if b in padded:
                return False
        elif b in t:
            return False
    for pat in f.get("exclude_title_regex", []):
        if re.search(pat, t):
            return False
    for good in f["include_title_any"]:
        if good.lower() in t:
            return True
    return False


def _matches_any(loc, padded, hints):
    """Short hints (state codes) match as whole tokens, longer ones as
    substrings, so "ca" hits "Austin, TX, CA" but not "Decatur"."""
    for hint in hints or []:
        h = hint.lower()
        if len(h) <= 3:                     # short state codes, match as token
            if f" {h} " in padded or f" {h}," in padded or f",{h} " in padded:
                return True
        elif h in loc:
            return True
    return False


def _matches_word_any(loc, hints):
    """Whole-word match, so "india" does not fire on "Indianapolis" and "uk"
    does not fire on "Paducah"."""
    for hint in hints or []:
        if re.search(rf"\b{re.escape(hint.lower())}\b", loc):
            return True
    return False


def location_ok(location, f):
    if not f.get("us_only", True):
        return True
    loc = norm(location)
    if not loc:
        return True  # unknown location, keep and let the human judge
    padded = f" {loc} "

    # An explicit US city or state anywhere in the string wins outright.
    # Multi-office roles like "Toronto, ON, Canada, Dallas, TX" are open to
    # US candidates, so one US marker is enough to keep them.
    if _matches_any(loc, padded, f["us_location_hints"]):
        return True

    # No US marker found. A bare "Remote" is assumed US, but an explicitly
    # foreign remote role ("Remote in UK") is not, so check for a foreign
    # marker before falling back to that assumption. These match on word
    # boundaries, not substrings, so "india" cannot swallow "Indianapolis".
    if _matches_word_any(loc, f.get("non_us_location_any", [])):
        return False
    return "remote" in loc


def date_ok(date_posted, f):
    """Drop postings older than min_date_posted. The community feeds keep
    prior-cycle roles flagged active, so without this the sheet fills up with
    last year's listings. An unparseable or missing date is kept, on the
    theory that a human should judge it rather than lose it silently."""
    floor = str(f.get("min_date_posted") or "").strip()
    if not floor:
        return True
    d = (date_posted or "").strip()
    if len(d) < 10 or not d[:4].isdigit():
        return True
    return d[:10] >= floor


def keep(job, f):
    return (
        title_ok(job["title"], f)
        and location_ok(job["location"], f)
        and date_ok(job.get("date_posted"), f)
    )


# ----------------------------------------------------------------------------
# sources
# ----------------------------------------------------------------------------
def fetch_github_feeds(feeds):
    out = []
    for feed in feeds:
        try:
            r = http_get(feed["url"])
            r.raise_for_status()
            data = r.json()
            n = 0
            for item in data:
                # only live, visible postings
                if item.get("active") is False or item.get("is_visible") is False:
                    continue
                locs = item.get("locations") or []
                out.append({
                    "company": item.get("company_name", ""),
                    "title": item.get("title", ""),
                    "location": ", ".join(locs) if isinstance(locs, list) else str(locs),
                    "category": item.get("category", "New Grad"),
                    "source": feed["name"],
                    "date_posted": ts_to_date(item.get("date_posted")),
                    "url": item.get("url", ""),
                })
                n += 1
            log(f"  github feed '{feed['name']}': {n} live listings")
        except Exception as e:
            log(f"  github feed '{feed['name']}' FAILED: {e}")
    return out


def fetch_greenhouse(tokens):
    out = []
    for tok in tokens:
        url = f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs?content=false"
        try:
            r = http_get(url)
            if r.status_code != 200:
                log(f"  greenhouse '{tok}': skipped (HTTP {r.status_code})")
                continue
            jobs = r.json().get("jobs", [])
            for j in jobs:
                out.append({
                    "company": tok.capitalize(),
                    "title": j.get("title", ""),
                    "location": (j.get("location") or {}).get("name", ""),
                    "category": "Greenhouse",
                    "source": f"Greenhouse:{tok}",
                    "date_posted": ts_to_date(j.get("updated_at") or j.get("first_published")),
                    "url": j.get("absolute_url", ""),
                })
            log(f"  greenhouse '{tok}': {len(jobs)} postings")
        except Exception as e:
            log(f"  greenhouse '{tok}' FAILED: {e}")
        time.sleep(0.3)
    return out


def fetch_lever(sites):
    out = []
    for site in sites:
        url = f"https://api.lever.co/v0/postings/{site}?mode=json"
        try:
            r = http_get(url)
            if r.status_code != 200:
                log(f"  lever '{site}': skipped (HTTP {r.status_code})")
                continue
            postings = r.json()
            for p in postings:
                cats = p.get("categories") or {}
                out.append({
                    "company": site.capitalize(),
                    "title": p.get("text", ""),
                    "location": cats.get("location", ""),
                    "category": "Lever",
                    "source": f"Lever:{site}",
                    "date_posted": ts_to_date(p.get("createdAt")),
                    "url": p.get("hostedUrl", ""),
                })
            log(f"  lever '{site}': {len(postings)} postings")
        except Exception as e:
            log(f"  lever '{site}' FAILED: {e}")
        time.sleep(0.3)
    return out


def fetch_adzuna(cfg):
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        log("  adzuna: skipped (no ADZUNA_APP_ID / ADZUNA_APP_KEY set)")
        return []
    out = []
    country = cfg.get("country", "us")
    for query in cfg.get("queries", []):
        for page in range(1, cfg.get("pages_per_query", 1) + 1):
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": cfg.get("results_per_page", 50),
                "what": query,
                "max_days_old": cfg.get("max_days_old", 7),
                "content-type": "application/json",
            }
            try:
                r = http_get(url, params=params)
                if r.status_code != 200:
                    log(f"  adzuna '{query}' p{page}: HTTP {r.status_code}")
                    break
                results = r.json().get("results", [])
                for j in results:
                    out.append({
                        "company": (j.get("company") or {}).get("display_name", ""),
                        "title": j.get("title", ""),
                        "location": (j.get("location") or {}).get("display_name", ""),
                        "category": "Adzuna",
                        "source": "Adzuna",
                        "date_posted": ts_to_date(j.get("created")),
                        "url": j.get("redirect_url", ""),
                    })
                if len(results) < cfg.get("results_per_page", 50):
                    break
            except Exception as e:
                log(f"  adzuna '{query}' p{page} FAILED: {e}")
                break
            time.sleep(0.4)
    log(f"  adzuna: {len(out)} raw results across {len(cfg.get('queries', []))} queries")
    return out


# ----------------------------------------------------------------------------
# google sheet
# ----------------------------------------------------------------------------
def open_worksheet(cfg):
    import gspread
    from google.oauth2.service_account import Credentials

    sheet_id = os.environ.get("SHEET_ID", "").strip()
    if not sheet_id:
        sys.exit("ERROR: SHEET_ID environment variable is not set.")

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        sys.exit("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set.")
    info = json.loads(raw)

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)

    ss = gc.open_by_key(sheet_id)
    ws_name = cfg["sheet"]["worksheet"]
    created = False
    try:
        ws = ss.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=ws_name, rows=2000, cols=len(COLUMNS))
        created = True

    # Write the header straight to A1 rather than appending it. append_row
    # picks its target from the API's idea of where the table ends, which on a
    # freshly created sheet can be stale, and a header that lands below the
    # data is worse than no header at all.
    header = ws.row_values(1)
    if not header_is_valid(header):
        if header:
            # Row 1 holds something else (data, or a partial header). Push a
            # correct header above it instead of overwriting a real row.
            ws.insert_row(HEADER_LABELS, index=1, value_input_option="RAW")
            log(f"  worksheet '{ws_name}' was missing its header row, inserted one")
        else:
            ws.update(range_name="A1", values=[HEADER_LABELS], value_input_option="RAW")
            if created:
                log(f"  created worksheet '{ws_name}' with header row")
    return ws


def sort_by_date_desc(ws):
    """Sort the data rows (never the header) newest posting first."""
    last_row = len(ws.col_values(COLUMNS.index("key") + 1))
    if last_row < 3:          # header plus at most one row, nothing to sort
        return
    date_col = COLUMNS.index("date_posted") + 1
    last_col = chr(ord("A") + len(COLUMNS) - 1)
    try:
        ws.sort((date_col, "des"), range=f"A2:{last_col}{last_row}")
        log(f"  sorted rows 2..{last_row} by date_posted, newest first")
    except Exception as e:
        log(f"  could not sort sheet (rows are still correct): {e}")


def existing_keys(ws):
    """Read the key column (last column) so we never add a duplicate."""
    try:
        col_idx = COLUMNS.index("key") + 1
        keys = ws.col_values(col_idx)[1:]  # drop header
        return set(k.strip().lower() for k in keys if k.strip())
    except Exception as e:
        log(f"  could not read existing keys, treating sheet as empty: {e}")
        return set()


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    cfg = load_config()
    f = cfg["filters"]

    log("Fetching sources ...")
    raw = []
    raw += fetch_github_feeds(cfg.get("github_feeds", []))
    raw += fetch_greenhouse(cfg.get("greenhouse_boards", []))
    raw += fetch_lever(cfg.get("lever_boards", []))
    raw += fetch_adzuna(cfg.get("adzuna", {}))
    log(f"Total raw postings pulled: {len(raw)}")

    # filter
    filtered = [j for j in raw if keep(j, f)]
    log(f"After new grad / US / no intern filter: {len(filtered)}")

    # dedup within this run
    seen_now = {}
    for j in filtered:
        k = make_key(j["company"], j["title"], j["url"])
        if k not in seen_now:
            j["key"] = k
            seen_now[k] = j
    log(f"Unique this run: {len(seen_now)}")

    # dedup against the sheet
    ws = open_worksheet(cfg)
    already = existing_keys(ws)
    log(f"Already in sheet: {len(already)}")

    today = dt.date.today().strftime("%Y-%m-%d")
    new_rows = []
    for k, j in seen_now.items():
        if k in already:
            continue
        row = {
            "status": "",              # you fill this in: Applied / Interested / Skip
            "company": j["company"],
            "title": j["title"],
            "location": j["location"],
            "category": j["category"],
            "source": j["source"],
            "date_posted": j["date_posted"],
            "first_seen": today,
            "url": j["url"],
            "key": k,
        }
        new_rows.append([row[c] for c in COLUMNS])

    if new_rows:
        ws.append_rows(new_rows, value_input_option="RAW")
    log(f"NEW jobs added to sheet: {len(new_rows)}")

    # Keep the newest postings at the top. Rows move as a unit, so a status
    # you typed stays attached to its job. date_posted is YYYY-MM-DD, so a
    # plain text sort is already chronological; blank dates sink to the
    # bottom, which is where unknowns belong.
    if new_rows:
        sort_by_date_desc(ws)

    print(f"::notice::Added {len(new_rows)} new jobs")


if __name__ == "__main__":
    main()
