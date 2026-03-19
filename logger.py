import json, os, datetime
from logging.handlers import RotatingFileHandler
import logging

os.makedirs("logs", exist_ok=True)

# ── Setup rotating log files ──────────────────────────────────────────────────
def _make_logger(name, filepath):
    h = RotatingFileHandler(filepath, maxBytes=5*1024*1024, backupCount=5)
    l = logging.getLogger(name)
    l.setLevel(logging.DEBUG)
    l.addHandler(h)
    return l

_monitor_logger     = _make_logger("monitor",     "logs/system_health.log")
_aggregated_logger  = _make_logger("aggregated",  "logs/aggregated.log")

# ── Other service log files to aggregate (add paths here) ────────────────────

# See README for instructions.
EXTERNAL_LOGS = {}

_file_offsets = {}   # tracks how far we've read each external file


def write_log(module, message, severity="INFO", extra=None):
    """Write one JSON log entry."""
    entry = {
        # "timestamp": datetime.datetime.now().isoformat(),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "module":    module,
        "severity":  severity,
        "message":   message,
    }
    if extra:
        entry.update(extra)

    line = json.dumps(entry)
    _monitor_logger.info(line)
    _aggregated_logger.info(line)

    colors = {"INFO": "\033[92m", "WARNING": "\033[93m",
              "CRITICAL": "\033[91m", "RECOVERY": "\033[94m", "ALERT": "\033[95m"}
    c, r = colors.get(severity, "\033[0m"), "\033[0m"
    print(f"{c}[{severity}]{r} {entry['timestamp']} | {module} | {message}")


def aggregate_external_logs():
    """
    Pull new lines from each registered external service log into aggregated.log.
    Called periodically from main.py.
    """
    for service, path in EXTERNAL_LOGS.items():
        if not os.path.exists(path):
            continue
        offset = _file_offsets.get(path, os.path.getsize(path))  # start from end on first run
        try:
            with open(path, "r", errors="replace") as f:
                f.seek(offset)
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        # Plain text — wrap it
                        entry = {"timestamp": datetime.datetime.now().isoformat(),
                                 "module": service, "severity": "INFO", "message": raw}
                    entry["source"] = service
                    _aggregated_logger.info(json.dumps(entry))
                _file_offsets[path] = f.tell()
        except OSError:
            pass
