#!/usr/bin/env python3
"""
Scrape court bookings from royalbadminton.ezfacility.com for specific dates.

Usage:
    python ezf_scrape.py --dates 2026-03-07,2026-03-14 --out /tmp/ezf_out.json

Credentials from env vars: RF_USERNAME, RF_PASSWORD
Remote browser: BROWSERLESS_URL (e.g. wss://production-sfo.browserless.io?token=TOKEN)
Outputs JSON list of court bookings to --out file.
"""
import sys, os, re, json, argparse, html as html_mod
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

LOGIN_URL    = "https://royalbadminton.ezfacility.com/login"
SCHEDULE_URL = "https://royalbadminton.ezfacility.com/MySchedule"

PRICE_MAP = {60: 45.0, 120: 75.0, 150: 90.0, 180: 105.0}
DEFAULT_RATE = 45.0


def suggest_cost(mins):
    if mins in PRICE_MAP:
        return PRICE_MAP[mins]
    return round(DEFAULT_RATE * mins / 60, 2)


def make_browser(playwright):
    browserless_url = os.environ.get("BROWSERLESS_URL", "").strip()
    if browserless_url:
        base = browserless_url.split('?')[0]
        has_token = 'token=' in browserless_url
        print(f"[DEBUG] BROWSERLESS_URL found. Base: {base} | Token present: {has_token}", flush=True)
        try:
            print(f"[DEBUG] Calling playwright.chromium.connect() ...", flush=True)
            browser = playwright.chromium.connect(browserless_url)
            print(f"[DEBUG] Connected! Browser version: {browser.version}", flush=True)
            return browser
        except Exception as e:
            print(f"[DEBUG] connect() failed: {type(e).__name__}: {e}", flush=True)
            raise
    else:
        print(f"[DEBUG] BROWSERLESS_URL not set — using local Chromium", flush=True)
        return playwright.chromium.launch(headless=bool(os.environ.get("RENDER")))


def login(page, username, password):
    page.goto(LOGIN_URL, timeout=30000)
    page.wait_for_load_state('networkidle', timeout=15000)

    # Debug: log all input fields found on the page
    inputs = page.query_selector_all("input")
    for inp in inputs:
        print(f"  input: name={inp.get_attribute('name')} type={inp.get_attribute('type')} id={inp.get_attribute('id')}", flush=True)

    # Fill username — try multiple selectors
    filled = False
    for sel in ["input[name='UserName']", "input[name='username']", "input[name='Email']",
                "input[type='email']", "input[id*='user' i]", "input[id*='email' i]"]:
        try:
            el = page.query_selector(sel)
            if el:
                el.fill(username)
                filled = True
                print(f"  Filled username with selector: {sel}", flush=True)
                break
        except Exception:
            continue

    if not filled:
        print("  WARNING: Could not find username field", flush=True)

    page.fill("input[type='password']", password)

    # Click submit and wait for navigation
    for sel in ["button[type='submit']", "input[type='submit']", "button:has-text('Login')",
                "button:has-text('Sign in')", "button:has-text('Log in')"]:
        try:
            el = page.query_selector(sel)
            if el:
                print(f"  Clicking submit: {sel}", flush=True)
                with page.expect_navigation(timeout=30000):
                    el.click()
                break
        except Exception as e:
            print(f"  Submit {sel} failed: {e}", flush=True)
            continue

    print(f"Logged in → {page.url}", flush=True)


def get_week_dates(page):
    headers = page.query_selector_all("th.fc-day-header")
    return [h.get_attribute("data-date") for h in headers if h.get_attribute("data-date")]


def navigate_to_date(page, target_date):
    for _ in range(30):
        dates = get_week_dates(page)
        if not dates:
            page.wait_for_timeout(1000)
            continue
        first, last = min(dates), max(dates)
        if first <= target_date <= last:
            return True
        btn = ".calendar-next" if last < target_date else ".calendar-prev"
        page.click(btn)
        page.wait_for_timeout(1800)
    return False


def duration_to_minutes(info):
    after_venue = re.split(r'Venues\s*-', info, flags=re.I)
    text = after_venue[-1] if len(after_venue) > 1 else info
    h = re.search(r'(\d+)\s*hour', text, re.I)
    m = re.search(r'(\d+)\s*min',  text, re.I)
    return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)


