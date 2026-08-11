"""Generate a static, full-screen TV dashboard (support_tv.html) from the
Help Scout conversation export. Pure stdlib + the CSV already produced by
export_helpscout.py - no server, no extra dependencies.
"""

import csv
import html
import statistics
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CSV_FILE = "helpscout_conversations_last_30_days.csv"
OUTPUT_FILE = "support_tv.html"

# Only this mailbox counts toward the TV metrics - the general Ahoy inbox is excluded.
SUPPORT_MAILBOX = "BRNKL Support"

LOCAL_TZ = ZoneInfo("America/Vancouver")
OPEN_STATUSES = {"active", "pending"}

TOP_ISSUES_N = 5
OLDEST_CASES_N = 5
CLOSED_TODAY_N = 5
SUBJECT_MAX_LEN = 46

STALE_WARN_MINUTES = 30
STALE_CRITICAL_MINUTES = 120

DEVICE_TAGS = [("5g", "5G"), ("blue", "Blue"), ("black", "Black")]


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_local(dt):
    return dt.astimezone(LOCAL_TZ) if dt else None


def tag_values(tags, prefix):
    return [t.strip()[len(prefix) + 1:] for t in tags if t.strip().startswith(prefix + "-")]


def humanize(tag_value):
    return " ".join(w.capitalize() for w in tag_value.replace("-", " ").split(" "))


def truncate(text, max_len=SUBJECT_MAX_LEN):
    text = text or "(no subject)"
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def format_duration(total_seconds):
    if total_seconds is None or total_seconds < 0:
        return "—"
    total_seconds = int(total_seconds)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m" if minutes else "<1m"


def load_rows():
    try:
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            raw_rows = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"Error: {CSV_FILE} not found. Run export_helpscout.py first.")
        sys.exit(1)

    rows = []
    for r in raw_rows:
        if r.get("mailbox") != SUPPORT_MAILBOX:
            continue
        tags = [t.strip() for t in r["tags"].split(",")] if r.get("tags", "").strip() else []
        created = parse_iso(r.get("created_at"))
        closed = parse_iso(r.get("closed_at"))
        rows.append({
            "number": r.get("conversation_number"),
            "status": r.get("status"),
            "subject": r.get("subject") or "",
            "tags": tags,
            "created_at": created,
            "created_local": to_local(created),
            "closed_at": closed,
            "closed_local": to_local(closed),
        })
    return rows


def device_label(tags):
    values = set(tag_values(tags, "product"))
    for key, label in DEVICE_TAGS:
        if key in values:
            return label
    return "—"


def compute_metrics(rows, now_utc):
    now_local = to_local(now_utc)
    today = now_local.date()
    yesterday = today.fromordinal(today.toordinal() - 1)

    open_rows = [r for r in rows if r["status"] in OPEN_STATUSES]
    active_count = sum(1 for r in open_rows if r["status"] == "active")
    pending_count = sum(1 for r in open_rows if r["status"] == "pending")

    new_today = [r for r in rows if r["created_local"] and r["created_local"].date() == today]
    new_yesterday = [r for r in rows if r["created_local"] and r["created_local"].date() == yesterday]

    closed_today = [r for r in rows if r["closed_local"] and r["closed_local"].date() == today]
    closed_yesterday = [r for r in rows if r["closed_local"] and r["closed_local"].date() == yesterday]

    close_durations = [
        (r["closed_at"] - r["created_at"]).total_seconds()
        for r in closed_today
        if r["created_at"] and r["closed_at"]
    ]
    avg_close = statistics.mean(close_durations) if close_durations else None
    median_close = statistics.median(close_durations) if close_durations else None

    issue_counts = {}
    for r in open_rows:
        for v in tag_values(r["tags"], "issue"):
            label = humanize(v)
            issue_counts[label] = issue_counts.get(label, 0) + 1
    top_issues = sorted(issue_counts.items(), key=lambda kv: kv[1], reverse=True)[:TOP_ISSUES_N]

    device_counts = {label: 0 for _, label in DEVICE_TAGS}
    other_device_count = 0
    for r in open_rows:
        values = set(tag_values(r["tags"], "product"))
        matched = False
        for key, label in DEVICE_TAGS:
            if key in values:
                device_counts[label] += 1
                matched = True
        if not matched:
            other_device_count += 1

    oldest_open = sorted(
        (r for r in open_rows if r["created_at"]), key=lambda r: r["created_at"]
    )[:OLDEST_CASES_N]
    oldest_open_view = [
        {
            "number": r["number"],
            "age_seconds": (now_utc - r["created_at"]).total_seconds(),
            "subject": truncate(r["subject"]),
            "device": device_label(r["tags"]),
        }
        for r in oldest_open
    ]

    closed_today_sorted = sorted(
        (r for r in closed_today if r["closed_at"]), key=lambda r: r["closed_at"], reverse=True
    )[:CLOSED_TODAY_N]
    closed_today_view = [
        {
            "number": r["number"],
            "subject": truncate(r["subject"]),
            "duration_seconds": (r["closed_at"] - r["created_at"]).total_seconds() if r["created_at"] else None,
        }
        for r in closed_today_sorted
    ]

    return {
        "now_local": now_local,
        "open_total": len(open_rows),
        "active_count": active_count,
        "pending_count": pending_count,
        "new_today_count": len(new_today),
        "new_yesterday_count": len(new_yesterday),
        "closed_today_count": len(closed_today),
        "closed_yesterday_count": len(closed_yesterday),
        "avg_close_seconds": avg_close,
        "median_close_seconds": median_close,
        "top_issues": top_issues,
        "device_counts": device_counts,
        "other_device_count": other_device_count,
        "oldest_open": oldest_open_view,
        "closed_today_list": closed_today_view,
    }


