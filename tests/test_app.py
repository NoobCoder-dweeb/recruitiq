import sys
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
