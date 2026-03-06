"""
EZFacility scraper for Royal Badminton Academy.

Flow:
  1. Read live session cookies from the user's Brave browser (browser_cookie3).
  2. Inject them into headless Playwright Chromium.
  3. Navigate to /MySchedule — no login form, no reCAPTCHA.
  4. Parse FullCalendar week views for the requested session dates.

The user must be logged into royalbadminton.ezfacility.com in Brave.
"""
import html as html_mod
import re
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional

import browser_cookie3
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

BASE_URL     = 'https://royalbadminton.ezfacility.com'
LOGIN_URL    = f'{BASE_URL}/login'
SCHEDULE_URL = f'{BASE_URL}/MySchedule'
DOMAIN       = 'royalbadminton.ezfacility.com'

# ── Court cost rules ────────────────────────────────────────────────────────────
COST_RULES = {
    60:  45.00,
    120: 75.00,
    150: 90.00,   # flat rate
    180: 105.00,
}
DEFAULT_RATE_PER_HOUR = 45.00


def suggest_cost(duration_minutes: int) -> float:
    if duration_minutes in COST_RULES:
        return COST_RULES[duration_minutes]
    return round(DEFAULT_RATE_PER_HOUR * duration_minutes / 60, 2)


# ── Cookie helpers ──────────────────────────────────────────────────────────────

def get_brave_cookies() -> List[dict]:
    """
    Read live EZFacility session cookies from the user's Brave browser.
    Returns a list of Playwright-compatible cookie dicts.
    Raises ValueError if no valid session is found.
    """
    try:
        jar = browser_cookie3.brave(domain_name=DOMAIN)
        cookies = list(jar)
    except Exception as e:
        raise ValueError(
            f'Could not read Brave cookies: {e}. '
            'Make sure Brave is installed and you are logged into Royal Facility.'
        )

    if not cookies:
        raise ValueError(
            'No EZFacility cookies found in Brave. '
            'Please log into royalbadminton.ezfacility.com in Brave and try again.'
        )

    # Convert to Playwright format
    return [
        {'name': c.name, 'value': c.value, 'domain': DOMAIN, 'path': '/'}
        for c in cookies
    ]


# ── FullCalendar parsing ────────────────────────────────────────────────────────

def _parse_week_source(page_source: str) -> list:
    """Parse one week's FullCalendar HTML into a list of booking dicts."""
    soup = BeautifulSoup(page_source, 'html.parser')
    bookings = []

    headers = soup.select('th.fc-day-header')
    col_dates = {
        i: th.get('data-date', '')
        for i, th in enumerate(headers) if th.get('data-date')
    }

    tbody = soup.select_one('.fc-content-skeleton table tbody')
    if not tbody:
        return bookings

    col_events: dict = {i: [] for i in col_dates}
    rowspan_remaining: dict = {}

    for row in tbody.find_all('tr'):
        tds = row.find_all('td')
        col_ptr = 0
        for td in tds:
            while rowspan_remaining.get(col_ptr, 0) > 0:
                rowspan_remaining[col_ptr] -= 1
                col_ptr += 1
            rowspan = int(td.get('rowspan', 1))
            if rowspan > 1:
                rowspan_remaining[col_ptr] = rowspan - 1
            for a in td.select('a.fc-day-grid-event'):
                div = a.find('div', class_='fc-content')
                if not div:
                    continue
                raw  = div.get('data-content', '')
                text = BeautifulSoup(
                    html_mod.unescape(raw), 'html.parser'
                ).get_text(' ', strip=True)
                time_tag = div.find('span', class_='fc-time')
                col_events.setdefault(col_ptr, []).append({
                    'time': time_tag.text.strip() if time_tag else '',
                    'info': text,
                })
            col_ptr += 1

    for col_i, date_str in col_dates.items():
        if not date_str:
            continue
        for e in col_events.get(col_i, []):
            b = _event_to_booking(date_str, e)
            if b:
                bookings.append(b)

    return bookings


def _duration_to_minutes(info: str) -> int:
    after_venue = re.split(r'Venues\s*-', info, flags=re.I)
    text = after_venue[-1] if len(after_venue) > 1 else info
    hours   = re.search(r'(\d+)\s*hour', text, re.I)
    minutes = re.search(r'(\d+)\s*min',  text, re.I)
    h = int(hours.group(1))   if hours   else 0
    m = int(minutes.group(1)) if minutes else 0
    return h * 60 + m


def _extract_court_name(info: str) -> str:
    m = re.search(r'Venues\s*-\s*(.+?)\s+\d+\s*hour', info, re.I)
    return m.group(1).strip() if m else 'Court'


