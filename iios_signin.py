#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iios 每日签到 — 纯协议实现

加解密：crypto/wasm_crypto.cjs（本地 WASM e/d）
传输：urllib 裸 HTTP（默认 iOS Safari UA，一般无需 CF 挑战）
业务：
  POST /api/user/login  → JWT
  GET  /api/task/all    → checkIn 状态
  POST /api/task        → {type:2, webapp:bool}

环境变量：
  IIOS_USERNAME / IIOS_PASSWORD  账号
  IIOS_BASE_URL                  默认 https://www.iios.fun
  IIOS_USER_AGENT                请求/签名共用 UA
  IIOS_WEBAPP                    默认 true（目标 2 积分）；false 则普通签到
  IIOS_LOG_LEVEL                 debug|info|warning|error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

DIR = Path(__file__).resolve().parent
CRYPTO_DIR = DIR / "crypto"
WASM_CLI = CRYPTO_DIR / "wasm_crypto.cjs"
TOKEN_FILE = DIR / "data" / "token.json"

DEFAULT_BASE_URL = "https://www.iios.fun"
DEFAULT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7.5 "
    "Mobile/15E148 Safari/604.1"
)
DEFAULT_LOG_LEVEL = "info"
LOG_LEVEL_PRIORITY = {"debug": 10, "info": 20, "warning": 30, "error": 40}
ACTIVE_LOG_LEVEL = DEFAULT_LOG_LEVEL


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    base_url: str
    host: str
    user_agent: str
    webapp: bool
    dry_run: bool
    log_level: str
    timeout_s: int


