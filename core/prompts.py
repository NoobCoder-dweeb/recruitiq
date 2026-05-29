from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Any

template = """
ASK \
You are a Human Resource assistant who reviews resumes and determines if the candidate is suitable for the role, given the job description. You are to map the keywords and content in the resume to the job description and rate the similarity from 0.00 to 1.00. More matches lead to higher rating. \
\
JOB DESCRIPTION: \
{job_description} \
\
CANDIDATE EMAIL: \
{email} \
\
RESUME: \
{resume} \
\
CONSTRAINTS: \
- Must adhere to the output format provided. \
- Do not generate any irrelevant or fake information. \
\
OUTPUT FORMAT: \
{format_instructions}
"""


class OutputParser(BaseModel):
    email: EmailStr = Field(title="email", description="Candidate email.")
    rating: float = Field(
        title="rating",
        description="Rating of the suitability of the candidate to the job description",
        ge=0.0,
        le=1.0,
    )
    explanation: str = Field(
        title="explanation",
        description="Explanation provided by agent on why the rating is given to the candidate",
    )

    @field_validator("rating", mode="before")
    @classmethod
    def val_rating(cls, value: Any) -> Any:
        value = float(value)

        if value < 0.0:
            return 0.0
        elif value > 1.0:
            return 1.0
        else:
            return round(value, 2)


output_parser = PydanticOutputParser(
    name="output_parser",
    pydantic_object=OutputParser,
)

# prompt_template = PromptTemplate(
#     template=template,
#     input_variables=['job_description', 'resume'],
#     output_parser=output_parser,
# )
prompt_template = ChatPromptTemplate.from_template(
    template=template,
).partial(format_instructions=output_parser.get_format_instructions())