def _parse_start_end(time_str: str, duration_minutes: int):
    time_str = time_str.strip()
    cleaned  = re.sub(r'([aApP])$', lambda x: x.group(1).upper() + 'M', time_str)
    for fmt in ('%I:%M%p', '%I:%M %p', '%I%p', '%I %p'):
        try:
            t_start = datetime.strptime(cleaned, fmt)
            t_end   = t_start + timedelta(minutes=duration_minutes)
            return t_start.strftime('%H:%M'), t_end.strftime('%H:%M')
        except ValueError:
            continue
    return None, None


def _event_to_booking(date_str: str, event: dict):
    try:
        info     = event['info']
        time_str = event['time']
        dur      = _duration_to_minutes(info)
        court    = _extract_court_name(info)
        start_24, end_24 = _parse_start_end(time_str, dur)
        return {
            'date':             datetime.strptime(date_str, '%Y-%m-%d').date(),
            'date_str':         date_str,
            'court_name':       court,
            'start_time':       time_str,
            'start_time_24':    start_24 or '',
            'end_time_24':      end_24   or '',
            'duration_minutes': dur,
            'suggested_cost':   suggest_cost(dur),
        }
    except Exception as e:
        logger.debug(f'Event parse error: {e} | {event}')
        return None


# ── Playwright navigation ───────────────────────────────────────────────────────

def _get_current_week_dates(page) -> list:
    return page.eval_on_selector_all(
        'th.fc-day-header',
        'els => els.map(e => e.getAttribute("data-date")).filter(Boolean)'
    )


def _navigate_to_date(page, target_date: str) -> bool:
    """Navigate FullCalendar until the week containing target_date is visible."""
    for _ in range(26):
        dates = _get_current_week_dates(page)
        if not dates:
            page.wait_for_timeout(1000)
            continue
        first, last = min(dates), max(dates)
        if first <= target_date <= last:
            return True
        btn = '.calendar-next' if last < target_date else '.calendar-prev'
        page.click(btn)
        page.wait_for_timeout(1500)
    return False


# ── Public API ──────────────────────────────────────────────────────────────────

def fetch_bookings(username: str, password: str,
                   debug_dump_path: Optional[str] = None,
                   target_dates: Optional[List[str]] = None,
                   **_kwargs) -> list:
    """
    Get cookies from the user's live Brave browser and scrape court bookings
    for the given session dates using headless Playwright.

    The user must be logged into royalbadminton.ezfacility.com in Brave.
    target_dates: list of 'YYYY-MM-DD' strings.
    """
    target_dates = sorted(set(target_dates or []))
    all_bookings = []

    # Step 1: get live cookies from Brave
    pw_cookies = get_brave_cookies()
    logger.info(f'Got {len(pw_cookies)} cookies from Brave')

    # Step 2: inject into headless Playwright and scrape
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/121.0.0.0 Safari/537.36'
            )
        )
        context.add_cookies(pw_cookies)
        page = context.new_page()

        # Verify session is valid
        page.goto(SCHEDULE_URL, wait_until='networkidle', timeout=30000)
        if '/login' in page.url.lower():
            browser.close()
            raise ValueError(
                'EZFacility session in Brave has expired. '
                'Please log into royalbadminton.ezfacility.com in Brave and try again.'
            )

        logger.info('Brave session verified — at schedule page')

        # Switch to week view
        try:
            page.click("[data-calendar-view='basicWeek']", timeout=3000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        if debug_dump_path:
            try:
                with open(debug_dump_path, 'w', encoding='utf-8') as f:
                    f.write(page.content())
                logger.info(f'Debug HTML dumped to {debug_dump_path}')
            except Exception as e:
                logger.warning(f'Could not write debug dump: {e}')

        # Scrape each target week
        scraped_weeks: set = set()
        for date_str in target_dates:
            if not _navigate_to_date(page, date_str):
                logger.warning(f'Could not navigate to week for {date_str}')
                continue

            week_dates = _get_current_week_dates(page)
            if not week_dates:
                continue
            week_key = (min(week_dates), max(week_dates))
            if week_key in scraped_weeks:
                continue
            scraped_weeks.add(week_key)

            page.wait_for_timeout(1200)
            source = page.content()

            week_bookings = _parse_week_source(source)
            matched = [b for b in week_bookings if b['date_str'] in target_dates]
            all_bookings.extend(matched)
            logger.info(f'Week {week_key}: {len(matched)} booking(s) for {date_str}')

        browser.close()

    # Deduplicate
    seen: set = set()
    unique = []
    for b in all_bookings:
        key = (b['date_str'], b['court_name'], b['start_time'])
        if key not in seen:
            seen.add(key)
            unique.append(b)

    return sorted(unique, key=lambda x: (x['date_str'], x['start_time']))
