#!/usr/bin/env python3
"""
One time (and safely repeatable) styling for the tracker sheet.

Applies the header style, column widths, row banding, the Status dropdown and
the colour rules. Formatting lives on the sheet, not in the rows, so new jobs
appended by main.py pick it up automatically and this only needs rerunning if
you change something here.

    python format_sheet.py

Reads the same SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON environment variables as
main.py, so `export $(grep -v '^#' .env | xargs)` first when running locally.
"""

import os
import sys
import json

import gspread
import yaml
from google.oauth2.service_account import Credentials

from main import COLUMNS, HEADER_LABELS, CONFIG_PATH

# --- palette ----------------------------------------------------------------
# Chosen to stay readable against black text and to keep the status colours
# distinguishable from each other at a glance.
SLATE_900 = {"red": 0.118, "green": 0.161, "blue": 0.231}   # header fill
WHITE     = {"red": 1.0, "green": 1.0, "blue": 1.0}
SLATE_50  = {"red": 0.973, "green": 0.980, "blue": 0.988}   # banding stripe
SLATE_400 = {"red": 0.580, "green": 0.639, "blue": 0.722}   # muted text
BLUE_700  = {"red": 0.114, "green": 0.306, "blue": 0.847}   # link text

STATUS_STYLES = [
    # (value, row background, text colour, strikethrough)
    ("Interested",   {"red": 0.996, "green": 0.953, "blue": 0.780}, None,      False),
    ("Applied",      {"red": 0.859, "green": 0.918, "blue": 0.996}, None,      False),
    ("Interviewing", {"red": 0.929, "green": 0.914, "blue": 0.996}, None,      False),
    ("Offer",        {"red": 0.863, "green": 0.988, "blue": 0.906}, None,      False),
    ("Rejected",     {"red": 0.996, "green": 0.886, "blue": 0.886}, SLATE_400, False),
    ("Skip",         {"red": 0.945, "green": 0.957, "blue": 0.976}, SLATE_400, True),
]
STATUS_VALUES = [s[0] for s in STATUS_STYLES]

# Column widths in pixels, in COLUMNS order. "key" is hidden so its width
# does not matter.
WIDTHS = [110, 165, 400, 210, 120, 175, 100, 100, 320, 100]


def col_letter(idx):
    return chr(ord("A") + idx)


def open_sheet():
    sheet_id = os.environ.get("SHEET_ID", "").strip()
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sheet_id or not raw:
        sys.exit("ERROR: set SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON first.")
    creds = Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(sheet_id)
    with open(CONFIG_PATH) as fh:
        ws_name = yaml.safe_load(fh)["sheet"]["worksheet"]
    return ss, ss.worksheet(ws_name)


def clear_previous(ss, sheet_id):
    """Drop banding and colour rules we added before, so rerunning this script
    restyles the sheet instead of stacking a second set of rules on top."""
    meta = ss.fetch_sheet_metadata()
    sheet = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == sheet_id)
    reqs = []
    for band in sheet.get("bandedRanges", []):
        reqs.append({"deleteBanding": {"bandedRangeId": band["bandedRangeId"]}})
    # Deleting by index shifts the rest, so always remove index 0.
    for _ in sheet.get("conditionalFormats", []):
        reqs.append({"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}})
    return reqs


def build_requests(sheet_id, n_cols):
    full = {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0,
            "endColumnIndex": n_cols}
    reqs = []

    # Freeze the header so it stays put while scrolling.
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount",
    }})

    # Header: dark bar, white bold text.
    reqs.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 0, "endColumnIndex": n_cols},
        "cell": {"userEnteredFormat": {
            "backgroundColor": SLATE_900,
            "horizontalAlignment": "LEFT",
            "verticalAlignment": "MIDDLE",
            "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": WHITE},
        }},
        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,"
                  "verticalAlignment,textFormat)",
    }})
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "ROWS",
                  "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 40}, "fields": "pixelSize",
    }})

    # Body: middle aligned, clipped so one long title cannot balloon a row.
    reqs.append({"repeatCell": {
        "range": dict(full),
        "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE",
                                       "wrapStrategy": "CLIP"}},
        "fields": "userEnteredFormat(verticalAlignment,wrapStrategy)",
    }})

    # Column widths, and hide the dedup key.
    for i, width in enumerate(WIDTHS[:n_cols]):
        props = {"pixelSize": width}
        fields = "pixelSize"
        if COLUMNS[i] == "key":
            props["hiddenByUser"] = True
            fields = "pixelSize,hiddenByUser"
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": props, "fields": fields,
        }})

    # Link column in blue so it reads as clickable.
    link_i = COLUMNS.index("url")
    reqs.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 1,
                  "startColumnIndex": link_i, "endColumnIndex": link_i + 1},
        "cell": {"userEnteredFormat": {"textFormat": {"foregroundColor": BLUE_700,
                                                      "underline": True}}},
        "fields": "userEnteredFormat.textFormat(foregroundColor,underline)",
    }})

    # Dates and short columns centred.
    for name in ("date_posted", "first_seen", "status"):
        i = COLUMNS.index(name)
        reqs.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1,
                      "startColumnIndex": i, "endColumnIndex": i + 1},
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.horizontalAlignment",
        }})

    # Zebra striping.
    reqs.append({"addBanding": {"bandedRange": {
        "range": dict(full),
        "rowProperties": {"firstBandColor": WHITE, "secondBandColor": SLATE_50},
    }}})

    # Status dropdown.
    status_i = COLUMNS.index("status")
    reqs.append({"setDataValidation": {
        "range": {"sheetId": sheet_id, "startRowIndex": 1,
                  "startColumnIndex": status_i, "endColumnIndex": status_i + 1},
        "rule": {
            "condition": {"type": "ONE_OF_LIST",
                          "values": [{"userEnteredValue": v} for v in STATUS_VALUES]},
            "showCustomUi": True,
            "strict": False,     # never reject a value you typed by hand
        },
    }})

    # Colour the whole row from the Status cell.
    for value, bg, fg, strike in STATUS_STYLES:
        fmt = {"backgroundColor": bg}
        text = {}
        if fg:
            text["foregroundColor"] = fg
        if strike:
            text["strikethrough"] = True
        if text:
            fmt["textFormat"] = text
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [dict(full)],
            "booleanRule": {
                "condition": {"type": "CUSTOM_FORMULA", "values": [
                    {"userEnteredValue": f'=$A2="{value}"'}]},
                "format": fmt,
            },
        }}})

    # Anything first seen today, still untouched, gets a highlighted date cell.
    seen_i = COLUMNS.index("first_seen")
    reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {
        "ranges": [{"sheetId": sheet_id, "startRowIndex": 1,
                    "startColumnIndex": seen_i, "endColumnIndex": seen_i + 1}],
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [
                {"userEnteredValue": '=AND($H2=TEXT(TODAY(),"yyyy-mm-dd"),$A2="")'}]},
            "format": {"backgroundColor": {"red": 0.996, "green": 0.906, "blue": 0.616},
                       "textFormat": {"bold": True}},
        },
    }}})

    return reqs


def main():
    ss, ws = open_sheet()
    n_cols = len(COLUMNS)

    ws.update(range_name="A1", values=[HEADER_LABELS], value_input_option="RAW")

    reqs = clear_previous(ss, ws.id) + build_requests(ws.id, n_cols)
    ss.batch_update({"requests": reqs})
    print(f"Formatted '{ws.title}': {len(reqs)} requests applied.")
    print(f"  header       {HEADER_LABELS}")
    print(f"  status list  {STATUS_VALUES}")


if __name__ == "__main__":
    main()
