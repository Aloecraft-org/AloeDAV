"""
HTML rendering for the browser view.

Plain string templating with no engine and no build step, because the page is
a window onto the store rather than a product surface. Everything
caller-supplied goes through `esc` -- calendar data is written by other people's
clients, so a SUMMARY is untrusted input like any other.
"""
from datetime import datetime
from html import escape as _escape

from aloedav.model.m00_datetime import DateTimeKind

STYLE = """
:root {
  --bg: #fbfaf8; --fg: #23201c; --muted: #6b665e; --line: #e5e0d8;
  --card: #ffffff; --accent: #3a6b4f; --accent-soft: #eaf2ec; --warn: #8a5a2b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16181a; --fg: #e6e3de; --muted: #9b968d; --line: #2b2e31;
    --card: #1d2022; --accent: #7fb894; --accent-soft: #1f2c25; --warn: #c99a63;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 940px; margin: 0 auto; padding: 28px 20px 64px; }
header.top { border-bottom: 1px solid var(--line); margin-bottom: 24px; padding-bottom: 14px; }
header.top h1 { font-size: 20px; margin: 0 0 4px; letter-spacing: -0.01em; }
.crumb { color: var(--muted); font-size: 13px; }
.crumb a { color: var(--muted); }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 14px 16px;
}
.card h3 { margin: 0 0 4px; font-size: 15px; }
.card .meta { color: var(--muted); font-size: 12.5px; }
.day { margin: 22px 0 8px; font-size: 13px; font-weight: 600; color: var(--muted);
       text-transform: uppercase; letter-spacing: 0.06em; }
.event {
  display: flex; gap: 14px; align-items: baseline;
  background: var(--card); border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: 8px; padding: 10px 14px; margin-bottom: 6px;
}
.event .when { font-variant-numeric: tabular-nums; color: var(--muted);
               font-size: 13px; min-width: 108px; }
.event .what { flex: 1; }
.event .what .sub { color: var(--muted); font-size: 12.5px; }
.tag { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 20px;
       background: var(--accent-soft); color: var(--accent); margin-left: 6px;
       vertical-align: 1px; }
.tag.warn { background: transparent; color: var(--warn); border: 1px solid var(--warn); }
.nav { display: flex; gap: 10px; align-items: center; margin: 18px 0; font-size: 14px; }
.nav .spacer { flex: 1; }
.empty { color: var(--muted); padding: 30px 0; }
pre.raw {
  background: var(--card); border: 1px solid var(--line); border-radius: 8px;
  padding: 14px; overflow-x: auto; font-size: 12.5px; line-height: 1.5;
  white-space: pre; color: var(--fg);
}
table.props { border-collapse: collapse; width: 100%; font-size: 13.5px; margin-bottom: 20px; }
table.props th { text-align: left; color: var(--muted); font-weight: 500;
                 padding: 5px 14px 5px 0; vertical-align: top; white-space: nowrap; }
table.props td { padding: 5px 0; }
"""


def esc(value) -> str:
    return _escape("" if value is None else str(value))


def page(title: str, body: str, crumbs: list = None) -> str:
    trail = ""
    if crumbs:
        parts = [f'<a href="{esc(href)}">{esc(label)}</a>' if href else esc(label)
                 for label, href in crumbs]
        trail = f'<div class="crumb">{" / ".join(parts)}</div>'
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(title)}</title><style>{STYLE}</style></head><body>"
            f'<div class="wrap"><header class="top"><h1>{esc(title)}</h1>{trail}</header>'
            f"{body}</div></body></html>")


def user_list(users: list) -> str:
    if not users:
        return ('<p class="empty">No users yet. Create a collection to get started '
                "&mdash; see <code>aloedav.storage.file_store</code>.</p>")
    cards = "".join(
        f'<a class="card" href="/{esc(u)}/"><h3>{esc(u)}</h3>'
        f'<div class="meta">collections</div></a>' for u in users)
    return f'<div class="grid">{cards}</div>'


def collection_list(user: str, collections: list) -> str:
    if not collections:
        return f'<p class="empty">{esc(user)} has no collections.</p>'
    cards = []
    for info in collections:
        count = f"{info.resource_count} resource" + ("" if info.resource_count == 1 else "s")
        cards.append(
            f'<a class="card" href="/{esc(user)}/{esc(info.collection_id)}/">'
            f"<h3>{esc(info.displayname or info.collection_id)}</h3>"
            f'<div class="meta">{esc(info.collection_type.value)} &middot; {count}</div>'
            f"</a>")
    return f'<div class="grid">{"".join(cards)}</div>'


