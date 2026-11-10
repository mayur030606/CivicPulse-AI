"""Deterministic, keyword-and-rule-based complaint classification.

This provider does not use an LLM and does not produce a model-confidence score.
Every decision is derived from auditable keywords, category base severity, and
explicit high/low-impact terms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.enums import ComplaintCategory, Priority, Severity
from app.services.classification.base import ClassificationProvider, ClassificationResult
from app.services.classification.taxonomy import (
    CATEGORY_RULES,
    CRITICAL_SEVERITY_SIGNALS,
    HIGH_SEVERITY_SIGNALS,
    LOW_SEVERITY_SIGNALS,
    OTHER_BASE_SEVERITY,
    OTHER_DEPARTMENT,
    CategoryRule,
    contains_keyword,
    normalize_for_matching,
)

_SEVERITY_SCORES = {
    Severity.low: 1,
    Severity.medium: 2,
    Severity.high: 3,
    Severity.critical: 4,
}
_SCORE_SEVERITIES = {score: severity for severity, score in _SEVERITY_SCORES.items()}

# Longest markers are matched first so "in front of" is not split into "in".
_LOCATION_MARKERS = (
    "in front of",
    "at the corner of",
    "corner of",
    "next to",
    "opposite to",
    "opposite",
    "nearby",
    "near by",
    "near",
    "behind",
    "beside",
    "outside",
    "along",
    "around",
    "between",
    "on",
    "at",
    "in",
    "ke paas",
    "ke samne",
    "ke peeche",
    "के पास",
    "के सामने",
    "के पीछे",
    "पास",
    "सामने",
    "पीछे",
    "જવળ",
    "પાસે",
    "સામે",
    "પાછળ",
    "जवळ",
    "समोर",
    "मागे",
)
_LOCATION_PATTERN = re.compile(
    r"(?<!\w)("
    + "|".join(
        re.escape(marker)
        for marker in sorted(_LOCATION_MARKERS, key=len, reverse=True)
    )
    + r")(?!\w)\s+",
    re.IGNORECASE,
)

_LOCATION_PLACE_HINTS = frozenset(
    {
        "area",
        "avenue",
        "block",
        "bridge",
        "building",
        "bus",
        "bus stop",
        "chowk",
        "circle",
        "city",
        "colony",
        "corner",
        "cross",
        "flyover",
        "gate",
        "ground",
        "highway",
        "hospital",
        "house",
        "junction",
        "lane",
        "locality",
        "main road",
        "mall",
        "market",
        "mosque",
        "nagar",
        "park",
        "phase",
        "road",
        "school",
        "sector",
        "shop",
        "society",
        "stand",
        "station",
        "street",
        "temple",
        "town",
        "village",
        "ward",
        "अस्पताल",
        "गली",
        "नगर",
        "बाजार",
        "मार्ग",
        "सड़क",
        "स्कूल",
        "બજાર",
        "શાળા",
        "સડક",
        "रस्ता",
        "शाळा",
        "बाजार",
    }
)

_LOCATION_REJECT_WORDS = frozenset(
    {
        "accident",
        "afternoon",
        "blockage",
        "complaint",
        "currently",
        "daytime",
        "drain",
        "evening",
        "friday",
        "garbage",
        "here",
        "issue",
        "leak",
        "leakage",
        "midnight",
        "monday",
        "month",
        "months",
        "morning",
        "night",
        "noon",
        "now",
        "pothole",
        "problem",
        "recently",
        "saturday",
        "sewage",
        "sunday",
        "that",
        "there",
        "this",
        "thursday",
        "time",
        "today",
        "tomorrow",
        "traffic",
        "tuesday",
        "wednesday",
        "week",
        "weeks",
        "yesterday",
    }
)

_LOCATION_ISSUE_WORDS = frozenset(
    {
        "accident",
        "blockage",
        "complaint",
        "drain",
        "garbage",
        "issue",
        "leak",
        "leakage",
        "pothole",
        "problem",
        "sewage",
        "traffic",
    }
)

_NEGATION_WORDS = frozenset({"no", "not", "without", "never"})


@dataclass(frozen=True, slots=True)
class _CategorySelection:
    rule: CategoryRule | None
    matched_keywords: tuple[str, ...]
    ambiguous: bool
    runner_up: CategoryRule | None


@dataclass(frozen=True, slots=True)
class _SeverityDecision:
    severity: Severity
    base_severity: Severity
    critical_signals: tuple[str, ...]
    high_signals: tuple[str, ...]
    low_signals: tuple[str, ...]


class DeterministicClassificationProvider(ClassificationProvider):
    """Explainable keyword rules for Phase 1 civic complaint classification."""

    name = "deterministic_rules"

    def classify(
        self, *, text: str, language: str | None = None
    ) -> ClassificationResult:
        matching_text = normalize_for_matching(text)
        selection = _select_category(matching_text)
        severity_decision = _determine_severity(
            selection.rule.base_severity
            if selection.rule is not None
            else OTHER_BASE_SEVERITY,
            matching_text,
        )
        category = (
            selection.rule.category
            if selection.rule is not None
            else ComplaintCategory.other
        )
        department = (
            selection.rule.department
            if selection.rule is not None
            else OTHER_DEPARTMENT
        )
        needs_review = selection.rule is None or selection.ambiguous

        return ClassificationResult(
            provider=self.name,
            summary=_build_summary(text),
            description=text,
            category=category,
            severity=severity_decision.severity,
            priority=Priority(severity_decision.severity.value),
            responsible_department=department,
            language=language,
            location_hint=_extract_location(text),
            matched_keywords=selection.matched_keywords,
            severity_signals=(
                severity_decision.critical_signals
                + severity_decision.high_signals
                + severity_decision.low_signals
            ),
            explanation=_build_explanation(selection, severity_decision),
            needs_review=needs_review,
            confidence=None,
        )


def _select_category(matching_text: str) -> _CategorySelection:
    scored: list[tuple[int, CategoryRule, tuple[str, ...]]] = []

    for rule in CATEGORY_RULES:
        matches = tuple(
            keyword
            for keyword in rule.keywords
            if contains_keyword(matching_text, keyword)
        )
        if not matches:
            continue

        # Longer phrases are more specific than single-word keywords.
        score = sum(max(1, len(keyword.split())) for keyword in matches)
        scored.append((score, rule, matches))

    if not scored:
        return _CategorySelection(
            rule=None,
            matched_keywords=(),
            ambiguous=False,
            runner_up=None,
        )

    # Stable ordering keeps CATEGORY_RULES as the documented tie-breaker.
    scored.sort(key=lambda item: item[0], reverse=True)
    top_score, top_rule, top_matches = scored[0]
    runner_up = scored[1][1] if len(scored) > 1 else None
    ambiguous = runner_up is not None and scored[1][0] == top_score

    return _CategorySelection(
        rule=top_rule,
        matched_keywords=top_matches,
        ambiguous=ambiguous,
        runner_up=runner_up,
    )


def _determine_severity(
    base_severity: Severity, matching_text: str
) -> _SeverityDecision:
    critical_signals = _find_signals(
        matching_text, CRITICAL_SEVERITY_SIGNALS
    )
    high_signals = _find_signals(matching_text, HIGH_SEVERITY_SIGNALS)
    low_signals = _find_signals(matching_text, LOW_SEVERITY_SIGNALS)

    if critical_signals:
        severity = Severity.critical
    else:
        score = _SEVERITY_SCORES[base_severity]
        if high_signals:
            score += 1
        if low_signals:
            score -= 1
        # High-impact terms can raise severity to high, but only explicit
        # critical signals can produce critical.
        score = max(1, min(3, score))
        severity = _SCORE_SEVERITIES[score]

    return _SeverityDecision(
        severity=severity,
        base_severity=base_severity,
        critical_signals=critical_signals,
        high_signals=high_signals,
        low_signals=low_signals,
    )


def _find_signals(text: str, signals: tuple[str, ...]) -> tuple[str, ...]:
    matches = []
    for signal in signals:
        if contains_keyword(text, signal) and not _is_negated(text, signal):
            matches.append(signal)
    return tuple(dict.fromkeys(matches))


def _is_negated(text: str, keyword: str) -> bool:
    match = re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text)
    if match is None:
        return False

    prefix_words = text[: match.start()].split()[-3:]
    return any(word in _NEGATION_WORDS for word in prefix_words)


def _extract_location(text: str) -> str | None:
    best_candidate: str | None = None
    best_score = -1

    for clause in re.split(r"[.,;!?\n]+", text):
        matches = list(_LOCATION_PATTERN.finditer(clause))
        for index, match in enumerate(matches):
            start = match.end()
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(clause)
            )
            candidate = _clean_location(clause[start:end])
            if candidate is None:
                continue

            score = _location_score(candidate)
            if score > best_score:
                best_candidate = candidate
                best_score = score

    return best_candidate


def _clean_location(candidate: str) -> str | None:
    candidate = re.sub(r"\s+", " ", candidate).strip(" \t-")
    candidate = re.sub(
        r"^(?:the|a|an|my|our|this|that|these|those)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"\s+(?:at|in the|during)\s+"
        r"(?:night|morning|afternoon|evening|daytime|noon|midnight)\b.*$",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"\s+(?:today|yesterday|tomorrow|now|currently|recently|since|for)\b.*$",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"\s+(?:because|due to|so that|where|which|that)\b.*$",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = candidate.strip(" ,.-")
    if not candidate:
        return None

    words = candidate.split()
    lower_words = [word.casefold().strip(".,;:!?") for word in words]
    if len(words) == 1 and lower_words[0] in _LOCATION_REJECT_WORDS:
        return None
    if all(word in _LOCATION_ISSUE_WORDS for word in lower_words):
        return None
    if candidate[0].isdigit() and not _has_place_hint(candidate):
        return None

    if len(candidate) > 120:
        candidate = candidate[:117].rsplit(" ", 1)[0] + "..."

    return candidate


def _has_place_hint(candidate: str) -> bool:
    lower_candidate = candidate.casefold()
    return any(hint in lower_candidate for hint in _LOCATION_PLACE_HINTS)


def _location_score(candidate: str) -> int:
    score = min(len(candidate.split()), 4)
    if _has_place_hint(candidate):
        score += 4
    if any(word[:1].isupper() for word in candidate.split()):
        score += 1
    return score


def _build_summary(text: str) -> str:
    """Extractive summary: first sentence, truncated without inventing content."""

    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if len(first_sentence) <= 280:
        return first_sentence
    return first_sentence[:277].rsplit(" ", 1)[0] + "..."


def _build_explanation(
    selection: _CategorySelection, severity_decision: _SeverityDecision
) -> str:
    if selection.rule is None:
        parts = [
            "Deterministic keyword rules found no complaint-category keyword; "
            "the category defaulted to other."
        ]
    else:
        parts = [
            f"Deterministic keyword rules selected "
            f"'{selection.rule.category.value}' "
            f"({selection.rule.department}) from matched terms: "
            f"{', '.join(selection.matched_keywords)}."
        ]
        if selection.ambiguous and selection.runner_up is not None:
            parts.append(
                f"Evidence tied with '{selection.runner_up.category.value}'; "
                "the first taxonomy rule was used and human review is recommended."
            )

    if severity_decision.critical_signals:
        parts.append(
            "Critical terms set severity to critical: "
            f"{', '.join(severity_decision.critical_signals)}."
        )
    else:
        parts.append(
            "Base severity is "
            f"{severity_decision.base_severity.value} for this category."
        )
        if severity_decision.high_signals:
            parts.append(
                "High-impact terms raised severity: "
                f"{', '.join(severity_decision.high_signals)}."
            )
        if severity_decision.low_signals:
            parts.append(
                "Low-impact terms lowered severity: "
                f"{', '.join(severity_decision.low_signals)}."
            )
        if not severity_decision.high_signals and not severity_decision.low_signals:
            parts.append("No severity modifiers matched.")
        parts.append(f"Final severity is {severity_decision.severity.value}.")

    if selection.rule is None or selection.ambiguous:
        parts.append(
            "Marked needs_review because the complaint is ambiguous or "
            "insufficiently supported."
        )

    return " ".join(parts)
