import json
import logging
import re
import time
import uuid

from .config import settings
from .memory import MemoryStore
from .models import AgentResult, IncomingMessage, Situation, Lifecycle, Mode
from .prompts import MODE_GUIDANCE, SYSTEM_PROMPT

log = logging.getLogger("tavryx.engine")

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "situation_id": {"type": "STRING"},
        "title": {"type": "STRING"},
        "mode": {"type": "STRING", "enum": ["INCIDENT","DECISION","LEARNING","CREATIVE","PLANNING","GENERAL"]},
        "lifecycle": {"type": "STRING", "enum": ["EMERGING","ACTIVE","ESCALATING","BLOCKED","RESOLVING","RESOLVED","PARKED"]},
        "severity": {"type": "STRING", "enum": ["LOW","MEDIUM","HIGH","CRITICAL"]},
        "trajectory": {"type": "STRING"},
        "confidence": {"type": "INTEGER"},
        "summary": {"type": "STRING"},
        "answer": {"type": "STRING"},
        "impact": {"type": "STRING"},
        "evidence": {"type": "ARRAY", "items": {"type": "STRING"}},
        "options": {"type": "ARRAY", "items": {"type": "STRING"}},
        "recommendation": {"type": "STRING"},
        "next_move": {"type": "STRING"},
        "why": {"type": "STRING"},
        "state_delta": {"type": "STRING"},
        "decision_revised": {"type": "BOOLEAN"},
        "revision_reason": {"type": "STRING"},
        "observed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "inferred": {"type": "ARRAY", "items": {"type": "STRING"}},
        "recommended": {"type": "ARRAY", "items": {"type": "STRING"}},
        "executed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "verified": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "situation_id","title","mode","lifecycle","severity","trajectory","confidence",
        "summary","answer","impact","evidence","options","recommendation","next_move","why",
        "state_delta","decision_revised","revision_reason","observed","inferred",
        "recommended","executed","verified"
    ],
}