def log(step: str, message: str, level: str = "info", **context: object) -> None:
    normalized = level.strip().lower()
    if LOG_LEVEL_PRIORITY.get(normalized, 20) < LOG_LEVEL_PRIORITY.get(
        ACTIVE_LOG_LEVEL, 20
    ):
        return
    record: dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "level": normalized,
        "step": step,
        "message": message,
    }
    if context:
        record["context"] = context
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="iios pure-protocol daily sign-in")
    p.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Login + task/all only; skip POST /api/task (default: true)",
    )
    p.add_argument(
        "--webapp",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("IIOS_WEBAPP", True),
        help="Send webapp=true for 2-point desktop check-in (default: true)",
    )
    p.add_argument(
        "--base-url",
        default=os.getenv("IIOS_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        help="Site origin, e.g. https://www.iios.fun",
    )
    p.add_argument(
        "--user-agent",
        default=os.getenv("IIOS_USER_AGENT", DEFAULT_UA),
        help="Must match crypto sandbox UA (signature binds UA)",
    )
    p.add_argument(
        "--timeout-s",
        type=int,
        default=_env_int("IIOS_TIMEOUT_S", 45),
        help="HTTP timeout seconds",
    )
    p.add_argument(
        "--log-level",
        default=os.getenv("IIOS_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        help="debug|info|warning|error",
    )
    p.add_argument(
        "--selftest",
        action="store_true",
        help="Only test WASM encrypt + bare GET home",
    )
    return p.parse_args()


def load_config(args: argparse.Namespace) -> Config:
    username = os.getenv("IIOS_USERNAME", "").strip()
    password = os.getenv("IIOS_PASSWORD", "").strip()
    if not args.selftest:
        if not username:
            raise ValueError("Missing IIOS_USERNAME")
        if not password:
            raise ValueError("Missing IIOS_PASSWORD")
    base = args.base_url.rstrip("/")
    host = urlparse(base).hostname or "www.iios.fun"
    return Config(
        username=username,
        password=password,
        base_url=base,
        host=host,
        user_agent=args.user_agent,
        webapp=bool(args.webapp),
        dry_run=bool(args.dry_run),
        log_level=(args.log_level or DEFAULT_LOG_LEVEL).strip().lower(),
        timeout_s=args.timeout_s,
    )


def node_crypto(cmd: str, payload: dict) -> dict:
    if not WASM_CLI.is_file():
        raise FileNotFoundError(f"missing {WASM_CLI}")
    proc = subprocess.run(
        ["node", str(WASM_CLI), cmd, "-"],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        cwd=str(CRYPTO_DIR),
        timeout=60,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"wasm_crypto {cmd} failed:\n{err}")
    out = proc.stdout.decode("utf-8", "replace").strip()
    idx = out.find("{")
    if idx < 0:
        raise RuntimeError(f"no json from wasm_crypto: {out[:200]}")
    return json.loads(out[idx:])


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: Optional[str],
    user_agent: str,
    timeout_s: int,
) -> dict[str, Any]:
    h = {
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "Accept-Encoding": "identity",
    }
    h.update(headers)
    data = body.encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            text = resp.read().decode("utf-8", "replace")
            rh = {k.lower(): v for k, v in resp.headers.items()}
            return {"status": resp.status, "text": text, "headers": rh}
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        rh = {k.lower(): v for k, v in e.headers.items()} if e.headers else {}
        return {"status": e.code, "text": text, "headers": rh}


class ProtocolClient:
    def __init__(self, config: Config):
        self.config = config
        self.api_base = config.base_url + "/api"

    def api(
        self,
        method: str,
        path: str,
        data: Any = None,
        token: Optional[str] = None,
    ) -> dict[str, Any]:
        enc = node_crypto(
            "encrypt",
            {
                "method": method,
                "url": path if path.startswith("/") else f"/{path}",
                "baseURL": "/api",
                "data": data,
                "token": token,
                "userAgent": self.config.user_agent,
                "standalone": self.config.webapp,
                "host": self.config.host,
            },
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "text/plain",
            "X-Timestamp": str(enc["timestamp"]),
            "X-Signature": enc["signature"],
            "Origin": self.config.base_url,
            "Referer": self.config.base_url + "/",
        }
        if token:
            headers["Authorization"] = "Basic " + token

        full = self.api_base + (path if path.startswith("/") else f"/{path}")
        method_u = method.upper()
        body = enc.get("body") if method_u not in ("GET", "HEAD") else None

        http = http_request(
            method_u,
            full,
            headers=headers,
            body=body,
            user_agent=self.config.user_agent,
            timeout_s=self.config.timeout_s,
        )
        text = http["text"]
        status = http["status"]

        plain = None
        js = None
        decrypt_error = None
        looks_cipher = (
            len(text) > 16
            and status < 500
            and not text.lstrip().startswith("<")
            and text.strip() not in ("Forbidden", "forbidden")
            and "Just a moment" not in text
            and "error code:" not in text.lower()
            and "Connection timed out" not in text
        )
        if looks_cipher:
            try:
                dec = node_crypto(
                    "decrypt",
                    {
                        "data": text,
                        "status": status,
                        "headers": http.get("headers") or {},
                        "config": {
                            "method": method,
                            "url": path if path.startswith("/") else f"/{path}",
                            "baseURL": "/api",
                            "headers": enc.get("headers") or headers,
                        },
                        "userAgent": self.config.user_agent,
                        "host": self.config.host,
                    },
                )
                plain = dec.get("plain")
                if isinstance(plain, str):
                    try:
                        js = json.loads(plain)
                    except json.JSONDecodeError:
                        js = None
                else:
                    js = plain
            except Exception as e:
                decrypt_error = str(e)
        else:
            decrypt_error = f"not_ciphertext status={status} body={text[:100]!r}"

        return {
            "status": status,
            "raw": text,
            "plain": plain,
            "json": js,
            "decrypt_error": decrypt_error,
            "request": {
                "url": full,
                "method": method_u,
                "X-Timestamp": headers["X-Timestamp"],
                "X-Signature": headers["X-Signature"][:40] + "…",
            },
        }

    def login(self) -> str:
        log("login", "POST /api/user/login", host=self.config.host)
        r = self.api(
            "post",
            "/user/login",
            data={"email": self.config.username, "password": self.config.password},
        )
        if r["decrypt_error"]:
            log("login", "failed", level="error", **{k: r[k] for k in ("status", "decrypt_error")})
            raise RuntimeError(f"login decrypt failed: {r['decrypt_error']}")
        j = r["json"] or {}
        token = (j.get("result") or {}).get("token") or j.get("token")
        if not token:
            raise RuntimeError(f"login no token: {j}")
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(
            json.dumps({"token": token, "host": self.config.host}, ensure_ascii=False),
            encoding="utf-8",
        )
        log("login", "ok", status=r["status"], token_head=token[:36] + "…")
        return token

    def task_all(self, token: str) -> dict:
        log("task", "GET /api/task/all")
        r = self.api("get", "/task/all", token=token)
        if r["decrypt_error"]:
            log("task", "failed", level="error", status=r["status"], error=r["decrypt_error"])
            raise RuntimeError(f"task/all failed: {r['decrypt_error']}")
        result = (r["json"] or {}).get("result") or {}
        log(
            "task",
            "ok",
            checkIn=result.get("checkIn"),
            status=r["status"],
        )
        return r["json"] or {}

    def checkin(self, token: str) -> dict:
        payload = {"type": 2, "webapp": bool(self.config.webapp)}
        log("checkin", "POST /api/task", payload=payload)
        r = self.api("post", "/task", data=payload, token=token)
        if r["decrypt_error"]:
            # 412 body is still ciphertext usually — if decrypt works we're fine
            log("checkin", "decrypt issue", level="warning", status=r["status"], error=r["decrypt_error"])
        j = r["json"] or {}
        msg = j.get("message") if isinstance(j, dict) else None
        log(
            "checkin",
            "response",
            status=r["status"],
            success=j.get("success") if isinstance(j, dict) else None,
            message=msg,
            result=j.get("result") if isinstance(j, dict) else None,
        )
        return {"status": r["status"], "json": j, "plain": r["plain"]}


def selftest(config: Config) -> int:
    log("selftest", "encrypt", ua=config.user_agent[:50], host=config.host)
    enc = node_crypto(
        "encrypt",
        {
            "method": "post",
            "url": "/task",
            "baseURL": "/api",
            "data": {"type": 2, "webapp": True},
            "userAgent": config.user_agent,
            "standalone": True,
            "host": config.host,
        },
    )
    log("selftest", "encrypt ok", ts=enc["timestamp"], sig_head=enc["signature"][:32])
    req = urllib.request.Request(
        config.base_url + "/",
        headers={"User-Agent": config.user_agent, "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read(400).decode("utf-8", "replace")
            cf = (
                "Just a moment" in html
                or "cf-browser-verification" in html
                or "安全验证" in html
            )
            log(
                "selftest",
                "home",
                status=resp.status,
                cf_challenge=cf,
                html_head=html[:60],
            )
    except Exception as e:
        log("selftest", "home failed", level="warning", error=str(e))
        return 1
    log("selftest", "PASS")
    return 0


def main() -> int:
    global ACTIVE_LOG_LEVEL
    args = parse_args()
    config = load_config(args)
    ACTIVE_LOG_LEVEL = config.log_level

    log(
        "config",
        "loaded",
        base_url=config.base_url,
        host=config.host,
        dry_run=config.dry_run,
        webapp=config.webapp,
        log_level=config.log_level,
    )

    if args.selftest:
        return selftest(config)

    # node present?
    try:
        subprocess.run(["node", "-v"], check=True, capture_output=True)
    except Exception as e:
        log("config", "node is required for WASM crypto", level="error", error=str(e))
        return 2

    client = ProtocolClient(config)
    try:
        token = client.login()

        already = False
        try:
            status = client.task_all(token)
            already = bool((status.get("result") or {}).get("checkIn"))
        except Exception as e:
            # 522 等源站抖动时跳过状态查询，直接尝试签到
            log("task", "skip task/all", level="warning", error=str(e)[:200])

        if already:
            log("result", "already_signed", result="already_signed")
            return 0

        if config.dry_run:
            log(
                "result",
                "dry_run_ready",
                result="dry_run_ready",
                note="use --no-dry-run to POST /api/task",
            )
            return 0

        cr = client.checkin(token)
        j = cr.get("json") or {}
        if j.get("success") is True:
            log(
                "result",
                "signed_now",
                result="signed_now",
                points=(j.get("result") or {}).get("points"),
            )
            return 0
        msg = str(j.get("message") or "")
        if "已完成" in msg or "已经" in msg or "已签" in msg:
            log("result", "already_signed", result="already_signed", message=msg)
            return 0
        log("result", "failed", level="error", status=cr.get("status"), json=j)
        return 1
    except Exception as e:
        log("failure", str(e), level="error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
