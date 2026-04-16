from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from cloakbrowser import launch_persistent_context
from playwright.sync_api import Error, Locator, Page


LOGIN_URL = "https://www.iios.fun/"
POINTS_URL = "https://www.iios.fun/#/points"
DEFAULT_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7.5 "
    "Mobile/15E148 Safari/604.1"
)
DEFAULT_VIEWPORT = {"width": 390, "height": 844}
DEFAULT_TIMEOUT_MS = 20_000
ALREADY_SIGNED_TEXTS = (
    "今日已签到",
    "已签到",
    "签到成功",
)
SIGNIN_TEXT = "立即签到"
SIGNED_OUT_HINT_TEXTS = (
    "登录",
    "立即登录",
    "密码",
    "邮箱",
    "账号",
)
LOGGED_IN_HINT_TEXTS = (
    "退出登录",
    "我的积分",
    "积分明细",
    "签到记录",
)
LOGIN_BUTTON_TEXTS = (
    "登录",
    "立即登录",
    "登 录",
    "密码登录",
    "账号登录",
    "sign in",
    "login",
)
USER_FIELD_RE = re.compile(r"邮箱|邮件|账号|用户名|手机号|手机号码|phone|mobile|email|account|login|user", re.I)
PASSWORD_FIELD_RE = re.compile(r"密码|password|passcode", re.I)
LOGIN_ROOT_SELECTOR = "[class*='login' i], [class*='signin' i], [id*='login' i], [id*='signin' i], [data-testid*='login' i], [data-test*='login' i]"
DEFAULT_LOG_LEVEL = "info"
LOG_LEVEL_PRIORITY = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}
ACTIVE_LOG_LEVEL = DEFAULT_LOG_LEVEL


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    headless: bool
    fingerprint_seed: str
    user_agent: str
    profile_dir: Path
    timeout_ms: int
    dry_run: bool
    artifact_dir: Path
    log_level: str
    success_screenshot: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="iios.fun CloakBrowser auto sign-in")
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("CLOAK_HEADLESS", True),
        help="Launch the browser in headless mode.",
    )
    parser.add_argument(
        "--profile-dir",
        default=os.getenv("IIOS_PROFILE_DIR", "data/profile/iios.fun"),
        help="Persistent profile directory.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Validate login and sign-in target without clicking the sign-in button.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=_env_int("IIOS_TIMEOUT_MS", DEFAULT_TIMEOUT_MS),
        help="Default Playwright timeout in milliseconds.",
    )
    parser.add_argument(
        "--fingerprint-seed",
        default=os.getenv("CLOAK_FINGERPRINT_SEED", "12345"),
        help="Stable CloakBrowser fingerprint seed.",
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("IIOS_USER_AGENT", DEFAULT_MOBILE_UA),
        help="User agent override for the persistent context.",
    )
    parser.add_argument(
        "--artifact-dir",
        default=os.getenv("IIOS_ARTIFACT_DIR", "data/artifacts/iios.fun"),
        help="Directory for screenshots and local run artifacts.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("IIOS_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        help="Structured log level label for stdout output.",
    )
    parser.add_argument(
        "--success-screenshot",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("IIOS_SUCCESS_SCREENSHOT", False),
        help="Save screenshots on successful checkpoints.",
    )
    return parser.parse_args()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"Environment variable {name} must be positive.")
    return value


def load_config(args: argparse.Namespace) -> Config:
    username = os.getenv("IIOS_USERNAME", "").strip()
    password = os.getenv("IIOS_PASSWORD", "").strip()
    if not username:
        raise ValueError("Missing IIOS_USERNAME environment variable.")
    if not password:
        raise ValueError("Missing IIOS_PASSWORD environment variable.")
    if not args.fingerprint_seed.strip():
        raise ValueError("Fingerprint seed must not be empty.")
    if args.timeout_ms <= 0:
        raise ValueError("--timeout-ms must be a positive integer.")

    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        username=username,
        password=password,
        headless=args.headless,
        fingerprint_seed=args.fingerprint_seed.strip(),
        user_agent=args.user_agent,
        profile_dir=profile_dir,
        timeout_ms=args.timeout_ms,
        dry_run=args.dry_run,
        artifact_dir=artifact_dir,
        log_level=args.log_level.strip().lower() or DEFAULT_LOG_LEVEL,
        success_screenshot=args.success_screenshot,
    )


