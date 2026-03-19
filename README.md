# Automated Health Monitoring & Self Recovering Infrastructure

## Overview

An automated system that monitors all services of the AI Interview platform,
detects anomalies, aggregates logs from every module, and performs self-healing
recovery actions without any manual intervention.

Built as part of the AI Interview & Assessment System — Automation Engineering task.

---

## Features

- **Service health checks** — monitors CPU, RAM, and process status of every registered service every 10 seconds
- **Automated recovery** — detects crashed services and automatically restarts them with cooldown and retry logic
- **Log aggregation** — collects logs from all platform services into one central file for unified visibility
- **Anomaly detection** — detects CPU/RAM spikes using statistical z-score analysis on rolling baselines
- **Log-based anomaly detection** — scans aggregated logs for error bursts and crash loops in real time
- **Automated alert system** — fires structured alerts to console and `logs/alerts.log` whenever something goes wrong
- **Multi-module support** — supports three connection types: HTTP health check, PID file, and process name
- **Extensible notifications** — email and Slack alert stubs ready to plug in with credentials

---

## File Structure

```
health_monitor/
│
├── main.py          # Entry point — starts and coordinates all components
├── check.py         # Health checker — reads CPU, RAM, process status
├── logger.py        # Structured JSON logger + cross-service log aggregator
├── recovery.py      # Auto-recovery — kill, restart, verify with cooldown
├── anomaly.py       # Metrics anomaly (z-score) + log-based anomaly scanner
├── alert.py         # Alert system — writes to alerts.log, prints console block
│
└── logs/            # Created automatically on first run
    ├── system_health.log     # All monitor events (JSON lines)
    ├── aggregated.log        # Combined log from all platform services
    └── alerts.log            # Alerts only
```

## Run it right now (testing)

```bash
pip install psutil
python main.py
```

**Open Notepad** → terminal shows `HEALTHY`  
**Close Notepad** → terminal shows `DOWN` + auto-recovery attempt

---

## Log files created

| File | Contains |
|---|---|
| `logs/system_health.log` | Everything this monitor logs |
| `logs/aggregated.log` | Combined log from all services |
| `logs/alerts.log` | Alerts only |

---

## Adding real modules — choose the right check type

There are three ways to monitor a module depending on what it is.  
Open `main.py`, find `MODULES`, and uncomment the matching example.

---

### If their module is a FastAPI / uvicorn service → use `"http"`

**Tell them to add one route:**
```python
@app.get("/health")
def health():
    return {"status": "ok"}
```
**And run on a specific port:**
```bash
uvicorn their_app:app --port 8001
```

**Add to MODULES in main.py:**
```python
{
    "check_type": "http",
    "display":    "Interview API",
    "url":        "http://localhost:8001/health",
    "port":       8001,
    "cpu_warn": 75, "cpu_critical": 90,
    "mem_warn": 75, "mem_critical": 90,
    "auto_recover": False,
},
```

---

### If their module is a plain Python script → use `"pidfile"`

**Tell them to add 2 lines at the very top of their script:**
```python
import os
os.makedirs("pids", exist_ok=True); open("pids/their_script.pid", "w").write(str(os.getpid()))
```

For example in `llm_engine.py`:
```python
import os
os.makedirs("pids", exist_ok=True); open("pids/llm_engine.pid", "w").write(str(os.getpid()))

# ... rest of their code ...
```

**Add to MODULES in main.py:**
```python
{
    "check_type": "pidfile",
    "display":    "LLM Engine",
    "pid_file":   "pids/llm_engine.pid",
    "cpu_warn": 75, "cpu_critical": 90,
    "mem_warn": 75, "mem_critical": 90,
    "auto_recover": False,
},
```

---

### If it's a standalone application → use `"process"` (testing only)

Only for apps that have their own process name (like `notepad.exe`).  
Don't use this for Python scripts — they all appear as `python.exe`.

---

## Connecting other services' log files

When a module writes its own log file, add it to `EXTERNAL_LOGS` in `logger.py`:

```python
EXTERNAL_LOGS = {
    "LLM Engine":    "path/to/llm_engine.log",
    "Scoring API":   "path/to/scoring_api.log",
}
```

The aggregator tails those files every 5s into `logs/aggregated.log`.

---

## To enable email or Slack alerts

Open `alert.py` — the functions are already written at the bottom.  
Fill in credentials and uncomment the call inside `send_alert()`.

---

## Recovery behavior

```
DOWN      → alert → restart (if auto_recover: True) → if all fail → CRITICAL alert
CRITICAL  → alert → restart
WARNING   → alert only
Spike     → WARNING alert only, no restart
5+ errors in 60s in logs → error burst alert
Same error 3x in logs    → crash loop alert
```

> Set `auto_recover: False` for real modules. Restarting without knowing  
> their startup command can cause data loss or port conflicts.

