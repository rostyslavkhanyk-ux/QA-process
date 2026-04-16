"""
QA Agent — LLM Evaluator (Ollama — no API key required)
Scores each call using a local AI model via Ollama.
"""

import json
import asyncio
import re
import requests
import concurrent.futures
from typing import Optional

import config

OLLAMA_URL = "http://localhost:11434/api/chat"

# ─── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a certified QA evaluator for Brighterly's Closing Department — an EdTech company selling personalized Math & ELA tutoring for kids (B2C, USA market). Closing agents call parents who just had a demo lesson and try to sell a subscription.

Your job: score each call using the QA scorecard below and provide specific, actionable feedback.

═══════════════════════════════════════════════════════════════
BLOCK 1 — CQ SCORE (items 1–16, max 52 points)
═══════════════════════════════════════════════════════════════

Item 1 — Mandatory Questions (max 2)
• If client volunteers all info themselves → max score
• Score what was ACTUALLY uncovered, not just whether questions were asked

Item 2 — Quality of Dialogue & Needs Uncovering (max 4)
• 4/4 = 2–3 specific needs uncovered, conversation natural and adaptive
• 2/4 = needs partially uncovered, surface level
• 0/4 = no needs uncovered, scripty/rigid flow

Item 3 — Voicing Strong & Weak Sides (max 2)
• Both strong AND weak sides of child must be mentioned
• Exclusion: client already knows feedback OR no feedback given after demo

Item 4 — Creating Urgency (max 3)
• 3/3 = strong, unprompted urgency — snowball language, foundation risk, falling behind
• 1/3 = urgency present but weak
• 0/3 = no urgency at all
• Exclusion: client said they want to start ASAP
• A single urgency pitch = 1, not 3

Item 5 — Dialogue with Client — FEEDBACK SECTION ONLY (max 3)
• Evaluated ONLY during the feedback/teacher evaluation section
• Discovery dialogue does NOT count here
• 3/3 = natural back-and-forth during feedback delivery
• 1/3 = one question asked during feedback
• 0/3 = agent monologues through feedback

Item 6 — Pitches & Mirroring (max 3)
• Evaluated across ENTIRE call
• Agent must mirror client's own words and needs
• 3+ targeted personalized pitches = 3/3

Item 7 — Mandatory Benefits (max 3)
• Personalization beats completeness
• Benefits must be relevant to THIS specific client's needs

Item 8 — Additional Benefits (max 3)
• Same as item 7
• Agent responding to client questions with relevant benefits = 3/3

Item 9 — Visual Price Presentation (max 2)
• Link MUST be sent BEFORE or DURING price explanation — NOT after
• Link sent AFTER price explanation = 0/2
• Client already on pricing page = max

Item 10 — Subscription Explanation (max 3)
• Brief and clear = max
• Must cover pace/period logic at minimum

Item 11 — Authority & Recommendation (max 3)
• Client chose own plan AND is confident = max
• "Okay got it" with no reinforcement = 0/3

