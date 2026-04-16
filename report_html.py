"""
QA Agent — HTML Report Generator
Produces a single self-contained HTML report file.
"""

import json
from datetime import datetime
from typing import Optional
import config


# ─── Helpers ──────────────────────────────────────────────────────────────────

def score_color(pct: Optional[float]) -> str:
    if pct is None:
        return "#9CA3AF"
    if pct >= config.THRESHOLD_TARGET:
        return "#10B981"
    if pct >= config.THRESHOLD_POOR:
        return "#F59E0B"
    return "#EF4444"


def score_badge(pct: Optional[float]) -> str:
    if pct is None:
        return '<span class="badge badge-gray">N/A</span>'
    color = score_color(pct)
    if pct >= config.THRESHOLD_TARGET:
        label, cls = "Good", "badge-green"
    elif pct >= config.THRESHOLD_POOR:
        label, cls = "Average", "badge-amber"
    else:
        label, cls = "Poor", "badge-red"
    return f'<span class="badge {cls}">{label}</span>'


def pct_bar(score: int, max_score: int) -> str:
    if max_score == 0:
        return ""
    pct = score / max_score * 100
    color = score_color(pct)
    return f"""<div class="score-bar-wrap">
        <div class="score-bar-fill" style="width:{pct:.0f}%;background:{color}"></div>
        <span class="score-bar-label">{score}/{max_score}</span>
    </div>"""


def item_row(num: int, name: str, score: int, max_score: int, note: str) -> str:
    return f"""<tr>
        <td class="item-num">{num}</td>
        <td class="item-name">{name}</td>
        <td class="item-score">{pct_bar(score, max_score)}</td>
        <td class="item-note">{note}</td>
    </tr>"""


def flag_badge(flag_data: dict) -> str:
    result = flag_data.get("result", "")
    if result == "flagged" or result == "unable":
        flags = flag_data.get("flags", [])
        detail = "; ".join(flags) if flags else flag_data.get("note", "")
        return f'<span class="flag-critical">⚠ {detail}</span>'
    return '<span class="flag-ok">✓ OK</span>'


def recording_link(url: str, deal_id: str, customer_id: str) -> str:
    parts = []
    if url:
        parts.append(f'<a href="{url}" target="_blank" class="link-btn">Recording</a>')
    if deal_id:
        zoho = config.ZOHO_URL.format(deal_id=deal_id)
        parts.append(f'<a href="{zoho}" target="_blank" class="link-btn">CRM</a>')
    if customer_id:
        app = config.APP_URL.format(customer_id=customer_id)
        parts.append(f'<a href="{app}" target="_blank" class="link-btn">APP</a>')
    return " ".join(parts) if parts else "—"


# ─── Call scorecard section ────────────────────────────────────────────────────