# ---------- HTML rendering ----------

def esc(value):
    return html.escape(str(value), quote=True)


def render_issue_bars(top_issues):
    if not top_issues:
        return '<div class="empty">No open tickets are tagged with an issue category</div>'
    max_count = max(count for _, count in top_issues)
    rows_html = []
    for label, count in top_issues:
        pct = round((count / max_count) * 100) if max_count else 0
        rows_html.append(f'''
        <div class="issue-row">
          <div class="issue-label">{esc(label)}</div>
          <div class="issue-track"><div class="issue-fill" style="width:{pct}%"></div></div>
          <div class="issue-count">{count}</div>
        </div>''')
    return "".join(rows_html)


def render_device_cards(device_counts, other_count):
    cards = []
    for _, label in DEVICE_TAGS:
        cards.append(f'''
        <div class="device-card">
          <div class="device-name">{esc(label)}</div>
          <div class="device-count">{device_counts.get(label, 0)}</div>
          <div class="device-unit">OPEN</div>
        </div>''')
    other_html = ""
    if other_count:
        other_html = f'<div class="device-other">Other / Unclassified &nbsp;<strong>{other_count}</strong></div>'
    return "".join(cards), other_html


def render_oldest_cases(cases):
    if not cases:
        return '<div class="empty">No open cases</div>'
    rows_html = []
    for c in cases:
        age_class = ""
        age_seconds = c["age_seconds"]
        if age_seconds >= 7 * 86400:
            age_class = "age-critical"
        elif age_seconds >= 3 * 86400:
            age_class = "age-warning"
        rows_html.append(f'''
        <div class="case-row">
          <div class="case-age {age_class}">{esc(format_duration(age_seconds))}</div>
          <div class="case-number">#{esc(c["number"])}</div>
          <div class="case-subject">{esc(c["subject"])}</div>
          <div class="case-device">{esc(c["device"])}</div>
        </div>''')
    return "".join(rows_html)


def render_closed_today(cases):
    if not cases:
        return '<div class="empty">No cases closed yet today</div>'
    rows_html = []
    for c in cases:
        rows_html.append(f'''
        <div class="closed-row">
          <div class="closed-number">#{esc(c["number"])}</div>
          <div class="closed-subject">{esc(c["subject"])}</div>
          <div class="closed-duration">{esc(format_duration(c["duration_seconds"]))}</div>
        </div>''')
    return "".join(rows_html)


