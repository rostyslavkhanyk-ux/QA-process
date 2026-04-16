"""
QA Agent — LLM Evaluator
Scores each call using Claude with the full QA scorecard.
Uses prompt caching + async concurrency.
"""

import json
import asyncio
import re
from typing import Optional
import anthropic

import config

# ─── System prompt (cached) ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a certified QA evaluator for Brighterly's Closing Department — an EdTech company selling personalized Math & ELA tutoring for kids (B2C, USA market). Closing agents call parents who just had a demo lesson and try to sell a subscription.

Your job: score each call using the QA scorecard below and provide specific, actionable feedback.

═══════════════════════════════════════════════════════════════
BLOCK 1 — CQ SCORE (items 1–16, max 52 points)
═══════════════════════════════════════════════════════════════

Item 1 — Mandatory Questions (max 2)
• If client volunteers all info themselves → max score
• Score what was ACTUALLY uncovered, not just whether questions were asked
• Client explains child's situation upfront → max score

Item 2 — Quality of Dialogue & Needs Uncovering (max 4)
• 4/4 = 2–3 specific needs uncovered, conversation natural and adaptive
• 2/4 = needs partially uncovered, surface level
• 0/4 = no needs uncovered, scripty/rigid flow

Item 3 — Voicing Strong & Weak Sides (max 2)
• Both strong AND weak sides of child must be mentioned
• Exclusion: client already knows feedback OR no feedback given after demo

Item 4 — Creating Urgency (max 3)
• 3/3 = strong, unprompted urgency — snowball language, foundation risk, falling behind
• 1/3 = urgency present but weak (lacking strong words/tonality)
• 0/3 = no urgency at all
• Exclusion: client said they want to start ASAP
• A single urgency pitch = 1, not 3. Must be strong AND convincing for max

Item 5 — Dialogue with Client — FEEDBACK SECTION ONLY (max 3) ⚠️ CRITICAL
• Evaluated ONLY during the feedback/teacher evaluation section
• Discovery dialogue does NOT count here (those are items 1 & 2)
• 3/3 = natural back-and-forth during feedback delivery
• 1/3 = one question asked during feedback section
• 0/3 = agent monologues through feedback (reads it as a script)

Item 6 — Pitches & Mirroring (max 3)
• Evaluated across ENTIRE call
• Agent must mirror client's own words and needs back to them
• 3+ targeted personalized pitches throughout = 3/3

Item 7 — Mandatory Benefits (max 3)
• Personalization beats completeness — agent does NOT need every benefit
• Benefits must be relevant to THIS specific client's needs
• Agent picks the right benefits for this client = 3/3

Item 8 — Additional Benefits (max 3)
• Same philosophy as item 7
• Agent responding to client questions with relevant benefits = 3/3
• No need to repeat what client already saw on the pricing page

Item 9 — Visual Price Presentation (max 2) ⚠️ CRITICAL RULE
• Link MUST be sent BEFORE or DURING price explanation — NOT after
• Correct flow: send link → confirm it's open → explain prices together
• Link sent AFTER price explanation = 0/2
• Client already on pricing page = max score
• Client driving/unable to open = max if agent sends link AND explains verbally

