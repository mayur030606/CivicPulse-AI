"""Complaint taxonomy, text normalization, and deterministic rule data."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.models.enums import ComplaintCategory, Severity
from app.services.classification.base import ClassificationValidationError

MAX_TEXT_LENGTH = 4000

SUPPORTED_LANGUAGE_PRIMARY_CODES = frozenset(
    {"en", "hi", "gu", "mr", "ta", "te", "kn", "bn"}
)
AUTO_LANGUAGE_ALIASES = frozenset({"auto", "automatic", "indic-auto"})


def normalize_text(text: str) -> str:
    """Normalize whitespace and reject empty or oversized complaint text."""

    if not isinstance(text, str):
        raise ClassificationValidationError("Complaint text must be a string.")

    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        raise ClassificationValidationError("Complaint text must not be empty.")
    if len(normalized) > MAX_TEXT_LENGTH:
        raise ClassificationValidationError(
            f"Complaint text must be at most {MAX_TEXT_LENGTH} characters."
        )

    return normalized


def normalize_for_matching(text: str) -> str:
    """Prepare text for case-insensitive keyword matching.

    Unicode combining marks are kept because Indic vowel signs and similar
    marks are not matched by a plain ``\\w`` character class.
    """

    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("_", " ")
    normalized = "".join(
        character
        if character.isalnum()
        or character.isspace()
        or unicodedata.category(character).startswith("M")
        else " "
        for character in normalized
    )
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_language(language: str | None) -> str | None:
    """Return a supported primary language code, or ``None`` for auto-detect."""

    if language is None:
        return None

    value = language.strip().lower().replace("_", "-")
    if not value:
        return None
    if value in AUTO_LANGUAGE_ALIASES:
        return None

    primary = value.split("-", 1)[0]
    if primary not in SUPPORTED_LANGUAGE_PRIMARY_CODES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGE_PRIMARY_CODES))
        raise ClassificationValidationError(
            f"Unsupported language '{language}'. Supported language codes: "
            f"{supported}."
        )

    return primary


def contains_keyword(text: str, keyword: str) -> bool:
    """Match a whole keyword or phrase without matching inside larger words."""

    if not keyword:
        return False
    return (
        re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None
    )


def _keywords(*items: str) -> tuple[str, ...]:
    return tuple(normalize_for_matching(item) for item in items)


@dataclass(frozen=True, slots=True)
class CategoryRule:
    category: ComplaintCategory
    department: str
    base_severity: Severity
    keywords: tuple[str, ...]


# Order is also the deterministic tie-breaker: the first category with the
# highest score wins, and the request is flagged for review.
CATEGORY_RULES: tuple[CategoryRule, ...] = (
    CategoryRule(
        category=ComplaintCategory.traffic_accident,
        department="Traffic Police",
        base_severity=Severity.high,
        keywords=_keywords(
            "traffic accident",
            "road accident",
            "accident",
            "collision",
            "crash",
            "vehicle collision",
            "car accident",
            "bike accident",
            "two wheeler accident",
            "hit and run",
            "दुर्घटना",
            "सड़क दुर्घटना",
            "अपघात",
            "અકસ્માત",
        ),
    ),
    CategoryRule(
        category=ComplaintCategory.road_blockage,
        department="Traffic Department",
        base_severity=Severity.high,
        keywords=_keywords(
            "road blockage",
            "road block",
            "roadblock",
            "road blocked",
            "blocked road",
            "road closed",
            "road closure",
            "blocking the road",
            "blocking traffic",
            "fallen tree",
            "tree fallen",
            "tree on road",
            "debris",
            "obstruction",
            "obstructed",
            "traffic jam",
            "congestion",
            "मार्ग अवरुद्ध",
            "सड़क बंद",
            "पेड़ गिरा",
            "रस्ता बंद",
            "वृक्ष पडला",
            "માર્ગ બંધ",
            "રસ્તો બંધ",
            "વૃક્ષ પડ્યું",
        ),
    ),
    CategoryRule(
        category=ComplaintCategory.drainage,
        department="Drainage Department",
        base_severity=Severity.medium,
        keywords=_keywords(
            "drainage",
            "sewage",
            "sewer",
            "sewerage",
            "drain",
            "drains",
            "blocked drain",
            "overflowing drain",
            "open drain",
            "manhole",
            "gutter",
            "waterlogging",
            "water logging",
            "waste water",
            "wastewater",
            "flooding",
            "flood",
            "नाली",
            "नाला",
            "सीवर",
            "गटर",
            "सीवेज",
            "सांडपाणी",
            "गटार",
            "पूर",
            "ગટર",
            "ગટરો",
            "ગંદા પાણી",
            "સીવર",
        ),
    ),
    CategoryRule(
        category=ComplaintCategory.water_leakage,
        department="Water Department",
        base_severity=Severity.medium,
        keywords=_keywords(
            "water leakage",
            "water leak",
            "leaking water",
            "water is leaking",
            "pipe leak",
            "pipe leakage",
            "broken pipe",
            "burst pipe",
            "water pipe",
            "water pipeline",
            "leaking pipeline",
            "water supply",
            "no water",
            "water shortage",
            "drinking water",
            "tap leak",
            "tap water",
            "पानी लीक",
            "पानी बह",
            "पाइप",
            "पानी की लीक",
            "पाणी गळ",
            "पाण्याची गळती",
            "પાણી લીક",
            "પાણી વહે",
            "પાઇપ",
        ),
    ),
    CategoryRule(
        category=ComplaintCategory.streetlight,
        department="Electrical Department",
        base_severity=Severity.medium,
        keywords=_keywords(
            "streetlight",
            "street light",
            "street lights",
            "street lamp",
            "lamp post",
            "lamppost",
            "light not working",
            "lights not working",
            "street light not working",
            "no light",
            "no lights",
            "dark street",
            "street lighting",
            "electric pole",
            "power outage",
            "power cut",
            "बत्ती",
            "स्ट्रीट लाइट",
            "रोशनी",
            "बिजली",
            "दिवा",
            "रस्त्यावरचा दिवा",
            "वीज",
            "સ્ટ્રીટ લાઇટ",
            "લાઇટ",
            "વીજ",
        ),
    ),
    CategoryRule(
        category=ComplaintCategory.pothole,
        department="Road Department",
        base_severity=Severity.medium,
        keywords=_keywords(
            "pothole",
            "potholes",
            "pot hole",
            "pot holes",
            "damaged road",
            "damaged roads",
            "broken road",
            "road damage",
            "road is damaged",
            "road cave in",
            "cave in",
            "crater",
            "craters",
            "uneven road",
            "bad road",
            "गड्ढा",
            "गड्ढे",
            "सड़क खराब",
            "सड़क टूटी",
            "रस्ता खराब",
            "खड्डा",
            "खड्डे",
            "સડક ખરાબ",
            "ખાડો",
            "ખાડા",
        ),
    ),
    CategoryRule(
        category=ComplaintCategory.garbage,
        department="Sanitation Department",
        base_severity=Severity.medium,
        keywords=_keywords(
            "garbage",
            "trash",
            "rubbish",
            "litter",
            "waste",
            "solid waste",
            "waste pile",
            "garbage pile",
            "dumping",
            "illegal dumping",
            "dump site",
            "not collected",
            "uncollected",
            "sanitation",
            "कचरा",
            "कूड़ा",
            "कचरे",
            "घाण",
            "ગંદકી",
            "કચરો",
            "કચરા",
        ),
    ),
)

OTHER_DEPARTMENT = "General Administration"
OTHER_BASE_SEVERITY = Severity.low

CRITICAL_SEVERITY_SIGNALS = _keywords(
    "death",
    "dead",
    "fatal",
    "killed",
    "killing",
    "casualty",
    "casualties",
    "injury",
    "injuries",
    "injured",
    "serious injury",
    "serious injuries",
    "severe injury",
    "severe injuries",
    "critically injured",
    "unconscious",
    "person trapped",
    "people trapped",
    "trapped",
    "electrocuted",
    "electrocution",
    "live wire",
    "gas leak",
    "building collapse",
    "building collapsed",
    "road collapse",
    "road collapsed",
    "sinkhole",
    "explosion",
    "fire",
    "burning",
    "missing child",
    "मौत",
    "मृत",
    "घायल",
    "गंभीर",
    "मृत्यू",
    "गंभीर जखमी",
    "મૃત્યુ",
    "ઈજા",
    "આગ",
)

HIGH_SEVERITY_SIGNALS = _keywords(
    "major",
    "heavy",
    "severe",
    "danger",
    "dangerous",
    "hazard",
    "hazardous",
    "unsafe",
    "exposed",
    "overflowing",
    "overflow",
    "burst",
    "leaking badly",
    "several days",
    "two days",
    "three days",
    "for days",
    "night",
    "dark",
    "school",
    "hospital",
    "main road",
    "highway",
    "traffic jam",
    "sewage",
    "open manhole",
    "manhole open",
    "deep pothole",
    "large pothole",
    "big pothole",
    "health risk",
    "children",
    "elderly",
    "disabled",
    "ambulance",
    "emergency",
    "fallen tree",
    "tree fallen",
    "power line",
    "रात",
    "स्कूल",
    "अस्पताल",
    "बड़ा",
    "શાળા",
    "હોસ્પિટલ",
    "મોટું",
)

LOW_SEVERITY_SIGNALS = _keywords(
    "minor",
    "small",
    "slight",
    "slightly",
    "cosmetic",
    "not urgent",
    "low priority",
    "occasional",
    "single",
    "tiny",
    "little",
    "no damage",
    "not dangerous",
    "not hazardous",
    "छोटा",
    "मामूली",
    "નાનું",
)
