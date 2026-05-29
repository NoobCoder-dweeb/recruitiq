import sys
import time
from os import path
from types import SimpleNamespace

import pytest

# handle test
absolute_path: str = path.abspath(__file__)
parent_dir: str = path.dirname(absolute_path)
grandparent_dir: str = path.dirname(parent_dir)

# append grandparent to path
sys.path.append(grandparent_dir)

class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakePlaceholder:
    def container(self, **kwargs):
        return FakeColumn()

    def empty(self):
        return None


class FakeUpload:
    def __init__(self, name):
        self.name = name
        self.seek_calls = []

    def getvalue(self):
        return f"pdf-bytes-{self.name}".encode()

    def seek(self, position):
        self.seek_calls.append(position)


class FakeChain:
    def __init__(self, calls=None, delay=0):
        self.calls = calls if calls is not None else []
        self.delay = delay

    def invoke(self, input):
        if self.delay:
            time.sleep(self.delay)

        self.calls.append(input)
        return {
            "email": input["email"],
            "rating": 0.7,
            "explanation": "Deterministic test response",
        }


class FakeStreamlit:
    def __init__(self, *, job_description=None, resumes=None, submit=False):
        self.job_description = job_description
        self.resumes = resumes if resumes is not None else []
        self.submit = submit
        self.session_state = SessionState()
        self.page_config = None
        self.titles = []
        self.headers = []
        self.writes = []
        self.markdowns = []
        self.toasts = []
        self.uploaders = []
        self.buttons = []

    def set_page_config(self, **kwargs):
        self.page_config = kwargs

    def title(self, text):
        self.titles.append(text)

    def write(self, *args):
        self.writes.append(args)

    def markdown(self, *args, **kwargs):
        self.markdowns.append((args, kwargs))

    def empty(self):
        return FakePlaceholder()

    def columns(self, count):
        column_count = len(count) if isinstance(count, list) else count
        return [FakeColumn() for _ in range(column_count)]

    def header(self, text):
        self.headers.append(text)

    def file_uploader(self, label, **kwargs):
        self.uploaders.append((label, kwargs))
        key = kwargs.get("key")

        if key == "jd":
            self.session_state[key] = self.job_description
            return self.job_description

        if key == "resumes":
            self.session_state[key] = self.resumes
            on_change = kwargs.get("on_change")
            if on_change:
                on_change()
            return self.resumes

        return None

    def toast(self, message, icon=None):
        self.toasts.append((message, icon))

    def button(self, label, **kwargs):
        self.buttons.append(label)
        return self.submit

@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace())

    import app

    return app

def test_handle_upload_counts_uploaded_resumes(app_module, monkeypatch):
    fake_st = SimpleNamespace(
        session_state=SessionState(resumes=[object(), object(), object()])
    )

    monkeypatch.setattr(app_module, "st", fake_st)

    app_module.handle_upload()

    assert fake_st.session_state.resume_count == 3


def test_clean_response_text_removes_asterisk_bullets(app_module):
    text = "* Strong Python match\n* Relevant SQL experience"

    assert (
        app_module.clean_response_text(text)
        == "Strong Python match\nRelevant SQL experience"
    )


def test_get_rating_class(app_module):
    assert app_module.get_rating_class(0.81) == "rating-high"
    assert app_module.get_rating_class(0.5) == "rating-neutral"
    assert app_module.get_rating_class(0.49) == "rating-low"


def test_format_elapsed_time(app_module):
    assert app_module.format_elapsed_time(0) == "00:00"
    assert app_module.format_elapsed_time(65.9) == "01:05"


def test_render_ats_summary_html_highlights_score_and_keywords(app_module):
    html = app_module.render_ats_summary_html(
        {
            "present_keywords": ["Python", "SQL & BI", "<script>"],
            "partial_keywords": ["model training"],
            "keyword_coverage": 0.75,
            "total_keywords": 4,
        }
    )

    assert "ATS match" in html
    assert "75%" in html
    assert "3 exact, 1 partial of 4 JD keywords" in html
    assert "Python" in html
    assert "SQL &amp; BI" in html
    assert "model training" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_find_keyword_boxes_locates_single_and_multi_word_matches(app_module):
    words = [
        {"text": "Built", "x0": 0, "x1": 20, "top": 0, "bottom": 10},
        {"text": "Python", "x0": 25, "x1": 60, "top": 0, "bottom": 10},
        {"text": "SQL", "x0": 65, "x1": 90, "top": 0, "bottom": 10},
        {"text": "BI", "x0": 95, "x1": 110, "top": 0, "bottom": 10},
    ]

    boxes = app_module.find_keyword_boxes(words, ["Python", "SQL BI"])

    assert boxes == [
        {"x0": 25, "x1": 60, "top": 0, "bottom": 10},
        {"x0": 65, "x1": 110, "top": 0, "bottom": 10},
    ]


def test_main_submit_requires_resume(app_module, monkeypatch):
    fake_st = FakeStreamlit(
        job_description=SimpleNamespace(name="job-description.pdf"),
        submit=True,
    )
    monkeypatch.setattr(app_module, "st", fake_st)

    app_module.main()

    assert(
        ":red[No resume. Please upload it before submitting.]",
        "🤦",
    ) in fake_st.toasts


