import streamlit as st
import json
import hashlib
import secrets
import time
import io
import csv
import html as html_lib

from pathlib import Path
from datetime import datetime

# ==========================================================
# PYTHONGURUKOOL BANK
# Advanced Digital Banking Simulator
# ==========================================================

st.set_page_config(
    page_title="PYTHONGURUKOOL BANK",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="auto"   # auto = collapsed on phones, open on desktop
)

DATA_FILE = Path("bank_data.json")
PREFIX = "11151040000"
MIN_DEPOSIT = 500.0
WELCOME_TEXT = "Aapka PythonGurukool Bank mai swagat hai"

# ==========================================================
# DATABASE
# ==========================================================

def empty_database():
    return {
        "accounts": {},
        "transactions": []
    }


def load_database():
    if not DATA_FILE.exists():
        return empty_database()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return empty_database()

        data.setdefault("accounts", {})
        data.setdefault("transactions", [])

        return data

    except (json.JSONDecodeError, OSError):
        return empty_database()


if "database" not in st.session_state:
    st.session_state.database = load_database()

db = st.session_state.database


def save_database():
    temp = DATA_FILE.with_suffix(".tmp")

    with open(temp, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)

    temp.replace(DATA_FILE)


# ==========================================================
# SECURITY / HELPERS
# ==========================================================

def hash_pin(pin):
    return hashlib.sha256(
        pin.encode("utf-8")
    ).hexdigest()


LOCK_AFTER = 3        # wrong PIN attempts before a lock
LOCK_SECONDS = 60     # lock duration
CREDIT_TYPES = {"Deposit", "Transfer In", "Account Opened"}
DEBIT_TYPES = {"Withdrawal", "Transfer Out"}


def lock_remaining(account):
    return max(0, int(account.get("locked_until", 0) - time.time()))


def verify_pin(account, pin):
    """Check a PIN. 3 wrong attempts lock the account for 60 seconds."""
    if lock_remaining(account) > 0:
        return False

    if secrets.compare_digest(account["pin_hash"], hash_pin(pin)):
        if account.get("failed_attempts", 0):
            account["failed_attempts"] = 0
            account["locked_until"] = 0
            save_database()
        return True

    account["failed_attempts"] = account.get("failed_attempts", 0) + 1

    if account["failed_attempts"] >= LOCK_AFTER:
        account["locked_until"] = time.time() + LOCK_SECONDS
        account["failed_attempts"] = 0

    save_database()
    return False


def pin_error(account):
    remaining = lock_remaining(account)

    if remaining > 0:
        st.error(
            "🔒 Account temporarily locked after too many wrong PINs. "
            f"Try again in {remaining} seconds."
        )
    else:
        left = LOCK_AFTER - account.get("failed_attempts", 0)
        st.error(
            f"Incorrect PIN. {left} attempt(s) left before a temporary lock."
        )


def generate_account_number():
    while True:
        number = PREFIX + str(
            secrets.randbelow(90000) + 10000
        )

        if number not in db["accounts"]:
            return number


def money(value):
    return f"₹{value:,.2f}"


def current_time():
    return datetime.now().strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )


def render_html(html):
    """
    Render HTML safely in Streamlit.

    Markdown treats lines indented by 4+ spaces as code blocks and
    blank lines can break HTML blocks. Stripping indentation and
    blank lines makes the HTML render properly.
    """
    cleaned = " ".join(
        line.strip()
        for line in html.splitlines()
        if line.strip()
    )

    st.markdown(cleaned, unsafe_allow_html=True)


def notify_success(message):
    st.success(message)

    try:
        st.toast(message, icon="✅")
    except Exception:
        pass


def go_to(target_page):
    """Button callback used by Quick Actions to switch pages."""
    st.session_state.page_nav = target_page


def greeting():
    hour = datetime.now().hour

    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def daily_activity():
    import pandas as pd

    buckets = {}

    for t in db["transactions"]:
        if t["type"] not in ("Deposit", "Withdrawal"):
            continue

        day = t["time"][:10]
        row = buckets.setdefault(
            day, {"Deposits": 0.0, "Withdrawals": 0.0}
        )
        key = "Deposits" if t["type"] == "Deposit" else "Withdrawals"
        row[key] += t["amount"]

    if not buckets:
        return pd.DataFrame()

    ordered = sorted(
        buckets,
        key=lambda d: datetime.strptime(d, "%d-%m-%Y")
    )

    return pd.DataFrame(
        [buckets[d] for d in ordered],
        index=ordered
    )


def show_activity_chart(activity):
    if activity.empty:
        st.info(
            "Activity will appear here after the first deposit or withdrawal."
        )
        return

    colors = ["#d4af37", "#f0d98a"]
    chart = st.area_chart if len(activity) > 1 else st.bar_chart

    try:
        chart(activity, color=colors)
    except Exception:
        chart(activity)


def bank_card(account):
    digits = account["account_number"]
    grouped = " ".join(
        digits[i:i + 4] for i in range(0, len(digits), 4)
    )
    holder = html_lib.escape(account["name"]).upper()
    status = html_lib.escape(account["status"]).upper()
    since = html_lib.escape(account["created_at"][:10])

    render_html(f"""
    <div class="bank-card">
        <div class="bank-card-top">
            <span class="bank-card-brand">PYTHONGURUKOOL</span>
            <span class="bank-card-tier">{status}</span>
        </div>
        <div class="bank-card-chip"></div>
        <div class="bank-card-number">{grouped}</div>
        <div class="bank-card-bottom">
            <div><small>ACCOUNT HOLDER</small><b>{holder}</b></div>
            <div><small>MEMBER SINCE</small><b>{since}</b></div>
        </div>
    </div>
    """)


def leaderboard(limit=5):
    ranked = sorted(
        active_accounts().values(),
        key=lambda a: a["balance"],
        reverse=True
    )[:limit]

    if not ranked:
        st.info("Top accounts will appear here.")
        return

    top = max(a["balance"] for a in ranked) or 1
    rows = ""

    for i, a in enumerate(ranked, start=1):
        pct = max(4, int(a["balance"] / top * 100))
        rows += f"""
        <div class="lb-row">
            <div class="lb-head">
                <span><span class="lb-rank">#{i}</span>{html_lib.escape(a["name"])}</span>
                <span class="lb-amount">{money(a["balance"])}</span>
            </div>
            <div class="lb-track"><div class="lb-fill" style="width:{pct}%"></div></div>
        </div>
        """

    render_html(f'<div class="lb-panel">{rows}</div>')


