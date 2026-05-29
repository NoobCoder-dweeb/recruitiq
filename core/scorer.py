from langchain_groq import ChatGroq
from langchain_core.rate_limiters import InMemoryRateLimiter
from dotenv import load_dotenv
import os

load_dotenv()

# Define the rate limiter to set number of requests to 2 per second
rate_limiter = InMemoryRateLimiter(
    requests_per_second=2.0,
    check_every_n_seconds=0.1,
    max_bucket_size=10, # number of requests per batch
)

groq = ChatGroq(
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model="llama-3.3-70b-versatile",
    temperature=0.1,
    max_tokens=1024,
    rate_limiter=rate_limiter,
    max_retries=3, # returns "429" after 3 failures,
    timeout=60, # max waiting time before cancelling and retrying
)