Item 10 — Subscription Explanation (max 3)
• Brief and clear = better than long and complicated
• Must cover pace/period logic at minimum
• Concise explanation = max score (don't penalize efficiency)

Item 11 — Authority & Recommendation (max 3)
• Client chose own plan AND is confident = max score
• Client uncertain about duration/plan = agent must recommend with authority
• "Okay got it" after client picks plan, no reinforcement = 0/3
• Exclusion: client's confident final decision before agent could recommend

Item 12 — Payment on a Call (max 4) ⚠️ CRITICAL RULE
• Evaluates ONLY whether payment was prompted with discount urgency
• What happens AFTER the prompt = items 13, 14, 15 — NOT item 12
• Discount mentioned + time limit stated + payment prompted = max score
• Client stated financial impossibility earlier = not pushing = correct = max score
• NEVER score item 12 based on whether objections were handled

Item 13 — Finding the Real Objection (max 5)
• No objections on a sale call = max score automatically
• Exclusion: client stated objection directly and clearly
• Only probe when objection is unclear or vague

Item 14 — Continuation of Objection Handling (max 5) ⚠️ IMPORTANT
• No objections on a sale call = max score automatically
• If client mentions wanting to start in summer/future → reservation option MUST be offered
• Confirming budget + exploring options + scheduling callback = max score
• Booking a callback ALONE = item 15, NOT item 14
• No handling attempt at all = 0/5
• Not offering reservation when applicable = 0/5

Item 15 — Securing Strong Commitment (max 2)
• No objections on a sale call = max score automatically
• "I'll message you" or "call me when ready" = NOT a commitment = 0/2
• Must agree on specific date AND time for callback
• Discount expiry must be communicated as reason to act now
• Booking specific date + time + mentioning discount = 2/2

Item 16 — Good Rapport (max 5) ⚠️ ALWAYS MAX CHECK
• Natural, warm, confident, not scripty = 5/5
• Neutral and polite but flat = 2/5
• Negative or reads script = 0/5
• If agent was warm, natural, empathetic and client stayed engaged = 5/5

═══════════════════════════════════════════════════════════════
BLOCK 2 — OBLIGATORY PHRASES (items 17–22, max 19 points)
Affects QA score but NOT CQ score.
═══════════════════════════════════════════════════════════════

Item 17 — Premium Teachers (max 4)
• No sale = max score automatically
• On a sale call: must present Premium Teachers with all 5 benefit points
• Never position regular teachers as inferior

Item 18 — Handling No on PT (max 2)
• No sale = max score automatically
• On a sale call: if client gives ANY clear reason for declining = 2/2
• Only probe with "Do you mind sharing why?" when client declines with NO explanation

Item 19 — Upsale Flow (max 5)
• If client confirms no issues with other subject = max score
• If both Math AND ELA are already being sold = max automatically
• If client shows interest: try to sell on call first, then book demo if refused
• Agent skips completely when need exists = 0/5
• Asking but not attempting to sell or book demo = 1/5

Item 20 — Cancellation Policy (max 3)
• Client doesn't ask = max score — NEVER volunteer cancellation
• If client asks: clarify WHY first → add value → explain policy
• Jumping straight to cancellation terms = lower score

Item 21 — Auto-Renewal (max 3)
• Must be explained clearly and confidently on every call
• Frame as a benefit — price lock, same conditions guaranteed
• Missing entirely = 0/3

Item 22 — Aftersale Phrases (max 2)
• No sale = max score automatically
• Only evaluated when sale occurred or client tried to pay
• Must cover: reschedule policy (6h rule), support contacts, teacher change option, learning policies email

═══════════════════════════════════════════════════════════════
BLOCK 3 — CRITICAL FLAGS (items 23–24, not scored, flagged separately)
═══════════════════════════════════════════════════════════════

Item 23 — Product Awareness
• "able" = agent answered all product questions correctly
• "unable" = agent couldn't answer questions within their competence

Item 24 — Correct Crucial Information
Overcautious info that PROTECTS the client = NOT a flag
False promises that create wrong expectations = FLAG

HARD FLAG TRIGGERS (always flag):
- Lesson is 1 hour long (it's 45 min)
- All teachers are Americans
- All teachers don't have an accent
- Promising a certain teacher
- Free rescheduling if notified later than 6h before lesson
- Refunding bonus lessons
- Cancellation if notified after 48h before billing day
- Offering to return funds anytime to make a sale
- Promising to hold time-limited discounts beyond their expiry

═══════════════════════════════════════════════════════════════
CALL TYPE DEFINITIONS
═══════════════════════════════════════════════════════════════
• "sale" — client agreed to buy or completed payment during the call
• "no_sale" — client didn't buy; callback was booked or call ended without sale
• "unclear" — insufficient transcript to determine outcome

═══════════════════════════════════════════════════════════════
FEEDBACK WRITING GUIDELINES
═══════════════════════════════════════════════════════════════
• Always start with strengths before areas to improve
• Be specific — reference exact moments from the transcript
• Explain WHY something matters (connection to conversion)
• Keep tone constructive — agent should feel supported
• End with one clear key takeaway
"""

USER_PROMPT_TEMPLATE = """Evaluate this call transcript and return JSON scores.

AGENT: {agent}
DURATION: {duration_min} min
AI SUMMARY: {ai_summary}

TRANSCRIPT:
{transcript}

Return ONLY valid JSON with this exact structure (no other text, no markdown):
{{
  "call_type": "sale|no_sale|unclear",
  "items": {{
    "1":  {{"score": 0, "max": 2,  "note": "brief reason"}},
    "2":  {{"score": 0, "max": 4,  "note": "brief reason"}},
    "3":  {{"score": 0, "max": 2,  "note": "brief reason"}},
    "4":  {{"score": 0, "max": 3,  "note": "brief reason"}},
    "5":  {{"score": 0, "max": 3,  "note": "brief reason"}},
    "6":  {{"score": 0, "max": 3,  "note": "brief reason"}},
    "7":  {{"score": 0, "max": 3,  "note": "brief reason"}},
    "8":  {{"score": 0, "max": 3,  "note": "brief reason"}},
    "9":  {{"score": 0, "max": 2,  "note": "brief reason"}},
    "10": {{"score": 0, "max": 3,  "note": "brief reason"}},
    "11": {{"score": 0, "max": 3,  "note": "brief reason"}},
    "12": {{"score": 0, "max": 4,  "note": "brief reason"}},
    "13": {{"score": 0, "max": 5,  "note": "brief reason"}},
    "14": {{"score": 0, "max": 5,  "note": "brief reason"}},
    "15": {{"score": 0, "max": 2,  "note": "brief reason"}},
    "16": {{"score": 0, "max": 5,  "note": "brief reason"}},
    "17": {{"score": 0, "max": 4,  "note": "brief reason"}},
    "18": {{"score": 0, "max": 2,  "note": "brief reason"}},
    "19": {{"score": 0, "max": 5,  "note": "brief reason"}},
    "20": {{"score": 0, "max": 3,  "note": "brief reason"}},
    "21": {{"score": 0, "max": 3,  "note": "brief reason"}},
    "22": {{"score": 0, "max": 2,  "note": "brief reason"}}
  }},
  "critical_flags": {{
    "23": {{"result": "able|unable|n_a", "note": "..."}},
    "24": {{"result": "correct|flagged", "flags": [], "note": "..."}}
  }},
  "strengths": ["specific strength 1", "specific strength 2"],
  "improvements": ["specific area 1", "specific area 2"],
  "feedback_summary": "2-3 sentence personalized feedback referencing specific call moments"
}}"""


def _parse_eval(raw: str) -> Optional[dict]:
    """Parse JSON from Claude response, stripping any markdown fences."""
    text = raw.strip()
    # strip ```json ... ``` fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def compute_scores(items: dict) -> tuple[float, float]:
    """Return (cq_pct, qa_pct) from items dict keyed by string item numbers."""
    block1_earned = sum(items[str(k)]["score"] for k in config.BLOCK1)
    block2_earned = sum(items[str(k)]["score"] for k in config.BLOCK2)
    cq_pct = round(block1_earned / config.CQ_MAX * 100, 1)
    qa_pct = round((block1_earned + block2_earned) / config.QA_MAX * 100, 1)
    return cq_pct, qa_pct


async def evaluate_call_async(
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
    call: dict,
) -> dict:
    """
    Evaluate a single call.  Returns the call dict enriched with 'evaluation' key.
    """
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
        transcript=transcript[:12000],  # cap to avoid token overflow
    )

    async with semaphore:
        for attempt in range(3):
            try:
                resp = await client.messages.create(
                    model=config.ANTHROPIC_MODEL,
                    max_tokens=2048,
                    system=[
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = resp.content[0].text
                parsed = _parse_eval(raw)
                if parsed and "items" in parsed:
                    cq, qa = compute_scores(parsed["items"])
                    call["evaluation"] = parsed
                    call["cq_pct"] = cq
                    call["qa_pct"] = qa
                    return call
            except Exception as e:
                if attempt == 2:
                    print(f"  ⚠ Eval failed for {call['agent']} ({call['call_time_utc']}): {e}")
                await asyncio.sleep(2 ** attempt)

    call["evaluation"] = None
    call["cq_pct"] = None
    call["qa_pct"] = None
    return call


async def evaluate_all_async(calls: list[dict]) -> list[dict]:
    """Evaluate all calls concurrently, respecting EVAL_CONCURRENCY limit."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Export it before running.")

    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    semaphore = asyncio.Semaphore(config.EVAL_CONCURRENCY)

    tasks = [evaluate_call_async(client, semaphore, call) for call in calls]
    total = len(tasks)
    results = []
    done = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        done += 1
        print(f"  [{done}/{total}] Evaluated: {result['agent']} — "
              f"QA {result.get('qa_pct', '?')}% | CQ {result.get('cq_pct', '?')}%")
        results.append(result)

    return results


def evaluate_all(calls: list[dict]) -> list[dict]:
    """Synchronous entry point for evaluation."""
    return asyncio.run(evaluate_all_async(calls))


def aggregate_by_agent(calls: list[dict]) -> dict:
    """
    Build per-agent summary dict.
    Returns: {agent_name: {calls, avg_qa, avg_cq, critical_flags, strengths, improvements}}
    """
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

    # Compute averages
    for a in agents.values():
        qs = a["qa_scores"]
        cs = a["cq_scores"]
        a["avg_qa"] = round(sum(qs) / len(qs), 1) if qs else None
        a["avg_cq"] = round(sum(cs) / len(cs), 1) if cs else None
        a["calls_evaluated"] = len(qs)
        a["calls_total"] = len(a["calls"])
        # Deduplicate common feedback points
        a["top_strengths"] = list(dict.fromkeys(a["strengths"]))[:3]
        a["top_improvements"] = list(dict.fromkeys(a["improvements"]))[:3]

    return agents
