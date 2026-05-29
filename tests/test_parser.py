import sys
from os import path

# handle test
absolute_path: str = path.abspath(__file__)
parent_dir: str = path.dirname(absolute_path)
grandparent_dir: str = path.dirname(parent_dir)

# append grandparent to path
sys.path.append(grandparent_dir)

from core.parser import extract_sections
from utils.helpers import RESUME_HEADING_ALIASES


def test_extract_sections_supports_singular_skill_heading():
    text = (
        "Summary Candidate profile "
        "Experience Built data products "
        "Education BSc Computer Science "
        "Skill Python, SQL, Streamlit"
    )

    sections = extract_sections(text, RESUME_HEADING_ALIASES)

    assert sections["skills"] == "Python, SQL, Streamlit"


def test_extract_sections_extracts_final_section_without_next_heading():
    text = "Summary Candidate profile Languages English Malay"

    sections = extract_sections(text, RESUME_HEADING_ALIASES)

    assert sections["languages"] == "English Malay"