class TavryxEngine:
    def __init__(self, memory):
        self.memory = memory
        self.client = None
        if settings.gemini_api_key:
            from google import genai
            from google.genai import types
            self.client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
            )

    def _extract_json(self, text):
        if not text:
            raise ValueError("Gemini returned an empty response")
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Be tolerant of a provider response that wraps otherwise-valid JSON.
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _context(self, sender=None):
        history = []
        for row in self.memory.recent(settings.tavryx_max_context_messages):
            history.append({
                "situation_id": row["situation_id"],
                "input": row["input_text"],
                "situation": json.loads(row["situation_json"]),
                "channel": row["channel"],
            })
        return history

    def _candidate_context(self, sender):
        candidates = []
        for row in self.memory.candidates(sender, settings.tavryx_candidate_situations):
            situation = json.loads(row["situation_json"])
            candidates.append({
                "situation_id": row["situation_id"],
                "title": situation.get("title", ""),
                "mode": situation.get("mode", "GENERAL"),
                "lifecycle": situation.get("lifecycle", "EMERGING"),
                "severity": situation.get("severity", "LOW"),
                "summary": situation.get("summary", ""),
                "recommendation": situation.get("recommendation", ""),
                "next_move": situation.get("next_move", ""),
                "last_channel": row["channel"],
            })
        return candidates

    def _thinking_level(self, text, previous):
        value = text.lower()
        critical = any(k in value for k in (
            "production down", "outage", "data loss", "security breach", "breach",
            "payment failure", "payments failing", "critical incident", "customers unable",
            "http 500", "http 503", "database down", "service unavailable"
        ))
        complex_words = sum(value.count(k) for k in (
            "trade-off", "tradeoff", "architecture", "deploy", "deployment", "deadline",
            "strategy", "compare", "choose", "decide", "prioritize", "root cause", "why"
        ))
        if critical or (previous and previous.severity == "CRITICAL"):
            return settings.tavryx_critical_thinking_level
        if complex_words >= 2 or len(value) > 650:
            return settings.tavryx_complex_thinking_level
        return settings.tavryx_fast_thinking_level

    def _config(self, thinking_level, structured=True):
        from google.genai import types
        kwargs = dict(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=settings.tavryx_max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        )
        if structured:
            kwargs.update(
                response_mime_type="application/json",
                response_schema=SCHEMA,
            )
        return types.GenerateContentConfig(**kwargs)

    def _generate(self, payload, thinking_level):
        if self.client is None:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        return self.client.models.generate_content(
            model=settings.gemini_model,
            contents=json.dumps(payload, ensure_ascii=False),
            config=self._config(thinking_level, structured=True),
        )

    def _generate_text(self, payload, thinking_level, model=None):
        """Unstructured recovery call used when structured generation is rejected."""
        if self.client is None:
            raise RuntimeError("Gemini client is not configured")
        recovery = dict(payload)
        recovery["instruction"] = (
            recovery.get("instruction", "")
            + "\nReturn a direct human-readable answer first. "
              "Do not output JSON, markdown code fences, or machine-readable metadata. "
              "Keep it concise and useful."
        )
        return self.client.models.generate_content(
            model=model or settings.gemini_model,
            contents=json.dumps(recovery, ensure_ascii=False),
            config=self._config(thinking_level, structured=False),
        )

    def _answer_from_text(self, text):
        if not text:
            return ""
        # Remove accidental fences but preserve useful Markdown bullets.
        text = re.sub(r"```(?:text|markdown)?", "", text, flags=re.I)
        return text.replace("```", "").strip()

    def analyze(self, message: IncomingMessage):
        started = time.perf_counter()
        previous = self.memory.latest_for(message.sender) or self.memory.latest()
        requested_mode = (message.mode or "").strip().lower()

        mode_lens = {
            "analyze": "Give the complete decision-oriented situation answer.",
            "focus": "Return the single highest-leverage next move and why it matters.",
            "brief": "Give a compact current-state brief: what is happening, impact, and next move.",
            "why": "Explain why the situation is in its current state and what evidence caused the movement.",
            "timeline": "Summarize the evolution of this situation from prior evidence to the current state.",
            "state": "Describe the current state: lifecycle, severity, trajectory, confidence, and the key state delta.",
        }
        lens = mode_lens.get(requested_mode, mode_lens["analyze"])

        payload = {
            "current_message": message.text,
            "requested_view": requested_mode or "analyze",
            "view_instruction": lens,
            "sender": message.sender,
            "channel": message.channel,
            "previous_situation": previous.model_dump(mode="json") if previous else None,
            "candidate_situations": self._candidate_context(message.sender)[:4],
            "recent_history": self._context(message.sender)[:4],
            "mode_guidance": MODE_GUIDANCE,
            "instruction": (
                "You are maintaining a portfolio of living situations, not one global conversation. "
                "First decide whether the message continues one of candidate_situations or creates a new situation. "
                "If continuing, reuse that candidate's exact situation_id and update its state. "
                "If unrelated, create a new S-XXXXXXXX id. Never merge unrelated situations merely because they share a mode. "
                "Treat channel as transport metadata; continuity belongs to the situation and sender. "
                "Answer the user's actual question directly. Never return only a situation label. "
                "For learning questions, provide the useful explanation/formulas/example requested. "
                "For general questions, provide a concrete answer before the situation metadata. "
                f"{lens} Keep the answer concise but complete. "
                "State what changed, what is known, what is inferred, and the single highest-leverage next move."
            ),
        }

        level = self._thinking_level(message.text, previous)

        # Stage 1: structured generation.
        try:
            response = self._generate(payload, level)
            raw = self._extract_json(getattr(response, "text", "") or "")
            if not raw.get("answer"):
                raw["answer"] = raw.get("summary", "")
            situation = Situation.model_validate(raw)
        except Exception as exc:
            log.warning("Structured Gemini analysis failed: %s", exc)

            # Stage 2: same model, plain text. This avoids turning schema/format
            # failures into a fake outage and still gives the user an answer.
            try:
                response = self._generate_text(payload, level)
                answer = self._answer_from_text(getattr(response, "text", "") or "")
                if not answer:
                    raise ValueError("Gemini recovery returned an empty answer")
                situation = self._situation_from_answer(message, previous, answer, started)
            except Exception as recovery_exc:
                log.warning("Gemini text recovery failed: %s", recovery_exc)

                # Stage 3: lower-cost/faster model, if configured and different.
                try:
                    if settings.gemini_fallback_model and settings.gemini_fallback_model != settings.gemini_model:
                        response = self._generate_text(payload, settings.tavryx_fast_thinking_level, settings.gemini_fallback_model)
                        answer = self._answer_from_text(getattr(response, "text", "") or "")
                        if not answer:
                            raise ValueError("Fallback Gemini returned an empty answer")
                        situation = self._situation_from_answer(message, previous, answer, started)
                    else:
                        return self._fallback_result(message, previous, started, requested_mode)
                except Exception as fallback_exc:
                    log.warning("Gemini fallback model failed: %s", fallback_exc)
                    return self._fallback_result(message, previous, started, requested_mode)

        situation.reasoning_level = {
            "low": "FAST", "medium": "BALANCED", "high": "DEEP", "minimal": "FAST"
        }.get(level, "BALANCED")
        situation = self._normalize_identity(previous, situation)
        if previous and situation.situation_id == previous.situation_id:
            situation = self._apply_transition(previous, situation)
        elif previous and situation.situation_id != previous.situation_id:
            situation.state_delta = (
                f"New situation created while {previous.situation_id} remains in memory. "
                + situation.state_delta
            ).strip()

        self.memory.add(message.sender, message.channel, message.text, situation)
        situation.processing_ms = round((time.perf_counter() - started) * 1000)
        return AgentResult(situation=situation, response=render_situation(situation))

    def _situation_from_answer(self, message, previous, answer, started):
        """Wrap a successful plain-text AI answer in a valid situation."""
        mode = previous.mode if previous else Mode.GENERAL
        lifecycle = previous.lifecycle if previous else Lifecycle.ACTIVE
        sid = previous.situation_id if previous else "S-" + uuid.uuid4().hex[:8].upper()
        return Situation(
            situation_id=sid,
            title=previous.title if previous else "TAVRYX analysis",
            mode=mode,
            lifecycle=lifecycle,
            severity=previous.severity if previous else "LOW",
            trajectory=previous.trajectory if previous else "ACTIVE",
            confidence=previous.confidence if previous else 72,
            reasoning_level="FAST",
            summary=answer[:500],
            answer=answer,
            impact=previous.impact if previous else "Based on the evidence supplied in the current signal.",
            evidence=[message.text],
            options=[answer],
            recommendation=previous.recommendation if previous else answer,
            next_move=previous.next_move if previous else "Use the answer above as the next decision point and provide new evidence if the situation changes.",
            why=previous.why if previous else "TAVRYX returned the best available answer after structured output recovery.",
            state_delta="Answer recovered through the text-response path; situation state preserved.",
            decision_revised=False,
            revision_reason="",
            observed=[message.text],
            inferred=[],
            recommended=[answer],
            executed=[],
            verified=[],
            processing_ms=round((time.perf_counter() - started) * 1000),
        )

    def _fallback_result(self, message, previous, started, requested_mode="analyze"):
        """Deterministic final degradation: never expose RECOVERING to the user."""
        text = message.text.strip()
        value = text.lower()
        critical_terms = ("outage", "production", "http 500", "http 503", "payment", "database", "security", "breach", "data loss")
        learning_terms = ("learn", "teach", "exam", "understand", "recursion", "explain", "what is", "how does")
        decision_terms = ("choose", "compare", "decision", "prioritize", "strategy")

        if any(k in value for k in critical_terms):
            mode, severity, lifecycle = Mode.INCIDENT, "HIGH", Lifecycle.ACTIVE
            title = "Production situation requires immediate triage"
            trajectory = "ESCALATING"
            answer = "The signal indicates a potentially material operational issue. First validate the newest production evidence, isolate the highest-impact failure, and verify the result after the corrective action."
        elif any(k in value for k in learning_terms):
            mode, severity, lifecycle = Mode.LEARNING, "LOW", Lifecycle.EMERGING
            title = "Learning request"
            trajectory = "EMERGING"
            answer = "The request is understood as a learning question. Start from the core concept, connect it to a simple example, then test the idea with one small application."
        elif any(k in value for k in decision_terms):
            mode, severity, lifecycle = Mode.DECISION, "MEDIUM", Lifecycle.EMERGING
            title = "Decision requires structured evaluation"
            trajectory = "EMERGING"
            answer = "Compare the available options on impact, risk, effort, reversibility, and fit with the objective before committing."
        else:
            mode, severity, lifecycle = Mode.GENERAL, "LOW", Lifecycle.EMERGING
            title = "Situation identified"
            trajectory = "EMERGING"
            answer = f"TAVRYX captured the signal: “{text[:260]}” The next step is to clarify the desired outcome and validate the most important evidence before acting."

        sid = previous.situation_id if previous and mode == previous.mode else "S-" + uuid.uuid4().hex[:8].upper()
        situation = Situation(
            situation_id=sid, title=title, mode=mode, lifecycle=lifecycle, severity=severity,
            trajectory=trajectory, confidence=55, reasoning_level="FAST",
            summary=text, answer=answer, impact="Based on the information currently available.",
            evidence=[text], options=[answer], recommendation=answer,
            next_move="Provide the next piece of evidence or constraint so TAVRYX can refine the situation.",
            why="The response is a safe degradation path because the primary reasoning service was unavailable.",
            state_delta="Signal captured; answer returned through the deterministic recovery path.",
            observed=[text], inferred=[], recommended=[answer], executed=[], verified=[]
        )
        if previous and situation.situation_id == previous.situation_id:
            situation.state_delta = _state_delta(previous, situation, situation.state_delta)
        self.memory.add(message.sender, message.channel, message.text, situation)
        situation.processing_ms = round((time.perf_counter() - started) * 1000)
        return AgentResult(situation=situation, response=render_situation(situation))

    def _normalize_identity(self, previous, current):
        raw = (current.situation_id or "").strip()
        if previous and raw.lower() in {"", "new", "none"}:
            current.situation_id = previous.situation_id if _related_enough(previous, current) else "S-" + uuid.uuid4().hex[:8].upper()
        elif not raw:
            current.situation_id = "S-" + uuid.uuid4().hex[:8].upper()
        return current

    def _apply_transition(self, previous, current):
        if previous.recommendation.strip().lower() != current.recommendation.strip().lower() and current.recommendation.strip():
            current.decision_revised = True
            current.revision_reason = current.revision_reason or "New evidence changed the recommended action from the previous state."
            current.trajectory = "REVISED"
        if previous.lifecycle == Lifecycle.PARKED:
            current.lifecycle = Lifecycle.ACTIVE
        current.state_delta = _state_delta(previous, current, current.state_delta)
        return current


