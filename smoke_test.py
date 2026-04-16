from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cloakbrowser import (
    binary_info,
    ensure_binary,
    launch,
    launch_context,
    launch_persistent_context,
)


DEFAULT_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7.5 "
    "Mobile/15E148 Safari/604.1"
)
DEFAULT_VIEWPORT = {"width": 390, "height": 844}
DEFAULT_TARGET_URL = "local://smoke-test"
EXPECTED_TITLE = "CloakBrowser Smoke Test"
EXPECTED_STATUS_TEXT = "ready"
NAVIGATION_TIMEOUT_MS = 15_000
TEST_PAGE_HTML = (
    "<html><head><title>CloakBrowser Smoke Test</title></head>"
    "<body><h1 id='status'>ready</h1></body></html>"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CloakBrowser smoke tests")
    parser.add_argument(
        "--mode",
        choices=("basic", "mobile", "persistent"),
        default="basic",
        help="Smoke test mode to run.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_TARGET_URL,
        help="Neutral URL to open during the smoke test.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("CLOAK_HEADLESS", True),
        help="Launch browser in headless mode.",
    )
    parser.add_argument(
        "--fingerprint-seed",
        default=os.getenv("CLOAK_FINGERPRINT_SEED", "12345"),
        help="Fixed fingerprint seed for repeatable sessions.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_MOBILE_UA,
        help="Custom user agent for mobile mode.",
    )
    parser.add_argument(
        "--profile-dir",
        default="data/profile",
        help="Persistent profile directory for persistent mode.",
    )
    return parser.parse_args()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def print_binary_details() -> None:
    ensure_binary()
    info = binary_info()
    print("[cloakbrowser] binary_info=")
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


def assert_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{name} mismatch: expected {expected!r}, got {actual!r}")


class SmokeTestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = TEST_PAGE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _get_free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def local_test_server() -> str:
    port = _get_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), SmokeTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def resolve_url(url: str) -> str:
    if url == DEFAULT_TARGET_URL:
        raise ValueError("DEFAULT_TARGET_URL must be resolved through local_test_server().")
    return url


def configure_page(page) -> None:
    page.set_default_timeout(NAVIGATION_TIMEOUT_MS)
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)


def open_and_verify_page(page, url: str) -> None:
    configure_page(page)
    page.goto(resolve_url(url), wait_until="domcontentloaded")
    title = page.title()
    status_text = page.locator("#status").inner_text()
    assert_equal("page title", title, EXPECTED_TITLE)
    assert_equal("status text", status_text, EXPECTED_STATUS_TEXT)


def run_basic(url: str, headless: bool, fingerprint_seed: str) -> None:
    browser = launch(headless=headless, args=[f"--fingerprint={fingerprint_seed}"])
    try:
        page = browser.new_page()
        open_and_verify_page(page, url)
        print(f"[basic] title={page.title()!r}")
        print(f"[basic] final_url={page.url}")
        print("[basic] result=PASS")
    finally:
        browser.close()


def run_mobile(url: str, headless: bool, fingerprint_seed: str, user_agent: str) -> None:
    context = launch_context(
        user_agent=user_agent,
        viewport=DEFAULT_VIEWPORT,
        locale="en-US",
        args=[f"--fingerprint={fingerprint_seed}"],
        headless=headless,
        humanize=True,
    )
    try:
        page = context.new_page()
        open_and_verify_page(page, url)
        current_ua = page.evaluate("() => navigator.userAgent")
        if current_ua != user_agent:
            raise AssertionError(
                "navigator.userAgent mismatch: "
                f"expected {user_agent!r}, got {current_ua!r}"
            )
        print(f"[mobile] title={page.title()!r}")
        print(f"[mobile] final_url={page.url}")
        print(f"[mobile] navigator.userAgent={current_ua}")
        print("[mobile] result=PASS")
    finally:
        context.close()


def run_persistent(
    url: str,
    headless: bool,
    fingerprint_seed: str,
    user_agent: str,
    profile_dir: str,
) -> None:
    profile_path = Path(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    first_context = launch_persistent_context(
        str(profile_path),
        user_agent=user_agent,
        viewport=DEFAULT_VIEWPORT,
        locale="en-US",
        args=[f"--fingerprint={fingerprint_seed}"],
        headless=headless,
        humanize=True,
    )
    try:
        first_page = first_context.new_page()
        open_and_verify_page(first_page, url)
        first_page.evaluate("() => localStorage.setItem('cloakbrowser-smoke', 'persisted')")
    finally:
        first_context.close()

    second_context = launch_persistent_context(
        str(profile_path),
        user_agent=user_agent,
        viewport=DEFAULT_VIEWPORT,
        locale="en-US",
        args=[f"--fingerprint={fingerprint_seed}"],
        headless=headless,
        humanize=True,
    )
    try:
        second_page = second_context.new_page()
        open_and_verify_page(second_page, url)
        persisted_value = second_page.evaluate(
            "() => localStorage.getItem('cloakbrowser-smoke')"
        )
        assert_equal("persistent localStorage", persisted_value, "persisted")
        print(f"[persistent] title={second_page.title()!r}")
        print(f"[persistent] final_url={second_page.url}")
        print(f"[persistent] profile_dir={profile_path.resolve()}")
        print("[persistent] result=PASS")
    finally:
        second_context.close()


def main() -> None:
    args = parse_args()
    print_binary_details()
    if args.url == DEFAULT_TARGET_URL:
        with local_test_server() as local_url:
            if args.mode == "basic":
                run_basic(local_url, args.headless, args.fingerprint_seed)
            elif args.mode == "mobile":
                run_mobile(local_url, args.headless, args.fingerprint_seed, args.user_agent)
            else:
                run_persistent(
                    local_url,
                    args.headless,
                    args.fingerprint_seed,
                    args.user_agent,
                    args.profile_dir,
                )
        return

    if args.mode == "basic":
        run_basic(args.url, args.headless, args.fingerprint_seed)
    elif args.mode == "mobile":
        run_mobile(args.url, args.headless, args.fingerprint_seed, args.user_agent)
    else:
        run_persistent(
            args.url,
            args.headless,
            args.fingerprint_seed,
            args.user_agent,
            args.profile_dir,
        )


if __name__ == "__main__":
    main()
