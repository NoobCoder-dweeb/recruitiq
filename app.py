import streamlit as st
import os

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
    submit_btn = st.button(label="Submit")

    if submit_btn:
        if not job_description and not resumes:
            raise Exception(
                "No job description or resume. Please upload them before submitting."
            )
        if not job_description:
            raise Exception("No job description. Please upload it before submitting.")
        if not resumes:
            raise Exception("No resume. Please upload it before submitting.")

        # parse the pdf
        jd = parse_job_description(job_description)

        # parse resume
        candidates: dict = {}

        for resume in resumes:
            filename: str = resume.name
            candidate = parse_resume(resume)
            candidates[filename] = candidate

        # score the resume against job description
        chain = prompt_template | groq | output_parser
        results: list = []

        for _, candidate in candidates.items():
            email: str = candidate.get("email", "")
            response = chain.invoke(
                input={
                    "email": email,
                    "job_description": jd,
                    "resume": candidate,
                }
            )

            results.append(response.model_dump())

        # sort the results by descending rating
        st.write(results) 
        

if __name__ == "__main__":
    try:
        st.session_state.setdefault("resume_count", 0)
        main()
    except Exception as e:
        st.toast(f":red[{e}]", icon="🤦")