Item 12 — Payment on a Call (max 4)
• Evaluates ONLY whether payment was prompted with discount urgency
• Discount + time limit + payment prompted = max
• Client stated financial impossibility earlier = max (don't push)

Item 13 — Finding the Real Objection (max 5)
• No objections = max automatically
• Only probe when objection is unclear

Item 14 — Continuation of Objection Handling (max 5)
• No objections = max automatically
• Summer/future start: reservation must be offered
• Confirming budget + exploring options + scheduling callback = max
• Booking callback alone = item 15, not 14

Item 15 — Securing Strong Commitment (max 2)
• No objections = max automatically
• Must agree on specific date AND time
• "I'll message you" = 0/2

Item 16 — Good Rapport (max 5)
• Natural, warm, confident = 5/5
• Neutral and polite but flat = 2/5
• Negative or reads script = 0/5

═══════════════════════════════════════════════════════════════
BLOCK 2 — OBLIGATORY PHRASES (items 17–22, max 19 points)
Affects QA score but NOT CQ score.
═══════════════════════════════════════════════════════════════

Item 17 — Premium Teachers (max 4)
• No sale = max automatically
• On a sale call: must present Premium Teachers with all 5 benefit points

Item 18 — Handling No on PT (max 2)
• No sale = max automatically
• Client gives ANY clear reason for declining = 2/2

Item 19 — Upsale Flow (max 5)
• Client confirms no need for other subject = max
• Both Math AND ELA already being sold = max
• Agent skips completely when need exists = 0/5

Item 20 — Cancellation Policy (max 3)
• Client doesn't ask = max — NEVER volunteer
• If client asks: clarify WHY first → add value → explain policy

Item 21 — Auto-Renewal (max 3)
• Must be explained on every call, framed as benefit
• Missing = 0/3

Item 22 — Aftersale Phrases (max 2)
• No sale = max automatically
• Must cover: reschedule 6h rule, support contacts, teacher change, learning policies email

═══════════════════════════════════════════════════════════════
BLOCK 3 — CRITICAL FLAGS (items 23–24, not scored)
═══════════════════════════════════════════════════════════════

Item 23 — Product Awareness
• "able" = answered all product questions correctly
• "unable" = couldn't answer competence questions

Item 24 — Correct Crucial Information
HARD FLAG TRIGGERS:
- Lesson is 1 hour long (it's 45 min)
- All teachers are Americans / don't have an accent
- Promising a certain teacher
- Free rescheduling after 6h before lesson
- Refunding bonus lessons
- Cancellation if notified after 48h before billing day
- Offering to return funds to make a sale
- Promising to hold discounts beyond expiry

═══════════════════════════════════════════════════════════════
CALL TYPES: "sale", "no_sale", "unclear"
═══════════════════════════════════════════════════════════════

You MUST respond with valid JSON only — no explanation, no markdown, just the JSON object."""

USER_PROMPT_TEMPLATE = """Score this call and return JSON.

AGENT: {agent}
DURATION: {duration_min} min
AI SUMMARY: {ai_summary}

TRANSCRIPT:
{transcript}

Return this exact JSON structure with real scores filled in:
{{
  "call_type": "sale",
  "items": {{
    "1":  {{"score": 2, "max": 2,  "note": "reason"}},
    "2":  {{"score": 3, "max": 4,  "note": "reason"}},
    "3":  {{"score": 2, "max": 2,  "note": "reason"}},
    "4":  {{"score": 2, "max": 3,  "note": "reason"}},
    "5":  {{"score": 2, "max": 3,  "note": "reason"}},
    "6":  {{"score": 2, "max": 3,  "note": "reason"}},
    "7":  {{"score": 3, "max": 3,  "note": "reason"}},
    "8":  {{"score": 2, "max": 3,  "note": "reason"}},
    "9":  {{"score": 2, "max": 2,  "note": "reason"}},
    "10": {{"score": 2, "max": 3,  "note": "reason"}},
    "11": {{"score": 2, "max": 3,  "note": "reason"}},
    "12": {{"score": 3, "max": 4,  "note": "reason"}},
    "13": {{"score": 4, "max": 5,  "note": "reason"}},
    "14": {{"score": 4, "max": 5,  "note": "reason"}},
    "15": {{"score": 2, "max": 2,  "note": "reason"}},
    "16": {{"score": 4, "max": 5,  "note": "reason"}},
    "17": {{"score": 3, "max": 4,  "note": "reason"}},
    "18": {{"score": 2, "max": 2,  "note": "reason"}},
    "19": {{"score": 4, "max": 5,  "note": "reason"}},
    "20": {{"score": 3, "max": 3,  "note": "reason"}},
    "21": {{"score": 2, "max": 3,  "note": "reason"}},
    "22": {{"score": 2, "max": 2,  "note": "reason"}}
  }},
  "critical_flags": {{
    "23": {{"result": "able", "note": "reason"}},
    "24": {{"result": "correct", "flags": [], "note": "reason"}}
  }},
  "strengths": ["specific strength 1", "specific strength 2"],
  "improvements": ["specific area 1", "specific area 2"],
  "feedback_summary": "2-3 sentence personalized feedback referencing specific call moments"
}}"""


# ─── Ollama call (sync, runs in thread pool) ────────────────────────────────────

def _ollama_request(messages: list[dict]) -> str:
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _check_ollama() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


# ─── Parsing ───────────────────────────────────────────────────────────────────

def _parse_eval(raw: str) -> Optional[dict]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract first JSON object
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return None


def compute_scores(items: dict) -> tuple:
    block1_earned = sum(items[str(k)]["score"] for k in config.BLOCK1)
    block2_earned = sum(items[str(k)]["score"] for k in config.BLOCK2)
    cq_pct = round(block1_earned / config.CQ_MAX * 100, 1)
    qa_pct = round((block1_earned + block2_earned) / config.QA_MAX * 100, 1)
    return cq_pct, qa_pct


# ─── Async evaluation ──────────────────────────────────────────────────────────

async def evaluate_call_async(
    executor: concurrent.futures.ThreadPoolExecutor,
    semaphore: asyncio.Semaphore,
    call: dict,
) -> dict:
    transcript = call.get("transcription", "")
    if not transcript or len(transcript) < 150:
        call["evaluation"] = None
        call["cq_pct"] = None
        call["qa_pct"] = None
        return call

    user_msg = USER_PROMPT_TEMPLATE.format(
        agent=call["agent"],
        duration_min=call["duration_min"],
        ai_summary=call.get("ai_summary", "N/A"),
        transcript=transcript[:10000],
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    async with semaphore:
        loop = asyncio.get_event_loop()
        for attempt in range(3):
            try:
                raw = await loop.run_in_executor(
                    executor, lambda m=messages: _ollama_request(m)
                )
                parsed = _parse_eval(raw)
                if parsed and "items" in parsed:
                    cq, qa = compute_scores(parsed["items"])
                    call["evaluation"] = parsed
                    call["cq_pct"] = cq
                    call["qa_pct"] = qa
                    return call
            except Exception as e:
                if attempt == 2:
                    print(f"  ⚠ Eval failed for {call['agent']}: {e}")
                await asyncio.sleep(2 ** attempt)

    call["evaluation"] = None
    call["cq_pct"] = None
    call["qa_pct"] = None
    return call


async def evaluate_all_async(calls: list[dict]) -> list[dict]:
    if not _check_ollama():
        raise RuntimeError(
            "Ollama is not running.\n"
            "Start it with:  ollama serve\n"
            "Or install it:  brew install ollama && ollama pull llama3.1"
        )

    semaphore = asyncio.Semaphore(config.EVAL_CONCURRENCY)
    results = []
    done = 0
    total = len(calls)

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.EVAL_CONCURRENCY) as executor:
        tasks = [
            evaluate_call_async(executor, semaphore, call)
            for call in calls
        ]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            done += 1
            print(f"  [{done}/{total}] {result['agent']} — "
                  f"QA {result.get('qa_pct', '?')}% | CQ {result.get('cq_pct', '?')}%")
            results.append(result)

    return results


def evaluate_all(calls: list[dict]) -> list[dict]:
    return asyncio.run(evaluate_all_async(calls))


def aggregate_by_agent(calls: list[dict]) -> dict:
    agents: dict[str, dict] = {}

    for call in calls:
        agent = call["agent"]
        if agent not in agents:
            agents[agent] = {
                "name": agent,
                "calls": [],
                "qa_scores": [],
                "cq_scores": [],
                "critical_flags": 0,
                "strengths": [],
                "improvements": [],
            }

        agents[agent]["calls"].append(call)

        if call.get("qa_pct") is not None:
            agents[agent]["qa_scores"].append(call["qa_pct"])
            agents[agent]["cq_scores"].append(call["cq_pct"])

        ev = call.get("evaluation")
        if ev:
            flags = ev.get("critical_flags", {})
            if flags.get("24", {}).get("result") == "flagged":
                agents[agent]["critical_flags"] += 1
            if flags.get("23", {}).get("result") == "unable":
                agents[agent]["critical_flags"] += 1
            agents[agent]["strengths"].extend(ev.get("strengths", []))
            agents[agent]["improvements"].extend(ev.get("improvements", []))

    for a in agents.values():
        qs = a["qa_scores"]
        cs = a["cq_scores"]
        a["avg_qa"] = round(sum(qs) / len(qs), 1) if qs else None
        a["avg_cq"] = round(sum(cs) / len(cs), 1) if cs else None
        a["calls_evaluated"] = len(qs)
        a["calls_total"] = len(a["calls"])
        a["top_strengths"] = list(dict.fromkeys(a["strengths"]))[:3]
        a["top_improvements"] = list(dict.fromkeys(a["improvements"]))[:3]

    return agents
