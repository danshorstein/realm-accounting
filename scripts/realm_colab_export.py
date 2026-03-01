# realm_colab_export.py
#
# Standalone Colab-compatible script for downloading ledger data from OnRealm
# and parsing beginning balances.
#
# Credentials are read from google.colab.userdata — this script is intended
# to be run inside a Google Colab notebook. Running outside Colab will fail
# at the userdata.get() calls, which is expected.
#
# The login and download logic mirrors realm_client.py in the main project.
# beginning_balances.py in the main project contains the same trial balance data.

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote
from decimal import Decimal, getcontext

from google.colab import userdata
import pandas as pd
import requests

# -----------------------------
# Config
# -----------------------------

getcontext().prec = 28  # Increased precision for Decimal operations


@dataclass
class Config:
    ministrylogin_url: str
    site: str = "JacksonvilleJewishCenter"
    base_realm: str = "https://onrealm.org"
    timeout: int = 60

    def url_landing(self) -> str:
        return f"{self.base_realm}/{self.site}/LedgerInquiry"

    def url_export(self) -> str:
        return f"{self.base_realm}/{self.site}/LedgerInquiry/ExportGridReport"


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
        rf'\b{attr}\s*=\s*(?:"([^"]*)"' + r"|'([^']*)'|([^\s>]+))",
        tag,
        re.I,
    )
    return (m.group(1) or m.group(2) or m.group(3) or "") if m else ""


def extract_password_form_block(html: str) -> tuple[str | None, str]:
    forms = re.findall(r"(<form\b.*?</form>)", html, flags=re.I | re.S)
    for form_html in forms:
        if re.search(r'type\s*=\s*["\']?password["\']?', form_html, flags=re.I):
            am = re.search(
                r'\baction\s*=\s*(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))',
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
            r'<input[^>]*name=["\']' + re.escape(name) + r'["\'][^>]*value=["\']([^"\']*)["\']',
            html,
            flags=re.I,
        )
        return m.group(1) if m else ""

    token = find_hidden("token")
    state = find_hidden("state")
    if not token or not state:
        raise RuntimeError("Found oauth-authorize page but could not parse token/state.")

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


def login(cfg: Config, username: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)

    r = s.get(cfg.ministrylogin_url, allow_redirects=True, timeout=cfg.timeout)
    r.raise_for_status()

    if looks_like_cookie_gate(r.text):
        host = urlparse(r.url).hostname or "auth.ministrylogin.com"
        s.cookies.set("cookietest", "1", domain=host, path="/")
        s.get("https://onrealm.org", allow_redirects=True, timeout=cfg.timeout).raise_for_status()
        r = s.get(cfg.ministrylogin_url, allow_redirects=True, timeout=cfg.timeout)
        r.raise_for_status()

    action, form_html = extract_password_form_block(r.text)
    if not action:
        raise RuntimeError("Could not find password form on ministrylogin page.")

    post_url = urljoin(r.url, action)
    origin = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"

    payload = parse_form_inputs(form_html)
    payload["userName"] = username
    payload["password"] = password

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

    return s


# -----------------------------
# Export download
# -----------------------------

def build_export_filter(
    begin_mmddyyyy: str, end_mmddyyyy: str, include_open: bool = True
) -> dict:
    """Matches the ExportGridReport curl payload structure."""
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


def download_export_csv(
    session: requests.Session, cfg: Config, filt: dict, out_path: str
) -> None:
    # JSON -> query param. Use quote to match curl's percent-encoding behavior.
    filt_json = json.dumps(filt, separators=(",", ":"))
    url = f"{cfg.url_export()}?filter={quote(filt_json, safe='')}"

    headers = {
        "referer": cfg.url_landing(),
        "upgrade-insecure-requests": "1",
        "accept": "text/csv,application/octet-stream,*/*;q=0.8",
    }

    r = session.get(
        url, headers=headers, stream=True, timeout=cfg.timeout, allow_redirects=True
    )
    r.raise_for_status()

    # Guardrail: make sure we didn't get HTML (like a login page)
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


# -----------------------------
# Main
# -----------------------------

ministrylogin_url = userdata.get("MINISTRYLOGIN_URL").strip()
username = userdata.get("REALM_USERNAME").strip()
password = userdata.get("REALM_PASSWORD").strip()

if not ministrylogin_url:
    raise SystemExit("Set MINISTRYLOGIN_URL env var.")
if not username or not password:
    raise SystemExit("Set REALM_USERNAME and REALM_PASSWORD env vars.")

begin = os.environ.get("BEGIN_DATE", "07/01/2025")
end = os.environ.get("END_DATE", datetime.today().strftime("%m/%d/%Y"))
include_open = os.environ.get("INCLUDE_OPEN", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
)

cfg = Config(ministrylogin_url=ministrylogin_url)

print("Logging in...")
session = login(cfg, username, password)
print("✅ Logged in.")

filt = build_export_filter(begin, end, include_open=include_open)
out_file = f"LedgerInquiry_Export_{begin.replace('/', '-')}to{end.replace('/', '-')}.csv"

print(f"Downloading export CSV for {begin} to {end} ...")
download_export_csv(session, cfg, filt, out_file)
print(f"✅ Saved: {out_file}")

# -----------------------------
# Load and inspect
# -----------------------------

TWO_PLACES = Decimal("0.00")

df = pd.read_csv(out_file)
df["Debit"] = df["Debit"].fillna(0)
df["Credit"] = df["Credit"].fillna(0)
df["Debit"] = df["Debit"].astype(str).str.replace(",", "", regex=False).apply(Decimal)
df["Credit"] = df["Credit"].astype(str).str.replace(",", "", regex=False).apply(Decimal)
df["net"] = df["Debit"] - df["Credit"]
df["net"] = df["net"].apply(lambda x: x.quantize(TWO_PLACES))

print(f"Net is {df.net.sum().quantize(TWO_PLACES)}")
df.head()

# -----------------------------
# Beginning balances (from beg_bal tab-separated string)
# -----------------------------
# Paste your beg_bal string here if running standalone.
# In the main project, use beginning_balances.py instead.

# beg_bal = """..."""  # paste raw tab-separated trial balance here

# cols = [
#     "Fund", "Core", "Department", "Account", "Account Description",
#     "Date", "Reference", "Payee", "Description", "Transaction Status",
#     "Comment", "Project", "Transaction Type", "Debit", "Credit", "net",
# ]
#
# bb = pd.DataFrame(
#     [line.split("\t") for line in beg_bal.split("\n")[1:]],
#     columns=["Account_Name", "net"],
# )
# bb["Account"] = bb["Account_Name"].map(lambda x: x.split(" ")[0] + "-000")
# bb["Fund"] = bb["Account"].map(lambda x: int(x.split("-")[0]))
# bb["Core"] = bb["Account"].map(lambda x: int(x.split("-")[1]))
# bb["Department"] = ""
# bb["Account Description"] = "Beginning Balance"
# bb["Date"] = "7/1/2025"
# bb["Reference"] = ""
# bb["Payee"] = ""
# bb["Description"] = "Beginning Balance"
# bb["Transaction Status"] = ""
# bb["Comment"] = ""
# bb["Project"] = ""
# bb["Transaction Type"] = ""
# bb["Debit"] = 0
# bb["Credit"] = 0
# bb = bb[cols]
# bb["net"] = (
#     bb["net"]
#     .str.replace(",", "", regex=False)
#     .str.replace("(", "-", regex=False)
#     .str.replace(")", "", regex=False)
#     .str.strip()
#     .apply(Decimal)
# )