def render_call_card(call: dict, idx: int) -> str:
    ev = call.get("evaluation")
    qa = call.get("qa_pct")
    cq = call.get("cq_pct")
    call_id = f"call-{idx}"

    header_color = score_color(cq)

    # Meta line
    links = recording_link(
        call.get("recording_url", ""),
        call.get("deal_id", ""),
        call.get("customer_id", ""),
    )
    call_type = ev.get("call_type", "?").upper() if ev else "?"

    meta = f"""<div class="call-meta">
        <span class="call-time">{call.get('call_time_utc','?')} UTC</span>
        <span class="call-dur">{call.get('duration_min','?')} min</span>
        <span class="call-type-badge">{call_type}</span>
        {links}
    </div>"""

    if not ev:
        return f"""<div class="call-card" id="{call_id}">
            <div class="call-card-header" style="border-left:4px solid #9CA3AF">
                {meta}
                <span class="no-transcript">No transcript available</span>
            </div>
        </div>"""

    # Score pills
    qa_color = score_color(qa)
    cq_color = score_color(cq)
    score_pills = f"""
        <span class="score-pill" style="background:{cq_color}">CQ {cq}%</span>
        <span class="score-pill" style="background:{qa_color}">QA {qa}%</span>
    """

    # Scorecard table — Block 1
    b1_rows = ""
    for num, info in config.BLOCK1.items():
        item = ev["items"].get(str(num), {})
        b1_rows += item_row(num, info["name"], item.get("score", 0), info["max"], item.get("note", ""))

    # Scorecard table — Block 2
    b2_rows = ""
    for num, info in config.BLOCK2.items():
        item = ev["items"].get(str(num), {})
        b2_rows += item_row(num, info["name"], item.get("score", 0), info["max"], item.get("note", ""))

    # Critical flags
    flags = ev.get("critical_flags", {})
    flag23 = flags.get("23", {})
    flag24 = flags.get("24", {})
    flag_section = f"""<div class="flags-row">
        <div class="flag-item"><strong>Item 23 — Product Awareness:</strong> {flag_badge(flag23)} <span class="flag-note">{flag23.get('note','')}</span></div>
        <div class="flag-item"><strong>Item 24 — Correct Information:</strong> {flag_badge(flag24)} <span class="flag-note">{flag24.get('note','')}</span></div>
    </div>"""

    # Feedback
    strengths_html = "".join(f"<li>{s}</li>" for s in ev.get("strengths", []))
    improvements_html = "".join(f"<li>{s}</li>" for s in ev.get("improvements", []))
    feedback_html = f"""<div class="call-feedback">
        <div class="feedback-summary">{ev.get('feedback_summary','')}</div>
        <div class="feedback-cols">
            <div class="feedback-col strengths-col">
                <h5>✓ Strengths</h5><ul>{strengths_html}</ul>
            </div>
            <div class="feedback-col improvements-col">
                <h5>→ Areas for improvement</h5><ul>{improvements_html}</ul>
            </div>
        </div>
    </div>"""

    # AI summary
    ai_summary = call.get("ai_summary", "")
    ai_html = f'<div class="ai-summary"><strong>AI Summary:</strong> {ai_summary}</div>' if ai_summary else ""

    return f"""<div class="call-card" id="{call_id}">
        <div class="call-card-header" style="border-left:4px solid {header_color}" onclick="toggleCall('{call_id}')">
            {meta}
            <div class="call-scores">{score_pills}</div>
            <span class="toggle-icon">▾</span>
        </div>
        <div class="call-card-body" id="{call_id}-body">
            {ai_html}
            {feedback_html}
            <div class="scorecard-tables">
                <div class="scorecard-block">
                    <h5 class="block-title">Block 1 — CQ Score (max {config.CQ_MAX})</h5>
                    <table class="scorecard-table">
                        <thead><tr><th>#</th><th>Item</th><th>Score</th><th>Notes</th></tr></thead>
                        <tbody>{b1_rows}</tbody>
                    </table>
                </div>
                <div class="scorecard-block">
                    <h5 class="block-title">Block 2 — Obligatory Phrases (max {sum(v['max'] for v in config.BLOCK2.values())})</h5>
                    <table class="scorecard-table">
                        <thead><tr><th>#</th><th>Item</th><th>Score</th><th>Notes</th></tr></thead>
                        <tbody>{b2_rows}</tbody>
                    </table>
                </div>
            </div>
            {flag_section}
        </div>
    </div>"""


# ─── Agent section ─────────────────────────────────────────────────────────────

def render_agent_section(agent_data: dict) -> str:
    name = agent_data["name"]
    avg_qa = agent_data.get("avg_qa")
    avg_cq = agent_data.get("avg_cq")
    total = agent_data["calls_total"]
    evaluated = agent_data["calls_evaluated"]
    flags = agent_data["critical_flags"]

    qa_color = score_color(avg_qa)
    cq_color = score_color(avg_cq)

    agent_id = name.replace(" ", "-").replace(".", "")

    call_cards = "".join(
        render_call_card(c, f"{agent_id}-{i}")
        for i, c in enumerate(agent_data["calls"])
    )

    strengths_li = "".join(f"<li>{s}</li>" for s in agent_data.get("top_strengths", []))
    improvements_li = "".join(f"<li>{i}</li>" for i in agent_data.get("top_improvements", []))

    feedback_block = f"""<div class="agent-feedback-block">
        <div class="agent-feedback-col">
            <h4>✓ Common Strengths</h4>
            <ul class="feedback-list">{strengths_li if strengths_li else '<li>—</li>'}</ul>
        </div>
        <div class="agent-feedback-col">
            <h4>→ Focus Areas</h4>
            <ul class="feedback-list">{improvements_li if improvements_li else '<li>—</li>'}</ul>
        </div>
    </div>"""

    flag_badge_html = f'<span class="flag-count {"flag-count-bad" if flags > 0 else "flag-count-ok"}">⚠ {flags} flag{"s" if flags != 1 else ""}</span>' if flags else ""

    return f"""<div class="agent-section">
        <div class="agent-header" onclick="toggleAgent('{agent_id}')">
            <div class="agent-name">{name}</div>
            <div class="agent-stats">
                <span class="stat-pill">{total} call{"s" if total != 1 else ""}</span>
                <span class="score-pill" style="background:{cq_color}">CQ {avg_cq if avg_cq is not None else 'N/A'}%</span>
                <span class="score-pill" style="background:{qa_color}">QA {avg_qa if avg_qa is not None else 'N/A'}%</span>
                {flag_badge_html}
            </div>
            <span class="toggle-icon">▾</span>
        </div>
        <div class="agent-body" id="{agent_id}-body">
            {feedback_block}
            <div class="call-list">{call_cards}</div>
        </div>
    </div>"""


