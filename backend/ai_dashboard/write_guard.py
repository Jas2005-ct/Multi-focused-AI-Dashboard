import re

WRITE_RE = re.compile(
    r"\b(insert|update|delete|create|alter|drop|truncate|replace|upsert|merge)\b",
    re.IGNORECASE,
)

def is_write_intent(sentence: str) -> bool:
    return bool(WRITE_RE.search(sentence)) if sentence else False
