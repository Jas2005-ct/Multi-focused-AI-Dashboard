import os
import logging

logger = logging.getLogger(__name__)

# Celery task — only registered if broker is configured
try:
    from celery_app import celery_app

    @celery_app.task(name="auths.tasks.send_otp_email")
    def send_otp_email(email: str, otp: str):
        """Prod: send OTP via email. Replace SMTP details via env."""
        # TODO: plug real SMTP / SES / SendGrid
        # Example with smtplib:
        # import smtplib
        # from email.message import EmailMessage
        # msg = EmailMessage()
        # msg["Subject"] = "Your OTP"
        # msg["From"] = os.getenv("EMAIL_FROM", "noreply@example.com")
        # msg["To"] = email
        # msg.set_content(f"Your OTP is {otp} (valid 5 min)")
        # with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587"))) as s:
        #     s.starttls()
        #     s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
        #     s.send_message(msg)
        logger.info(f"[Celery] OTP email to {email}: {otp} (valid 5 min)")
        # For now just log — proves Celery pipeline works
        print(f"\n[Celery] OTP for {email}: {otp}\n")
        return True

except Exception as e:
    logger.warning(f"Celery not configured, email tasks disabled: {e}")
    send_otp_email = None  # type: ignore


def dispatch_otp(email: str, otp: str):
    """Env-driven sender: Celery if broker set, else terminal print (dev)."""
    broker = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL")
    use_celery = os.getenv("OTP_EMAIL_BACKEND", "auto").lower()

    # Explicit env forces behavior
    if use_celery == "celery" and send_otp_email and broker:
        send_otp_email.delay(email, otp)  # type: ignore
        logger.info(f"OTP dispatched via Celery to {email}")
        return
    if use_celery == "print":
        _print_otp(email, otp)
        return

    # Auto: if broker + task available → Celery, else print
    if broker and send_otp_email:
        try:
            send_otp_email.delay(email, otp)  # type: ignore
            logger.info(f"OTP auto-dispatched via Celery to {email}")
            return
        except Exception as e:
            logger.warning(f"Celery dispatch failed ({e}), falling back to print")
    _print_otp(email, otp)


def _print_otp(email: str, otp: str):
    print(f"\n{'='*50}\n[FORGOT-PASSWORD] OTP for {email}: {otp} (valid 5 min)\n{'='*50}\n")
    logger.info(f"OTP for {email}: {otp} (expires in 300s)")