# ─── Leaderboard ───────────────────────────────────────────────────────────────

def render_leaderboard(agents: dict, sort_by: str = "avg_cq") -> str:
    sorted_agents = sorted(
        agents.values(),
        key=lambda a: (a.get(sort_by) or 0),
        reverse=True
    )
    rows = ""
    for rank, a in enumerate(sorted_agents, 1):
        qa = a.get("avg_qa")
        cq = a.get("avg_cq")
        qa_color = score_color(qa)
        cq_color = score_color(cq)
        flags = a["critical_flags"]

        cq_cell = f'<td style="color:{cq_color};font-weight:600">{cq}%</td>' if cq is not None else '<td>—</td>'
        qa_cell = f'<td style="color:{qa_color};font-weight:600">{qa}%</td>' if qa is not None else '<td>—</td>'
        flag_cell = f'<td class="flag-cell-bad">⚠ {flags}</td>' if flags > 0 else '<td class="flag-cell-ok">—</td>'

        agent_id = a["name"].replace(" ", "-").replace(".", "")
        rows += f"""<tr onclick="scrollToAgent('{agent_id}')" style="cursor:pointer">
            <td class="rank-cell">#{rank}</td>
            <td class="agent-name-cell">{a['name']}</td>
            <td>{a['calls_evaluated']}/{a['calls_total']}</td>
            {cq_cell}
            {qa_cell}
            {flag_cell}
        </tr>"""

    return f"""<table class="leaderboard-table" id="leaderboard">
        <thead>
            <tr>
                <th>Rank</th>
                <th>Agent</th>
                <th>Calls</th>
                <th onclick="sortTable('avg_cq')" class="sortable">CQ% ↕</th>
                <th onclick="sortTable('avg_qa')" class="sortable">QA% ↕</th>
                <th>Flags</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""


# ─── Summary cards ─────────────────────────────────────────────────────────────

def render_summary_cards(report: dict) -> str:
    total_calls = report["total_calls"]
    total_evaluated = report["total_evaluated"]
    avg_qa = report.get("dept_avg_qa")
    avg_cq = report.get("dept_avg_cq")
    flags = report["total_flags"]

    qa_color = score_color(avg_qa)
    cq_color = score_color(avg_cq)

    def stat_card(label, value, color="#1E3A8A", icon=""):
        return f"""<div class="stat-card">
            <div class="stat-icon">{icon}</div>
            <div class="stat-value" style="color:{color}">{value}</div>
            <div class="stat-label">{label}</div>
        </div>"""

    return f"""<div class="summary-cards">
        {stat_card("Total Calls", total_calls, icon="📞")}
        {stat_card("Evaluated", total_evaluated, icon="✓")}
        {stat_card("Dept. CQ Score", f"{avg_cq}%" if avg_cq else "N/A", cq_color, icon="🎯")}
        {stat_card("Dept. QA Score", f"{avg_qa}%" if avg_qa else "N/A", qa_color, icon="📊")}
        {stat_card("Critical Flags", flags, "#EF4444" if flags > 0 else "#10B981", icon="⚠")}
    </div>"""


# ─── Full HTML ─────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #F1F5F9; color: #1E293B; font-size: 14px; }
a { color: inherit; text-decoration: none; }

/* Header */
.report-header { background: #0D1B40; color: white; padding: 24px 32px; display:flex;
    justify-content: space-between; align-items: center; }
.report-title { font-size: 22px; font-weight: 700; }
.report-subtitle { font-size: 13px; color: #94A3B8; margin-top: 4px; }
.header-badge { background: #1E3A8A; padding: 8px 16px; border-radius: 8px;
    font-size: 12px; color: #93C5FD; }

/* Layout */
.container { max-width: 1400px; margin: 0 auto; padding: 24px 32px; }
section { margin-bottom: 32px; }
.section-title { font-size: 18px; font-weight: 700; color: #0D1B40;
    margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #E2E8F0; }

/* Summary cards */
.summary-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; }
.stat-card { background: white; border-radius: 12px; padding: 20px; text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.stat-icon { font-size: 24px; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 700; }
.stat-label { font-size: 12px; color: #64748B; margin-top: 4px; text-transform: uppercase;
    letter-spacing: .5px; }

/* Leaderboard */
.leaderboard-wrap { background: white; border-radius: 12px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.leaderboard-table { width: 100%; border-collapse: collapse; }
.leaderboard-table th { background: #F8FAFC; padding: 12px 16px; text-align: left;
    font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: #64748B;
    border-bottom: 2px solid #E2E8F0; }
.leaderboard-table td { padding: 12px 16px; border-bottom: 1px solid #F1F5F9; }
.leaderboard-table tr:hover td { background: #F8FAFC; }
.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: #1E3A8A; }
.rank-cell { font-weight: 700; color: #64748B; }
.agent-name-cell { font-weight: 600; }
.flag-cell-bad { color: #EF4444; font-weight: 600; }
.flag-cell-ok { color: #94A3B8; }

/* Score pills */
.score-pill { display: inline-block; padding: 3px 10px; border-radius: 20px;
    color: white; font-size: 12px; font-weight: 600; margin-left: 4px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
    font-weight: 600; }
.badge-green { background: #D1FAE5; color: #065F46; }
.badge-amber { background: #FEF3C7; color: #92400E; }
.badge-red { background: #FEE2E2; color: #991B1B; }
.badge-gray { background: #F1F5F9; color: #475569; }

/* Agent sections */
.agent-section { background: white; border-radius: 12px; margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08); overflow: hidden; }
.agent-header { display: flex; align-items: center; padding: 16px 20px;
    cursor: pointer; user-select: none; border-left: 4px solid #1E3A8A;
    transition: background .15s; }
.agent-header:hover { background: #F8FAFC; }
.agent-name { font-size: 16px; font-weight: 700; flex: 1; }
.agent-stats { display: flex; align-items: center; gap: 6px; }
.stat-pill { background: #E2E8F0; color: #475569; padding: 3px 10px;
    border-radius: 20px; font-size: 12px; }
.flag-count { padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.flag-count-bad { background: #FEE2E2; color: #991B1B; }
.flag-count-ok { background: #D1FAE5; color: #065F46; }
.toggle-icon { margin-left: 12px; color: #94A3B8; font-size: 18px; transition: transform .2s; }
.toggle-icon.open { transform: rotate(180deg); }

.agent-body { padding: 0 20px 20px; display: none; }
.agent-body.open { display: block; }

/* Agent feedback */
.agent-feedback-block { display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
    margin: 16px 0; padding: 16px; background: #F8FAFC; border-radius: 8px; }
.agent-feedback-col h4 { font-size: 13px; font-weight: 700; margin-bottom: 8px;
    color: #475569; text-transform: uppercase; letter-spacing: .4px; }
.feedback-list { padding-left: 16px; }
.feedback-list li { margin-bottom: 6px; font-size: 13px; color: #334155; }

/* Call cards */
.call-card { border: 1px solid #E2E8F0; border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.call-card-header { display: flex; align-items: center; padding: 12px 16px; cursor: pointer;
    gap: 12px; flex-wrap: wrap; background: #FAFAFA; transition: background .15s; }
.call-card-header:hover { background: #F1F5F9; }
.call-meta { display: flex; align-items: center; gap: 10px; flex: 1; flex-wrap: wrap; }
.call-time { font-size: 12px; color: #64748B; }
.call-dur { font-weight: 600; }
.call-type-badge { background: #EEF2FF; color: #4F46E5; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600; }
.call-scores { display: flex; gap: 6px; }
.no-transcript { font-size: 12px; color: #94A3B8; font-style: italic; }

.call-card-body { padding: 16px; display: none; }
.call-card-body.open { display: block; }

/* Link buttons */
.link-btn { background: #EFF6FF; color: #1D4ED8; padding: 3px 10px; border-radius: 4px;
    font-size: 12px; font-weight: 500; }
.link-btn:hover { background: #DBEAFE; }

/* AI Summary */
.ai-summary { background: #F0FDF4; border-left: 3px solid #10B981; padding: 10px 14px;
    border-radius: 0 6px 6px 0; margin-bottom: 12px; font-size: 13px; color: #166534; }

/* Call feedback */
.call-feedback { margin-bottom: 16px; }
.feedback-summary { color: #334155; font-size: 13px; line-height: 1.6;
    background: #F8FAFC; padding: 12px; border-radius: 6px; margin-bottom: 10px; }
.feedback-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.feedback-col h5 { font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .4px; margin-bottom: 6px; }
.strengths-col h5 { color: #065F46; }
.improvements-col h5 { color: #92400E; }
.feedback-col ul { padding-left: 16px; }
.feedback-col li { font-size: 13px; margin-bottom: 4px; color: #334155; }

/* Scorecard tables */
.scorecard-tables { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px; }
.scorecard-block h5 { font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .4px; color: #475569; margin-bottom: 8px; }
.block-title { border-bottom: 1px solid #E2E8F0; padding-bottom: 6px; }
.scorecard-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.scorecard-table th { background: #F1F5F9; padding: 6px 8px; text-align: left;
    color: #64748B; font-weight: 600; border-bottom: 1px solid #E2E8F0; }
.scorecard-table td { padding: 6px 8px; border-bottom: 1px solid #F8FAFC; vertical-align: middle; }
.item-num { font-weight: 700; color: #64748B; width: 28px; }
.item-name { font-weight: 500; color: #334155; }
.item-note { color: #64748B; font-style: italic; max-width: 200px; }
.item-score { width: 120px; }

/* Score bar */
.score-bar-wrap { position: relative; background: #F1F5F9; border-radius: 4px;
    height: 20px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 4px; transition: width .3s; }
.score-bar-label { position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
    font-size: 11px; font-weight: 700; color: #1E293B; }

/* Flags */
.flags-row { display: flex; gap: 12px; flex-wrap: wrap; padding: 10px;
    background: #FFF7ED; border-radius: 6px; margin-top: 8px; }
.flag-item { font-size: 12px; }
.flag-critical { color: #B45309; font-weight: 600; }
.flag-ok { color: #065F46; }
.flag-note { color: #64748B; font-style: italic; }

/* Footer */
.report-footer { text-align: center; padding: 24px; color: #94A3B8; font-size: 12px; }

@media (max-width: 900px) {
    .summary-cards { grid-template-columns: repeat(3, 1fr); }
    .scorecard-tables { grid-template-columns: 1fr; }
    .feedback-cols { grid-template-columns: 1fr; }
    .agent-feedback-block { grid-template-columns: 1fr; }
}
"""