def log(step: str, message: str, level: str = "info", **context: object) -> None:
    normalized_level = level.strip().lower()
    active_priority = LOG_LEVEL_PRIORITY.get(ACTIVE_LOG_LEVEL, LOG_LEVEL_PRIORITY[DEFAULT_LOG_LEVEL])
    message_priority = LOG_LEVEL_PRIORITY.get(normalized_level, LOG_LEVEL_PRIORITY[DEFAULT_LOG_LEVEL])
    if message_priority < active_priority:
        return
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "level": normalized_level,
        "step": step,
        "message": message,
    }
    if context:
        record["context"] = context
    print(json.dumps(record, ensure_ascii=False), flush=True)


def sanitize_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_")
    return cleaned or "artifact"


def capture_screenshot(page: Page, artifact_dir: Path, label: str) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    file_path = artifact_dir / f"{timestamp}_{sanitize_label(label)}.png"
    page.screenshot(path=str(file_path), full_page=True)
    log("artifact", "saved screenshot", path=str(file_path))
    return file_path


def maybe_capture_success(page: Page, config: Config, label: str) -> None:
    if config.success_screenshot:
        capture_screenshot(page, config.artifact_dir, label)


def raise_with_screenshot(page: Page, config: Config, label: str, message: str) -> None:
    capture_screenshot(page, config.artifact_dir, label)
    raise RuntimeError(message)


def configure_page(page: Page, timeout_ms: int) -> None:
    page.set_default_timeout(timeout_ms)
    page.set_default_navigation_timeout(timeout_ms)


def locator_with_candidates(page: Page, candidates: list[str]) -> Locator | None:
    for candidate in candidates:
        locator = page.locator(candidate).first
        try:
            if locator.count() > 0 and locator.is_visible(timeout=1_000):
                return locator
        except Error:
            continue
    return None


def first_visible(candidates: list[Locator], timeout_ms: int = 1_500) -> Locator | None:
    for locator in candidates:
        try:
            candidate = locator.first
            if candidate.count() > 0 and candidate.is_visible(timeout=timeout_ms):
                return candidate
        except Error:
            continue
    return None


def clickable_text_locator(page: Page, text: str) -> Locator | None:
    candidates = [
        f"button:has-text('{text}')",
        f"a:has-text('{text}')",
        f"[role='button']:has-text('{text}')",
        f"text={text}",
    ]
    return locator_with_candidates(page, candidates)


def unique_visible_locator(page: Page, candidates: list[str]) -> Locator | None:
    for candidate in candidates:
        locator = page.locator(candidate)
        try:
            if locator.count() == 1 and locator.first.is_visible(timeout=1_000):
                return locator.first
        except Error:
            continue
    return None


