"""
anomaly.py — Two types of anomaly detection:
  1. Metrics  — flags CPU/RAM spikes using z-score on rolling history
  2. Log scan — flags error bursts in the aggregated log file
"""

import collections, statistics, time, json, os
from logger import write_log
from alert  import send_alert

# ── 1. Metrics anomaly (z-score) ───

_history = collections.defaultdict(lambda: collections.deque(maxlen=30))


def check_metrics_anomaly(module, cpu, ram):
    """
    Feed current CPU/RAM into rolling history.
    Returns True if either value is a statistical spike.
    """
    cpu_key = (module, "cpu")
    ram_key = (module, "ram")

    cpu_spike = _is_spike(cpu_key, cpu)
    ram_spike = _is_spike(ram_key, ram)

    _history[cpu_key].append(cpu)
    _history[ram_key].append(ram)

    return cpu_spike, ram_spike


def _is_spike(key, value, z_threshold=2.5):
    hist = _history[key]
    if len(hist) < 5:
        return False
    mean  = statistics.mean(hist)
    stdev = statistics.stdev(hist)
    if stdev < 0.5:
        return False
    return (value - mean) / stdev > z_threshold


# ── 2. Log-based anomaly scanner ─────────────────────────────────────────────

_log_offset      = 0          # byte position we've already scanned
_error_times     = collections.deque()   # timestamps of recent CRITICAL lines
_repeated_msgs   = collections.Counter() # count of each repeated error message

ERROR_BURST_LIMIT   = 5    # 5 CRITICALs in 60s = anomaly
REPEAT_MSG_LIMIT    = 3    # same message 3x = anomaly (crash loop)
WINDOW_SECONDS      = 60


def scan_logs_for_anomalies(log_file="logs/aggregated.log"):
    """
    Read new lines from aggregated log. Flag error bursts and repeated crashes.
    Call this periodically from main.py.
    """
    global _log_offset

    if not os.path.exists(log_file):
        return

    try:
        with open(log_file, "r", errors="replace") as f:
            f.seek(_log_offset)
            new_lines = f.readlines()
            _log_offset = f.tell()
    except OSError:
        return

    now = time.time()

    for raw in new_lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        sev = entry.get("severity", "").upper()
        msg = entry.get("message", "")[:80]
        mod = entry.get("module",  "unknown")

        if sev == "CRITICAL":
            _error_times.append(now)
            if msg:
                _repeated_msgs[f"{mod}::{msg}"] += 1

    # Prune old error timestamps
    cutoff = now - WINDOW_SECONDS
    while _error_times and _error_times[0] < cutoff:
        _error_times.popleft()

    # Check: error burst
    if len(_error_times) >= ERROR_BURST_LIMIT:
        write_log("LOG_SCANNER",
                  f"Error burst: {len(_error_times)} CRITICAL events in last {WINDOW_SECONDS}s",
                  severity="CRITICAL")
        send_alert("Error burst detected",
                   f"{len(_error_times)} CRITICAL log events in {WINDOW_SECONDS}s",
                   severity="CRITICAL", source="log_scanner")

    # Check: repeated identical error (crash loop)
    for key, count in list(_repeated_msgs.items()):
        if count >= REPEAT_MSG_LIMIT:
            write_log("LOG_SCANNER",
                      f"Repeated error ({count}x): {key}",
                      severity="CRITICAL")
            send_alert("Crash loop detected",
                       f"Same error seen {count} times: {key}",
                       severity="CRITICAL", source="log_scanner")
            _repeated_msgs[key] = 0   # reset so we don't keep re-alerting