JS = """
function toggleAgent(id) {
    const body = document.getElementById(id + '-body');
    const header = body.previousElementSibling;
    const icon = header.querySelector('.toggle-icon');
    body.classList.toggle('open');
    icon.classList.toggle('open');
}

function toggleCall(id) {
    const body = document.getElementById(id + '-body');
    const header = body.previousElementSibling;
    const icon = header.querySelector('.toggle-icon');
    body.classList.toggle('open');
    icon.classList.toggle('open');
}

function scrollToAgent(id) {
    const el = document.querySelector('.agent-section .agent-header');
    const sections = document.querySelectorAll('.agent-section');
    for (const s of sections) {
        const header = s.querySelector('.agent-header');
        const agentName = header.querySelector('.agent-name');
        if (agentName && agentName.textContent.replace(/\\s+/g,'-').replace(/\\./g,'') === id) {
            s.scrollIntoView({behavior:'smooth', block:'start'});
            const body = s.querySelector('.agent-body');
            const icon = header.querySelector('.toggle-icon');
            if (!body.classList.contains('open')) {
                body.classList.add('open');
                icon.classList.add('open');
            }
            return;
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Auto-open agents with poor CQ scores
    document.querySelectorAll('.score-pill').forEach(function(pill) {
        const txt = pill.textContent;
        const match = txt.match(/CQ (\\d+\\.?\\d*)%/);
        if (match && parseFloat(match[1]) < 70) {
            const agentSection = pill.closest('.agent-section');
            if (agentSection) {
                const body = agentSection.querySelector('.agent-body');
                const icon = agentSection.querySelector('.toggle-icon');
                if (body && !body.classList.contains('open')) {
                    body.classList.add('open');
                    if (icon) icon.classList.add('open');
                }
            }
        }
    });
});
"""


