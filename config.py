"""
QA Agent — Configuration
Brighterly Closing Department
"""

import os
from pathlib import Path

# ─── Credentials ───────────────────────────────────────────────────────────────
GCP_KEY_PATH = "/Users/rostyslav.khanyk/Desktop/MD files /gcp-key.json"
BQ_PROJECT   = "brighterly-gcp"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = "claude-opus-4-6"  # highest quality for evaluation

# ─── Shift Window ───────────────────────────────────────────────────────────────
# Cron runs at 08:00 Kyiv (UTC+3 = 05:00 UTC).
# "Previous shift" = yesterday 14:00 UTC → today 04:00 UTC
# Covers Day-weekday (16:00), Day-weekend (15:00), Evening (17:00), Night (20:00)
SHIFT_START_UTC_HOUR = 14   # start of earliest possible shift
SHIFT_END_UTC_HOUR   = 4    # end of latest possible shift (next calendar day)

# Minimum call duration for QA review
MIN_CALL_DURATION_SEC = 360  # 6 minutes

# ─── BigQuery Tables ────────────────────────────────────────────────────────────
BQ_CALLS_TABLE    = "brighterly-gcp.staging.stg_callhippo_calls"
BQ_EVENTS_TABLE   = "brighterly-gcp.staging.stg_callhippo_wh_events"
BQ_CONTACTS_TABLE = "brighterly-gcp.zoho_tables.contacts"
BQ_DEALS_TABLE    = "brighterly-gcp.zoho_tables.deals"

# ─── URL Templates ──────────────────────────────────────────────────────────────
ZOHO_URL = "https://zcrm.zoho.eu/brighterly/index.do/cxapp/crm/org20079913819/tab/Potentials/{deal_id}"
APP_URL  = "https://app.brighterly.com/admin/customers/{customer_id}"

# ─── Paths ──────────────────────────────────────────────────────────────────────
QA_PROCESS_DIR = Path(__file__).parent
REPORTS_DIR    = QA_PROCESS_DIR / "reports"

# ─── QA Scorecard ───────────────────────────────────────────────────────────────
#
# Block 1 → CQ Score  (items 1–16)
# Block 2 → QA only   (items 17–22)
# Block 3 → Flags     (items 23–24, not scored)
#

BLOCK1 = {
    1:  {"name": "Mandatory Questions",                     "max": 2},
    2:  {"name": "Quality of Dialogue & Needs Uncovering",  "max": 4},
    3:  {"name": "Voicing Strong & Weak Sides",             "max": 2},
    4:  {"name": "Creating Urgency",                        "max": 3},
    5:  {"name": "Dialogue with Client (Feedback Section)", "max": 3},
    6:  {"name": "Pitches & Mirroring",                     "max": 3},
    7:  {"name": "Mandatory Benefits",                      "max": 3},
    8:  {"name": "Additional Benefits",                     "max": 3},
    9:  {"name": "Visual Price Presentation",               "max": 2},
    10: {"name": "Subscription Explanation",                "max": 3},
    11: {"name": "Authority & Recommendation",              "max": 3},
    12: {"name": "Payment on a Call",                       "max": 4},
    13: {"name": "Finding the Real Objection",              "max": 5},
    14: {"name": "Continuation of Objection Handling",      "max": 5},
    15: {"name": "Securing Strong Commitment",              "max": 2},
    16: {"name": "Good Rapport",                            "max": 5},
}

BLOCK2 = {
    17: {"name": "Premium Teachers",      "max": 4},
    18: {"name": "Handling No on PT",     "max": 2},
    19: {"name": "Upsale Flow",           "max": 5},
    20: {"name": "Cancellation Policy",   "max": 3},
    21: {"name": "Auto-Renewal",          "max": 3},
    22: {"name": "Aftersale Phrases",     "max": 2},
}

BLOCK3 = {
    23: {"name": "Product Awareness"},
    24: {"name": "Correct Crucial Information"},
}

CQ_MAX = sum(v["max"] for v in BLOCK1.values())   # 52
QA_MAX = CQ_MAX + sum(v["max"] for v in BLOCK2.values())  # 71

# Score thresholds
THRESHOLD_POOR   = 70   # CQ < 70 → flag immediately
THRESHOLD_TARGET = 80   # target 80+

# Concurrency for async Claude evaluations
EVAL_CONCURRENCY = 5
