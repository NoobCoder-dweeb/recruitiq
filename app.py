import streamlit as st
import os


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
                    f"You have uploaded a {extension} file! Please upload a .pdf file.",
                    icon="🚨",
                )
            else:
                st.toast(f"Job description uploaded successfully!", icon="😊")

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
                    f"You have uploaded a {extension} file! Please upload a .pdf file.",
                    icon="🚨",
                )
            else:
                st.toast(f"Resume uploaded successfully!", icon="😊")

        st.write("#### Number of resumes:", st.session_state.get("resume_count", 0))

    # Submit button
    submit_btn = st.button(label="Submit")

    if submit_btn:
        if job_description:
            st.write(job_description.name)
        if resumes:
            for resume in resumes:
                st.write(resume.name)


if __name__ == "__main__":
    st.session_state.setdefault("resume_count", 0)
    main()