def render_comparison(today_count, yesterday_count, noun):
    return f"Yesterday: {yesterday_count} {noun}" if yesterday_count or today_count else ""


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Support Operations - TV</title>
<style>
__CSS__
</style>
</head>
<body>
  <div id="stage">
  <div class="board">
    <header class="board-header">
      <div class="brand">
        <span class="brand-mark"></span>
        <span class="brand-name">SUPPORT</span>
      </div>
      <div class="header-right">
        <span id="staleFlag" class="stale-flag" hidden></span>
        <span class="updated" id="updatedLabel">Updated __UPDATED_LABEL__</span>
      </div>
    </header>

    <section class="kpi-row">
      <div class="kpi kpi-open">
        <div class="kpi-label">Open Now</div>
        <div class="kpi-value">__OPEN_TOTAL__</div>
        <div class="kpi-sub">__OPEN_SUB__</div>
      </div>
      <div class="kpi kpi-new">
        <div class="kpi-label">New Today</div>
        <div class="kpi-value">__NEW_TODAY__</div>
        <div class="kpi-sub">__NEW_SUB__</div>
      </div>
      <div class="kpi kpi-closed">
        <div class="kpi-label">Closed Today</div>
        <div class="kpi-value">__CLOSED_TODAY__</div>
        <div class="kpi-sub">__CLOSED_SUB__</div>
      </div>
      <div class="kpi kpi-time">
        <div class="kpi-label">Avg Time to Close</div>
        <div class="kpi-value">__AVG_CLOSE__</div>
        <div class="kpi-sub">__MEDIAN_SUB__</div>
      </div>
    </section>

    <section class="mid-row">
      <div class="panel panel-issues">
        <div class="panel-title">Top Open Issues</div>
        <div class="issue-list">__ISSUE_BARS__</div>
      </div>
      <div class="panel panel-devices">
        <div class="panel-title">Open by Device</div>
        <div class="device-row">__DEVICE_CARDS__</div>
        __DEVICE_OTHER__
      </div>
    </section>

    <section class="bottom-row">
      <div class="panel panel-oldest">
        <div class="panel-title">Oldest Open Cases</div>
        <div class="case-header-row">
          <div>Age</div><div>Case</div><div>Subject</div><div>Device</div>
        </div>
        <div class="case-list">__OLDEST_CASES__</div>
      </div>
      <div class="panel panel-closed">
        <div class="panel-title">Closed Today</div>
        <div class="closed-header-row">
          <div>Case</div><div>Subject</div><div>Time to Close</div>
        </div>
        <div class="closed-list">__CLOSED_TODAY_LIST__</div>
      </div>
    </section>
  </div>
  </div>

<script>
  var GENERATED_AT = __GENERATED_AT_MS__;
  var WARN_MS = __STALE_WARN_MS__;
  var CRITICAL_MS = __STALE_CRITICAL_MS__;

  function updateStaleness(){
    var ageMs = Date.now() - GENERATED_AT;
    var ageMin = Math.floor(ageMs / 60000);
    var flag = document.getElementById("staleFlag");
    if (ageMs < WARN_MS){
      flag.hidden = true;
      return;
    }
    flag.hidden = false;
    flag.textContent = "DATA " + ageMin + " MIN OLD";
    flag.className = "stale-flag " + (ageMs >= CRITICAL_MS ? "stale-critical" : "stale-warning");
  }
  updateStaleness();
  setInterval(updateStaleness, 30000);

  // Scale the fixed 1920x1080 design to fit whatever window it's actually
  // opened in - a laptop browser tab, a smaller preview window, or a real
  // 1920x1080 TV - so it always renders in full, centered, never clipped
  // or scrollable.
  function fitStage(){
    var stage = document.getElementById("stage");
    var scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    var x = (window.innerWidth - 1920 * scale) / 2;
    var y = (window.innerHeight - 1080 * scale) / 2;
    stage.style.transform = "translate(" + x + "px, " + y + "px) scale(" + scale + ")";
  }
  fitStage();
  window.addEventListener("resize", fitStage);