def open_home(page: Page) -> None:
    log("login", "opening home page", url=LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded")


def open_points_page(page: Page) -> None:
    log("points", "opening points page", url=POINTS_URL)
    page.goto(POINTS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2_000)


def looks_logged_in(page: Page) -> bool:
    text = current_page_text(page)
    if not text:
        return False
    if locate_signin_action(page) is not None:
        return True
    if any(marker in text for marker in LOGGED_IN_HINT_TEXTS):
        return True
    if page.url.startswith(POINTS_URL) and any(marker in text for marker in ALREADY_SIGNED_TEXTS):
        return True
    if any(marker in text for marker in SIGNED_OUT_HINT_TEXTS):
        return False
    return False


def try_open_password_login_mode(page: Page) -> None:
    for text in ("密码登录", "账号登录", "登录"):
        locator = clickable_text_locator(page, text)
        if locator is None:
            continue
        try:
            locator.click(timeout=1_000)
            page.wait_for_timeout(1_000)
            return
        except Error:
            continue


def login_roots(page: Page) -> list[Locator]:
    return [
        page.get_by_role("dialog").filter(has=page.locator("input[type='password']")),
        page.locator("form").filter(has=page.locator("input[type='password']")),
        page.locator(LOGIN_ROOT_SELECTOR).filter(has=page.locator("input[type='password']")),
        page.locator("body"),
    ]


def username_candidates(root: Locator) -> list[Locator]:
    return [
        root.get_by_label(USER_FIELD_RE),
        root.get_by_placeholder(USER_FIELD_RE),
        root.get_by_role("textbox", name=USER_FIELD_RE),
        root.locator("input[autocomplete='username']"),
        root.locator("input[autocomplete='email']"),
        root.locator("input[inputmode='email']"),
        root.locator("input[inputmode='tel']"),
        root.locator("input[type='email']"),
        root.locator("input[type='tel']"),
        root.locator("input[name*='user' i], input[name*='email' i], input[name*='login' i], input[name*='account' i], input[name*='mobile' i], input[name*='phone' i]"),
        root.locator("input[id*='user' i], input[id*='email' i], input[id*='login' i], input[id*='account' i], input[id*='mobile' i], input[id*='phone' i]"),
        root.locator("input[aria-label*='邮箱'], input[aria-label*='账号'], input[aria-label*='用户名'], input[aria-label*='手机号'], input[aria-label*='手机号码']"),
        root.locator("input[placeholder*='邮箱'], input[placeholder*='账号'], input[placeholder*='用户名'], input[placeholder*='手机号'], input[placeholder*='手机号码'], input[placeholder*='手机']"),
        root.locator("input:not([type='hidden']):not([type='password']):not([type='search'])"),
    ]


def password_candidates(root: Locator) -> list[Locator]:
    return [
        root.get_by_label(PASSWORD_FIELD_RE),
        root.get_by_placeholder(PASSWORD_FIELD_RE),
        root.locator("input[type='password']"),
        root.locator("input[autocomplete='current-password']"),
        root.locator("input[name*='pass' i], input[id*='pass' i], input[placeholder*='pass' i], input[placeholder*='密码']"),
    ]


def find_login_fields(page: Page) -> tuple[Locator, Locator, Locator]:
    try_open_password_login_mode(page)
    page.wait_for_timeout(1_000)

    for root in login_roots(page):
        password_field = first_visible(password_candidates(root))
        if password_field is None:
            continue
        username_field = first_visible(username_candidates(root))
        if username_field is not None:
            return root, username_field, password_field

    raise RuntimeError("Could not reliably locate both username and password fields.")


def locate_username_input(page: Page) -> Locator:
    _, username_field, _ = find_login_fields(page)
    return username_field


def locate_password_input(page: Page) -> Locator:
    _, _, password_field = find_login_fields(page)
    return password_field


def locate_login_button(root: Locator) -> Locator:
    for text in LOGIN_BUTTON_TEXTS:
        candidates = [
            root.locator(f"button:has-text('{text}')"),
            root.locator(f"a:has-text('{text}')"),
            root.locator(f"[role='button']:has-text('{text}')"),
            root.get_by_text(text, exact=True),
        ]
        locator = first_visible(candidates)
        if locator is not None:
            return locator
    locator = first_visible([root.locator("button[type='submit']"), root.locator("input[type='submit']")])
    if locator is None:
        raise RuntimeError("Could not find the login button.")
    return locator


def submit_login(page: Page, config: Config) -> None:
    log("login", "filling credential fields")
    try:
        login_root, username_field, password_field = find_login_fields(page)
    except RuntimeError as exc:
        raise_with_screenshot(page, config, "login_fields_not_found", str(exc))
    username_field.fill(config.username)
    password_field.fill(config.password)
    log("login", "submitting login form")
    locate_login_button(login_root).click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2_000)


