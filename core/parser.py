import pdfplumber
import copy
import re

from utils.helpers import JD_HEADING_ALIASES, RESUME_HEADING_ALIASES, RegexPattern


def extract_raw_text(file) -> str:
    """Function that extracts raw text from PDF file"""
    assert file is not None, "File is not parsed!"
    raw_text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            if page is not None:
                raw_text += page.extract_text()

    return raw_text


def normalise_text(raw_text) -> str:
    """Function that preprocesses extracted text"""
    normalised_text: str = copy.deepcopy(raw_text)
    normalised_text = normalised_text.replace("\n\n", "[SECTION BREAK]")
    normalised_text = normalised_text.replace("\n", " ")
    normalised_text = re.sub(r"[ \t]+", " ", normalised_text)  # removes tabs
    normalised_text = normalised_text.replace(", ", "", 1)

    return normalised_text


def find_heading(text: str, alias: str, position: int = 0) -> tuple[int, int] | None:
    """Find the start and end indexes of the heading given current position"""
    pattern = rf"(?<![a-zA-Z]){re.escape(alias)}(?![a-zA-Z])"
    match = re.search(pattern, text[position:], flags=re.IGNORECASE)

    if not match:
        return None

    return position + match.start(), position + match.end()


def extract_sections(
    text: str, heading_aliases: dict[str, list[str]]
) -> dict[str, str | list[str]]:
    assert len(text) > 0, "Text is empty!"
    section_dict: dict[str, str | list[str]] = {}

    heading_matches: list[tuple[int, int, str]] = []

    for key, aliases in heading_aliases.items():
        section_match: tuple[int, int] | None = None

        for alias in aliases:
            alias_match = find_heading(text, alias)

            if not alias_match:
                continue

            if section_match is None or alias_match[0] < section_match[0]:
                section_match = alias_match

        if section_match:
            start_idx, end_idx = section_match
            heading_matches.append((start_idx, end_idx, key))

    heading_matches.sort(key=lambda match: match[0])

    for idx, (_, heading_end_idx, key) in enumerate(heading_matches):
        section_end_idx = (
            heading_matches[idx + 1][0] if idx + 1 < len(heading_matches) else len(text)
        )

        content: str = text[heading_end_idx:section_end_idx].strip()
        content = re.sub(r"^\s*(\[SECTION BREAK\])?\s*[:\-–—|]?\s*", "", content)
        content = re.sub(r"\s*\[SECTION BREAK\]\s*", " ", content)
        content = re.sub(r"\s*[•●○▪◦]\s*", ", ", content)
        content = re.sub(r"^,\s*", "", content)

        section_dict[key] = content

    return section_dict


def parse_job_description(pdf_file) -> dict[str, str | list[str]]:
    """Function to parse job description from PDF"""

    assert pdf_file is not None, "Job Description file is not parsed!"

    raw_text = extract_raw_text(pdf_file)

    normalised_text: str = normalise_text(raw_text)

    # extract text
    jd_index: int = normalised_text.find("— ")
    company_index: int = normalised_text.find(" Company:")

    job_description = normalised_text[jd_index + 1 : company_index].strip()

    jd: dict[str, str | list[str]] = {
        "job_description": job_description,
    }

    section_dict: dict = extract_sections(
        text=normalised_text, heading_aliases=JD_HEADING_ALIASES
    )

    jd = jd | section_dict

    return jd


def parse_resume(pdf_file) -> dict[str, str | list[str]]:
    """Function to parse resume"""

    raw_text: str = extract_raw_text(pdf_file)
    normalised_text: str = normalise_text(raw_text)

    email: str = re.findall(RegexPattern.EMAIL, normalised_text)[0]
    links: list[str] = re.findall(RegexPattern.URL, normalised_text)

    candidate: dict[str, str | list[str]] = {
        "email": email,
        "links": links,
    }

    resume = extract_sections(normalised_text, RESUME_HEADING_ALIASES)
    candidate = candidate | resume

    return candidate