def generate_html(report: dict) -> str:
    date_str = report["date"]
    shift_start = report["shift_window"]["start"]
    shift_end = report["shift_window"]["end"]
    generated_at = report.get("generated_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    summary_html = render_summary_cards(report)

    agents = report["agents"]
    leaderboard_html = render_leaderboard(agents)

    # Sort agents by avg_cq descending for detail sections
    sorted_agents = sorted(agents.values(), key=lambda a: (a.get("avg_cq") or 0), reverse=True)
    agent_sections_html = "".join(render_agent_section(a) for a in sorted_agents)

    # Flagged calls section
    flagged_calls = []
    for a in sorted_agents:
        for call in a["calls"]:
            ev = call.get("evaluation", {})
            if ev:
                f24 = ev.get("critical_flags", {}).get("24", {})
                f23 = ev.get("critical_flags", {}).get("23", {})
                if f24.get("result") == "flagged" or f23.get("result") == "unable":
                    flagged_calls.append((a["name"], call))

    flags_html = ""
    if flagged_calls:
        flag_items = ""
        for agent_name, call in flagged_calls:
            ev = call["evaluation"]
            f23 = ev.get("critical_flags", {}).get("23", {})
            f24 = ev.get("critical_flags", {}).get("24", {})
            flags_detail = "; ".join(f24.get("flags", [])) or f24.get("note", "")
            flag_items += f"""<div class="flag-call-card">
                <div class="flag-call-header">
                    <strong>{agent_name}</strong>
                    <span>{call.get('call_time_utc','')} UTC</span>
                    <span>{call.get('duration_min','')} min</span>
                    {recording_link(call.get('recording_url',''), call.get('deal_id',''), call.get('customer_id',''))}
                </div>
                <div class="flag-call-body">
                    {'<div class="flag-item"><strong>Product Awareness:</strong> <span class="flag-critical">Unable to answer</span> — ' + f23.get("note","") + '</div>' if f23.get('result') == 'unable' else ''}
                    {'<div class="flag-item"><strong>Critical Info:</strong> <span class="flag-critical">⚠ ' + flags_detail + '</span></div>' if f24.get('result') == 'flagged' else ''}
                </div>
            </div>"""

        flags_html = f"""<section>
            <h2 class="section-title" style="color:#EF4444">⚠ Critical Flags ({len(flagged_calls)} calls)</h2>
            <div class="flagged-calls">{flag_items}</div>
        </section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brighterly QA Report — {date_str}</title>
<style>
{CSS}
.flagged-calls {{ display: grid; gap: 12px; }}
.flag-call-card {{ background: #FFF5F5; border: 1px solid #FCA5A5; border-left: 4px solid #EF4444;
    border-radius: 8px; overflow: hidden; }}
.flag-call-header {{ padding: 12px 16px; display: flex; gap: 12px; align-items: center;
    flex-wrap: wrap; background: #FEE2E2; font-size: 13px; }}
.flag-call-body {{ padding: 12px 16px; }}
.flag-item {{ margin-bottom: 6px; font-size: 13px; }}
</style>
</head>
<body>

<div class="report-header">
    <div>
        <div class="report-title">Brighterly QA Report</div>
        <div class="report-subtitle">Closing Department · {date_str} Shift</div>
    </div>
    <div class="header-badge">
        Shift window: {shift_start} – {shift_end} UTC<br>
        Generated: {generated_at}
    </div>
</div>

<div class="container">

    <section>
        <h2 class="section-title">Department Overview</h2>
        {summary_html}
    </section>

    <section>
        <h2 class="section-title">Agent Leaderboard</h2>
        <div class="leaderboard-wrap">{leaderboard_html}</div>
    </section>

    {flags_html}

    <section>
        <h2 class="section-title">Call Details by Agent</h2>
        <p style="font-size:12px;color:#64748B;margin-bottom:12px">
            Click agent row to expand. Calls are sorted by time.
            Agents with CQ &lt; {config.THRESHOLD_POOR}% are auto-expanded.
        </p>
        {agent_sections_html}
    </section>

</div>

<div class="report-footer">
    Brighterly QA System · Powered by Claude · All feedback pending Ron &amp; Daryna review before sending to agents
</div>

<script>{JS}</script>
</body>
</html>"""
