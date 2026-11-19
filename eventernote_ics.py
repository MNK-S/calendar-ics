#!/usr/bin/env python3
"""Build an iCalendar (.ics) feed from Eventernote actor pages.

Data source: https://www.eventernote.com/actors/<id>/events
  - sorted by date descending, 20 entries per page
  - each entry: date, title, venue, optional 開場/開演/終演, performers

Groups (unit -> members, with optional character names) live in groups.json.

Usage:
  python eventernote_ics.py                 # normal run
  python eventernote_ics.py --no-details    # skip official-link fetching
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from lxml import html as lxml_html

BASE = "https://www.eventernote.com"
JST = ZoneInfo("Asia/Tokyo")
BJT = ZoneInfo("Asia/Shanghai")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 eventernote-ics/1.0"
)

# (label, actor id) — label is only used for log output.
ACTORS: list[tuple[str, str]] = [
    ("渡瀬結月", "55045"),
    ("川村玲奈", "77840"),
    ("学園アイドルマスター", "77694"),
]

CALENDAR_NAME = "推し活"
CALENDAR_DESC = "Eventernote 艺人日程（自动生成）"
DEFAULT_DURATION = timedelta(hours=2)
MAX_PAGES = 5
REQUEST_DELAY = 0.8  # seconds between HTTP requests

ROOT = Path(__file__).resolve().parent
FEED_PATH = ROOT / "feed.ics"
CACHE_PATH = ROOT / "links_cache.json"
GROUPS_PATH = ROOT / "groups.json"
TIMEZONES_PATH = ROOT / "timezones.json"
PLACES_CACHE_PATH = ROOT / "places_cache.json"
TARGETS_PATH = ROOT / "targets.json"


@dataclass
class Event:
    id: str
    title: str
    day: date
    url: str
    venue: str = ""
    open_time: dtime | None = None
    start_time: dtime | None = None
    end_time: dtime | None = None
    place_id: str = ""
    tz_name: str = "Asia/Tokyo"
    tz_note: str = ""
    performers: list[str] = field(default_factory=list)
    official_links: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- HTTP

_ssl_ctx: ssl.SSLContext | None = None


def _context() -> ssl.SSLContext:
    global _ssl_ctx
    if _ssl_ctx is None:
        if os.environ.get("EVENTERNOTE_INSECURE") == "1":
            # Local debugging only (TLS-intercepting sandbox). Never set this in CI.
            _ssl_ctx = ssl._create_unverified_context()
        else:
            _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx


def http_get(url: str, *, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "ja,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            with urllib.request.urlopen(req, timeout=30, context=_context()) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"GET failed: {url}: {last_error}")


# ---------------------------------------------------------------- parsing

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_EVENT_ID_RE = re.compile(r"/events/(\d+)")
_PLACE_ID_RE = re.compile(r"/places/(\d+)")
_TIME_RE = {key: re.compile(key + r"\s*(\d{1,2}):(\d{2})") for key in ("開場", "開演", "終演")}


def _parse_clock(text: str, key: str) -> dtime | None:
    match = _TIME_RE[key].search(text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return dtime(hour, minute)


def _text(node: lxml_html.HtmlElement) -> str:
    return " ".join(node.text_content().split())


def parse_actor_page(page: str) -> list[Event]:
    tree = lxml_html.fromstring(page)
    events: list[Event] = []

    for item in tree.xpath('//div[contains(@class,"gb_event_list")]/ul/li'):
        date_nodes = item.xpath('.//div[@class="date"]/p[1]')
        title_nodes = item.xpath('.//div[@class="event"]/h4/a')
        if not date_nodes or not title_nodes:
            continue

        date_match = _DATE_RE.search(_text(date_nodes[0]))
        id_match = _EVENT_ID_RE.search(title_nodes[0].get("href", ""))
        if not date_match or not id_match:
            continue

        year, month, day = (int(x) for x in date_match.groups())
        try:
            event_day = date(year, month, day)
        except ValueError:
            continue

        venue_nodes = item.xpath('.//div[@class="event"]/div[@class="place"][a]//a/text()')
        venue = venue_nodes[0].strip() if venue_nodes else ""

        place_nodes = item.xpath('.//div[@class="event"]/div[@class="place"][a]/a/@href')
        place_id = ""
        if place_nodes:
            place_match = _PLACE_ID_RE.search(place_nodes[0])
            place_id = place_match.group(1) if place_match else ""

        time_nodes = item.xpath('.//div[@class="event"]/div[@class="place"][span]//span/text()')
        time_text = time_nodes[0] if time_nodes else ""

        performers = [
            t.strip()
            for t in item.xpath('.//div[@class="event"]/div[@class="actor"]//li/a/text()')
            if t.strip()
        ]

        events.append(
            Event(
                id=id_match.group(1),
                title=_text(title_nodes[0]),
                day=event_day,
                url=f"{BASE}/events/{id_match.group(1)}",
                venue=venue,
                open_time=_parse_clock(time_text, "開場"),
                start_time=_parse_clock(time_text, "開演"),
                end_time=_parse_clock(time_text, "終演"),
                place_id=place_id,
                performers=performers,
            )
        )

    return events


def collect_actor(actor_label: str, actor_id: str, today: date) -> list[Event]:
    collected: list[Event] = []
    for page_no in range(1, MAX_PAGES + 1):
        url = f"{BASE}/actors/{actor_id}/events?actor_id={actor_id}&limit=20&page={page_no}"
        events = parse_actor_page(http_get(url))
        if not events:
            if page_no == 1:
                raise RuntimeError(f"no events parsed for {actor_label} ({actor_id}); page layout changed?")
            break
        collected.extend(events)
        if min(e.day for e in events) < today:
            break
        time.sleep(REQUEST_DELAY)

    upcoming = [e for e in collected if e.day >= today]
    print(f"  {actor_label}: {len(collected)} parsed, {len(upcoming)} upcoming")
    return upcoming


def fetch_official_links(event_id: str) -> list[str]:
    page = http_get(f"{BASE}/events/{event_id}")
    tree = lxml_html.fromstring(page)
    links = tree.xpath('//td[normalize-space(.)="関連リンク"]/following-sibling::td[1]//a/@href')
    cleaned: list[str] = []
    for link in links:
        link = link.strip()
        if not link.startswith("http"):
            continue
        if "eventernote.com" in link or "twitter.com" in link:
            continue
        if link not in cleaned:
            cleaned.append(link)
    return cleaned[:2]


# ---------------------------------------------------------------- timezones

def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fetch_place_info(place_id: str) -> dict:
    page = http_get(f"{BASE}/places/{place_id}")
    tree = lxml_html.fromstring(page)
    nodes = tree.xpath('//td[normalize-space(.)="所在地"]/following-sibling::td[1]//text()')
    address = " ".join(" ".join(nodes).split())
    return {"address": address, "overseas": "海外の会場一覧" in page}


def resolve_timezone(event: Event, table: dict, cache: dict) -> None:
    """Fill event.tz_name from timezones.json / the venue page address."""
    if not event.place_id:
        return

    venues = table.get("venues", {})
    if event.place_id in venues:
        event.tz_name = venues[event.place_id]
        return

    info = cache.get(event.place_id)
    if info is None:
        try:
            info = fetch_place_info(event.place_id)
        except Exception as exc:  # noqa: BLE001 - best effort
            print(f"  ! place failed for {event.place_id}: {exc}", file=sys.stderr)
            info = {"address": "", "overseas": False}
        cache[event.place_id] = info
        time.sleep(REQUEST_DELAY)

    if not info.get("overseas"):
        event.tz_name = "Asia/Tokyo"
        return

    haystack = f"{info.get('address', '')} {event.title}".lower()

    for city, tz in table.get("cities", {}).items():
        if city.lower() in haystack:
            event.tz_name = tz
            return

    address = info.get("address", "")
    state_match = re.search(r"\b([A-Z]{2})\s+\d{5}", address)
    if state_match:
        tz = table.get("us_states", {}).get(state_match.group(1))
        if tz:
            event.tz_name = tz
            return

    for country, tz in table.get("countries", {}).items():
        if country.lower() in haystack:
            event.tz_name = tz
            return

    event.tz_name = "Asia/Tokyo"
    event.tz_note = "时区未识别（按 JST 写入）"


# ---------------------------------------------------------------- groups

def norm_name(value: str) -> str:
    return re.sub(r"\s+", "", value)


# Umbrella entries (a whole work). When a smaller unit of the same work is also
# listed for one event, only the unit is rendered — "有小团就不写大团".
OVERALL_GROUPS: set[str] = {
    norm_name("アイドルマスターシャイニーカラーズ"),
    norm_name("アイドルマスターSideM"),
}


def load_targets() -> list[tuple[str, str]]:
    """targets.json is the editable watchlist; ACTORS is the fallback."""
    if TARGETS_PATH.exists():
        try:
            data = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
            targets = [(str(item["name"]), str(item["id"])) for item in data]
            if targets:
                return targets
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return ACTORS


def load_groups() -> list[dict]:
    raw = json.loads(GROUPS_PATH.read_text(encoding="utf-8"))
    groups: list[dict] = []
    for name, members in raw.items():
        entries = []
        for item in members:
            if isinstance(item, str):
                cv, char = item, None
            else:
                cv = item[0]
                char = item[1] if len(item) > 1 and item[1] else None
            entries.append({"cv": cv, "char": char})
        groups.append({"name": name, "key": norm_name(name), "members": entries})
    return groups


def _render_group(group: dict, present: set[str], originals: dict[str, str]) -> str:
    shown: list[str] = []

    for member in group["members"]:
        cv_key = norm_name(member["cv"])
        char_key = norm_name(member["char"]) if member["char"] else None
        cv_in = cv_key in present
        char_in = bool(char_key and char_key in present)
        if not cv_in and not char_in:
            continue

        if char_in and cv_in:
            display = f"{member['char']}/{member['cv']}"
        elif char_in:
            display = member["char"]
        else:
            display = originals.get(cv_key, member["cv"])
        shown.append(display)

    if not shown:
        return f"・{group['name']}"
    return f"・{group['name']}（" + "、".join(shown) + "）"


def build_performer_lines(performers: list[str], groups: list[dict]) -> list[str]:
    if not performers:
        return []

    originals: dict[str, str] = {}
    for name in performers:
        key = norm_name(name)
        if key not in originals:
            originals[key] = name

    present = set(originals)
    present_groups = [g for g in groups if g["key"] in present]

    # 有小团就不写大团：总条目和小队同时出现时只保留小队。
    suppressed: set[str] = set()
    if len(present_groups) > 1:
        units = [g for g in present_groups if g["key"] not in OVERALL_GROUPS]
        if units:
            suppressed = {g["key"] for g in present_groups if g["key"] in OVERALL_GROUPS}
            present_groups = units

    member_keys: set[str] = set()
    for group in present_groups:
        for member in group["members"]:
            member_keys.add(norm_name(member["cv"]))
            if member["char"]:
                member_keys.add(norm_name(member["char"]))

    lines: list[str] = []
    emitted_groups: set[str] = set()
    for name in performers:
        key = norm_name(name)
        for group in present_groups:
            if group["key"] == key and key not in emitted_groups:
                emitted_groups.add(key)
                lines.append(_render_group(group, present, originals))

    individuals: list[str] = []
    for name in performers:
        key = norm_name(name)
        if key in member_keys or key in emitted_groups or key in suppressed:
            continue
        if name not in individuals:
            individuals.append(name)
    if individuals:
        lines.append("・" + "、".join(individuals))

    return lines


# ---------------------------------------------------------------- ics helpers

def ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Fold a content line to 75 octets per RFC 5545 (UTF-8 safe)."""
    if len(line.encode("utf-8")) <= 75:
        return line
    chunks: list[str] = []
    current = bytearray()
    limit = 75
    for char in line:
        raw = char.encode("utf-8")
        if len(current) + len(raw) > limit:
            chunks.append(current.decode("utf-8"))
            current = bytearray()
            limit = 74  # continuation lines start with a space
        current.extend(raw)
    if current:
        chunks.append(current.decode("utf-8"))
    return "\r\n ".join(chunks)


