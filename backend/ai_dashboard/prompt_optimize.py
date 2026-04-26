import requests
import json
from settings import OPEN_ROUTER_API_KEY
from ai_dashboard.schemas import QueryResponse, PromptRequest
  
api_key = OPEN_ROUTER_API_KEY


# ----------------------------------
# API Configuration
# ----------------------------------

URL="https://openrouter.ai/api/v1/chat/completions"
header = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
Model="openai/gpt-oss-120b:free"


SQL_SYSTEM_PROMPT = """
You are a senior PostgreSQL SQL Query Compiler.

Your job is to convert user business requests into syntactically valid raw SQL queries.

Rules:
1. Return only executable SQL query.
2. No explanation.
3. No markdown.
4. No introductory text.
"""

def _build_prompt(user_text:str):
    return f"""
Request:
{user_text}

Return JSON:
{{"output_query":""}}
"""


def get_query_format(sentence:PromptRequest) -> QueryResponse:
  try:
    response = requests.post(
        url=URL,
        headers=header,
        json={
            "model":Model,
            "messages":[
                {"role":"system","content":SQL_SYSTEM_PROMPT},
                {"role": "user","content":_build_prompt(sentence.input)}
            ],
            "temperature":0.1,
            "max_tokens":100,
            "response_format": {"type": "json_object"}

        }
    )
    content = response.json()["choices"][0]["message"]["content"]
    print(content)
    return QueryResponse.model_validate(json.loads(content)).model_dump()
  except Exception as e:
    return {"error": str(e)}