def _related_enough(previous, current):
    a = f"{previous.title} {previous.summary}".lower()
    b = f"{current.title} {current.summary}".lower()
    if previous.mode == current.mode:
        return True
    shared = {w for w in re.findall(r"[a-z0-9]{5,}", a) if w in b}
    return len(shared) >= 2


def _state_delta(previous, current, model_delta=""):
    changes = []
    if previous.lifecycle != current.lifecycle:
        changes.append(f"lifecycle {previous.lifecycle.value} → {current.lifecycle.value}")
    if previous.severity != current.severity:
        changes.append(f"severity {previous.severity} → {current.severity}")
    if previous.recommendation.strip() != current.recommendation.strip() and current.recommendation:
        changes.append("recommendation changed")
    if previous.next_move.strip() != current.next_move.strip() and current.next_move:
        changes.append("next move changed")
    prefix = " • ".join(changes)
    return (prefix + (f" — {model_delta}" if model_delta else "")).strip(" —")


def render_situation(s):
    lines = [
        f"**TAVRYX · {s.severity} · {s.mode.value}**",
        f"`{s.situation_id}` · **{s.lifecycle.value}** · **{s.reasoning_level}**",
        "",
        f"**{s.title}**",
        (s.answer or s.summary),
        "",
    ]
    if s.state_delta:
        lines += ["**STATE DELTA**", s.state_delta, ""]
    if s.impact:
        lines += ["**Impact**", s.impact, ""]
    if s.observed:
        lines += ["**Observed**"] + [f"• {x}" for x in s.observed[:4]] + [""]
    if s.inferred:
        lines += ["**Inferred**"] + [f"• {x}" for x in s.inferred[:4]] + [""]
    if s.options:
        lines += ["**Options**"] + [f"{i+1}. {x}" for i, x in enumerate(s.options[:5])] + [""]
    if s.recommendation:
        lines += ["**Recommendation**", s.recommendation, ""]
    if s.next_move:
        lines += ["**Next move**", s.next_move, ""]
    if s.why:
        lines += ["**Why**", s.why, ""]
    if s.decision_revised:
        lines += ["**Decision revised**", s.revision_reason, ""]
    lines += ["──────────", f"**Lifecycle:** {s.lifecycle.value}", f"**Confidence:** {s.confidence}%"]
    return "\n".join(lines)


