import streamlit as st
import base64
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from html import escape

from core.parser import parse_job_description, parse_resume
from core.scorer import groq
from core.prompts import prompt_template, output_parser


def handle_upload() -> None:
    """Function to increment or decrement resume_count on file upload or removal"""
    # retrieve the value
    resumes = st.session_state.get("resumes", None)

    # handle cases when file is none, is a list
    if resumes is None:
        st.session_state.resume_count = 0
    else:
        st.session_state.resume_count = len(resumes)


def clean_response_text(text: str) -> str:
    """Remove markdown bullet markers from generated response text."""
    text = re.sub(r"(?m)^\s*\*\s*", "", str(text))
    return text.replace("*", "").strip()


def get_rating_class(rating: float) -> str:
    if rating > 0.8:
        return "rating-high"
    if rating < 0.5:
        return "rating-low"
    return "rating-neutral"


def format_elapsed_time(seconds: float) -> str:
    total_seconds = int(seconds)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def render_empty_state() -> None:
    st.markdown(
        """
        <div style="text-align: center; padding: 56px 24px;">
            <h2 style="margin: 0;">Submit Document First</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pdf_preview(pdf_bytes: bytes, filename: str) -> None:
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(f"#### {escape(filename)}")
    st.markdown(
        f"""
        <iframe
            src="data:application/pdf;base64,{encoded_pdf}"
            width="100%"
            height="720"
            style="border: 1px solid #e2e8f0; border-radius: 8px;"
        ></iframe>
        """,
        unsafe_allow_html=True,
    )


def render_candidate_comparison(results: list[dict]) -> None:
    st.markdown(
        """
        <style>
        .candidate-card-content {
            padding: 14px 10px;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }
        .card-header h4 {
            margin: 0;
            font-size: 1.05rem;
        }
        .rating-high {
            color: #15803d;
            font-weight: 700;
        }
        .rating-low {
            color: #dc2626;
            font-weight: 700;
        }
        .rating-neutral {
            color: #334155;
            font-weight: 700;
        }
        .card-summary {
            color: #334155;
            line-height: 1.6;
            margin: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    selected_filename = st.session_state.get("selected_resume_filename")
    available_filenames = [result.get("filename") for result in results]

    if selected_filename not in available_filenames:
        selected_filename = available_filenames[0]
        st.session_state.selected_resume_filename = selected_filename

    responses_col, pdf_col = st.columns([1, 1.2])

    with responses_col:
        with st.expander("Candidate Rankings", expanded=True):
            with st.container(height=720, border=False):
                for idx, result in enumerate(results, 1):
                    rating = result.get("rating", 0)
                    email = result.get("email", "N/A")
                    filename = result.get("filename", f"resume-{idx}.pdf")
                    pdf_bytes = result.get("pdf_bytes", b"")
                    summary = clean_response_text(
                        result.get("explanation", "No summary available.")
                    )
                    rating_class = get_rating_class(rating)

                    with st.container(border=True):
                        st.markdown(
                            f"""
                            <div class="candidate-card-content">
                            <div class="card-header">
                                <h3>{escape(email)}</h3>
                                <span class="{rating_class}">Rating: {rating:.2f}</span>
                            </div>
                            <p class="card-summary">{escape(summary)}</p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        preview_col, download_col = st.columns(2)

                        with preview_col:
                            if st.button(
                                "View PDF",
                                key=f"view-{idx}-{filename}",
                                use_container_width=True,
                            ):
                                st.session_state.selected_resume_filename = filename
                                selected_filename = filename

                        with download_col:
                            st.download_button(
                                "Download PDF",
                                data=pdf_bytes,
                                file_name=filename,
                                mime="application/pdf",
                                key=f"download-{idx}-{filename}",
                                use_container_width=True,
                            )

    selected_result = next(
        result for result in results if result.get("filename") == selected_filename
    )

    with pdf_col:
        render_pdf_preview(
            selected_result.get("pdf_bytes", b""),
            selected_result.get("filename", "resume.pdf"),
        )


def main():
    st.set_page_config(
        page_title="RecruitIQ",
        page_icon="🪪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("RecruitIQ")
    st.write(
        "AI-powered resume screening tool that helps recruiters evaluate candidates in seconds"
    )

    job_description_col, input_col = st.columns(2)

    with job_description_col:
        st.header("Job Description")
        job_description = st.file_uploader(
            "Upload job description in PDF format.",
            key="jd",
            max_upload_size=2,  # 2 MB
        )

        if job_description is not None:
            extension = os.path.splitext(job_description.name)[1].lower()

            if extension != ".pdf":
                st.toast(
                    f":red[You have uploaded a {extension} file! Please upload a .pdf file.]",
                    icon="🚨",
                )
            else:
                st.toast(f":green[Job description uploaded successfully!]", icon="😊")

    with input_col:
        st.header("Candidate Resumes")
        resumes: list = st.file_uploader(
            "Upload resumes in PDF format.",
            accept_multiple_files=True,
            key="resumes",
            max_upload_size=200,  # 10 * 2 MB = 200 MB,
            on_change=handle_upload,
        )

        for resume in resumes:
            extension: str = os.path.splitext(resume.name)[1].lower()
            if extension != ".pdf":
                st.toast(
                    f":red[You have uploaded a {extension} file! Please upload a .pdf file.]",
                    icon="🚨",
                )
            else:
                st.toast(f":green[Resume uploaded successfully!]", icon="😊")

        st.write("#### Number of resumes:", st.session_state.get("resume_count", 0))

    # Submit button
    _, submit_col, _ = st.columns([2, 1, 2])
    with submit_col:
        submit_btn = st.button(label="Submit", use_container_width=True)

    # bottom row to display list of candidates
    response_placeholder = st.empty()
    saved_results = st.session_state.get("scoring_results", [])

    if saved_results:
        with response_placeholder.container():
            render_candidate_comparison(saved_results)
    else:
        with response_placeholder.container(border=True):
            render_empty_state()

    if submit_btn:
        if not job_description and not resumes:
            st.toast(
                ":red[No job description or resume. Please upload them before submitting.]",
                icon="🤦",
            )
            return
        if not job_description:
            st.toast(
                ":red[No job description. Please upload it before submitting.]",
                icon="🤦",
            )
            return
        if not resumes:
            st.toast(":red[No resume. Please upload it before submitting.]", icon="🤦")
            return
        if len(resumes) != len(list(set(resumes))):
            st.toast(":red[Cannot upload duplicates. Please retry again.]", icon="🤦")
            return

        response_placeholder.empty()

        with response_placeholder.container(border=True):
            st.markdown(
                """
                <div style="padding: 28px 24px 12px;">
                    <h2 style="margin: 0 0 8px;">Resume is being scored...</h2>
                </div>
                """,
                unsafe_allow_html=True,
            )
            progress_bar = st.progress(
                0,
                text="Resume is being scored... Time taken: 00:00",
            )
            progress_status = st.empty()

            # parse the pdf
            start_time = time.monotonic()
            progress_status.markdown("Parsing job description and resumes...")
            jd = parse_job_description(job_description)

            # parse resume
            candidates: dict = {}
            resume_files: dict[str, bytes] = {}

            for resume in resumes:
                filename: str = resume.name
                resume_files[filename] = resume.getvalue()
                resume.seek(0)
                candidate = parse_resume(resume)
                candidates[filename] = candidate

            # score the resume against job description
            chain = prompt_template | groq | output_parser
            results: list = []
            total_candidates = len(candidates)

            with ThreadPoolExecutor(max_workers=1) as executor:
                for idx, (filename, candidate) in enumerate(candidates.items(), 1):
                    email: str = candidate.get("email", "candidate")
                    future = executor.submit(
                        chain.invoke,
                        input={
                            "email": email,
                            "job_description": jd,
                            "resume": candidate,
                        },
                    )

                    while not future.done():
                        elapsed = format_elapsed_time(time.monotonic() - start_time)
                        progress_bar.progress(
                            (idx - 1) / total_candidates,
                            text=(
                                f"Resume is being scored... {idx}/{total_candidates} "
                                f"| Time taken: {elapsed}"
                            ),
                        )
                        progress_status.markdown(
                            f"Scoring **{email}**. Time taken: `{elapsed}`"
                        )
                        time.sleep(1)

                    response = future.result()
                    result = response.model_dump()
                    result["filename"] = filename
                    result["pdf_bytes"] = resume_files[filename]
                    results.append(result)

                    elapsed = format_elapsed_time(time.monotonic() - start_time)
                    progress_bar.progress(
                        idx / total_candidates,
                        text=(
                            f"Resume scoring complete... {idx}/{total_candidates} "
                            f"| Time taken: {elapsed}"
                        ),
                    )
                    progress_status.markdown(
                        f"Completed **{email}**. Time taken: `{elapsed}`"
                    )

            progress_status.empty()

        # sort the results by descending rating
        results = sorted(results, key=lambda item: item.get("rating", 0), reverse=True)
        st.session_state.scoring_results = results
        st.session_state.selected_resume_filename = results[0].get("filename")

        # display responses as side-by-side cards and PDF preview
        response_placeholder.empty()
        with response_placeholder.container():
            render_candidate_comparison(results)


if __name__ == "__main__":
    try:
        st.session_state.setdefault("resume_count", 0)
        main()
    except Exception as e:
        st.toast(f":red[{e}]", icon="🤦")
