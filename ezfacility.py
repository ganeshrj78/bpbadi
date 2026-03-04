"""
EZFacility scraper for Royal Badminton Academy.
Handles login, schedule page scraping, court booking data parsing,
and password encryption (key derived from app's SECRET_KEY).

SECURITY: No credentials are stored in this file.
Credentials are stored encrypted in the SiteSettings DB table.
"""
import re
import base64
import hashlib
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

BASE_URL = 'https://royalbadminton.ezfacility.com'
LOGIN_URL = f'{BASE_URL}/Account/Login'
SCHEDULE_URL = f'{BASE_URL}/MySchedule'

# ── Court cost rules ──────────────────────────────────────────────────────────
# These are SUGGESTED costs. Admin can override per court during sync.
COST_RULES = {
    60:  45.00,   # $45/hr × 1 hr
    120: 75.00,   # $37.50/hr × 2 hrs
    150: 90.00,   # flat rate
    180: 105.00,  # $35/hr × 3 hrs
}
DEFAULT_RATE_PER_HOUR = 45.00


def suggest_cost(duration_minutes: int) -> float:
    """Return suggested court cost based on reservation duration."""
    if duration_minutes in COST_RULES:
        return COST_RULES[duration_minutes]
    return round(DEFAULT_RATE_PER_HOUR * duration_minutes / 60, 2)


# ── Encryption helpers ────────────────────────────────────────────────────────

def _get_fernet(secret_key: str) -> Fernet:
    """Derive a Fernet cipher from the app's SECRET_KEY (never stored)."""
    key_bytes = hashlib.sha256(secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_password(plaintext: str, secret_key: str) -> str:
    """Encrypt a password; returns ciphertext string safe for DB storage."""
    return _get_fernet(secret_key).encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str, secret_key: str) -> str:
    """Decrypt a previously encrypted password."""
    return _get_fernet(secret_key).decrypt(ciphertext.encode()).decode()


# ── Scraper ───────────────────────────────────────────────────────────────────

