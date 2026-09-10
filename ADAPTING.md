# Adapting this to a different job search

The pipeline is field-agnostic. Only `config.yaml` is SWE-specific — the code
never mentions engineering. Non-developers: you edit one text file, no Python.

Do the [README](README.md) setup first, then change these.

## The three sources, and which apply to you

| Source | Keep it? |
| --- | --- |
| `github_feeds` | **Software only.** Delete for any other field. |
| `greenhouse_boards` / `lever_boards` | **Any field.** These list every open role at a company, not just tech. |
| `adzuna` | **Any field. This becomes your main source** once the feeds are gone. |

So a non-SWE search is: delete one section, add employers, rewrite the
keywords. Adzuna needs its free key or you will have almost no results.

## 1. Delete the SWE feeds

```yaml
github_feeds: []
```

## 2. Rewrite the keywords

`include_title_any` — a title must contain one of these. `exclude_title_any` —
drop it if it contains one of these, always wins. `adzuna.queries` — what gets
searched. Match all three to your field.

Keep the seniority exclusions (`senior`, `staff`, `principal`, `director`,
`manager`) for an entry-level search, and keep `intern` unless you want
internships.

<details>
<summary><b>Finance / investment banking</b></summary>

```yaml
include_title_any: ["analyst", "investment banking", "equity research",
  "financial analyst", "capital markets", "private equity", "asset management",
  "rotational", "analyst program", "new grad", "entry level"]
adzuna:
  queries: ["investment banking analyst", "financial analyst new grad",
    "equity research associate", "capital markets analyst program"]
```
Boards: `jpmorgan`, `evercore`, `moelis`, `lazard` (verify each, see below).
</details>

<details>
<summary><b>Marketing / communications</b></summary>

```yaml
include_title_any: ["marketing", "brand", "social media", "content",
  "communications", "public relations", "growth", "coordinator", "associate",
  "entry level", "new grad"]
exclude_title_any: ["intern", "senior", "director", "manager", "head of", "vp "]
adzuna:
  queries: ["marketing coordinator entry level", "brand associate new grad",
    "social media coordinator", "communications associate"]
```
</details>

<details>
<summary><b>Nursing / healthcare</b></summary>

```yaml
include_title_any: ["registered nurse", "rn ", "new grad nurse",
  "nurse residency", "clinical", "patient care", "medical assistant"]
exclude_title_any: ["travel", "per diem", "supervisor", "director", "manager"]
adzuna:
  queries: ["new grad registered nurse", "nurse residency program",
    "rn new graduate"]
```
Most hospitals use Workday, which has no public API — Adzuna does the work here.
</details>

<details>
<summary><b>Teaching / education</b></summary>

```yaml
include_title_any: ["teacher", "teaching fellow", "instructor", "tutor",
  "education", "paraprofessional", "resident"]
exclude_title_any: ["substitute", "senior", "principal", "director", "head of"]
adzuna:
  queries: ["elementary teacher", "high school teacher", "teaching fellow",
    "teacher residency program"]
```
Note `principal` is excluded as a seniority word — remove it if you want
school principal roles.
</details>

<details>
<summary><b>Design / UX</b></summary>

```yaml
include_title_any: ["designer", "design", "ux", "ui", "product design",
  "graphic", "visual", "junior", "associate", "entry level", "new grad"]
adzuna:
  queries: ["junior product designer", "ux designer new grad",
    "graphic designer entry level"]
```
</details>

## 3. Add employers you would actually join

Open a company's careers page and check the URL:

- `boards.greenhouse.io/COMPANY` or `job-boards.greenhouse.io/COMPANY` →
  add `COMPANY` to `greenhouse_boards`
- `jobs.lever.co/COMPANY` → add `COMPANY` to `lever_boards`
- anything else (Workday, Taleo, iCIMS, in-house) → not supported, rely on
  Adzuna

Verify a token before adding it — paste in a browser, expect JSON not an error:

```
https://boards-api.greenhouse.io/v1/boards/COMPANY/jobs
https://api.lever.co/v0/postings/COMPANY?mode=json
```

A dead token is skipped with a log line, never fatal.

## 4. Location

`us_location_hints` is a plain list of cities, states and codes. For a local
search, cut it down to your metro. Two rules that will bite you:

- **Never add `remote`** — it makes "Remote in UK" look US based. Bare "Remote"
  is already handled.
- **Never add the codes `in`, `or`, `me`, `hi`, `de`, `la`, `ok`** — they are
  English words and match foreign locations. Use the city name.

Outside the US, set `us_only: false` and change `adzuna.country` (`gb`, `ca`,
`au`, `de`, ...).

## 5. Dates

`min_date_posted` drops anything older. Set it to the start of your hiring
cycle, or delete the line for no floor.

## Sanity check

Run it once, then read the log: `Total raw postings pulled` → `After filter` →
`NEW jobs added`.

- **Filtered down to ~0** → `include_title_any` too narrow, or a word in
  `exclude_title_any` is eating your titles (`lead ` and `principal` are the
  usual culprits).
- **Hundreds of junk rows** → tighten `include_title_any`, or add the offending
  words to `exclude_title_any`.

Adjust and rerun. Nothing is deleted, and duplicates are impossible, so
experimenting is cheap — but a bad filter can add junk rows you then have to
clear out by hand.
