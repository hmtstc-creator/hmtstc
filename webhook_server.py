import hashlib
import hmac
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request


load_dotenv("/var/www/hmtstc/backend/.env")

app = FastAPI()

LOG_FILE = Path("/var/log/hmtstc-webhook.log")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

DEPLOY_SERVICE = "hmtstc-deploy.service"


def write_log(message: str) -> None:
    text = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(text, flush=True)

    try:
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(text + "\n")
            file.flush()
    except Exception:
        pass


def verify_github_signature(body: bytes, signature: str | None) -> bool:
    if not WEBHOOK_SECRET:
        write_log("WEBHOOK_SECRET eksik.")
        return False

    if not signature or not signature.startswith("sha256="):
        write_log("Webhook signature eksik veya format hatalı.")
        return False

    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    received = signature.replace("sha256=", "", 1)

    return hmac.compare_digest(expected, received)


def get_deploy_status() -> str:
    try:
        result = subprocess.run(
            [
                "sudo",
                "-n",
                "/usr/bin/systemctl",
                "is-active",
                DEPLOY_SERVICE
            ],
            capture_output=True,
            text=True,
            timeout=5
        )

        return (result.stdout or result.stderr or "unknown").strip()

    except Exception as error:
        return f"unknown: {str(error)}"


def trigger_deploy() -> dict:
    current_status = get_deploy_status()

    if current_status == "active":
        write_log("Deploy zaten çalışıyor, yeni istek atlandı.")

        return {
            "triggered": False,
            "reason": "deploy_already_running",
            "deploy_status": current_status
        }

    try:
        result = subprocess.run(
            [
                "sudo",
                "-n",
                "/usr/bin/systemctl",
                "start",
                "--no-block",
                DEPLOY_SERVICE
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            write_log(f"Deploy tetiklenemedi: {error_text}")

            return {
                "triggered": False,
                "reason": "systemctl_start_failed",
                "error": error_text,
                "return_code": result.returncode
            }

        write_log("Deploy service tetiklendi.")

        return {
            "triggered": True,
            "reason": None,
            "deploy_status": "started"
        }

    except Exception as error:
        write_log(f"Deploy tetikleme exception: {str(error)}")

        return {
            "triggered": False,
            "reason": "exception",
            "error": str(error)
        }


@app.post("/webhook")
async def webhook(
    req: Request,
    x_hub_signature_256: str | None = Header(default=None),
):
    body = await req.body()

    if not verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    commits = data.get("commits", [])

    for commit in commits:
        write_log("----")
        write_log("Mesaj: " + str(commit.get("message")))

        for file in commit.get("modified", []):
            write_log("MODIFIED: " + file)

        for file in commit.get("added", []):
            write_log("ADDED: " + file)

        for file in commit.get("removed", []):
            write_log("REMOVED: " + file)

    deploy_result = trigger_deploy()

    return {
        "ok": True,
        "deploy": deploy_result
    }


@app.get("/webhook/health")
def webhook_health():
    return {
        "status": "ok",
        "service": "hmtstc-webhook",
        "secret_loaded": bool(WEBHOOK_SECRET),
        "deploy_service": DEPLOY_SERVICE,
        "deploy_status": get_deploy_status()
    }