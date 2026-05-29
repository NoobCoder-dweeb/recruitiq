import sys
from os import path

# handle test
absolute_path: str = path.abspath(__file__)
parent_dir: str = path.dirname(absolute_path)
grandparent_dir: str = path.dirname(parent_dir)

# append grandparent to path
sys.path.append(grandparent_dir)

from core.prompts import OutputParser, prompt_template


def test_resume_scoring_prompt_has_expected_inputs():
    assert set(prompt_template.input_variables) == {
        "email",
        "job_description",
        "resume",
    }


def test_resume_scoring_prompt_formats_without_extra_variables():
    messages = prompt_template.format_messages(
        email="candidate@example.com",
        job_description={"job_description": "Build data products"},
        resume={"skills": "Python"},
    )

    assert len(messages) == 1


def test_output_parser_accepts_float_rating():
    output = OutputParser(
        email="candidate@example.com",
        rating=0.95,
        explanation="Strong match",
    )

    assert output.rating == 0.95


def test_output_parser_clamps_and_rounds_rating():
    output = OutputParser(
        email="candidate@example.com",
        rating=1.234,
        explanation="Strong match",
    )

    assert output.rating == 1.0