# ==========================================================
# TRANSACTION SYSTEM
# ==========================================================

def record_transaction(
    account_number,
    transaction_type,
    amount,
    note=""
):
    account = db["accounts"][account_number]

    transaction = {
        "reference": secrets.token_hex(5).upper(),
        "account_number": account_number,
        "customer": account["name"],
        "type": transaction_type,
        "amount": round(float(amount), 2),
        "balance": round(float(account["balance"]), 2),
        "note": note,
        "time": current_time()
    }

    db["transactions"].append(transaction)

    return transaction


def active_accounts():
    return {
        number: account
        for number, account in db["accounts"].items()
        if account["status"] == "Active"
    }


def account_history(number):
    return [
        t for t in reversed(db["transactions"])
        if t["account_number"] == number
    ]


# ==========================================================
# PROFESSIONAL UI THEME + ANIMATIONS
# ==========================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* ---------- Base ---------- */

.stApp {
    background:
        radial-gradient(circle at 10% 5%, rgba(212,175,55,.16), transparent 30%),
        radial-gradient(circle at 90% 15%, rgba(240,217,138,.13), transparent 30%),
        linear-gradient(135deg, #050505, #121212, #0b0b0b);

    color: #f6edd9;
    font-family: 'Space Grotesk', sans-serif;
}

[data-testid="stHeader"] {
    background: transparent;
}

.block-container {
    max-width: 1500px;
    padding-top: 1.5rem;
}

#MainMenu, footer {
    visibility: hidden;
}

h1, h2, h3, h4 {
    color: #faf3e2 !important;
    font-family: 'Space Grotesk', sans-serif;
}

/* ---------- Readable text everywhere ---------- */

.block-container [data-testid="stMarkdownContainer"] p,
.block-container [data-testid="stMarkdownContainer"] li {
    color: #eadfc6;
}

[data-testid="stWidgetLabel"] p,
.stApp label p,
.stApp label {
    color: #e3d6bb !important;
    font-weight: 500;
}

[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    color: #a9a391 !important;
}

/* ---------- Sidebar (high contrast) ---------- */

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #141414, #050505);
    border-right: 1px solid rgba(240,217,138,.25);
}

[data-testid="stSidebar"] * {
    font-family: 'Space Grotesk', sans-serif;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: #efe4cc !important;
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: #a9a391 !important;
}

[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: #f0d98a !important;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
}

[data-testid="stSidebar"] hr {
    border-color: rgba(200,190,160,.2);
}

[data-testid="stSidebar"] [role="radiogroup"] {
    gap: 4px;
}

[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid transparent;
    transition: .2s ease;
    width: 100%;
}

[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: rgba(240,217,138,.09);
    border-color: rgba(240,217,138,.25);
    transform: translateX(3px);
}

[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: linear-gradient(90deg, rgba(212,175,55,.24), rgba(212,175,55,.05));
    border-color: rgba(212,175,55,.6);
}

[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
    color: #fff8e7 !important;
    font-weight: 700;
}

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 0 4px 0;
}

