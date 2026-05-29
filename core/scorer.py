from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os

load_dotenv()

groq = ChatGroq(
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model="llama-3.3-70b-versatile",
    temperature=0.1,
    max_tokens=1024,
)