def _fmt_time(day: date, clock: dtime, tz_name: str) -> str:
    if tz_name != "Asia/Tokyo":
        return f"当地{clock.strftime('%H:%M')}"
    moment = datetime.combine(day, clock, tzinfo=JST).astimezone(BJT)
    prefix = "前日" if moment.date() != day else ""
    return f"J{clock.strftime('%H:%M')}（B{prefix}{moment.strftime('%H:%M')}）"


def build_description(event: Event, groups: list[dict]) -> str:
    lines: list[str] = []
    if event.start_time:
        if event.open_time:
            lines.append(f"开场 {_fmt_time(event.day, event.open_time, event.tz_name)}")
        lines.append(f"开演 {_fmt_time(event.day, event.start_time, event.tz_name)}")
        if event.end_time:
            lines.append(f"终演 {_fmt_time(event.day, event.end_time, event.tz_name)}")
    else:
        lines.append("时间未定（eventernote 未收录）")
        if event.open_time:
            lines.append(f"开场 {_fmt_time(event.day, event.open_time, event.tz_name)}")

    if event.tz_note:
        lines.append(event.tz_note)

    performer_lines = build_performer_lines(event.performers, groups)
    if performer_lines:
        lines.append("出演：")
        lines.extend(performer_lines)

    lines.append("")
    lines.append("")
    links = list(event.official_links) + [event.url]
    for index, link in enumerate(links):
        if index:
            lines.append("")
        lines.append(link)
    return "\n".join(lines)


