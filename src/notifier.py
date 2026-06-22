"""Notificações opcionais via Telegram e webhook."""
import logging
import requests
from .config import env

log = logging.getLogger(__name__)


def send_telegram(text: str) -> bool:
    token = env("TELEGRAM_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        max_len = 4000
        chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
        for chunk in chunks:
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }, timeout=20)
            if r.status_code != 200:
                log.warning("Telegram %s: %s", r.status_code, r.text[:200])
                return False
        return True
    except Exception as e:
        log.warning("Falha Telegram: %s", e)
        return False


def post_webhook(payload: dict) -> bool:
    url = env("WEBHOOK_URL")
    if not url:
        return False
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.status_code < 400
    except Exception as e:
        log.warning("Webhook falhou: %s", e)
        return False


def notify_brief(summary_text: str, brief_path: str, repo_url: str = ""):
    sent_t = send_telegram(summary_text)
    if sent_t:
        log.info("Telegram enviado.")
    sent_w = post_webhook({"summary": summary_text, "path": brief_path, "repo": repo_url})
    if sent_w:
        log.info("Webhook enviado.")
    return sent_t, sent_w
