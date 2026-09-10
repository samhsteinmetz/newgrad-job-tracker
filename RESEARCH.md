# Automating a 2027 new grad job search: research and design

Goal: a Google Sheet that stays continuously current with US new grad software
engineering, tech consulting, and rotational program roles, with no duplicates
and no internships, and that adds new postings automatically as they appear.

You graduate December 2026, so the roles that matter are the ones labelled
"2026 new grad", "2027 new grad", or "class of 2027", which open in waves from
roughly August 2026 through spring 2027. The timing is good: the fall wave is
opening right now.

## The core insight

You do not need to scrape the whole internet yourself. Three layers already do
most of the aggregation, and stacking them covers almost everything a new grad
would find by hand, minus the manual clicking.

### Layer 1: community GitHub feeds (highest signal, free, no key)

A handful of open source repos are maintained by large communities whose entire
purpose is exactly your goal. They watch company career pages and post new grad
roles within hours, and crucially they publish the data as a machine readable
`listings.json`, not just a README table. That JSON is already deduped and
normalized, which makes it the best single source to build on.

The two the pipeline uses:

- **SimplifyJobs/New-Grad-Positions** — the largest and most trusted. Feed:
  `raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json`.
  Fields: `company_name`, `title`, `locations`, `url`, `date_posted`, `active`,
  `is_visible`, `category`, `sponsorship`.
- **vanshb03/New-Grad-2027** — a very active 2027 focused list with the same
  JSON shape.

Both mark stale roles `active: false`, so the pipeline drops closed postings for
free. This layer alone will likely fill most of your sheet.

### Layer 2: company career boards (free public JSON, no key)

Most tech companies run their careers page on a shared applicant tracking
system, and two of the biggest expose a public JSON endpoint with no auth:

- **Greenhouse**: `https://boards-api.greenhouse.io/v1/boards/{token}/jobs`
- **Lever**: `https://api.lever.co/v0/postings/{site}?mode=json`

You add a company by dropping its token into `config.yaml`. This layer catches
new roles the moment a target company posts them, sometimes before the community
repos pick them up, and it lets you follow specific employers you care about
even if they are small. Ashby and Workday also power many boards; Ashby has a
usable public endpoint you can add later, Workday is harder and is better
reached through Layer 3.

### Layer 3: Adzuna keyword API (free key, best for consulting and rotational)

The big consulting firms and rotational programs (Deloitte, Accenture, EY, PwC,
KPMG technology practices, Capital One Technology Development Program, and
similar) mostly run closed applicant systems with no clean public API. But they
all syndicate their postings to job aggregators. Adzuna offers a free API that
indexes those aggregators, so a keyword search for "technology development
program" or "technology consulting analyst new grad" surfaces exactly the
employers that Layers 1 and 2 miss. This is the piece that makes the tracker
cover consulting and rotational and not just pure SWE.

## Why not scrape LinkedIn, Indeed, or Handshake directly

Tempting, but a bad foundation. LinkedIn and Indeed actively block scraping,
change their markup often, and put it against their terms of service, so any
scraper you build there breaks constantly and risks your account. Handshake is
login walled per school. The three layers above give you the same postings
through supported, stable, free interfaces, which is what makes a set and forget
pipeline actually stay running. If you later want more breadth, the clean next
add is another aggregator API (JSearch on RapidAPI, which wraps Google Jobs),
not a scraper.

## Why GitHub Actions as the engine

You needed something that runs on a schedule, writes to your sheet, and never
needs a server you maintain.

- **GitHub Actions** (chosen): free, cron built in, zero hosting. The script
  runs in a fresh container every 6 hours and writes to your sheet using a
  Google service account. Nothing to keep online.
- **n8n** (your consulting stack): great for visual pipelines, but to run
  continuously it needs a host that is always on, which is one more thing to pay
  for and maintain. Better kept for client work where you already host it.
- **Google Apps Script**: no hosting and lives in the sheet, but it is weak at
  calling many external APIs and has tight runtime limits, so it does not scale
  to this many sources cleanly.

## Why the sheet is its own dedup store

Rather than a separate database, the sheet itself records every job you have
ever seen through a hidden `key` column (a cleaned, tracking free version of the
job URL). Each run reads those keys, then appends only jobs whose key is new.
This gives you three things at once: no duplicates ever, a permanent history of
what has appeared, and a `status` column you own that the pipeline never
touches, so "haven't applied to yet" is just an empty status cell you can filter
on.

## What to do after it is running

- Add every company you would actually take an offer from to the Greenhouse and
  Lever lists in `config.yaml`. That turns the tracker into a personal watchlist
  on top of the broad feeds.
- Filter the sheet by `first_seen = today` each morning to triage only what is
  new, and set `status` as you go.
- If you want a nudge, add a second GitHub Actions step that emails you the
  count of new rows, or posts it to a Discord or Slack webhook.

## Limits worth knowing

- Community feeds are curated by volunteers, so a brand new posting can lag a
  few hours. Layer 2 shortens that for companies you list explicitly.
- Adzuna results are only as clean as the aggregators it indexes, so the title
  filters in `config.yaml` do real work removing noise. Tune them if junk slips
  through.
- The pipeline reads live status from Layer 1 (it drops `active: false`) but
  does not re-check whether a Layer 2 or Adzuna role has since closed. A closed
  role simply stops reappearing; you can add a "still open" recheck later.

## Sources
- [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions)
- [vanshb03/New-Grad-2027](https://github.com/vanshb03/New-Grad-2027)
- [speedyapply/2027-SWE-College-Jobs](https://github.com/speedyapply/2027-SWE-College-Jobs)
- [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [Adzuna developer API](https://developer.adzuna.com/docs/search)
