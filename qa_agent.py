#!/usr/bin/env python3
"""
QA Agent — Main Entry Point
Brighterly Closing Department

Usage:
    python qa_agent.py                    # evaluate previous shift
    python qa_agent.py --date 2026-04-15  # evaluate a specific shift date
    python qa_agent.py --dry-run          # fetch calls only, skip LLM evaluation
    python qa_agent.py --no-cache         # re-evaluate even if cached results exist
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
import bq_client
import evaluator
import report_html


def load_cache(report_dir: Path) -> Optional[dict]:
    cache_file = report_dir / "data.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    return None


def save_cache(report_dir: Path, data: dict):
    report_dir.mkdir(parents=True, exist_ok=True)
    with open(report_dir / "data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)


def save_html(report_dir: Path, html: str):
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "report.html"
    with open(path, "w") as f:
        f.write(html)
    return path


def build_report_data(date_str: str, shift_start, shift_end, evaluated_calls: list) -> dict:
    """Aggregate evaluated calls into a full report data structure."""
    agents = evaluator.aggregate_by_agent(evaluated_calls)

    qa_scores = [c["qa_pct"] for c in evaluated_calls if c.get("qa_pct") is not None]
    cq_scores = [c["cq_pct"] for c in evaluated_calls if c.get("cq_pct") is not None]
    total_flags = sum(a["critical_flags"] for a in agents.values())

    return {
        "date": date_str,
        "shift_window": {
            "start": shift_start.strftime("%Y-%m-%d %H:%M"),
            "end": shift_end.strftime("%Y-%m-%d %H:%M"),
        },
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "total_calls": len(evaluated_calls),
        "total_evaluated": len(qa_scores),
        "dept_avg_qa": round(sum(qa_scores) / len(qa_scores), 1) if qa_scores else None,
        "dept_avg_cq": round(sum(cq_scores) / len(cq_scores), 1) if cq_scores else None,
        "total_flags": total_flags,
        "agents": agents,
    }


def print_summary(report: dict):
    print("\n" + "═" * 60)
    print(f"  QA Report — {report['date']} Shift")
    print("═" * 60)
    print(f"  Total calls:   {report['total_calls']}")
    print(f"  Evaluated:     {report['total_evaluated']}")
    print(f"  Dept QA:       {report.get('dept_avg_qa', 'N/A')}%")
    print(f"  Dept CQ:       {report.get('dept_avg_cq', 'N/A')}%")
    print(f"  Critical flags:{report['total_flags']}")
    print("═" * 60)
    print("\n  Agent Summary:")
    print(f"  {'Agent':<30} {'Calls':>6} {'CQ%':>7} {'QA%':>7} {'Flags':>6}")
    print("  " + "-" * 58)
    sorted_agents = sorted(
        report["agents"].values(),
        key=lambda a: (a.get("avg_cq") or 0),
        reverse=True,
    )
    for a in sorted_agents:
        cq = f"{a['avg_cq']}%" if a.get("avg_cq") is not None else "N/A"
        qa = f"{a['avg_qa']}%" if a.get("avg_qa") is not None else "N/A"
        flag_str = f"⚠{a['critical_flags']}" if a["critical_flags"] else "—"
        print(f"  {a['name']:<30} {a['calls_total']:>6} {cq:>7} {qa:>7} {flag_str:>6}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Brighterly QA Agent")
    parser.add_argument("--date", help="Shift date to evaluate (YYYY-MM-DD). Default: yesterday.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch calls only, skip LLM evaluation.")
    parser.add_argument("--no-cache", action="store_true", help="Re-evaluate even if cached data exists.")
    args = parser.parse_args()

    # ── Determine shift window ──────────────────────────────────────────────────
    if args.date:
        try:
            base = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.")
            sys.exit(1)
        shift_start, shift_end = bq_client.get_shift_window(
            base.replace(hour=12)  # pass noon to get that day as "today"
        )
        date_str = args.date
    else:
        now = datetime.now(timezone.utc)
        shift_start, shift_end = bq_client.get_shift_window(now)
        date_str = shift_start.strftime("%Y-%m-%d")

    report_dir = config.REPORTS_DIR / date_str
    print(f"\nBrighterly QA Agent")
    print(f"Shift: {shift_start:%Y-%m-%d %H:%M} → {shift_end:%Y-%m-%d %H:%M} UTC")
    print(f"Output: {report_dir}\n")

    # ── Check cache ─────────────────────────────────────────────────────────────
    if not args.no_cache and not args.dry_run:
        cached = load_cache(report_dir)
        if cached:
            print("  Cached data found. Regenerating HTML report...")
            html = report_html.generate_html(cached)
            html_path = save_html(report_dir, html)
            print(f"  HTML report: {html_path}")
            print_summary(cached)
            return

    # ── Fetch calls from BigQuery ───────────────────────────────────────────────
    print("Fetching calls from BigQuery...")
    calls = bq_client.fetch_calls(shift_start, shift_end)

    if not calls:
        print("  No calls found for this shift window.")
        return

    if args.dry_run:
        print(f"\nDry run complete. {len(calls)} calls found:")
        for c in calls:
            print(f"  {c['agent']:<30} {c['duration_min']:>5} min  transcript:{bool(c.get('transcription'))}")
        return

    # ── Evaluate with Claude ────────────────────────────────────────────────────
    print(f"\nEvaluating {len(calls)} calls with Claude ({config.ANTHROPIC_MODEL})...")
    print(f"Concurrency: {config.EVAL_CONCURRENCY} parallel calls\n")

    evaluated = evaluator.evaluate_all(calls)

    # ── Build report data ───────────────────────────────────────────────────────
    report = build_report_data(date_str, shift_start, shift_end, evaluated)

    # ── Save ────────────────────────────────────────────────────────────────────
    save_cache(report_dir, report)
    html = report_html.generate_html(report)
    html_path = save_html(report_dir, html)

    print_summary(report)
    print(f"  HTML report saved: {html_path}")
    print(f"  JSON data saved:   {report_dir / 'data.json'}")

    # Open in browser on macOS
    import subprocess
    subprocess.run(["open", str(html_path)], check=False)


if __name__ == "__main__":
    main()
