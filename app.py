import streamlit as st
import base64
import io
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from html import escape

import pdfplumber
import pypdfium2 as pdfium
from PIL import ImageDraw

from core.ats_checker import extract_jd_keywords, generate_ats_analysis
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


def build_scoring_chain():
    return prompt_template | groq | output_parser


def response_to_dict(response) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    return dict(response)


def keyword_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", str(text).lower())


def find_keyword_boxes(words: list[dict], keywords: list[str]) -> list[dict[str, float]]:
    token_stream: list[tuple[str, int]] = []

    for word_idx, word in enumerate(words):
        for token in keyword_tokens(word.get("text", "")):
            token_stream.append((token, word_idx))

    boxes: list[dict[str, float]] = []
    seen_boxes: set[tuple[float, float, float, float]] = set()

    for keyword in sorted(keywords, key=lambda item: len(str(item)), reverse=True):
        tokens = keyword_tokens(keyword)
        if not tokens:
            continue

        token_count = len(tokens)
        for idx in range(0, len(token_stream) - token_count + 1):
            candidate_tokens = [
                token for token, _ in token_stream[idx : idx + token_count]
            ]
            if candidate_tokens != tokens:
                continue

            word_indexes = {
                word_idx for _, word_idx in token_stream[idx : idx + token_count]
            }
            matched_words = [words[word_idx] for word_idx in sorted(word_indexes)]
            x0 = min(word["x0"] for word in matched_words)
            x1 = max(word["x1"] for word in matched_words)
            top = min(word["top"] for word in matched_words)
            bottom = max(word["bottom"] for word in matched_words)
            box_key = (round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1))

            if box_key in seen_boxes:
                continue

            boxes.append({"x0": x0, "x1": x1, "top": top, "bottom": bottom})
            seen_boxes.add(box_key)

    return boxes


def render_ats_summary_html(ats_analysis: dict) -> str:
    keyword_coverage = ats_analysis.get("keyword_coverage")
    total_keywords = ats_analysis.get("total_keywords")

    if keyword_coverage is None or total_keywords is None:
        return ""

    present_keywords = ats_analysis.get("present_keywords", [])
    partial_keywords = ats_analysis.get("partial_keywords", [])
    exact_keyword_chips = "".join(
        f'<span class="ats-keyword-chip">{escape(str(keyword))}</span>'
        for keyword in present_keywords
    )
    partial_keyword_chips = "".join(
        f'<span class="ats-keyword-chip ats-keyword-chip-partial">{escape(str(keyword))}</span>'
        for keyword in partial_keywords
    )

    if not exact_keyword_chips and not partial_keyword_chips:
        keyword_chips = '<span class="ats-empty-keywords">No keyword matches</span>'
    else:
        keyword_chips = exact_keyword_chips + partial_keyword_chips

    return (
        '<section class="ats-summary-box">'
        '<div class="ats-score-row">'
        '<span class="ats-score-label">ATS match</span>'
        f'<span class="ats-score-value">{keyword_coverage:.0%}</span>'
        "</div>"
        '<div class="ats-meter">'
        f'<div class="ats-meter-fill" style="width: {keyword_coverage:.0%};"></div>'
        "</div>"
        f'<div class="ats-keyword-count">{len(present_keywords)} exact, {len(partial_keywords)} partial of {total_keywords} JD keywords</div>'
        f'<div class="ats-keyword-grid">{keyword_chips}</div>'
        "</section>"
    )


def render_pdf_page_image(pdf_document, page_index: int, scale: float = 1.4):
    page = pdf_document[page_index]
    bitmap = page.render(scale=scale)
    return bitmap.to_pil()


def draw_keyword_boxes(image, page, boxes: list[dict[str, float]]) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    scale_x = image.width / page.width
    scale_y = image.height / page.height

    for box in boxes:
        rectangle = (
            box["x0"] * scale_x,
            box["top"] * scale_y,
            box["x1"] * scale_x,
            box["bottom"] * scale_y,
        )
        draw.rectangle(
            rectangle,
            fill=(20, 184, 166, 70),
            outline=(15, 118, 110, 255),
            width=4,
        )


def build_annotated_pdf_page_images(
    pdf_bytes: bytes, matched_keywords: list[str]
) -> list:
    pdf_document = pdfium.PdfDocument(pdf_bytes)
    images = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            image = render_pdf_page_image(pdf_document, page_index)
            words = page.extract_words() if matched_keywords else []
            boxes = find_keyword_boxes(words, matched_keywords)
            draw_keyword_boxes(image, page, boxes)
            images.append(image)

    return images