</script>
</body>
</html>
"""


CSS = """
  :root{
    --page:      #0a0e12;
    --panel:     #121820;
    --panel-2:   #182029;
    --hairline:  #232d38;
    --ink:       #f4f7f9;
    --ink-dim:   #9db0bd;
    --ink-mute:  #6c7f8c;

    --cyan:      #38bdf8;
    --cyan-dim:  #1c3a4a;
    --green:     #34d399;
    --green-dim: #113328;
    --amber:     #fbbf24;
    --amber-dim: #3a2f10;
    --red:       #f87171;
  }
  *{ box-sizing: border-box; }
  html, body{ margin:0; padding:0; width:100%; height:100%; background: var(--page); }
  body{
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--ink);
    overflow: hidden;
  }
  /* The design is authored for a fixed 1920x1080 canvas. #stage holds that
     canvas at its native size; JS scales+centers it to whatever window it's
     actually shown in (laptop or TV) so nothing ever clips or scrolls. */
  #stage{
    position: fixed; top: 0; left: 0;
    width: 1920px; height: 1080px;
    transform-origin: top left;
  }
  .board{
    width: 100%; height: 100%;
    display: flex; flex-direction: column;
    padding: 28px 40px 32px;
    gap: 20px;
  }

  .board-header{ display:flex; align-items:center; justify-content:space-between; flex: 0 0 auto; }
  .brand{ display:flex; align-items:center; gap: 14px; }
  .brand-mark{ width: 14px; height: 14px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 16px var(--cyan); }
  .brand-name{ font-size: 26px; font-weight: 700; letter-spacing: 0.12em; color: var(--ink-dim); }
  .header-right{ display:flex; align-items:center; gap: 16px; }
  .updated{ font-size: 20px; color: var(--ink-mute); font-variant-numeric: tabular-nums; }
  .stale-flag{ font-size: 16px; font-weight: 700; letter-spacing: 0.06em; padding: 5px 12px; border-radius: 6px; }
  .stale-warning{ background: var(--amber-dim); color: var(--amber); }
  .stale-critical{ background: #3a1414; color: var(--red); }

  .kpi-row{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 20px; flex: 0 0 auto; }
  .kpi{ background: var(--panel); border: 1px solid var(--hairline); border-radius: 26px; padding: 22px 28px; position: relative; overflow: hidden; }
  .kpi::before{ content:""; position:absolute; left:0; top:0; bottom:0; width: 6px; }
  .kpi-open::before{ background: var(--cyan); }
  .kpi-new::before{ background: var(--cyan); opacity: .55; }
  .kpi-closed::before{ background: var(--green); }
  .kpi-time::before{ background: var(--green); opacity: .7; }
  .kpi-label{ font-size: 20px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-dim); }
  .kpi-value{ font-size: 88px; font-weight: 800; line-height: 1.05; margin-top: 6px; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
  .kpi-open .kpi-value{ color: var(--cyan); }
  .kpi-new .kpi-value{ color: var(--ink); }
  .kpi-closed .kpi-value{ color: var(--green); }
  .kpi-time .kpi-value{ color: var(--ink); font-size: 68px; }
  .kpi-sub{ font-size: 19px; color: var(--ink-mute); margin-top: 4px; min-height: 24px; }

  .mid-row{ display:grid; grid-template-columns: 1.5fr 1fr; gap: 20px; flex: 1 1 auto; min-height: 0; }
  .bottom-row{ display:grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 1 1 auto; min-height: 0; }

  .panel{ background: var(--panel); border: 1px solid var(--hairline); border-radius: 26px; padding: 24px 28px; display:flex; flex-direction:column; min-height: 0; }
  .panel-title{ font-size: 22px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-dim); margin-bottom: 18px; flex: 0 0 auto; }

  .issue-list{ display:flex; flex-direction:column; justify-content: space-evenly; flex: 1 1 auto; }
  .issue-row{ display:grid; grid-template-columns: 230px 1fr 70px; align-items:center; gap: 18px; }
  .issue-label{ font-size: 26px; font-weight: 600; color: var(--ink); }
  .issue-track{ background: var(--panel-2); border-radius: 999px; height: 30px; overflow: hidden; }
  .issue-fill{ height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--cyan-dim), var(--cyan)); }
  .issue-count{ font-size: 30px; font-weight: 700; text-align: right; font-variant-numeric: tabular-nums; }

  .device-row{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 16px; flex: 1 1 auto; align-content: center; }
  .device-card{ background: var(--panel-2); border-radius: 20px; padding: 20px 10px; text-align:center; }
  .device-name{ font-size: 22px; font-weight: 700; letter-spacing: 0.06em; color: var(--ink-dim); text-transform: uppercase; }
  .device-count{ font-size: 64px; font-weight: 800; color: var(--cyan); margin-top: 6px; font-variant-numeric: tabular-nums; }
  .device-unit{ font-size: 16px; color: var(--ink-mute); letter-spacing: 0.1em; margin-top: 2px; }
  .device-other{ text-align:center; margin-top: 14px; font-size: 18px; color: var(--ink-mute); flex: 0 0 auto; }
  .device-other strong{ color: var(--ink-dim); font-size: 22px; }

  .case-header-row, .closed-header-row{
    display:grid; font-size: 15px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--ink-mute); padding-bottom: 10px; border-bottom: 1px solid var(--hairline); flex: 0 0 auto;
  }
  .case-header-row{ grid-template-columns: 110px 90px 1fr 90px; }
  .closed-header-row{ grid-template-columns: 90px 1fr 160px; }

  .case-list, .closed-list{ display:flex; flex-direction:column; justify-content: space-evenly; flex: 1 1 auto; }
  .case-row{ display:grid; grid-template-columns: 110px 90px 1fr 90px; align-items:center; gap: 4px; padding: 6px 0; }
  .case-age{ font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--ink); }
  .case-age.age-warning{ color: var(--amber); }
  .case-age.age-critical{ color: var(--red); }
  .case-number{ font-size: 22px; color: var(--ink-mute); font-variant-numeric: tabular-nums; }
  .case-subject{ font-size: 24px; color: var(--ink); overflow:hidden; white-space:nowrap; text-overflow:ellipsis; padding-right: 10px; }
  .case-device{ font-size: 20px; font-weight: 600; color: var(--ink-dim); text-transform: uppercase; }

  .closed-row{ display:grid; grid-template-columns: 90px 1fr 160px; align-items:center; gap: 4px; padding: 6px 0; }
  .closed-number{ font-size: 22px; color: var(--ink-mute); font-variant-numeric: tabular-nums; }
  .closed-subject{ font-size: 24px; color: var(--ink); overflow:hidden; white-space:nowrap; text-overflow:ellipsis; padding-right: 10px; }
  .closed-duration{ font-size: 24px; font-weight: 700; color: var(--green); text-align:right; font-variant-numeric: tabular-nums; }

  .empty{ font-size: 22px; color: var(--ink-mute); text-align:center; margin: auto; }
