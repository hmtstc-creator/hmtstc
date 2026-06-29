import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2").strip()


def llm_enabled() -> bool:
    return bool(OPENAI_API_KEY)


def _extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()

    output = payload.get("output", [])

    if not isinstance(output, list):
        return ""

    chunks: list[str] = []

    for item in output:
        if not isinstance(item, dict):
            continue

        content = item.get("content", [])

        if not isinstance(content, list):
            continue

        for part in content:
            if not isinstance(part, dict):
                continue

            text = part.get("text")

            if isinstance(text, str):
                chunks.append(text)

    return "\n".join(chunks).strip()


def build_market_context(data: dict, settings: dict) -> dict:
    last_scan = data.get("last_scan", {}) if isinstance(data, dict) else {}
    positions = data.get("open_positions", []) if isinstance(data, dict) else []
    history = data.get("history", []) if isinstance(data, dict) else []

    if not isinstance(last_scan, dict):
        last_scan = {}

    candidates = last_scan.get("candidates", [])
    scan_rows = last_scan.get("scan_rows", [])

    if not isinstance(candidates, list):
        candidates = []

    if not isinstance(scan_rows, list):
        scan_rows = []

    return {
        "bot_running": bool(data.get("bot_running", False)),
        "engine_status": data.get("engine_status", "unknown"),
        "mode": data.get("mode", "shadow"),
        "last_scan": {
            "live": bool(last_scan.get("live", False)),
            "time": last_scan.get("time"),
            "scanned": last_scan.get("scanned", 0),
            "candidates_count": last_scan.get("candidates_count", 0),
            "error": last_scan.get("error"),
            "top_candidates": candidates[:8],
            "scan_rows": scan_rows[:10],
        },
        "positions": positions[:10] if isinstance(positions, list) else [],
        "history_tail": history[-10:] if isinstance(history, list) else [],
        "settings": {
            "bot": settings.get("bot", {}),
            "risk": settings.get("risk", {}),
            "current_strategy": settings.get("current_strategy"),
            "coin_filter": settings.get("coin_filter", {}),
        },
    }


def ask_openai_agent(data: dict, settings: dict, message: str) -> dict:
    if not llm_enabled():
        return {
            "ok": False,
            "answer": "",
            "error": "OPENAI_API_KEY missing",
            "provider": "fallback",
        }

    context = build_market_context(data, settings)

    instructions = """
Sen HMTSTC içinde çalışan Jarvis Market Agent'sın.
Görevin kullanıcıya Türkçe, kısa, net, profesyonel ve uygulanabilir cevap vermek.

Kurallar:
- Gerçek emir verdiğini asla söyleme; gerçek emir, unlock, pilot başlatma veya strateji aktif etme yetkin yoktur.
- Bu sistem şu anda sadece analiz, rapor, yorum ve shadow/paper trade öneri modundadır.
- Öneriler paper-only kuyruğa gidebilir; canlı emir uygulaması yapamaz.
- Kesin kazanç, garanti kâr veya yatırım tavsiyesi dili kullanma.
- Market verisi zayıfsa bunu açık söyle.
- Yanıtların kısa, teknik ve karar destek odaklı olsun.
- Gerekirse şu formatı kullan:
  Durum:
  Gözlem:
  Risk:
  Aksiyon:
"""

    user_input = {
        "message": message,
        "market_context": context,
    }

    payload = {
        "model": OPENAI_MODEL,
        "instructions": instructions.strip(),
        "input": json.dumps(user_input, ensure_ascii=False),
        "text": {
            "format": {
                "type": "text"
            }
        }
    }

    request = Request(
        url="https://api.openai.com/v1/responses",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=35) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)

        answer = _extract_output_text(parsed)

        if not answer:
            return {
                "ok": False,
                "answer": "",
                "error": "Empty OpenAI response",
                "provider": "openai",
            }

        return {
            "ok": True,
            "answer": answer,
            "error": None,
            "provider": "openai",
            "model": OPENAI_MODEL,
        }

    except HTTPError as error:
        try:
            raw_error = error.read().decode("utf-8")
        except Exception:
            raw_error = str(error)

        return {
            "ok": False,
            "answer": "",
            "error": raw_error,
            "provider": "openai",
        }

    except URLError as error:
        return {
            "ok": False,
            "answer": "",
            "error": str(error.reason),
            "provider": "openai",
        }

    except Exception as error:
        return {
            "ok": False,
            "answer": "",
            "error": str(error),
            "provider": "openai",
        }