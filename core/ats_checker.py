import re
from collections.abc import Iterable
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "for",
    "in",
    "of",
    "or",
    "the",
    "to",
    "with",
}


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _normalise_keyword(keyword: str) -> str:
    keyword = re.sub(r"\s+", " ", keyword.strip().lower())
    return keyword.strip(" .,:;|/-")


def _split_keyword_candidates(text: str) -> list[str]:
    parts = re.split(r"[,;\n\r•●○▪◦]| and | or ", text, flags=re.IGNORECASE)
    return [_normalise_keyword(part) for part in parts]


def extract_jd_keywords(job_description: dict[str, Any], limit: int = 30) -> list[str]:
    """Extract a stable keyword list from one parsed job description."""
    priority_fields = (
        "required_skills",
        "responsibilities",
        "nice_to_have",
        "about_role",
        "job_description",
    )
    keywords: list[str] = []
    seen: set[str] = set()

    for field in priority_fields:
        value = job_description.get(field)
        if not value:
            continue

        for candidate in _split_keyword_candidates(_flatten_text(value)):
            words = re.findall(r"[a-z0-9+#.]+", candidate)
            if not words or all(word in STOPWORDS for word in words):
                continue

            keyword = " ".join(words)
            if keyword and keyword not in seen:
                keywords.append(keyword)
                seen.add(keyword)

            if len(keywords) >= limit:
                return keywords

    return keywords


def generate_ats_analysis(
    jd_keywords: list[str], resume: dict[str, Any]
) -> dict[str, Any]:
    """Compare one resume against the already-extracted JD keywords."""
    resume_text = _normalise_keyword(_flatten_text(resume))
    resume_tokens = set(re.findall(r"[a-z0-9+#.]+", resume_text))

    present_keywords: list[str] = []
    partial_keywords: list[str] = []
    missing_keywords: list[str] = []

    for keyword in jd_keywords:
        normalised_keyword = _normalise_keyword(keyword)
        keyword_tokens = re.findall(r"[a-z0-9+#.]+", normalised_keyword)

        if not keyword_tokens:
            continue
        if re.search(rf"\b{re.escape(normalised_keyword)}\b", resume_text):
            present_keywords.append(keyword)
        elif len(keyword_tokens) > 1 and any(
            token in resume_tokens for token in keyword_tokens
        ):
            partial_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    total_keywords = (
        len(present_keywords) + len(partial_keywords) + len(missing_keywords)
    )
    coverage = 0.0
    if total_keywords:
        coverage = round(
            (len(present_keywords) + 0.5 * len(partial_keywords)) / total_keywords,
            2,
        )

    return {
        "present_keywords": present_keywords,
        "partial_keywords": partial_keywords,
        "missing_keywords": missing_keywords,
        "keyword_coverage": coverage,
        "total_keywords": total_keywords,
    }