def build_ics(events: list[Event], groups: list[dict], generated_at: datetime) -> str:
    stamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//eventernote-ics//JA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(CALENDAR_NAME)}",
        "X-WR-TIMEZONE:Asia/Tokyo",
        f"X-WR-CALDESC:{ics_escape(CALENDAR_DESC)}",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Tokyo",
        "X-LIC-LOCATION:Asia/Tokyo",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:JST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for event in events:
        out.append("BEGIN:VEVENT")
        out.append(f"UID:eventernote-{event.id}@eventernote-ics")
        out.append(f"DTSTAMP:{stamp}")

        if event.start_time:
            tzinfo = ZoneInfo(event.tz_name)
            start = datetime.combine(event.day, event.start_time, tzinfo=tzinfo)
            if event.end_time:
                end = datetime.combine(event.day, event.end_time, tzinfo=tzinfo)
                if end <= start:
                    end += timedelta(days=1)
            else:
                end = start + DEFAULT_DURATION
            out.append(f"DTSTART;TZID={event.tz_name}:{start.strftime('%Y%m%dT%H%M%S')}")
            out.append(f"DTEND;TZID={event.tz_name}:{end.strftime('%Y%m%dT%H%M%S')}")
        else:
            out.append(f"DTSTART;VALUE=DATE:{event.day.strftime('%Y%m%d')}")
            out.append(f"DTEND;VALUE=DATE:{(event.day + timedelta(days=1)).strftime('%Y%m%d')}")

        out.append(f"SUMMARY:{ics_escape(event.title)}")
        if event.venue:
            out.append(f"LOCATION:{ics_escape(event.venue)}")
        out.append(f"URL:{event.url}")
        out.append(f"DESCRIPTION:{ics_escape(build_description(event, groups))}")
        out.append("STATUS:CONFIRMED")
        out.append("TRANSP:OPAQUE")
        out.append("END:VEVENT")

    out.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in out) + "\r\n"


