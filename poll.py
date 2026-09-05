"""Telegram'dan /tara /abd komutlarini okur. Ek paket gerekmez."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.telegram.org/bot{token}/{method}"
OFFSET_PATH = Path("telegram_offset.txt")
HELP = (
    "LiderBorsa komutlari\n"
    "\n"
    "/tara — Borsa Istanbul simdi tara\n"
    "/abd — Amerikan borsasi simdi tara\n"
    "/yardim — bu liste\n"
    "\n"
    "Komutu yazin, menuden de secilebilir.\n"
    "Yazinca en gec birkac dakika icinde cevap gelir. PC acik kalmaz."
)


def _api(token: str, method: str, payload: dict | None = None) -> dict:
    url = API.format(token=token, method=method)
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}


def _write_output(need_scan: bool, market: str, notify_all: bool) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        print(f"need_scan={need_scan} market={market} notify_all={notify_all}")
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"need_scan={'true' if need_scan else 'false'}\n")
        handle.write(f"market={market}\n")
        handle.write(f"notify_all={'true' if notify_all else 'false'}\n")


def _load_offset() -> int | None:
    if not OFFSET_PATH.exists():
        return None
    text = OFFSET_PATH.read_text(encoding="utf-8").strip()
    return int(text) if text.isdigit() else None


def _save_offset(value: int) -> None:
    OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(str(value), encoding="utf-8")


def _normalize(text: str) -> str:
    raw = (text or "").strip().lower()
    raw = raw.split("@", 1)[0].strip()
    return raw.lstrip("/").strip()


def _same_id(left: object, right: object) -> bool:
    try:
        return int(str(left).strip()) == int(str(right).strip())
    except (TypeError, ValueError):
        return str(left).strip() == str(right).strip()


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram secret yok.")
        _write_output(False, "Borsa İstanbul", False)
        return 0

    _api(
        token,
        "setMyCommands",
        {
            "commands": [
                {"command": "tara", "description": "Borsa Istanbul taramasi"},
                {"command": "abd", "description": "Amerikan borsasi taramasi"},
                {"command": "yardim", "description": "Komut listesi"},
            ]
        },
    )

    offset = _load_offset()
    payload: dict = {"timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    data = _api(token, "getUpdates", payload)
    desc = str(data.get("description") or "")
    if not data.get("ok") and "webhook" in desc.lower():
        print("webhook aktif; anlik yanit oradan gelir")
        _write_output(False, "Borsa İstanbul", False)
        return 0
    updates = data.get("result") or []
    print(f"updates={len(updates)} offset={offset} api_ok={bool(data.get('ok'))}")

    market = "Borsa İstanbul"
    need_scan = False
    max_id = offset or 0

    for item in updates:
        update_id = int(item.get("update_id") or 0)
        if update_id >= max_id:
            max_id = update_id + 1
        message = item.get("message") or {}
        from_user = (message.get("from") or {}).get("id")
        from_chat = (message.get("chat") or {}).get("id")
        if not (_same_id(from_chat, chat_id) or _same_id(from_user, chat_id)):
            print(f"skip update={update_id}")
            continue
        command = _normalize(str(message.get("text") or ""))
        reply_to = from_chat or chat_id
        print(f"command={command!r}")
        if command in {"start", "help", "yardim"}:
            _api(
                token,
                "sendMessage",
                {"chat_id": reply_to, "text": HELP, "disable_web_page_preview": True},
            )
        elif command == "tara":
            need_scan = True
            market = "Borsa İstanbul"
            _api(
                token,
                "sendMessage",
                {
                    "chat_id": reply_to,
                    "text": "Borsa Istanbul taranıyor. Liste birazdan gelir.",
                    "disable_web_page_preview": True,
                },
            )
        elif command == "abd":
            need_scan = True
            market = "Amerikan Borsası"
            _api(
                token,
                "sendMessage",
                {
                    "chat_id": reply_to,
                    "text": "Amerikan borsasi taranıyor. Liste birazdan gelir.",
                    "disable_web_page_preview": True,
                },
            )

    if max_id:
        _save_offset(max_id)
        _api(
            token,
            "getUpdates",
            {"offset": max_id, "timeout": 0, "allowed_updates": ["message"]},
        )
        print(f"confirmed_offset={max_id}")

    _write_output(need_scan, market, need_scan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
