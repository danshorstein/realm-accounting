from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urljoin, urlparse

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

logger = logging.getLogger(__name__)

# -----------------------------
# Config
# -----------------------------


@dataclass
class Config:
    # The tenant ID for your OnRealm instance (e.g. from auth.ministrylogin.com/service/authenticate/TenantId)
    site: str
    login_url: str
    export_url: str
    base_realm: str = "https://onrealm.org"
    timeout: int = 60

    def url_landing(self) -> str:
        return f"{self.base_realm}/{self.site}/LedgerInquiry"


DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# -----------------------------
# Login helpers
# -----------------------------


def looks_like_cookie_gate(html: str) -> bool:
    t = html.lower()
    return (
        "<title>cookies disabled</title>" in t
        or "cookies are disabled on your browser" in t
        or "cookietest=1" in t
        or "cookiesenabled()" in t
        or "processing request" in t
    )


def _get_attr(tag: str, attr: str) -> str:
    m = re.search(
        rf"\b{attr}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", tag, re.I
    )
    return (m.group(1) or m.group(2) or m.group(3) or "") if m else ""


def extract_password_form_block(html: str) -> tuple[str | None, str]:
    forms = re.findall(r"(<form\b.*?</form>)", html, flags=re.I | re.S)
    for form_html in forms:
        if re.search(r'type\s*=\s*["\']?password["\']?', form_html, flags=re.I):
            am = re.search(
                r"\baction\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))",
                form_html,
                flags=re.I,
            )
            action = (am.group(1) or am.group(2) or am.group(3)) if am else None
            return action, form_html
    return None, ""


def parse_form_inputs(form_html: str) -> dict:
    inputs = {}
    for inp in re.findall(r"<input[^>]*>", form_html, flags=re.I):
        name = _get_attr(inp, "name")
        if not name:
            continue
        value = _get_attr(inp, "value")
        inputs[name] = value
    return inputs


def maybe_submit_oauth_authorize(
    session: requests.Session, html: str, base_url: str
) -> requests.Response | None:
    if "/oauth/v2/oauth-authorize" not in html:
        return None

    def find_hidden(name: str) -> str:
        m = re.search(
            rf'<input[^>]*name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']+)["\']',
            html,
            flags=re.I,
        )
        return m.group(1) if m else ""

    token = find_hidden("token")
    state = find_hidden("state")
    if not token or not state:
        raise RuntimeError(
            "Found oauth-authorize page but could not parse token/state."
        )

    authorize_url = urljoin(base_url, "/oauth/v2/oauth-authorize")
    r_auth = session.post(
        authorize_url,
        data={"token": token, "state": state},
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "origin": f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}",
            "referer": base_url,
        },
        allow_redirects=True,
        timeout=60,
    )
    r_auth.raise_for_status()
    return r_auth


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def login(cfg: Config, username: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)

    logger.info("Navigating to ministrylogin URL...")
    r = s.get(cfg.login_url, allow_redirects=True, timeout=cfg.timeout)
    r.raise_for_status()

    if looks_like_cookie_gate(r.text):
        logger.info("Cookie gate detected, setting cookie and retrying...")
        host = urlparse(r.url).hostname or "auth.ministrylogin.com"
        s.cookies.set("cookietest", "1", domain=host, path="/")
        s.get(
            "https://onrealm.org", allow_redirects=True, timeout=cfg.timeout
        ).raise_for_status()
        r = s.get(cfg.login_url, allow_redirects=True, timeout=cfg.timeout)
        r.raise_for_status()

    action, form_html = extract_password_form_block(r.text)
    if not action:
        raise RuntimeError("Could not find password form on ministrylogin page.")

    post_url = urljoin(r.url, action)
    origin = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"

    payload = parse_form_inputs(form_html)
    payload["userName"] = username
    payload["password"] = password

    logger.info("Submitting credentials...")
    r_post = s.post(
        post_url,
        data=payload,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "origin": origin,
            "referer": r.url,
        },
        allow_redirects=True,
        timeout=cfg.timeout,
    )
    r_post.raise_for_status()

    r_oauth = maybe_submit_oauth_authorize(s, r_post.text, base_url=r_post.url)
    if r_oauth is not None:
        r_post = r_oauth

    # Warm LedgerInquiry page (keeps session "fresh")
    s.get(cfg.url_landing(), allow_redirects=True, timeout=cfg.timeout).raise_for_status()

    ck = requests.utils.dict_from_cookiejar(s.cookies)
    if "StratusWeb" not in ck:
        raise RuntimeError("Login succeeded but StratusWeb cookie not present.")

    logger.info("Login successful.")
    return s