# ---------------------------------------------------------------- main

def load_cache() -> dict[str, list[str]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return {str(k): list(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(cache: dict[str, list[str]]) -> None:
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-details", action="store_true", help="skip official link fetching")
    args = parser.parse_args()

    now = datetime.now(JST)
    today = now.date()
    groups = load_groups()
    targets = load_targets()
    print(f"Building feed for {today.isoformat()} (JST), {len(groups)} groups, {len(targets)} targets")

    merged: dict[str, Event] = {}
    for label, actor_id in targets:
        for event in collect_actor(label, actor_id, today):
            existing = merged.get(event.id)
            if existing:
                for name in event.performers:
                    if name not in existing.performers:
                        existing.performers.append(name)
                existing.official_links = existing.official_links or event.official_links
            else:
                merged[event.id] = event

    events = sorted(merged.values(), key=lambda e: (e.day, e.start_time or dtime(0, 0)))
    print(f"Merged: {len(events)} unique events")

    tz_table = load_json(TIMEZONES_PATH, {})
    places_cache = load_json(PLACES_CACHE_PATH, {})
    for event in events:
        resolve_timezone(event, tz_table, places_cache)
    save_json(PLACES_CACHE_PATH, places_cache)
    non_jst = sum(1 for e in events if e.tz_name != "Asia/Tokyo")
    print(f"Timezones: {len(places_cache)} venues cached, {non_jst} non-JST events")

    if not args.no_details:
        cache = load_cache()
        fetched = 0
        for event in events:
            if event.id in cache:
                event.official_links = cache[event.id]
                continue
            try:
                links = fetch_official_links(event.id)
            except Exception as exc:  # noqa: BLE001 - detail pages are best-effort
                print(f"  ! detail failed for {event.id}: {exc}", file=sys.stderr)
                links = []
            event.official_links = links
            cache[event.id] = links
            fetched += 1
            time.sleep(REQUEST_DELAY)
        save_cache(cache)
        print(f"Official links: {len(cache)} cached, {fetched} fetched now")

    FEED_PATH.write_text(build_ics(events, groups, now), encoding="utf-8", newline="")

    missing_time = sum(1 for e in events if not e.start_time)
    missing_venue = sum(1 for e in events if not e.venue)
    print(f"Wrote {FEED_PATH.name}: {len(events)} events, {missing_time} without time, {missing_venue} without venue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