"""


def render_html(metrics):
    open_sub = f"{metrics['active_count']} Active · {metrics['pending_count']} Pending"
    new_sub = render_comparison(metrics["new_today_count"], metrics["new_yesterday_count"], "new")
    closed_sub = render_comparison(metrics["closed_today_count"], metrics["closed_yesterday_count"], "closed")
    avg_close = format_duration(metrics["avg_close_seconds"]) if metrics["avg_close_seconds"] is not None else "—"
    median_sub = f"Median {format_duration(metrics['median_close_seconds'])}" if metrics["median_close_seconds"] is not None else ""

    device_cards_html, device_other_html = render_device_cards(metrics["device_counts"], metrics["other_device_count"])

    updated_label = metrics["now_local"].strftime("%b %-d · %-I:%M %p")

    out = HTML_TEMPLATE
    out = out.replace("__CSS__", CSS)
    out = out.replace("__UPDATED_LABEL__", esc(updated_label))
    out = out.replace("__OPEN_TOTAL__", str(metrics["open_total"]))
    out = out.replace("__OPEN_SUB__", esc(open_sub))
    out = out.replace("__NEW_TODAY__", str(metrics["new_today_count"]))
    out = out.replace("__NEW_SUB__", esc(new_sub))
    out = out.replace("__CLOSED_TODAY__", str(metrics["closed_today_count"]))
    out = out.replace("__CLOSED_SUB__", esc(closed_sub))
    out = out.replace("__AVG_CLOSE__", esc(avg_close))
    out = out.replace("__MEDIAN_SUB__", esc(median_sub))
    out = out.replace("__ISSUE_BARS__", render_issue_bars(metrics["top_issues"]))
    out = out.replace("__DEVICE_CARDS__", device_cards_html)
    out = out.replace("__DEVICE_OTHER__", device_other_html)
    out = out.replace("__OLDEST_CASES__", render_oldest_cases(metrics["oldest_open"]))
    out = out.replace("__CLOSED_TODAY_LIST__", render_closed_today(metrics["closed_today_list"]))
    out = out.replace("__GENERATED_AT_MS__", str(int(metrics["now_local"].timestamp() * 1000)))
    out = out.replace("__STALE_WARN_MS__", str(STALE_WARN_MINUTES * 60 * 1000))
    out = out.replace("__STALE_CRITICAL_MS__", str(STALE_CRITICAL_MINUTES * 60 * 1000))
    return out


def main():
    now_utc = datetime.now(timezone.utc)
    rows = load_rows()
    metrics = compute_metrics(rows, now_utc)
    html_out = render_html(metrics)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_out)

    print(f"Open now: {metrics['open_total']} ({metrics['active_count']} active, {metrics['pending_count']} pending)")
    print(f"New today: {metrics['new_today_count']}")
    print(f"Closed today: {metrics['closed_today_count']}")
    avg_str = format_duration(metrics["avg_close_seconds"]) if metrics["avg_close_seconds"] is not None else "n/a"
    print(f"Avg time to close (today): {avg_str}")
    if metrics["top_issues"]:
        print(f"Top open issue: {metrics['top_issues'][0][0]} ({metrics['top_issues'][0][1]})")
    else:
        print("Top open issue: none tagged")
    for _, label in DEVICE_TAGS:
        print(f"Open {label}: {metrics['device_counts'][label]}")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