# -----------------------------
# Export download
# -----------------------------


def build_export_filter(
    begin_mmddyyyy: str, end_mmddyyyy: str, include_open: bool = True
) -> dict:
    return {
        "FundId": None,
        "CoreAccountId": None,
        "DepartmentId": None,
        "VendorSearch": None,
        "ReferenceNumberMin": None,
        "ReferenceNumberMax": None,
        "AmountMin": None,
        "AmountMax": None,
        "TransactionTypeIdList": None,
        "DescriptionSearch": None,
        "ProjectId": None,
        "ReconcileStatus": None,
        "LedgerType": None,
        "IsImported": None,
        "BeginDate": begin_mmddyyyy,
        "EndDate": end_mmddyyyy,
        "IncludeOpenTransactions": bool(include_open),
        "IncludeUserClosingEntries": False,
        "SortBy": "TransactionDate",
        "SortAscending": False,
        "IsInquiry": True,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def download_export_csv(
    session: requests.Session, cfg: Config, filt: dict, out_path: str
) -> None:
    filt_json = json.dumps(filt, separators=(",", ":"))
    url = f"{cfg.export_url}?filter={quote(filt_json, safe='')}"

    headers = {
        "referer": cfg.url_landing(),
        "upgrade-insecure-requests": "1",
        "accept": "text/csv,application/octet-stream,*/*;q=0.8",
    }

    logger.info("Downloading export CSV...")
    r = session.get(
        url, headers=headers, stream=True, timeout=cfg.timeout, allow_redirects=True
    )
    r.raise_for_status()

    ct = (r.headers.get("content-type") or "").lower()
    if "text/html" in ct or r.text.lstrip().lower().startswith("<!doctype html"):
        with open("export_unexpected_html.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        raise RuntimeError(
            "Export returned HTML instead of CSV. Saved export_unexpected_html.html"
        )

    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)

    logger.info("CSV saved to %s", out_path)


def get_config() -> Config:
    """Load client configuration from environment variables."""
    site_id = os.getenv("REALM_SITE_ID")
    if not site_id:
        raise ValueError(
            "Missing REALM_SITE_ID in environment variables. "
            "Please check your .env file."
        )

    return Config(
        site=site_id,
        login_url=os.getenv(
            "REALM_LOGIN_URL", f"https://onrealm.org/{site_id}/SignIn"
        ),
        export_url=os.getenv(
            "REALM_EXPORT_URL",
            f"https://onrealm.org/{site_id}/LedgerInquiry/ExportGridReport",
        ),
    )


def get_credentials() -> tuple[str, str]:
    username = os.getenv("REALM_USERNAME", "").strip()
    password = os.getenv("REALM_PASSWORD", "").strip()
    if not username or not password:
        raise SystemExit("Set REALM_USERNAME and REALM_PASSWORD in .env file.")
    return username, password


# -----------------------------
# Standalone usage
# -----------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    cfg = get_config()
    username, password = get_credentials()

    begin = os.getenv("BEGIN_DATE", "07/01/2025")
    end = os.getenv("END_DATE", datetime.today().strftime("%m/%d/%Y"))
    include_open = os.getenv("INCLUDE_OPEN", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
    )

    print("Logging in...")
    session = login(cfg, username, password)
    print("Logged in.")

    filt = build_export_filter(begin, end, include_open=include_open)
    out_file = os.path.join(
        "data",
        f"LedgerInquiry_Export_{begin.replace('/', '-')}_to_{end.replace('/', '-')}.csv",
    )
    print(f"Downloading export CSV for {begin} to {end} ...")
    download_export_csv(session, cfg, filt, out_file)
    print(f"Saved: {out_file}")
