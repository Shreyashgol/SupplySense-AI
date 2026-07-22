"""Groq-backed recommendation justifier for Part G.

Turns a Part F ``Recommendation`` (already a fully-scored, policy-checked,
ranked object — see ``scripts/decision_optimization/models.py``) into a
grounded, human-readable justification sentence written in **plain English
for a non-technical business reader** (an executive, policymaker, or banker,
not an engineer).

The LLM is used strictly as a *renderer*, never as a decision-maker, and it
never even sees Part F's raw numbers: ``_describe()`` first converts every
score into a qualitative band ("high confidence", "moderate cost", "can be
implemented within a week", ...), and only those qualitative descriptors are
sent to Groq. This makes it structurally impossible for the model to parrot
back a rank score or a percentage — there is nothing numeric in its input to
repeat.

- it receives only qualitative bands + compliance facts Part F already computed
- it is instructed not to invent facts, not to re-rank, not to change status,
  and never to mention numbers, scores, or percentages
- if the bands look internally inconsistent (e.g. "top priority" paired with
  a policy BLOCKED status, or "low confidence") it must flag the
  recommendation as ambiguous for analyst review

If no Groq API key is configured, or the Groq call fails, a deterministic
template renders the same qualitative bands into prose so the pipeline never
silently drops justifications — this keeps Part G usable in offline/CI
environments while still using Groq (per project requirement) whenever a key
is present.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from scripts.decision_optimization.models import DecisionOptimizationResult, Recommendation

from .config import RecommendationOutputConfig
from .models import JustifiedDecisionResult, JustifiedRecommendation

LOGGER = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Recommendation Justifier for the SupplySense-AI \
energy supply chain resilience system. Your only job is to translate the \
qualitative facts you are given into ONE short, plain-English sentence a \
busy, non-technical executive, policymaker, or banker could read in a few \
seconds and immediately understand.

Hard rules:
- Use ONLY the facts provided. Never invent facts, sources, or events.
- Never change the ranking, the recommendation, or the compliance status.
- NEVER write a number, percentage, score, or the words "rank", "score", \
"confidence level", or "index" — describe things the way a person would \
speak about them (e.g. "quick to put in place", "fairly low cost", \
"a strong option", "needs a closer look before acting").
- Never mention "LLM", "prompt", "Groq", or that you are an AI.
- Set is_ambiguous=true whenever the facts look internally inconsistent, \
for example: a top-priority option paired with a policy status of blocked \
or needing conditions, or a low-confidence option paired with high urgency.
- Respond with strict JSON only: {"rationale_text": string, "is_ambiguous": boolean}
"""


class RecommendationJustifier:
    """Generate grounded, plain-English justifications via Groq."""

    def __init__(self, config: RecommendationOutputConfig) -> None:
        self.config = config
        self._client = None
        if config.groq_api_key:
            try:
                from groq import Groq  # noqa: PLC0415

                self._client = Groq(
                    api_key=config.groq_api_key,
                    timeout=config.groq_timeout_seconds,
                    max_retries=config.groq_max_retries,
                )
            except ImportError:
                LOGGER.warning("groq package not installed; falling back to template rationale.")
        else:
            LOGGER.warning("GROQ_API_KEY not configured; falling back to template rationale.")

    def justify_result(
        self, result: DecisionOptimizationResult
    ) -> JustifiedDecisionResult:
        """Justify every recommendation in a decision run."""
        justifications = [self.justify_recommendation(rec) for rec in result.recommendations]
        return JustifiedDecisionResult(
            decision_run_id=result.decision_run_id,
            scenario_id=result.scenario_id,
            scenario_name=result.scenario_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            justifications=justifications,
        )

    def justify_recommendation(self, rec: Recommendation) -> JustifiedRecommendation:
        generated_at = datetime.now(timezone.utc).isoformat()
        if self._client is not None:
            rationale_text, is_ambiguous, generated_by = self._call_groq(rec)
        else:
            rationale_text, is_ambiguous = _template_rationale(rec)
            generated_by = "template_fallback"

        return JustifiedRecommendation(
            recommendation=rec,
            rationale_text=rationale_text,
            is_ambiguous=is_ambiguous,
            generated_by=generated_by,
            generated_at=generated_at,
        )

    # ── Groq call ─────────────────────────────────────────────────────────────

    def _call_groq(self, rec: Recommendation) -> tuple[str, bool, str]:
        bands = _describe(rec)
        user_payload = {
            "action": rec.title,
            "target_asset": rec.target_asset_name,
            "target_asset_label": rec.target_asset_label,
            "impact": bands["impact"],
            "speed": bands["speed"],
            "cost": bands["cost"],
            "feasibility": bands["feasibility"],
            "confidence": bands["confidence"],
            "urgency": bands["urgency"],
            "priority": bands["priority"],
            "policy_status": bands["policy_status"],
            "policy_warnings": rec.policy_validation.warnings,
            "policy_blockers": rec.policy_validation.blockers,
        }
        try:
            completion = self._client.chat.completions.create(
                model=self.config.groq_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=250,
            )
            content = completion.choices[0].message.content
            parsed = json.loads(content)
            rationale_text = str(parsed.get("rationale_text") or "").strip()
            is_ambiguous = bool(parsed.get("is_ambiguous", False))
            if not rationale_text:
                raise ValueError("Empty rationale_text from Groq response.")
            return rationale_text, is_ambiguous, f"groq:{self.config.groq_model}"
        except Exception as exc:  # noqa: BLE001
            LOGGER.error(
                "Groq justification call failed for recommendation_id=%s: %s",
                rec.recommendation_id,
                exc,
            )
            rationale_text, is_ambiguous = _template_rationale(rec)
            return rationale_text, is_ambiguous, "template_fallback_after_error"