def fetch_bookings(username: str, password: str, debug_dump_path: str = None) -> list:
    """
    Log into EZFacility and scrape court bookings from MySchedule.

    Returns a list of booking dicts:
      {
        'date': date,
        'court_name': str,
        'start_time': str,        e.g. '6:30 AM'
        'end_time': str,          e.g. '9:30 AM'
        'start_time_24': str,     e.g. '06:30'
        'end_time_24': str,       e.g. '09:30'
        'duration_minutes': int,
        'suggested_cost': float,
      }

    Raises ValueError on login failure, requests.RequestException on network error.
    If debug_dump_path is provided, the raw schedule HTML is written there.
    """
    sess = requests.Session()
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36'
    })

    # GET login page to harvest anti-forgery token
    r = sess.get(LOGIN_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    token_input = (
        soup.find('input', {'name': '__RequestVerificationToken'}) or
        soup.find('input', {'name': 'csrf_token'})
    )
    token = token_input['value'] if token_input else ''

    # POST credentials
    payload = {
        'UserName': username,
        'Password': password,
        '__RequestVerificationToken': token,
    }
    r = sess.post(LOGIN_URL, data=payload, timeout=20, allow_redirects=True)
    r.raise_for_status()

    # Detect login failure
    if 'Account/Login' in r.url or '/login' in r.url.lower():
        raise ValueError('EZFacility login failed — check username and password in Settings.')

    # Fetch schedule
    r = sess.get(SCHEDULE_URL, timeout=20)
    r.raise_for_status()

    if debug_dump_path:
        try:
            with open(debug_dump_path, 'w', encoding='utf-8') as f:
                f.write(r.text)
            logger.info(f'EZFacility HTML dumped to {debug_dump_path}')
        except Exception as e:
            logger.warning(f'Could not write debug dump: {e}')

    return _parse_schedule(r.text)


def _parse_schedule(html: str) -> list:
    """
    Parse the MySchedule page to extract court bookings.
    EZFacility renders schedules in several possible formats; this handles
    the most common table and list-based layouts with graceful fallbacks.
    """
    soup = BeautifulSoup(html, 'html.parser')
    bookings = []

    # Strategy 1: look for structured booking elements (EZFacility uses
    # data attributes on some versions)
    booking_blocks = (
        soup.select('[data-start-time]') or
        soup.select('.schedule-item') or
        soup.select('.booking-item') or
        soup.select('.reservation-item')
    )
    if booking_blocks:
        for block in booking_blocks:
            b = _parse_block(block)
            if b:
                bookings.append(b)
        if bookings:
            return bookings

    # Strategy 2: parse table rows
    for table in soup.find_all('table'):
        headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
        # Look for tables that have date+time or court columns
        if not any(kw in ' '.join(headers) for kw in ['date', 'court', 'time', 'resource', 'reserv']):
            continue
        rows = table.find_all('tr')[1:]  # skip header
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            b = _parse_row_cells([c.get_text(strip=True) for c in cells])
            if b:
                bookings.append(b)

    # Strategy 3: look for any text blocks containing court + time info
    if not bookings:
        bookings = _parse_text_blocks(soup)

    # Deduplicate by (date, court_name, start_time)
    seen = set()
    unique = []
    for b in bookings:
        key = (b['date'], b['court_name'], b['start_time'])
        if key not in seen:
            seen.add(key)
            unique.append(b)

    return sorted(unique, key=lambda x: (x['date'], x['start_time']))


def _parse_block(block) -> dict:
    """Parse a single booking block element."""
    try:
        text = block.get_text(' ', strip=True)
        date_val = _extract_date(text) or _extract_date(block.get('data-date', ''))
        start_str, end_str = _extract_time_range(text)
        if not date_val or start_str == 'TBD':
            return None
        court = _extract_court_name(text) or 'Court'
        dur = _duration_minutes(start_str, end_str)
        return _make_booking(date_val, court, start_str, end_str, dur)
    except Exception:
        return None


def _parse_row_cells(cells: list) -> dict:
    """Parse a list of cell text values into a booking dict."""
    try:
        combined = ' '.join(cells)
        date_val = _extract_date(combined)
        if not date_val:
            return None
        start_str, end_str = _extract_time_range(combined)
        if start_str == 'TBD':
            return None
        court = _extract_court_name(combined) or 'Court'
        dur = _duration_minutes(start_str, end_str)
        return _make_booking(date_val, court, start_str, end_str, dur)
    except Exception:
        return None


def _parse_text_blocks(soup) -> list:
    """Last-resort: scan all text in the page for court/time patterns."""
    bookings = []
    text = soup.get_text('\n')
    lines = text.split('\n')
    date_val = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        d = _extract_date(line)
        if d:
            date_val = d
            continue
        if date_val:
            start_str, end_str = _extract_time_range(line)
            court = _extract_court_name(line)
            if start_str != 'TBD' and court:
                dur = _duration_minutes(start_str, end_str)
                bookings.append(_make_booking(date_val, court, start_str, end_str, dur))
    return bookings


# ── Parsing helpers ───────────────────────────────────────────────────────────

_DATE_PATTERNS = [
    ('%m/%d/%Y', r'\d{1,2}/\d{1,2}/\d{4}'),
    ('%Y-%m-%d', r'\d{4}-\d{2}-\d{2}'),
    ('%B %d, %Y', r'[A-Z][a-z]+ \d{1,2}, \d{4}'),
    ('%b %d, %Y',  r'[A-Z][a-z]{2} \d{1,2}, \d{4}'),
    ('%m/%d/%y',  r'\d{1,2}/\d{1,2}/\d{2}'),
]

_TIME_RE = re.compile(r'\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)', re.IGNORECASE)
_COURT_RE = re.compile(r'(?:Court|Ct\.?)\s*\d+', re.IGNORECASE)


def _extract_date(text: str):
    for fmt, pattern in _DATE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            try:
                return datetime.strptime(m.group(), fmt).date()
            except ValueError:
                continue
    return None


def _extract_time_range(text: str):
    times = _TIME_RE.findall(text)
    start = times[0].strip() if len(times) >= 1 else 'TBD'
    end   = times[1].strip() if len(times) >= 2 else 'TBD'
    return start, end


def _extract_court_name(text: str) -> str:
    m = _COURT_RE.search(text)
    return m.group().strip() if m else ''


def _duration_minutes(start_str: str, end_str: str) -> int:
    if start_str == 'TBD' or end_str == 'TBD':
        return 0
    for fmt in ('%I:%M %p', '%I:%M%p', '%I:%M %P', '%I:%M%P'):
        try:
            t1 = datetime.strptime(start_str.upper().replace('.', ''), fmt)
            t2 = datetime.strptime(end_str.upper().replace('.', ''), fmt)
            return int((t2 - t1).total_seconds() / 60)
        except ValueError:
            continue
    return 0


def _to_24h(time_str: str) -> str:
    """Convert '6:30 AM' → '06:30'."""
    for fmt in ('%I:%M %p', '%I:%M%p'):
        try:
            return datetime.strptime(time_str.upper().replace('.', ''), fmt).strftime('%H:%M')
        except ValueError:
            continue
    return time_str  # return as-is if unparseable


def _make_booking(date_val, court_name: str, start_str: str, end_str: str, dur: int) -> dict:
    return {
        'date': date_val,
        'court_name': court_name,
        'start_time': start_str,
        'end_time': end_str,
        'start_time_24': _to_24h(start_str),
        'end_time_24': _to_24h(end_str),
        'duration_minutes': dur,
        'suggested_cost': suggest_cost(dur),
    }
