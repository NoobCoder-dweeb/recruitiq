JD_HEADING_ALIASES: dict[str, list[str]] = {
    "about_role": ["About the Role", "Role Overview", "About This Role"],
    "responsibilities": [
        "Key Responsibilities",
        "Responsibilities",
        "What You’ll Do",
    ],
    "required_skills": [
        "Required Skills & Qualifications",
        "Requirements",
        "Qualifications",
    ],
    "nice_to_have": ["Nice to Have", "Preferred Qualifications", "Bonus Points"],
}

RESUME_HEADING_ALIASES: dict[str, list[str]] = {
    "summary": [
        "Summary",
        "Profile",
        "About Me",
        "Overview",
    ],
    "experience": [
        "Professional Experience",
        "Work Experience",
        "Employment History",
        "Career History",
        "Experience",
    ],
    "education": [
        "Education",
        "Academic Background",
        "Qualifications",
    ],
    "skills": [
        "Technical Skills",
        "Core Skills",
        "Key Skills",
        "Technical Competencies",
        "Skills",
        "Skill",
    ],
    "certifications": [
        "Certifications",
        "Certificates",
    ],
    "extracurricular": [
        "Extracurricular",
        "Activities",
    ],
    "languages": [
        "Languages",
        "Language Proficiency",
    ],
}


class RegexPattern:
    """Class containing regex patterns"""

    EMAIL: str = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    URL: str = r"(https?://[^\s]+|www\.[^\s]+|linkedin\.com/[^\s]+|github\.com/[^\s]+)"