def ensure_logged_in(page: Page, config: Config) -> None:
    open_points_page(page)
    if looks_logged_in(page):
        log("login", "existing session appears valid via points page", url=page.url)
        maybe_capture_success(page, config, "points_logged_in")
        return
    open_home(page)
    submit_login(page, config)
    open_points_page(page)
    if not looks_logged_in(page):
        raise_with_screenshot(page, config, "login_not_confirmed", "Login did not appear to succeed.")
    log("login", "login succeeded", url=page.url)
    maybe_capture_success(page, config, "points_logged_in")


def current_page_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3_000)
    except Error:
        return ""


def already_signed_in(page: Page) -> bool:
    text = current_page_text(page)
    return any(marker in text for marker in ALREADY_SIGNED_TEXTS)


def locate_signin_action(page: Page) -> Locator | None:
    candidates = [
        f"button:has-text('{SIGNIN_TEXT}')",
        f"a:has-text('{SIGNIN_TEXT}')",
        f"[role='button']:has-text('{SIGNIN_TEXT}')",
    ]
    locator = unique_visible_locator(page, candidates)
    if locator is not None:
        return locator

    text_locator = page.get_by_text(SIGNIN_TEXT, exact=True)
    try:
        if text_locator.count() == 1 and text_locator.first.is_visible(timeout=1_000):
            return text_locator.first
    except Error:
        return None
    return None


def verify_mobile_ua(page: Page, expected_user_agent: str) -> None:
    current_ua = page.evaluate("() => navigator.userAgent")
    if current_ua != expected_user_agent:
        raise RuntimeError(
            "navigator.userAgent mismatch: "
            f"expected {expected_user_agent!r}, got {current_ua!r}"
        )
    log("context", "mobile user agent verified", url=page.url)


def handle_signin(page: Page, config: Config) -> str:
    if already_signed_in(page):
        log("points", "already signed in for today", url=page.url)
        maybe_capture_success(page, config, "result_already_signed")
        return "already_signed"

    action = locate_signin_action(page)
    if action is None:
        raise_with_screenshot(page, config, "signin_action_not_found", "Could not safely locate the '立即签到' action.")

    log("points", "found sign-in action", url=page.url)
    if config.dry_run:
        log("dry-run", "sign-in click skipped", url=page.url)
        maybe_capture_success(page, config, "result_dry_run_ready")
        return "dry_run_ready"

    log("points", "clicking sign-in action")
    action.click()
    page.wait_for_timeout(2_000)

    if already_signed_in(page):
        log("points", "sign-in confirmed by updated page state", url=page.url)
        maybe_capture_success(page, config, "result_signed_now")
        return "signed_now"

    raise_with_screenshot(page, config, "signin_not_confirmed", "Sign-in click completed but the page state did not confirm success.")


def main() -> None:
    global ACTIVE_LOG_LEVEL
    args = parse_args()
    config = load_config(args)
    ACTIVE_LOG_LEVEL = config.log_level
    log("config", "loaded runtime configuration", profile_dir=str(config.profile_dir.resolve()), artifact_dir=str(config.artifact_dir.resolve()), dry_run=config.dry_run, headless=config.headless, log_level=config.log_level)

    context = launch_persistent_context(
        str(config.profile_dir),
        user_agent=config.user_agent,
        viewport=DEFAULT_VIEWPORT,
        locale="en-US",
        args=[f"--fingerprint={config.fingerprint_seed}"],
        headless=config.headless,
        humanize=True,
    )
    page: Page | None = None
    try:
        page = context.new_page()
        configure_page(page, config.timeout_ms)
        verify_mobile_ua(page, config.user_agent)
        ensure_logged_in(page, config)
        open_points_page(page)
        result = handle_signin(page, config)
        log("result", result, result=result, url=page.url)
    except Exception as exc:
        if page is not None:
            try:
                capture_screenshot(page, config.artifact_dir, "top_level_failure")
            except Exception:
                pass
            log("failure", str(exc), level="error", url=page.url)
        else:
            log("failure", str(exc), level="error")
        raise
    finally:
        context.close()


if __name__ == "__main__":
    main()
