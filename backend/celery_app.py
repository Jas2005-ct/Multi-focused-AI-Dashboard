import os
from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", ""))
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

celery_app = Celery(
    "ai_dashboard",
    broker=CELERY_BROKER_URL or "memory://",
    backend=CELERY_RESULT_BACKEND or "cache+memory://",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
)

# Auto-discover tasks in auths
celery_app.autodiscover_tasks(["auths"])