def command_response(command, memory, argument=None):
    current = memory.latest()
    if command == "/reset":
        memory.clear()
        return "**TAVRYX RESET**\n\nAll situation threads cleared. New situation thread started."
    if command == "/situations":
        situations = memory.list_situations()
        if not situations:
            return "**TAVRYX SITUATIONS**\n\nNo situations stored."
        out = ["**TAVRYX SITUATIONS**", ""]
        for s in situations:
            out += [f"• `{s.situation_id}` **{s.title}**", f"  {s.lifecycle.value} · {s.mode.value} · {s.severity}", f"  {s.summary[:150]}"]
        return "\n".join(out)
    if command == "/park":
        if not argument:
            return "**TAVRYX PARK**\n\nUsage: `/park S-XXXXXXXX`"
        s = memory.park(argument)
        return (f"**TAVRYX PARKED**\n\n`{s.situation_id}` · {s.title}\n\nThe situation remains in memory and can be resumed later."
                if s else f"**TAVRYX**\n\nSituation `{argument}` was not found.")
    if command == "/resume":
        if not argument:
            return "**TAVRYX RESUME**\n\nUsage: `/resume S-XXXXXXXX`"
        s = memory.resume(argument)
        return (f"**TAVRYX RESUMED**\n\n`{s.situation_id}` · {s.title}\n\n{s.summary}\n\n**Next:** {s.next_move}\n\n**State delta:** {s.state_delta}"
                if s else f"**TAVRYX**\n\nSituation `{argument}` was not found.")
    if not current:
        return "**TAVRYX**\n\nNo active situation yet. Send a message first."
    if command == "/focus":
        return f"**TAVRYX FOCUS**\n\n`{current.situation_id}` · {current.lifecycle.value}\n\n**DO THIS NEXT**\n{current.next_move}\n\n**WHY**\n{current.why}\n\n**CONFIDENCE**\n{current.confidence}%"
    if command == "/brief":
        return f"**TAVRYX BRIEF**\n\n`{current.situation_id}` · **{current.title}**\nLifecycle: {current.lifecycle.value}\nSeverity: {current.severity}\n\n{current.summary}\n\n**Impact:** {current.impact or 'None identified'}\n**Next:** {current.next_move}\n**Confidence:** {current.confidence}%"
    if command == "/why":
        return f"**TAVRYX WHY THE SITUATION MOVED**\n\n`{current.situation_id}`\n\n**STATE DELTA**\n{current.state_delta or 'No material state change recorded.'}\n\n**Why:** {current.why}\n\n**Lifecycle:** {current.lifecycle.value}\n**Confidence:** {current.confidence}%"
    if command == "/state":
        return f"**TAVRYX STATE**\n\nID: `{current.situation_id}`\nMode: {current.mode.value}\nLifecycle: {current.lifecycle.value}\nSeverity: {current.severity}\nTrajectory: {current.trajectory}\nReasoning: {current.reasoning_level}\nConfidence: {current.confidence}%\nDecision revised: {'yes' if current.decision_revised else 'no'}"
    if command == "/memory":
        rows = memory.recent(8)
        if not rows:
            return "**TAVRYX MEMORY**\n\nNo stored situations."
        out = ["**TAVRYX MEMORY**", ""]
        for row in rows:
            s = json.loads(row["situation_json"])
            out += [f"• `{row['situation_id']}` **{s['title']}** · {s['lifecycle']} · {row['channel']}", f"  {s['summary'][:180]}"]
        return "\n".join(out)
    if command == "/timeline":
        target = argument or (current.situation_id if current else None)
        if not target:
            return "**TAVRYX TIMELINE**\n\nNo situation available."
        rows = memory.history_for(target, 8)
        if not rows:
            return f"**TAVRYX TIMELINE**\n\nSituation `{target}` was not found."
        out = [f"**TAVRYX TIMELINE · `{target}`**", ""]
        for row in reversed(rows):
            s = json.loads(row["situation_json"])
            delta = s.get("state_delta") or "No material state delta recorded."
            out += [f"• **{s.get('lifecycle','ACTIVE')}** · {row['channel']}", f"  {delta[:260]}"]
        return "\n".join(out)
    return None