# ── Qualitative banding: the only thing Groq (and the template) ever see ─────


def _describe(rec: Recommendation) -> dict[str, str]:
    """Convert Part F's raw scores into plain-language bands (no numbers)."""
    return {
        "impact": (
            "a significant reduction in the disruption"
            if rec.expected_impact_reduction_pct >= 25
            else "a meaningful reduction in the disruption"
            if rec.expected_impact_reduction_pct >= 10
            else "a modest reduction in the disruption"
        ),
        "speed": (
            "can be put in place within a day or two"
            if rec.implementation_days <= 2
            else "can be implemented within about a week"
            if rec.implementation_days <= 7
            else "takes more than a week to fully put in place"
        ),
        "cost": (
            "at a low relative cost"
            if rec.cost_index <= 0.3
            else "at a moderate cost"
            if rec.cost_index <= 0.6
            else "at a high relative cost"
        ),
        "feasibility": (
            "is highly practical to carry out"
            if rec.feasibility_score >= 0.7
            else "is reasonably practical to carry out"
            if rec.feasibility_score >= 0.4
            else "faces real practical hurdles"
        ),
        "confidence": (
            "high confidence"
            if rec.confidence >= 0.7
            else "moderate confidence"
            if rec.confidence >= 0.4
            else "low confidence, so it is worth a closer look before acting"
        ),
        "urgency": (
            "urgent"
            if rec.urgency_score >= 0.6
            else "moderately time-sensitive"
            if rec.urgency_score >= 0.3
            else "not especially time-critical"
        ),
        "priority": (
            "a top-priority option"
            if rec.rank_score >= 0.25
            else "a solid option"
            if rec.rank_score >= 0.12
            else "a lower-priority option worth keeping on the list"
        ),
        "policy_status": {
            "COMPLIANT": "fully compliant with policy",
            "WITH_CONDITIONS": "compliant, but only under certain conditions",
            "BLOCKED": "currently blocked by policy rules",
        }.get(rec.policy_validation.status, rec.policy_validation.status.lower()),
    }


def _template_rationale(rec: Recommendation) -> tuple[str, bool]:
    """Deterministic, plain-English prose fallback — no numbers, ever."""
    bands = _describe(rec)
    status = rec.policy_validation.status
    is_ambiguous = (
        status != "COMPLIANT"
        or rec.confidence < 0.35
        or (rec.feasibility_score < 0.35 and rec.urgency_score > 0.6)
    )
    text = (
        f"For {rec.target_asset_name}, this is {bands['priority']}: it offers {bands['impact']} "
        f"and {bands['feasibility']}, {bands['speed']} {bands['cost']}. "
        f"The system has {bands['confidence']} in this assessment, and the action is "
        f"{bands['policy_status']}."
    )
    if rec.policy_validation.warnings:
        text += f" Before proceeding: {'; '.join(rec.policy_validation.warnings)}."
    if rec.policy_validation.blockers:
        text += f" This is currently blocked because: {'; '.join(rec.policy_validation.blockers)}."
    return text, is_ambiguous