def analyse_uploaded_resumes(
    job_description,
    resumes: list,
    *,
    chain=None,
    keyword_extractor=extract_jd_keywords,
    ats_analyzer=generate_ats_analysis,
    progress_callback=None,
    progress_interval: float = 1,
) -> list[dict]:
    jd = parse_job_description(job_description)
    jd_keywords = keyword_extractor(jd)

    candidates: dict = {}
    resume_files: dict[str, bytes] = {}

    for resume in resumes:
        filename: str = resume.name
        resume_files[filename] = resume.getvalue()
        resume.seek(0)
        candidates[filename] = parse_resume(resume)

    scoring_chain = chain or build_scoring_chain()
    results: list = []
    total_candidates = len(candidates)

    with ThreadPoolExecutor(max_workers=1) as executor:
        for idx, (filename, candidate) in enumerate(candidates.items(), 1):
            email: str = candidate.get("email", "candidate")
            future = executor.submit(
                scoring_chain.invoke,
                input={
                    "email": email,
                    "job_description": jd,
                    "resume": candidate,
                },
            )

            if progress_callback:
                while not future.done():
                    progress_callback("scoring", idx, total_candidates, email)
                    time.sleep(progress_interval)

            response = future.result()
            result = response_to_dict(response)
            result["filename"] = filename
            result["pdf_bytes"] = resume_files[filename]
            result["ats_analysis"] = ats_analyzer(jd_keywords, candidate)
            results.append(result)

            if progress_callback:
                progress_callback("completed", idx, total_candidates, email)

    return results


def render_empty_state() -> None:
    st.markdown(
        """
        <div style="text-align: center; padding: 56px 24px;">
            <h2 style="margin: 0;">Submit Document First</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pdf_preview(
    pdf_bytes: bytes,
    filename: str,
    *,
    matched_keywords: list[str] | None = None,
) -> None:
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(f"#### {escape(filename)}")

    try:
        page_images = build_annotated_pdf_page_images(
            pdf_bytes, matched_keywords or []
        )
        with st.container(height=720, border=True):
            for page_index, image in enumerate(page_images, 1):
                st.image(
                    image,
                    caption=f"Page {page_index}",
                    use_container_width=True,
                )
    except Exception:
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
        .ats-summary-box {
            border: 1px solid #94a3b8;
            border-radius: 8px;
            padding: 12px;
            margin-top: 14px;
            background: #f8fafc;
        }
        .ats-score-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 12px;
            margin-bottom: 8px;
        }
        .ats-score-label {
            color: #334155;
            font-size: 0.84rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .ats-score-value {
            color: #0f766e;
            font-size: 1.8rem;
            font-weight: 800;
            line-height: 1;
        }
        .ats-meter {
            height: 8px;
            overflow: hidden;
            border-radius: 999px;
            background: #cbd5e1;
            margin-bottom: 8px;
        }
        .ats-meter-fill {
            height: 100%;
            border-radius: 999px;
            background: #0f766e;
        }
        .ats-keyword-count {
            color: #475569;
            font-size: 0.88rem;
            font-weight: 600;
            margin-bottom: 8px;
        }
        .ats-keyword-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        .ats-keyword-chip {
            border: 1px solid #0f766e;
            border-radius: 6px;
            color: #0f766e;
            background: #ecfdf5;
            padding: 4px 8px;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .ats-keyword-chip-partial {
            border-style: dashed;
            color: #0369a1;
            background: #eff6ff;
        }
        .ats-empty-keywords {
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            color: #64748b;
            background: #ffffff;
            padding: 4px 8px;
            font-size: 0.82rem;
            font-weight: 600;
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
                    ats_analysis = result.get("ats_analysis", {})
                    rating_class = get_rating_class(rating)
                    ats_summary = render_ats_summary_html(ats_analysis)

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
                        if ats_summary:
                            st.markdown(ats_summary, unsafe_allow_html=True)
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
            matched_keywords=selected_result.get("ats_analysis", {}).get(
                "present_keywords", []
            ),
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

    def render_saved_results_or_empty() -> None:
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
            render_saved_results_or_empty()
            return
        if not job_description:
            st.toast(
                ":red[No job description. Please upload it before submitting.]",
                icon="🤦",
            )
            render_saved_results_or_empty()
            return
        if not resumes:
            st.toast(":red[No resume. Please upload it before submitting.]", icon="🤦")
            render_saved_results_or_empty()
            return
        if len(resumes) != len(list(set(resumes))):
            st.toast(":red[Cannot upload duplicates. Please retry again.]", icon="🤦")
            render_saved_results_or_empty()
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

            def update_progress(
                state: str, idx: int, total_candidates: int, email: str
            ) -> None:
                elapsed = format_elapsed_time(time.monotonic() - start_time)

                if state == "scoring":
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
                    return

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

            results = analyse_uploaded_resumes(
                job_description,
                resumes,
                progress_callback=update_progress,
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
    else:
        render_saved_results_or_empty()


if __name__ == "__main__":
    try:
        st.session_state.setdefault("resume_count", 0)
        main()
    except Exception as e:
        st.toast(f":red[{e}]", icon="🤦")
