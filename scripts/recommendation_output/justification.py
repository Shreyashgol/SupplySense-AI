"""Groq-backed recommendation justifier for Part G.

Turns a Part F ``Recommendation`` (already a fully-scored, policy-checked,
ranked object — see ``scripts/decision_optimization/models.py``) into a
grounded, human-readable justification sentence.

The LLM is used strictly as a *renderer*, never as a decision-maker:
- it receives only the numeric scores/checks Part F already computed
- it is instructed not to invent facts, not to re-rank, not to change status
- if the numbers look internally inconsistent (e.g. a high rank score paired
  with a policy BLOCKED status, or very low confidence) it must flag the
  recommendation as ambiguous for analyst review

If no Groq API key is configured, or the Groq call fails, a deterministic
template renders the same fields into prose so the pipeline never silently
drops justifications — this keeps Part G usable in offline/CI environments
while still using Groq (per project requirement) whenever a key is present.
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
numeric scores and compliance facts you are given into ONE concise, \
objective, third-person sentence explaining why the option scored the way \
it did.

Hard rules:
- Use ONLY the numbers and facts provided. Never invent facts, sources, or events.
- Never change the ranking, the recommendation, or the compliance status.
- Never mention "LLM", "prompt", "Groq", or that you are an AI.
- Set is_ambiguous=true whenever the numbers look internally inconsistent, \
for example: a high rank_score paired with policy status BLOCKED or WARN, \
or confidence below 0.35, or feasibility below 0.35 while urgency is high.
- Respond with strict JSON only: {"rationale_text": string, "is_ambiguous": boolean}
"""


class RecommendationJustifier:
    """Generate grounded natural-language justifications via Groq."""

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
        user_payload = {
            "action": rec.title,
            "action_type": rec.action_type,
            "target_asset": rec.target_asset_name,
            "target_asset_label": rec.target_asset_label,
            "expected_impact_reduction_pct": round(rec.expected_impact_reduction_pct, 2),
            "implementation_days": round(rec.implementation_days, 1),
            "cost_index": round(rec.cost_index, 2),
            "feasibility_score": round(rec.feasibility_score, 4),
            "urgency_score": round(rec.urgency_score, 4),
            "rank_score": round(rec.rank_score, 4),
            "confidence": round(rec.confidence, 4),
            "policy_status": rec.policy_validation.status,
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


def _template_rationale(rec: Recommendation) -> tuple[str, bool]:
    """Deterministic prose fallback built only from Part F's own fields."""
    status = rec.policy_validation.status
    is_ambiguous = (
        status != "COMPLIANT"
        or rec.confidence < 0.35
        or (rec.feasibility_score < 0.35 and rec.urgency_score > 0.6)
    )
    text = (
        f"This option is recommended because it targets {rec.target_asset_name} "
        f"with an estimated {rec.expected_impact_reduction_pct:.1f}% reduction in "
        f"supply disruption within {rec.implementation_days:.1f} day(s), at a "
        f"feasibility score of {rec.feasibility_score:.2f} and confidence of "
        f"{rec.confidence:.2f}. Policy compliance status: {status}."
    )
    if rec.policy_validation.warnings:
        text += f" Warnings: {'; '.join(rec.policy_validation.warnings)}."
    if rec.policy_validation.blockers:
        text += f" Blockers: {'; '.join(rec.policy_validation.blockers)}."
    return text, is_ambiguous
