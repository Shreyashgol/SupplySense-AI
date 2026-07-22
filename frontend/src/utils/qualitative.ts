// Mirrors scripts/recommendation_output/justification.py::_describe so the
// UI and the Groq/template rationale always use the same plain-English
// vocabulary instead of raw scores (rank, confidence, cost index, ...).

export function describePriority(rankScore: number): string {
  if (rankScore >= 0.25) return "Top priority";
  if (rankScore >= 0.12) return "Recommended";
  return "Additional option";
}

export function describeConfidence(confidence: number): string {
  if (confidence >= 0.7) return "High confidence";
  if (confidence >= 0.4) return "Moderate confidence";
  return "Low confidence — review before acting";
}

export function describeCost(costIndex: number): string {
  if (costIndex <= 0.3) return "Low cost";
  if (costIndex <= 0.6) return "Moderate cost";
  return "High cost";
}

export function describeSpeed(implementationDays: number): string {
  if (implementationDays <= 2) return "Fast to put in place";
  if (implementationDays <= 7) return "Ready within about a week";
  return "Takes more than a week";
}

export function describeImpact(expectedImpactReductionPct: number): string {
  if (expectedImpactReductionPct >= 25) return "Significant impact";
  if (expectedImpactReductionPct >= 10) return "Meaningful impact";
  return "Modest impact";
}

export function priorityBadgeClass(rankScore: number): string {
  if (rankScore >= 0.25) return "bg-emerald-500/20 text-emerald-300 border-emerald-400/30";
  if (rankScore >= 0.12) return "bg-sky-500/20 text-sky-300 border-sky-400/30";
  return "bg-gray-500/20 text-gray-300 border-gray-400/30";
}