def _clock(value) -> str:
    """A start time, or the all-day marker when the value has no time of day."""
    if value.kind is DateTimeKind.DATE:
        return "all day"
    stamp = value.value.strftime("%H:%M")
    if value.kind is DateTimeKind.ZONED:
        return f"{stamp} {esc(value.tzid.split('/')[-1].replace('_', ' '))}"
    if value.kind is DateTimeKind.FLOATING:
        return f"{stamp} (floating)"
    return f"{stamp}Z"


def agenda(user: str, collection_id: str, occurrences: list,
           window_start: datetime, window_end: datetime,
           previous: str, following: str) -> str:
    base = f"/{esc(user)}/{esc(collection_id)}/"
    nav = (f'<div class="nav">'
           f'<a href="{base}?start={esc(previous)}">&larr; earlier</a>'
           f'<span class="spacer"></span>'
           f'<span class="crumb">{window_start:%d %b %Y} &ndash; {window_end:%d %b %Y}</span>'
           f'<span class="spacer"></span>'
           f'<a href="{base}?start={esc(following)}">later &rarr;</a></div>')

    if not occurrences:
        return nav + '<p class="empty">Nothing scheduled in this window.</p>'

    blocks, current_day = [], None
    for occurrence in occurrences:
        day = occurrence.start.value.date()
        if day != current_day:
            current_day = day
            blocks.append(f'<div class="day">{day:%A %d %B %Y}</div>')

        tags = ""
        if occurrence.is_override:
            tags += '<span class="tag">moved</span>'
        elif occurrence.recurrence_id is not None:
            tags += '<span class="tag">repeats</span>'
        if occurrence.start.kind is DateTimeKind.ZONED and not occurrence.start.is_resolvable:
            tags += '<span class="tag warn">unresolved zone</span>'

        name = occurrence.stored_name or ""
        link = (f'/{esc(user)}/{esc(collection_id)}/{esc(name)}' if name else "")
        title = esc(occurrence.summary or "(no summary)")
        title = f'<a href="{link}">{title}</a>' if link else title
        sub = esc(getattr(occurrence.component, "location", "") or "")
        blocks.append(
            f'<div class="event"><div class="when">{_clock(occurrence.start)}</div>'
            f'<div class="what">{title}{tags}'
            + (f'<div class="sub">{sub}</div>' if sub else "")
            + "</div></div>")
    return nav + "".join(blocks)


def card_list(user: str, collection_id: str, resources: list) -> str:
    if not resources:
        return '<p class="empty">No contacts in this address book.</p>'
    rows = []
    for resource in sorted(resources, key=lambda r: (r.card.full_name or "").lower()):
        card = resource.card
        detail = esc((card.emails[0] if card.emails else "") or "")
        rows.append(
            f'<a class="card" href="/{esc(user)}/{esc(collection_id)}/{esc(resource.stored_name)}">'
            f"<h3>{esc(card.full_name or '(unnamed)')}</h3>"
            f'<div class="meta">{detail or "&nbsp;"}</div></a>')
    return f'<div class="grid">{"".join(rows)}</div>'


def resource_detail(resource, occurrences: list) -> str:
    rows = []

    def add(label, value):
        if value not in (None, "", []):
            rows.append(f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>")

    add("Stored as", resource.stored_name)
    add("ETag", resource.etag)
    add("Content-Type", resource.content_type)
    for item in resource.items():
        add("UID", item.uid)
        add("Summary", getattr(item, "summary", None))

    listing = ""
    if occurrences:
        shown = "".join(
            f'<div class="event"><div class="when">{_clock(o.start)}</div>'
            f'<div class="what">{o.start.value:%d %b %Y}'
            + ('<span class="tag">moved</span>' if o.is_override else "")
            + "</div></div>"
            for o in occurrences[:25])
        listing = f'<div class="day">Next occurrences</div>{shown}'

    body = resource.raw_contents or resource.to_webdav_string()
    return (f'<table class="props">{"".join(rows)}</table>{listing}'
            f'<div class="day">Stored bytes</div><pre class="raw">{esc(body)}</pre>')