.brand-logo {
    width: 46px;
    height: 46px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    background: linear-gradient(135deg, #d4af37, #a8841f);
    box-shadow: 0 4px 0 #6e5513, 0 10px 18px rgba(212,175,55,.25);
}

.brand-name {
    color: #fff8e7;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 1px;
}

.brand-tag {
    color: #f0d98a;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    margin-top: 2px;
}

.side-note {
    padding: 12px 14px;
    border-radius: 12px;
    background: rgba(240,217,138,.07);
    border: 1px solid rgba(240,217,138,.22);
    color: #e3d6bb;
    font-size: 12px;
    line-height: 1.6;
    margin-top: 6px;
}

/* ---------- Hero ---------- */

.hero {
    position: relative;
    overflow: hidden;

    padding: 32px;
    border-radius: 25px;

    background: linear-gradient(125deg, #1e1a12, #101010, #26200f);
    border: 1px solid rgba(212,175,55,.5);

    box-shadow:
        0 8px 0 #000000,
        0 18px 0 -8px #4a3a12,
        0 30px 50px rgba(0,0,0,.42),
        inset 0 1px 0 rgba(255,255,255,.13);

    animation: floatCard 5s ease-in-out infinite;
}

.hero > * {
    position: relative;
    z-index: 2;
}

@keyframes floatCard {
    0%, 100% { transform: translateY(0px); }
    50%      { transform: translateY(-5px); }
}

.coin {
    position: absolute !important;
    z-index: 1 !important;
    font-size: 26px;
    opacity: .35;
    animation: coinFloat 6s ease-in-out infinite;
}

.coin.c1 { right: 6%;  top: 14%;    animation-delay: 0s; }
.coin.c2 { right: 18%; bottom: 12%; animation-delay: 1.5s; font-size: 20px; }
.coin.c3 { right: 32%; top: 8%;     animation-delay: 3s;   font-size: 18px; }

@keyframes coinFloat {
    0%, 100% { transform: translateY(0) rotate(0deg); }
    50%      { transform: translateY(-14px) rotate(12deg); }
}

/* Floating welcome text */

.welcome-float {
    display: inline-block;
    padding: 9px 20px;
    margin-bottom: 14px;
    border-radius: 999px;

    font-size: clamp(13px, 2.6vw, 17px);
    font-weight: 700;
    letter-spacing: .5px;

    background: rgba(240,217,138,.10);
    border: 1px solid rgba(240,217,138,.45);

    animation: welcomeFloat 3.2s ease-in-out infinite;
}

.welcome-float span {
    background: linear-gradient(90deg, #f0d98a, #f8ecc9, #d4af37, #f0d98a);
    background-size: 250% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shimmer 4s linear infinite;
}

@keyframes welcomeFloat {
    0%, 100% {
        transform: translateY(0px);
        box-shadow: 0 0 0 rgba(240,217,138,0);
    }
    50% {
        transform: translateY(-8px);
        box-shadow: 0 14px 28px rgba(240,217,138,.22);
    }
}

@keyframes shimmer {
    0%   { background-position: 0% 50%; }
    100% { background-position: 250% 50%; }
}

.floating-text {
    color: #f0d98a;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 4px;
    animation: floatText 3s ease-in-out infinite;
}

@keyframes floatText {
    0%, 100% { transform: translateY(0px); opacity: .75; }
    50%      { transform: translateY(-4px); opacity: 1; }
}

.hero-title {
    font-size: clamp(30px, 5vw, 58px);
    font-weight: 700;
    letter-spacing: -2px;
    margin-top: 12px;
    color: #fff8e7;

    text-shadow:
        0 2px 0 #f8ecc9,
        0 4px 0 #d4af37,
        0 7px 0 #8a6d1a,
        0 15px 28px rgba(0,0,0,.7);
}

.hero-description {
    color: #e3d6bb;
    font-size: 15px;
    line-height: 1.7;
    max-width: 760px;
    margin-top: 6px;
}

.chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 18px;
}

.chip {
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    color: #efe4cc;
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.14);
}

/* ---------- Ticker ---------- */

.ticker {
    overflow: hidden;
    white-space: nowrap;
    margin-top: 18px;
    padding: 10px 0;
    border-radius: 12px;
    background: rgba(10,10,10,.85);
    border: 1px solid rgba(240,217,138,.2);
}

.ticker-track {
    display: inline-block;
    padding-left: 100%;
    animation: ticker 28s linear infinite;
    color: #a9a391;
    font-size: 13px;
    letter-spacing: 1px;
}

.ticker-track b {
    color: #f0d98a;
}

@keyframes ticker {
    0%   { transform: translateX(0); }
    100% { transform: translateX(-100%); }
}

/* ---------- Page header ---------- */

.page-header {
    display: flex;
    align-items: center;
    gap: 16px;
    margin: 6px 0 20px 0;
    padding: 18px 20px;
    border-radius: 18px;
    background: linear-gradient(90deg, rgba(22,22,22,.95), rgba(22,22,22,.35));
    border: 1px solid rgba(240,217,138,.18);
    border-left: 4px solid #d4af37;
}

.page-icon {
    width: 52px;
    height: 52px;
    flex-shrink: 0;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    background: rgba(212,175,55,.14);
    border: 1px solid rgba(212,175,55,.4);
}

.page-title {
    color: #fff8e7;
    font-size: clamp(20px, 4vw, 28px);
    font-weight: 700;
    letter-spacing: -.5px;
}

.page-subtitle {
    color: #a9a391;
    font-size: 13px;
    margin-top: 2px;
}

.section-title {
    color: #faf3e2;
    font-size: 18px;
    font-weight: 700;
    margin: 18px 0 10px 0;
    padding-left: 12px;
    border-left: 3px solid #f0d98a;
}

/* ---------- Cards ---------- */

.metric-card {
    background: linear-gradient(145deg, #1c1c1c, #0c0c0c);
    border: 1px solid rgba(240,217,138,.24);
    border-top: 3px solid #f0d98a;
    border-radius: 18px;

    padding: 22px;
    min-height: 125px;

    box-shadow:
        0 7px 0 #000000,
        0 17px 25px rgba(0,0,0,.28),
        inset 0 1px 0 rgba(255,255,255,.08);

    transition: .25s ease;
}

.metric-card:hover {
    transform: translateY(-5px);
    border-color: rgba(212,175,55,.6);
    border-top-color: #d4af37;
}

.metric-label {
    color: #b5ae9c;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1.5px;
}

.metric-value {
    color: #f0d98a;
    font-size: 26px;
    font-weight: 700;
    margin-top: 12px;
    overflow-wrap: anywhere;
}

.section-card {
    padding: 22px;
    border-radius: 18px;
    background: rgba(22,22,22,.92);
    border: 1px solid rgba(212,175,55,.25);
    box-shadow: 0 12px 28px rgba(0,0,0,.25);
}

.section-card p {
    color: #a9a391 !important;
    font-size: 12px;
    letter-spacing: 2px;
    margin: 14px 0 0 0;
}

/* ---------- Loader ---------- */

.loader-box {
    padding: 14px 18px 4px 18px;
    margin-bottom: 6px;
    border-radius: 14px;
    background: rgba(10,10,10,.9);
    border: 1px solid rgba(212,175,55,.35);
}

.loader-title {
    color: #f8ecc9;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 1px;
}

[data-testid="stProgress"] > div > div > div > div,
.stProgress > div > div > div > div {
    background-image: linear-gradient(90deg, #d4af37, #f0d98a) !important;
}

/* ---------- Inputs / forms / buttons ---------- */

.stButton > button,
.stFormSubmitButton > button,
.stDownloadButton > button {
    background: linear-gradient(135deg, #d4af37, #a8841f);
    color: #f6edd9 !important;
    border: 1px solid #f0d98a;
    border-radius: 11px;

    font-weight: 700;
    min-height: 43px;

    box-shadow:
        0 5px 0 #6e5513,
        0 12px 20px rgba(212,175,55,.16);

    transition: .2s ease;
}

.stButton > button:hover,
.stFormSubmitButton > button:hover,
.stDownloadButton > button:hover {
    color: #f6edd9 !important;
    transform: translateY(-2px);
    border-color: #f8ecc9;
}

.stTextInput input,
.stNumberInput input,
.stTextArea textarea {
    background: #0a0a0a !important;
    color: #f6edd9 !important;
    border: 1px solid #3a3320 !important;
    border-radius: 10px !important;
}

.stTextInput input:focus,
.stNumberInput input:focus {
    border-color: #f0d98a !important;
}

[data-testid="stNumberInput"] button {
    background: #1a1a1a !important;
    color: #efe4cc !important;
}

[data-baseweb="select"] > div {
    background: #0a0a0a !important;
    border: 1px solid #3a3320 !important;
    border-radius: 10px !important;
}

[data-baseweb="select"] * {
    color: #faf3e2 !important;
}

[data-testid="stForm"] {
    background: rgba(22,22,22,.75);
    border: 1px solid rgba(240,217,138,.2);
    border-radius: 18px;
    padding: 22px;
}

[data-testid="stDataFrame"] {
    border: 1px solid rgba(240,217,138,.2);
    border-radius: 12px;
}

/* ---------- Alerts (always dark + readable) ---------- */

[data-testid="stAlert"] {
    background: rgba(22,22,22,.95) !important;
    border: 1px solid rgba(240,217,138,.35);
    border-radius: 12px;
}

[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {
    border-color: rgba(34,197,94,.65);
}

[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) {
    border-color: rgba(239,68,68,.7);
}

[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {
    border-color: rgba(245,158,11,.7);
}

[data-testid="stAlert"] *,
[data-testid="stAlert"] p {
    color: #f3e9d2 !important;
}

/* ---------- Status bar ---------- */

.status-bar {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 10px;
    margin: 0 0 18px 0;
    padding: 10px 16px;
    border-radius: 12px;
    background: rgba(10,10,10,.85);
    border: 1px solid rgba(212,175,55,.22);
    color: #b5ae9c;
    font-size: 12px;
    letter-spacing: .5px;
}

.status-bar b { color: #f0d98a; }

.dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    margin-right: 8px;
    border-radius: 50%;
    background: #22c55e;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%   { box-shadow: 0 0 0 0 rgba(34,197,94,.6); }
    70%  { box-shadow: 0 0 0 9px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}

/* ---------- Leaderboard ---------- */

.lb-panel {
    padding: 18px 20px 6px 20px;
    border-radius: 18px;
    background: rgba(22,22,22,.9);
    border: 1px solid rgba(212,175,55,.22);
}

.lb-row { margin-bottom: 16px; }

.lb-head {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 13px;
    color: #eadfc6;
}

.lb-rank { color: #d4af37; font-weight: 700; margin-right: 8px; }
.lb-amount { color: #f0d98a; font-weight: 700; }

.lb-track {
    height: 7px;
    margin-top: 7px;
    border-radius: 99px;
    background: #1a1a1a;
    overflow: hidden;
}

.lb-fill {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg, #a8841f, #f0d98a);
}

/* ---------- Gold debit card ---------- */

.bank-card {
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    max-width: 430px;
    min-height: 230px;
    padding: 22px 24px;
    border-radius: 22px;
    color: #1a1405;
    background: linear-gradient(135deg, #f0d98a, #d4af37 48%, #8a6d1a);
    box-shadow:
        0 8px 0 #6e5513,
        0 24px 40px rgba(0,0,0,.55),
        inset 0 1px 0 rgba(255,255,255,.5);
    animation: floatCard 6s ease-in-out infinite;
}

.bank-card::after {
    content: "";
    position: absolute;
    top: 0;
    left: -60%;
    width: 38%;
    height: 100%;
    background: linear-gradient(100deg, transparent, rgba(255,255,255,.38), transparent);
    transform: skewX(-20deg);
    animation: cardShine 5s ease-in-out infinite;
}

@keyframes cardShine {
    0%   { left: -60%; }
    60%, 100% { left: 130%; }
}

.bank-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.bank-card-brand { font-weight: 700; letter-spacing: 3px; font-size: 14px; }

.bank-card-tier {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 3px 10px;
    border-radius: 99px;
    background: rgba(26,20,5,.16);
}

.bank-card-chip {
    width: 46px;
    height: 34px;
    border-radius: 8px;
    background: linear-gradient(135deg, #fff3c4, #c99a2e);
    border: 1px solid rgba(26,20,5,.35);
}

.bank-card-number {
    font-family: 'Courier New', monospace;
    font-size: clamp(16px, 4.6vw, 24px);
    font-weight: 700;
    letter-spacing: 3px;
}

.bank-card-bottom {
    display: flex;
    justify-content: space-between;
    gap: 12px;
}

.bank-card-bottom small {
    display: block;
    font-size: 9px;
    letter-spacing: 2px;
    opacity: .75;
}

.bank-card-bottom b {
    font-size: 13px;
    letter-spacing: 1px;
    overflow-wrap: anywhere;
}

/* ---------- Gold buttons: black text ---------- */

.stButton > button,
.stButton > button p,
.stButton > button:hover,
.stButton > button:hover p,
.stFormSubmitButton > button,
.stFormSubmitButton > button p,
.stFormSubmitButton > button:hover,
.stFormSubmitButton > button:hover p,
.stDownloadButton > button,
.stDownloadButton > button p,
.stDownloadButton > button:hover,
.stDownloadButton > button:hover p {
    color: #101010 !important;
}

/* ---------- Mobile ---------- */

@media (max-width: 640px) {
    .hero { padding: 22px 18px; border-radius: 20px; }
    .hero-description { font-size: 13px; }
    .coin { display: none; }
    .page-header { padding: 14px; gap: 12px; }
    .page-icon { width: 44px; height: 44px; font-size: 22px; }
    [data-testid="stForm"] { padding: 14px; }
    .metric-card { min-height: 105px; }
}
</style>
""", unsafe_allow_html=True)


# ==========================================================
# UI HELPERS
# ==========================================================

def page_header(icon, title, subtitle):
    render_html(f"""
    <div class="page-header">
        <div class="page-icon">{icon}</div>
        <div>
            <div class="page-title">{title}</div>
            <div class="page-subtitle">{subtitle}</div>
        </div>
    </div>
    """)


def section_title(text):
    render_html(f'<div class="section-title">{text}</div>')


def metric_card(title, value, icon):
    render_html(f"""
    <div class="metric-card">
        <span style="float:right;font-size:25px">{icon}</span>
        <div class="metric-label">{title}</div>
        <div class="metric-value">{value}</div>
    </div>
    """)


def feature_loader(page_name):
    """Short animated loading bar shown every time a feature opens."""
    holder = st.empty()

    with holder.container():

        render_html(f"""
        <div class="loader-box">
            <div class="loader-title">⚡ Loading {page_name}...</div>
        </div>
        """)

        bar = st.progress(0)
        note = st.empty()

        for percentage in range(0, 101, 10):

            bar.progress(percentage)

            note.caption(
                f"Preparing {page_name} securely... {percentage}%"
            )

            time.sleep(0.045)

    holder.empty()


# ==========================================================
# FIRST-VISIT LOADING SCREEN
# ==========================================================

if "loading_complete" not in st.session_state:
    st.session_state.loading_complete = False

if not st.session_state.loading_complete:

    loading_placeholder = st.empty()

    with loading_placeholder.container():

        render_html(f"""
        <div class="hero">
            <div class="welcome-float"><span>🙏 {WELCOME_TEXT}</span></div>
            <div class="floating-text">INITIALIZING DIGITAL BANKING SYSTEM</div>
            <div class="hero-title">PYTHONGURUKOOL BANK</div>
            <div class="hero-description">
                Preparing your next-generation banking experience...
            </div>
        </div>
        """)

        progress = st.progress(0)
        status = st.empty()

        for percentage in range(0, 101, 5):

            progress.progress(percentage)

            status.caption(
                f"Initializing banking dashboard... {percentage}%"
            )

            time.sleep(0.03)

    loading_placeholder.empty()
    st.session_state.loading_complete = True


# ==========================================================
# MAIN HEADER
# ==========================================================

ticker_item = (
    f"<b>✦</b> {WELCOME_TEXT} &nbsp;&nbsp; "
    "<b>✦</b> Safe &bull; Simple &bull; Smart Banking &nbsp;&nbsp; "
    "<b>✦</b> PIN Protected Transactions &nbsp;&nbsp; "
    "<b>✦</b> Live Financial Analytics &nbsp;&nbsp; "
)

render_html(f"""
<div class="hero">
    <span class="coin c1">🪙</span>
    <span class="coin c2">💰</span>
    <span class="coin c3">🪙</span>

    <div class="welcome-float"><span>🙏 {WELCOME_TEXT}</span></div>

    <div class="floating-text">✦ NEXT-GENERATION DIGITAL FINANCE ✦</div>
    <div class="hero-title">PYTHONGURUKOOL BANK</div>

    <div class="hero-description">
        Experience smarter banking with modern account management,
        transaction monitoring, PIN verification and interactive
        financial analytics.
    </div>

    <div class="chip-row">
        <span class="chip">🔒 PIN Protected</span>
        <span class="chip">⚡ Instant Transactions</span>
        <span class="chip">📊 Live Analytics</span>
        <span class="chip">📄 CSV Statements</span>
    </div>
</div>

<div class="ticker">
    <div class="ticker-track">{ticker_item * 3}</div>
</div>
""")

st.write("")


# ==========================================================
# GLOBAL STATISTICS
# ==========================================================

accounts = db["accounts"]
transactions = db["transactions"]

total_balance = sum(
    float(a["balance"])
    for a in accounts.values()
)

total_deposits = sum(
    t["amount"]
    for t in transactions
    if t["type"] == "Deposit"
)

total_withdrawals = sum(
    t["amount"]
    for t in transactions
    if t["type"] == "Withdrawal"
)


render_html(f"""
<div class="status-bar">
    <span><i class="dot"></i><b>System Online</b></span>
    <span>{greeting()} &bull; {datetime.now().strftime("%A, %d %B %Y")}</span>
    <span>🏦 <b>{len(accounts)}</b> accounts &bull; <b>{len(transactions)}</b> transactions</span>
</div>
""")


# ==========================================================
# SIDEBAR NAVIGATION
# ==========================================================

with st.sidebar:

    render_html("""
    <div class="brand">
        <div class="brand-logo">🏦</div>
        <div>
            <div class="brand-name">PYTHONGURUKOOL</div>
            <div class="brand-tag">DIGITAL BANKING PLATFORM</div>
        </div>
    </div>
    """)

    st.markdown("---")

    NAV_ICONS = {
        "Dashboard": "◈",
        "Create Account": "✨",
        "Deposit Money": "↗",
        "Withdraw Money": "↘",
        "Fund Transfer": "⇄",
        "Check Balance": "💎",
        "Account Details": "🪪",
        "Change PIN": "🔐",
        "Transaction History": "📜",
        "Search Account": "🔎",
        "EMI Calculator": "🧮",
        "Close Account": "⚠️",
        "Bank Statistics": "📊"
    }

    page = st.radio(
        "NAVIGATION",
        list(NAV_ICONS.keys()),
        key="page_nav",
        format_func=lambda p: f"{NAV_ICONS[p]}  {p}"
    )

    st.markdown("---")

    st.markdown("### 🛡️ Security Center")

    render_html("""
    <div class="side-note">
        🔐 PIN verification is required for sensitive operations.
        <br><br>
        ℹ️ Educational demo only. Not a real banking service.
    </div>
    """)


# ==========================================================
# LOADING BAR WHEN A FEATURE IS OPENED
# ==========================================================

if "active_page" not in st.session_state:
    st.session_state.active_page = page

elif st.session_state.active_page != page:
    feature_loader(page)
    st.session_state.active_page = page


# ==========================================================
# ACCOUNT SELECTOR
# ==========================================================

def select_account(
    label="Select Account",
    include_closed=False
):

    if include_closed:

        numbers = list(accounts.keys())

    else:

        numbers = [
            n for n, a in accounts.items()
            if a["status"] == "Active"
        ]

    if not numbers:

        st.warning(
            "No available accounts. Create an account first."
        )

        return None

    return st.selectbox(
        label,
        numbers,
        format_func=lambda n:
        f"{accounts[n]['name']} | {n}"
    )


# ==========================================================
# DASHBOARD
# ==========================================================

if page == "Dashboard":

    page_header(
        "◈",
        "Banking Command Center",
        "A live overview of accounts, balances and activity"
    )

    columns = st.columns(4)

    metrics = [
        ("TOTAL ACCOUNTS", str(len(accounts)), "👥"),
        ("TOTAL BALANCE", money(total_balance), "💎"),
        ("TOTAL DEPOSITS", money(total_deposits), "↗️"),
        ("TOTAL WITHDRAWALS", money(total_withdrawals), "↘️")
    ]

    for column, data in zip(columns, metrics):

        with column:

            metric_card(*data)

    st.write("")

    section_title("🚀 Quick Actions")

    quick_actions = [
        ("＋ Open Account", "Create Account"),
        ("↗ Deposit", "Deposit Money"),
        ("↘ Withdraw", "Withdraw Money"),
        ("⇄ Transfer", "Fund Transfer")
    ]

    for column, (label, target) in zip(st.columns(4), quick_actions):

        with column:

            st.button(
                label,
                key=f"quick_{target}",
                on_click=go_to,
                args=(target,),
                use_container_width=True
            )

    st.write("")

    left, right = st.columns([3, 2])

    with left:

        section_title("📈 Deposits vs Withdrawals")

        show_activity_chart(daily_activity())

    with right:

        section_title("🏆 Top Accounts")

        leaderboard()

    section_title("⚡ Recent Transactions")

    recent = list(reversed(transactions[-10:]))

    if recent:

        st.dataframe(
            [
                {
                    "Reference": t["reference"],
                    "Customer": t["customer"],
                    "Type": t["type"],
                    "Amount": money(t["amount"]),
                    "Time": t["time"]
                }
                for t in recent
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No transactions yet. Create an account to begin."
        )


# ==========================================================
# CREATE ACCOUNT
# ==========================================================

elif page == "Create Account":

    page_header(
        "✨",
        "Create New Account",
        "Open a new savings account in under a minute"
    )

    with st.form("create_account"):

        col1, col2 = st.columns(2)

        with col1:

            name = st.text_input("Customer Name")

            age = st.number_input(
                "Age",
                min_value=1,
                max_value=120,
                value=18
            )

            mobile = st.text_input(
                "Mobile Number",
                max_chars=10
            )

        with col2:

            pin = st.text_input(
                "Create 4-Digit PIN",
                type="password",
                max_chars=4
            )

            confirm_pin = st.text_input(
                "Confirm PIN",
                type="password",
                max_chars=4
            )

            opening_balance = st.number_input(
                "Opening Balance (₹)",
                min_value=MIN_DEPOSIT,
                value=500.0,
                step=100.0
            )

        submitted = st.form_submit_button(
            "＋ Create Account",
            use_container_width=True
        )

    if submitted:

        errors = []

        if not name.strip():

            errors.append("Customer name is required.")

        if not mobile.isdigit() or len(mobile) != 10:

            errors.append(
                "Mobile number must contain exactly 10 digits."
            )

        if not pin.isdigit() or len(pin) != 4:

            errors.append(
                "PIN must contain exactly 4 digits."
            )

        if pin != confirm_pin:

            errors.append("PIN confirmation does not match.")

        if (
            pin.isdigit()
            and len(pin) == 4
            and any(
                secrets.compare_digest(
                    a["pin_hash"],
                    hash_pin(pin)
                )
                for a in accounts.values()
            )
        ):

            errors.append(
                "Choose a PIN that is not used by another account."
            )

        if errors:

            for error in errors:

                st.error(error)

        else:

            number = generate_account_number()

            db["accounts"][number] = {
                "account_number": number,
                "name": name.strip(),
                "age": int(age),
                "mobile": mobile,
                "pin_hash": hash_pin(pin),
                "balance": float(opening_balance),
                "status": "Active",
                "created_at": current_time()
            }

            record_transaction(
                number,
                "Account Opened",
                opening_balance,
                "Opening balance"
            )

            save_database()

            notify_success("Account created successfully!")

            st.code(
                f"Account Number: {number}\n"
                f"Customer Name: {name.strip()}\n"
                f"Opening Balance: {money(opening_balance)}"
            )


# ==========================================================
# DEPOSIT MONEY
# ==========================================================

elif page == "Deposit Money":

    page_header(
        "↗",
        "Deposit Money",
        "Add funds to an account instantly"
    )

    number = select_account()

    if number:

        account = accounts[number]

        st.info(
            f"Current balance: {money(account['balance'])}"
        )

        with st.form("deposit_form"):

            pin = st.text_input(
                "Account PIN",
                type="password",
                max_chars=4
            )

            amount = st.number_input(
                "Deposit Amount (₹)",
                min_value=MIN_DEPOSIT,
                value=500.0,
                step=100.0
            )

            note = st.text_input("Transaction Note")

            submitted = st.form_submit_button(
                "Confirm Deposit",
                use_container_width=True
            )

        if submitted:

            if not verify_pin(account, pin):

                pin_error(account)

            else:

                account["balance"] = round(
                    account["balance"] + amount,
                    2
                )

                transaction = record_transaction(
                    number,
                    "Deposit",
                    amount,
                    note
                )

                save_database()

                notify_success(
                    f"{money(amount)} deposited successfully!"
                )

                st.code(
                    f"Reference: {transaction['reference']}\n"
                    f"New Balance: {money(account['balance'])}"
                )


# ==========================================================
# WITHDRAW MONEY
# ==========================================================

elif page == "Withdraw Money":

    page_header(
        "↘",
        "Withdraw Money",
        "Withdraw funds securely with PIN verification"
    )

    number = select_account()

    if number:

        account = accounts[number]

        st.info(
            f"Available balance: {money(account['balance'])}"
        )

        with st.form("withdraw_form"):

            pin = st.text_input(
                "Account PIN",
                type="password",
                max_chars=4
            )

            amount = st.number_input(
                "Withdrawal Amount (₹)",
                min_value=1.0,
                value=100.0,
                step=100.0
            )

            note = st.text_input("Transaction Note")

            submitted = st.form_submit_button(
                "Confirm Withdrawal",
                use_container_width=True
            )

        if submitted:

            if not verify_pin(account, pin):

                pin_error(account)

            elif amount > account["balance"]:

                st.error("Insufficient balance.")

            else:

                account["balance"] = round(
                    account["balance"] - amount,
                    2
                )

                transaction = record_transaction(
                    number,
                    "Withdrawal",
                    amount,
                    note
                )

                save_database()

                notify_success(
                    f"{money(amount)} withdrawn successfully!"
                )

                st.code(
                    f"Reference: {transaction['reference']}\n"
                    f"Remaining Balance: {money(account['balance'])}"
                )


# ==========================================================
# CHECK BALANCE
# ==========================================================

elif page == "Check Balance":

    page_header(
        "💎",
        "Check Balance",
        "Verify your PIN to view the available balance"
    )

    number = select_account()

    if number:

        account = accounts[number]

        pin = st.text_input(
            "Enter PIN",
            type="password",
            max_chars=4
        )

        if st.button("Verify & Show Balance"):

            if verify_pin(account, pin):

                metric_card(
                    "AVAILABLE BALANCE",
                    money(account["balance"]),
                    "💎"
                )

            else:

                pin_error(account)


# ==========================================================
# ACCOUNT DETAILS
# ==========================================================

elif page == "Account Details":

    page_header(
        "🪪",
        "Account Details",
        "Customer profile, status and account summary"
    )

    number = select_account(include_closed=True)

    if number:

        account = accounts[number]

        col1, col2 = st.columns(2)

        with col1:

            bank_card(account)

            st.metric("Balance", money(account["balance"]))

        with col2:

            st.write("**Age:**", account["age"])

            st.write("**Mobile:**", account["mobile"])

            st.write("**Status:**", account["status"])

            st.write("**Created:**", account["created_at"])

            st.write(
                "**Transactions:**",
                len(account_history(number))
            )

        st.write("")

        section_title("🧾 Mini Statement (Last 5)")

        last_five = account_history(number)[:5]

        if last_five:

            st.dataframe(
                [
                    {
                        "Time": t["time"],
                        "Type": t["type"],
                        "Amount": money(t["amount"]),
                        "Balance": money(t["balance"])
                    }
                    for t in last_five
                ],
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info("No transactions yet.")


# ==========================================================
# CHANGE PIN
# ==========================================================

elif page == "Change PIN":

    page_header(
        "🔐",
        "Change PIN",
        "Keep your account safe with a new 4-digit PIN"
    )

    number = select_account()

    if number:

        account = accounts[number]

        with st.form("change_pin"):

            old_pin = st.text_input(
                "Current PIN",
                type="password",
                max_chars=4
            )

            new_pin = st.text_input(
                "New PIN",
                type="password",
                max_chars=4
            )

            confirm_pin = st.text_input(
                "Confirm New PIN",
                type="password",
                max_chars=4
            )

            submitted = st.form_submit_button(
                "Update PIN",
                use_container_width=True
            )

        if submitted:

            if not verify_pin(account, old_pin):

                pin_error(account)

            elif not new_pin.isdigit() or len(new_pin) != 4:

                st.error("New PIN must contain four digits.")

            elif new_pin != confirm_pin:

                st.error("PIN confirmation does not match.")

            elif secrets.compare_digest(
                hash_pin(new_pin),
                account["pin_hash"]
            ):

                st.error("New PIN must be different.")

            elif any(
                other_number != number
                and secrets.compare_digest(
                    other["pin_hash"],
                    hash_pin(new_pin)
                )
                for other_number, other in accounts.items()
            ):

                st.error("This PIN is already in use.")

            else:

                account["pin_hash"] = hash_pin(new_pin)

                record_transaction(
                    number,
                    "PIN Changed",
                    0,
                    "PIN updated"
                )

                save_database()

                notify_success("PIN updated successfully.")


# ==========================================================
# TRANSACTION HISTORY
# ==========================================================

elif page == "Transaction History":

    page_header(
        "📜",
        "Transaction History",
        "Every transaction on the account, ready to export"
    )

    number = select_account(include_closed=True)

    if number:

        history = account_history(number)

        if history:

            all_types = sorted({t["type"] for t in history})

            chosen = st.multiselect(
                "Filter by transaction type",
                all_types,
                default=all_types
            )

            history = [t for t in history if t["type"] in chosen]

            money_in = sum(
                t["amount"] for t in history if t["type"] in CREDIT_TYPES
            )

            money_out = sum(
                t["amount"] for t in history if t["type"] in DEBIT_TYPES
            )

            h1, h2, h3 = st.columns(3)

            with h1:
                metric_card("MONEY IN", money(money_in), "↗️")

            with h2:
                metric_card("MONEY OUT", money(money_out), "↘️")

            with h3:
                metric_card("ENTRIES", str(len(history)), "🧾")

            st.write("")

            st.dataframe(
                [
                    {
                        "Reference": t["reference"],
                        "Time": t["time"],
                        "Type": t["type"],
                        "Amount": money(t["amount"]),
                        "Balance": money(t["balance"]),
                        "Note": t["note"]
                    }
                    for t in history
                ],
                use_container_width=True,
                hide_index=True
            )

            output = io.StringIO()

            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "reference",
                    "account_number",
                    "customer",
                    "type",
                    "amount",
                    "balance",
                    "note",
                    "time"
                ]
            )

            writer.writeheader()
            writer.writerows(history)

            st.download_button(
                "⬇ Export CSV",
                data=output.getvalue(),
                file_name=f"history_{number}.csv",
                mime="text/csv"
            )

        else:

            st.info("No transaction history found.")


# ==========================================================
# SEARCH ACCOUNT
# ==========================================================

elif page == "Search Account":

    page_header(
        "🔎",
        "Search Account",
        "Find accounts by name, account number or mobile"
    )

    query = st.text_input(
        "Customer name, account number or mobile"
    )

    if query.strip():

        query = query.lower().strip()

        results = []

        for number, account in accounts.items():

            if (
                query in number.lower()
                or query in account["name"].lower()
                or query in account["mobile"]
            ):

                results.append({
                    "Name": account["name"],
                    "Account Number": number,
                    "Mobile": account["mobile"],
                    "Balance": money(account["balance"]),
                    "Status": account["status"]
                })

        if results:

            st.dataframe(
                results,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.warning("No matching accounts found.")


# ==========================================================
# FUND TRANSFER
# ==========================================================

elif page == "Fund Transfer":

    page_header(
        "⇄",
        "Fund Transfer",
        "Send money between PYTHONGURUKOOL accounts instantly"
    )

    sender = select_account("From Account")

    if sender:

        receivers = [
            n for n in active_accounts() if n != sender
        ]

        if not receivers:

            st.warning(
                "At least two active accounts are needed to transfer money."
            )

        else:

            account = accounts[sender]

            st.info(
                f"Available balance: {money(account['balance'])}"
            )

            receiver = st.selectbox(
                "To Account",
                receivers,
                format_func=lambda n:
                f"{accounts[n]['name']} | {n}"
            )

            with st.form("transfer_form"):

                pin = st.text_input(
                    "Sender Account PIN",
                    type="password",
                    max_chars=4
                )

                amount = st.number_input(
                    "Transfer Amount (₹)",
                    min_value=1.0,
                    value=100.0,
                    step=100.0
                )

                note = st.text_input("Transaction Note")

                submitted = st.form_submit_button(
                    "Confirm Transfer",
                    use_container_width=True
                )

            if submitted:

                if not verify_pin(account, pin):

                    pin_error(account)

                elif amount > account["balance"]:

                    st.error("Insufficient balance.")

                else:

                    target = accounts[receiver]
                    extra = f" - {note}" if note.strip() else ""

                    account["balance"] = round(
                        account["balance"] - amount, 2
                    )

                    out_tx = record_transaction(
                        sender,
                        "Transfer Out",
                        amount,
                        f"To {target['name']} ({receiver}){extra}"
                    )

                    target["balance"] = round(
                        target["balance"] + amount, 2
                    )

                    record_transaction(
                        receiver,
                        "Transfer In",
                        amount,
                        f"From {account['name']} ({sender}){extra}"
                    )

                    save_database()

                    notify_success(
                        f"{money(amount)} transferred to {target['name']}!"
                    )

                    st.code(
                        f"Reference: {out_tx['reference']}\n"
                        f"Remaining Balance: {money(account['balance'])}"
                    )


# ==========================================================
# EMI CALCULATOR
# ==========================================================

elif page == "EMI Calculator":

    page_header(
        "🧮",
        "EMI Calculator",
        "Plan a loan with a full repayment breakdown"
    )

    e1, e2, e3 = st.columns(3)

    with e1:
        principal = st.number_input(
            "Loan Amount (₹)",
            min_value=10000.0,
            value=500000.0,
            step=10000.0
        )

    with e2:
        annual_rate = st.number_input(
            "Annual Interest Rate (%)",
            min_value=1.0,
            max_value=40.0,
            value=9.5,
            step=0.1
        )

    with e3:
        months = int(st.number_input(
            "Tenure (months)",
            min_value=3,
            max_value=360,
            value=60,
            step=3
        ))

    monthly_rate = annual_rate / 12 / 100
    growth = (1 + monthly_rate) ** months
    emi = principal * monthly_rate * growth / (growth - 1)
    total_payable = emi * months
    total_interest = total_payable - principal

    st.write("")

    m1, m2, m3, m4 = st.columns(4)

    with m1:
        metric_card("MONTHLY EMI", money(emi), "📅")

    with m2:
        metric_card("TOTAL INTEREST", money(total_interest), "📈")

    with m3:
        metric_card("TOTAL PAYABLE", money(total_payable), "💰")

    with m4:
        metric_card(
            "INTEREST SHARE",
            f"{total_interest / total_payable * 100:.1f}%",
            "🎯"
        )

    schedule = []
    balance = principal

    for month in range(1, months + 1):

        interest_part = balance * monthly_rate
        principal_part = emi - interest_part
        balance = max(0.0, balance - principal_part)

        schedule.append({
            "Month": month,
            "EMI": money(emi),
            "Principal": money(principal_part),
            "Interest": money(interest_part),
            "Balance": money(balance),
            "_balance": round(balance, 2)
        })

    st.write("")

    section_title("📉 Outstanding Loan Balance")

    st.area_chart(
        {"Outstanding Balance": [r["_balance"] for r in schedule]}
    )

    with st.expander("View full repayment schedule"):

        st.dataframe(
            [
                {k: v for k, v in r.items() if k != "_balance"}
                for r in schedule
            ],
            use_container_width=True,
            hide_index=True
        )

    st.caption(
        "Estimates only. Real loan terms depend on the lender."
    )


# ==========================================================
# CLOSE ACCOUNT
# ==========================================================

elif page == "Close Account":

    page_header(
        "⚠️",
        "Close Account",
        "Balance must be zero before an account can be closed"
    )

    number = select_account()

    if number:

        account = accounts[number]

        st.write("Customer:", account["name"])

        st.write(
            "Current Balance:",
            money(account["balance"])
        )

        with st.form("close_account"):

            pin = st.text_input(
                "Account PIN",
                type="password",
                max_chars=4
            )

            confirm = st.checkbox(
                "Confirm account closure"
            )

            submitted = st.form_submit_button(
                "Close Account",
                use_container_width=True
            )

        if submitted:

            if not verify_pin(account, pin):

                pin_error(account)

            elif not confirm:

                st.error("Please confirm account closure.")

            elif account["balance"] != 0:

                st.error(
                    "Withdraw the remaining balance first."
                )

            else:

                account["status"] = "Closed"

                record_transaction(
                    number,
                    "Account Closed",
                    0,
                    "Account closure"
                )

                save_database()

                notify_success("Account closed successfully.")


# ==========================================================
# BANK STATISTICS
# ==========================================================

elif page == "Bank Statistics":

    page_header(
        "📊",
        "Bank Analytics",
        "Account health, transaction mix and balance distribution"
    )

    all_accounts = list(accounts.values())

    active_count = sum(
        a["status"] == "Active"
        for a in all_accounts
    )

    closed_count = sum(
        a["status"] == "Closed"
        for a in all_accounts
    )

    average_balance = (
        total_balance / len(all_accounts)
        if all_accounts else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        metric_card(
            "ACTIVE ACCOUNTS",
            str(active_count),
            "🟢"
        )

    with c2:
        metric_card(
            "CLOSED ACCOUNTS",
            str(closed_count),
            "⚫"
        )

    with c3:
        metric_card(
            "TRANSACTIONS",
            str(len(transactions)),
            "🔁"
        )

    with c4:
        metric_card(
            "AVERAGE BALANCE",
            money(average_balance),
            "📈"
        )

    st.write("")

    col1, col2 = st.columns(2)

    with col1:

        section_title("Transaction Types")

        transaction_counts = {}

        for transaction in transactions:

            kind = transaction["type"]

            transaction_counts[kind] = (
                transaction_counts.get(kind, 0) + 1
            )

        if transaction_counts:

            st.bar_chart(transaction_counts)

        else:

            st.info("No transactions to chart.")

    with col2:

        section_title("Account Balances")

        balances = {
            a["name"]: a["balance"]
            for a in all_accounts
        }

        if balances:

            st.bar_chart(balances)

        else:

            st.info("Create an account to see balances.")

    st.write("")

    section_title("📈 Daily Activity")

    show_activity_chart(daily_activity())

    st.write("")

    ledger = io.StringIO()

    ledger_writer = csv.DictWriter(
        ledger,
        fieldnames=[
            "reference",
            "account_number",
            "customer",
            "type",
            "amount",
            "balance",
            "note",
            "time"
        ]
    )

    ledger_writer.writeheader()
    ledger_writer.writerows(transactions)

    st.download_button(
        "⬇ Download Full Ledger (CSV)",
        data=ledger.getvalue(),
        file_name="pythongurukool_ledger.csv",
        mime="text/csv"
    )


# ==========================================================
# FOOTER
# ==========================================================

st.markdown("---")

render_html("""
<div style="text-align:center;color:#908a7a;padding:20px;font-size:12px;letter-spacing:2px;">
    PYTHONGURUKOOL BANK<br><br>
    POWERED BY PYTHON + STREAMLIT<br><br>
    EDUCATIONAL BANKING SIMULATOR
</div>
""")