def test_jd_parsed_once_for_multiple_resumes(app_module, monkeypatch):
    parse_jd_calls = []
    parse_resume_calls = []
    keyword_calls = []

    def fake_parse_job_description(file):
        parse_jd_calls.append(file.name)
        return {"required_skills": "Python, SQL"}

    def fake_parse_resume(file):
        parse_resume_calls.append(file.name)
        return {"email": f"{file.name}@example.com", "skills": "Python"}

    def fake_keyword_extractor(jd):
        keyword_calls.append(jd)
        return ["python", "sql"]

    monkeypatch.setattr(app_module, "parse_job_description", fake_parse_job_description)
    monkeypatch.setattr(app_module, "parse_resume", fake_parse_resume)

    resumes = [FakeUpload("candidate-1.pdf"), FakeUpload("candidate-2.pdf")]

    app_module.analyse_uploaded_resumes(
        FakeUpload("job-description.pdf"),
        resumes,
        chain=FakeChain(),
        keyword_extractor=fake_keyword_extractor,
        ats_analyzer=lambda keywords, resume: {},
    )

    assert parse_jd_calls == ["job-description.pdf"]
    assert parse_resume_calls == ["candidate-1.pdf", "candidate-2.pdf"]
    assert len(keyword_calls) == 1


def test_resume_scoring_invoked_once_per_candidate(app_module, monkeypatch):
    chain_calls = []

    monkeypatch.setattr(
        app_module,
        "parse_job_description",
        lambda file: {"required_skills": "Python, SQL"},
    )
    monkeypatch.setattr(
        app_module,
        "parse_resume",
        lambda file: {"email": f"{file.name}@example.com", "skills": "Python"},
    )

    resumes = [
        FakeUpload("candidate-1.pdf"),
        FakeUpload("candidate-2.pdf"),
        FakeUpload("candidate-3.pdf"),
    ]

    app_module.analyse_uploaded_resumes(
        FakeUpload("job-description.pdf"),
        resumes,
        chain=FakeChain(chain_calls),
        keyword_extractor=lambda jd: ["python", "sql"],
        ats_analyzer=lambda keywords, resume: {},
    )

    assert len(chain_calls) == len(resumes)
    assert [call["email"] for call in chain_calls] == [
        "candidate-1.pdf@example.com",
        "candidate-2.pdf@example.com",
        "candidate-3.pdf@example.com",
    ]


def test_ats_analysis_invoked_once_per_candidate(app_module, monkeypatch):
    ats_calls = []

    monkeypatch.setattr(
        app_module,
        "parse_job_description",
        lambda file: {"required_skills": "Python, SQL"},
    )
    monkeypatch.setattr(
        app_module,
        "parse_resume",
        lambda file: {"email": f"{file.name}@example.com", "skills": "Python"},
    )

    def fake_ats_analyzer(keywords, resume):
        ats_calls.append((keywords, resume))
        return {"present_keywords": ["python"], "missing_keywords": ["sql"]}

    resumes = [FakeUpload("candidate-1.pdf"), FakeUpload("candidate-2.pdf")]

    app_module.analyse_uploaded_resumes(
        FakeUpload("job-description.pdf"),
        resumes,
        chain=FakeChain(),
        keyword_extractor=lambda jd: ["python", "sql"],
        ats_analyzer=fake_ats_analyzer,
    )

    assert len(ats_calls) == len(resumes)
    assert all(call[0] == ["python", "sql"] for call in ats_calls)


def test_every_candidate_result_contains_ats_analysis(app_module, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "parse_job_description",
        lambda file: {"required_skills": "Python, SQL"},
    )
    monkeypatch.setattr(
        app_module,
        "parse_resume",
        lambda file: {"email": f"{file.name}@example.com", "skills": "Python"},
    )

    resumes = [FakeUpload("candidate-1.pdf"), FakeUpload("candidate-2.pdf")]
    expected_ats = {
        "present_keywords": ["python"],
        "partial_keywords": [],
        "missing_keywords": ["sql"],
        "keyword_coverage": 0.5,
        "total_keywords": 2,
    }

    results = app_module.analyse_uploaded_resumes(
        FakeUpload("job-description.pdf"),
        resumes,
        chain=FakeChain(),
        keyword_extractor=lambda jd: ["python", "sql"],
        ats_analyzer=lambda keywords, resume: expected_ats,
    )

    assert len(results) == len(resumes)
    assert all(result["ats_analysis"] == expected_ats for result in results)


def test_processing_time_scales_linearly_with_candidate_count(app_module, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "parse_job_description",
        lambda file: {"required_skills": "Python"},
    )
    monkeypatch.setattr(
        app_module,
        "parse_resume",
        lambda file: {"email": f"{file.name}@example.com", "skills": "Python"},
    )

    def run_candidate_batch(candidate_count):
        resumes = [
            FakeUpload(f"candidate-{idx}.pdf") for idx in range(candidate_count)
        ]
        start = time.perf_counter()
        app_module.analyse_uploaded_resumes(
            FakeUpload("job-description.pdf"),
            resumes,
            chain=FakeChain(delay=0.02),
            keyword_extractor=lambda jd: ["python"],
            ats_analyzer=lambda keywords, resume: {},
        )
        return time.perf_counter() - start

    five_candidate_time = run_candidate_batch(5)
    ten_candidate_time = run_candidate_batch(10)
    ratio = ten_candidate_time / five_candidate_time

    assert 1.5 <= ratio <= 2.5
