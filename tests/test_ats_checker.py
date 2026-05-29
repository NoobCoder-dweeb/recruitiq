from core.ats_checker import generate_ats_analysis


def test_ats_keyword_coverage_counts_exact_and_partial_matches():
    analysis = generate_ats_analysis(
        ["python django", "sql analytics"],
        {"skills": "Python"},
    )

    assert analysis["present_keywords"] == []
    assert analysis["partial_keywords"] == ["python django"]
    assert analysis["keyword_coverage"] == 0.25
    assert analysis["exact_keyword_coverage"] == 0.0
