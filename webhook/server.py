import asyncio
import logging
import os
from fastapi import APIRouter, BackgroundTasks, Request
from bot.telegram import send_alert_notification, send_analysis

router = APIRouter()
logger = logging.getLogger(__name__)

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /app


@router.post("/webhook/alertmanager")
async def alertmanager_webhook(request: Request, background: BackgroundTasks):
    payload = await request.json()
    for alert in payload.get("alerts", []):
        if alert.get("status") != "firing":
            continue
        background.add_task(_process, alert)
    return {"status": "accepted"}


async def _process(alert: dict) -> None:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    alert_name = labels.get("alertname", "UnknownAlert")
    severity = labels.get("severity", "warning")
    namespace = labels.get("namespace", "bookgate")
    summary = annotations.get("summary", "")
    description = annotations.get("description", "")

    # Send the alert notification first and capture its message_id for threading
    notification_id = await send_alert_notification(alert_name, severity, summary)

    prompt = (
        f"Alert firing — use the /investigate-alert skill.\n\n"
        f"Alert: {alert_name}\n"
        f"Severity: {severity}\n"
        f"Namespace: {namespace}\n"
        f"Summary: {summary}\n"
        f"Description: {description}\n"
        f"Labels: {labels}"
    )

    logger.info(f"Analyzing alert: {alert_name}")
    try:
        analysis = await _run_claude(prompt)
        await send_analysis(alert_name, severity, analysis, reply_to_message_id=notification_id)
    except Exception as e:
        logger.exception(f"Failed to analyze {alert_name}")
        await send_analysis(alert_name, severity, f"Analysis failed: {e}", reply_to_message_id=notification_id)


async def _run_claude(prompt: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "claude", "--print", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKDIR,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        return "Analysis timed out after 5 minutes."

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")

    return stdout.decode().strip()
