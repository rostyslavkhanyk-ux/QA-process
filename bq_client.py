"""
QA Agent — BigQuery Client
Fetches calls + transcripts for the previous shift window.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from google.cloud import bigquery

import config

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config.GCP_KEY_PATH
_client: Optional[bigquery.Client] = None


def get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.BQ_PROJECT)
    return _client


def get_shift_window(for_date: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Return (shift_start, shift_end) UTC timestamps for the shift to evaluate.
    Default: yesterday 14:00 UTC → today 04:00 UTC.
    Covers all shift types (Day-weekday 16:00, Day-weekend 15:00, Evening 17:00, Night 20:00).
    """
    now = for_date or datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    shift_start = yesterday.replace(hour=config.SHIFT_START_UTC_HOUR)
    shift_end   = today.replace(hour=config.SHIFT_END_UTC_HOUR)

    return shift_start, shift_end


def fetch_calls(shift_start: datetime, shift_end: datetime) -> list[dict]:
    """
    Query BigQuery for all calls in the shift window longer than MIN_CALL_DURATION_SEC.
    Joins to Zoho contacts/deals and CallHippo webhook transcripts.
    Returns list of row dicts.
    """
    sql = f"""
WITH calls AS (
    SELECT
        call_sid,
        caller_name                        AS agent,
        `to`                               AS phone_dialled,
        call_started_at,
        call_duration_sec,
        ROUND(call_duration_sec / 60.0, 1) AS duration_min,
        recording_url,
        COALESCE(CAST(customer_id AS STRING), '') AS customer_id
    FROM `{config.BQ_CALLS_TABLE}`
    WHERE call_started_at >= TIMESTAMP('{shift_start.strftime("%Y-%m-%d %H:%M:%S")} UTC')
      AND call_started_at <  TIMESTAMP('{shift_end.strftime("%Y-%m-%d %H:%M:%S")} UTC')
      AND call_duration_sec > {config.MIN_CALL_DURATION_SEC}
      AND call_type = 'Outgoing'
),

deals AS (
    SELECT
        c.phone,
        d.id   AS deal_id,
        ROW_NUMBER() OVER (PARTITION BY c.phone ORDER BY d.created_time DESC) AS rn
    FROM `{config.BQ_CONTACTS_TABLE}` c
    JOIN `{config.BQ_DEALS_TABLE}` d
      ON d.contact_name = c.id
    WHERE c.phone IS NOT NULL
),

transcripts AS (
    SELECT
        call_sid,
        JSON_EXTRACT_SCALAR(raw_payload, '$.transcription')  AS transcription,
        JSON_EXTRACT_SCALAR(raw_payload, '$.aiCallSummary')  AS ai_summary
    FROM `{config.BQ_EVENTS_TABLE}`
    WHERE raw_payload LIKE '%transcription%'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY call_sid ORDER BY event_at DESC) = 1
)

SELECT
    c.call_sid,
    c.agent,
    FORMAT_TIMESTAMP('%Y-%m-%d %H:%M', c.call_started_at, 'UTC') AS call_time_utc,
    c.duration_min,
    c.customer_id,
    COALESCE(CAST(d.deal_id AS STRING), '')  AS deal_id,
    COALESCE(c.recording_url, '')            AS recording_url,
    COALESCE(t.transcription, '')            AS transcription,
    COALESCE(t.ai_summary, '')               AS ai_summary
FROM calls c
LEFT JOIN deals d
    ON d.phone = c.phone_dialled AND d.rn = 1
LEFT JOIN transcripts t
    ON t.call_sid = c.call_sid
ORDER BY c.agent, c.call_started_at
"""
    print(f"  Querying BigQuery: {shift_start:%Y-%m-%d %H:%M} → {shift_end:%Y-%m-%d %H:%M} UTC")
    rows = list(get_client().query(sql).result())
    result = [dict(r) for r in rows]
    print(f"  Found {len(result)} calls > {config.MIN_CALL_DURATION_SEC // 60} min")
    return result