def parse_week(page_source, target_dates_set):
    soup = BeautifulSoup(page_source, "html.parser")
    headers = soup.select("th.fc-day-header")
    col_dates = {i: th.get("data-date", "") for i, th in enumerate(headers) if th.get("data-date")}

    tbody = soup.select_one(".fc-content-skeleton table tbody")
    if not tbody:
        return {}

    col_events = {i: [] for i in col_dates}
    rowspan_remaining = {}

    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        col_ptr = 0
        for td in tds:
            while rowspan_remaining.get(col_ptr, 0) > 0:
                rowspan_remaining[col_ptr] -= 1
                col_ptr += 1
            rowspan = int(td.get("rowspan", 1))
            if rowspan > 1:
                rowspan_remaining[col_ptr] = rowspan - 1
            for a in td.select("a.fc-day-grid-event"):
                div = a.find("div", class_="fc-content")
                if not div:
                    continue
                raw  = div.get("data-content", "")
                text = BeautifulSoup(html_mod.unescape(raw), "html.parser").get_text(" ", strip=True)
                time_tag = div.find("span", class_="fc-time")
                col_events.setdefault(col_ptr, []).append({
                    "time": time_tag.text.strip() if time_tag else "",
                    "info": text,
                })
            col_ptr += 1

    result = {}
    for col_i, date_str in col_dates.items():
        if date_str not in target_dates_set:
            continue
        for e in col_events.get(col_i, []):
            court_m = re.search(r'Venues\s*-\s*(.+?)\s+\d+\s*hour', e["info"], re.I)
            court   = court_m.group(1).strip() if court_m else "Court"
            dur     = duration_to_minutes(e["info"])

            time_str = e["time"].strip()
            cleaned  = re.sub(r'([aApP])$', lambda x: x.group(1).upper() + 'M', time_str)
            start_24 = end_24 = ""
            for fmt in ('%I:%M%p', '%I:%M %p', '%I%p', '%I %p'):
                try:
                    t = datetime.strptime(cleaned, fmt)
                    end_t = t + timedelta(minutes=dur)
                    start_24 = t.strftime('%H:%M')
                    end_24   = end_t.strftime('%H:%M')
                    break
                except ValueError:
                    continue

            if date_str not in result:
                result[date_str] = []
            result[date_str].append({
                "court_name":       court,
                "start_time":       time_str,
                "start_time_24":    start_24,
                "end_time_24":      end_24,
                "duration_minutes": dur,
                "suggested_cost":   suggest_cost(dur),
            })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", required=True, help="Comma-separated YYYY-MM-DD dates")
    parser.add_argument("--out",   required=True, help="Output JSON file path")
    args = parser.parse_args()

    target_dates = sorted(set(d.strip() for d in args.dates.split(",") if d.strip()))
    username = os.environ.get("RF_USERNAME", "")
    password = os.environ.get("RF_PASSWORD", "")
    if not username or not password:
        print("ERROR: RF_USERNAME and RF_PASSWORD env vars required", file=sys.stderr)
        sys.exit(1)

    print(f"Scraping {len(target_dates)} date(s): {', '.join(target_dates)}", flush=True)

    all_bookings = []

    with sync_playwright() as p:
        print(f"[DEBUG] Starting Playwright ...", flush=True)
        browser = make_browser(p)
        try:
            print(f"[DEBUG] Opening new page ...", flush=True)
            page = browser.new_page()
            print(f"[DEBUG] Page opened. Starting login ...", flush=True)
            login(page, username, password)

            print(f"[DEBUG] Navigating to schedule: {SCHEDULE_URL}", flush=True)
            page.goto(SCHEDULE_URL)
            page.wait_for_timeout(3000)

            try:
                page.click("[data-calendar-view='basicWeek']", timeout=3000)
                page.wait_for_timeout(2000)
            except Exception:
                pass

            scraped_weeks = set()
            for date_str in target_dates:
                if not navigate_to_date(page, date_str):
                    print(f"  Could not navigate to {date_str}", flush=True)
                    continue

                dates_in_week = get_week_dates(page)
                if not dates_in_week:
                    continue
                week_key = (min(dates_in_week), max(dates_in_week))
                if week_key in scraped_weeks:
                    continue
                scraped_weeks.add(week_key)

                page.wait_for_timeout(1200)
                result = parse_week(page.content(), set(target_dates))
                for date, courts in result.items():
                    for c in courts:
                        all_bookings.append({"date": date, **c})
                print(f"  Week {week_key}: {sum(len(v) for v in result.values())} court(s)", flush=True)

        finally:
            browser.close()

    # Deduplicate
    seen = set()
    unique = []
    for b in all_bookings:
        key = (b["date"], b["court_name"], b["start_time"])
        if key not in seen:
            seen.add(key)
            unique.append(b)

    unique.sort(key=lambda x: (x["date"], x["start_time_24"]))

    with open(args.out, "w") as f:
        json.dump(unique, f, indent=2)

    print(f"Done. {len(unique)} booking(s) written to {args.out}", flush=True)


if __name__ == "__main__":
    main()
