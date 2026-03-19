
import time, threading, platform
from check    import check_module
from logger   import write_log, aggregate_external_logs
from recovery import fix_module
from anomaly  import check_metrics_anomaly, scan_logs_for_anomalies
from alert    import send_alert


# ─────────────────────────────────────────────────────────────────────────────
# MODULES
#
# Three check types depending on what the module is:
#
#  "process"  -> for apps with their own process name (notepad.exe, testing)
#  "http"     -> for FastAPI/uvicorn services (tell team: add a /health route)
#  "pidfile"  -> for plain python scripts (add 2 lines, see README)


MODULES = [

    # ── TEST MODULE (active) ───
    # Open Notepad to test HEALTHY, close it to test DOWN + recovery
    {
        "check_type": "process",
        "name":       "notepad.exe",
        "display":    "Test Module (Notepad)",
        "cpu_warn": 75, "cpu_critical": 90,
        "mem_warn": 75, "mem_critical": 90,
        "auto_recover": True,
    },

    # ── FastAPI / uvicorn services (http check) ──

    #   Add this to their FastAPI app:
    #     @app.get("/health")
    #     def health(): return {"status": "ok"}
    #   Then run with: uvicorn their_app:app --port 8001
    #
    # {
    #     "check_type": "http",
    #     "display":    "Interview API",
    #     "url":        "http://localhost:8001/health",
    #     "port":       8001,        # used to find the process for CPU/RAM stats
    #     "cpu_warn": 75, "cpu_critical": 90,
    #     "mem_warn": 75, "mem_critical": 90,
    #     "auto_recover": False,     # HTTP services — let them handle their own restart
    # }

    # ── Plain python scripts (pidfile check) ───
    # need to add below 2 lines to run plain python scripts
        # ->  import os
        # ->  os.makedirs("pids", exist_ok=True); open("pids/their_script.pid","w").write(str(os.getpid()))
    #
    # {
    #     "check_type": "pidfile",
    #     "display":    "LLM Engine",
    #     "pid_file":   "pids/llm_engine.pid",
    #     "cpu_warn": 75, "cpu_critical": 90,
    #     "mem_warn": 75, "mem_critical": 90,
    #     "auto_recover": False,    # can't restart a script we don't know the path to
    # },

]

CHECK_INTERVAL = 10   # seconds between health checks

_status = {}
_lock   = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Monitor loop (one thread per module)
# ─────────────────────────────────────────────────────────────────────────────

def monitor_module(cfg):
    display = cfg["display"]
    write_log(display, f"Started — check type: {cfg.get('check_type','process')}", severity="INFO")

    while True:
        h = check_module(cfg)
        cpu_spike, ram_spike = check_metrics_anomaly(display, h["cpu"], h["ram"])

        with _lock:
            _status[display] = {**h, "checked": time.strftime("%H:%M:%S")}

        if h["status"] == "DOWN":
            write_log(display, f"DOWN — {h['issues'][0]}", severity="CRITICAL")
            send_alert(f"{display} is DOWN", h["issues"][0], severity="CRITICAL")
            if cfg.get("auto_recover"):
                name   = cfg.get("name", display)
                result = fix_module(name)
                write_log(display, f"Recovery: {result}", severity="RECOVERY")
                if result == "RECOVERY_FAILED":
                    send_alert(f"{display} recovery failed",
                               "All restart attempts exhausted. Manual action needed.",
                               severity="CRITICAL")

        elif h["status"] == "CRITICAL":
            for issue in h["issues"]:
                write_log(display, issue, severity="CRITICAL",
                          extra={"cpu": h["cpu"], "ram": h["ram"]})
            send_alert(f"{display} — CRITICAL", " | ".join(h["issues"]), severity="CRITICAL")
            if cfg.get("auto_recover"):
                result = fix_module(cfg.get("name", display))
                write_log(display, f"Recovery: {result}", severity="RECOVERY")

        elif h["status"] == "WARNING":
            for issue in h["issues"]:
                write_log(display, issue, severity="WARNING")
            send_alert(f"{display} — WARNING", " | ".join(h["issues"]), severity="WARNING")

        else:
            if cpu_spike:
                write_log(display, f"CPU spike: {h['cpu']:.1f}%", severity="WARNING")
                send_alert(f"{display} — CPU spike", f"Unusual CPU: {h['cpu']:.1f}%", severity="WARNING")
            elif ram_spike:
                write_log(display, f"RAM spike: {h['ram']:.1f}%", severity="WARNING")
                send_alert(f"{display} — RAM spike", f"Unusual RAM: {h['ram']:.1f}%", severity="WARNING")
            else:
                write_log(display, f"Healthy — CPU:{h['cpu']:.1f}% RAM:{h['ram']:.1f}%",
                          severity="INFO", extra={"pid": h["pid"]})

        time.sleep(CHECK_INTERVAL)


# ─────────────────────────────────────────────────────────────────────────────
# Background threads
# ─────────────────────────────────────────────────────────────────────────────

def _aggregator_loop():
    while True:
        aggregate_external_logs()
        time.sleep(5)

def _log_scanner_loop():
    while True:
        time.sleep(30)
        scan_logs_for_anomalies()

def _status_printer():
    while True:
        time.sleep(30)
        print("\n" + "="*55)
        print(f"  {'MODULE':<24} {'STATUS':<10} {'CPU':>5} {'RAM':>5}")
        print("-"*55)
        with _lock:
            for display, info in _status.items():
                c = {"HEALTHY":"\033[92m","WARNING":"\033[93m",
                     "CRITICAL":"\033[91m","DOWN":"\033[91m"}.get(info["status"],"\033[0m")
                print(f"  {display:<24} {c}{info['status']:<10}\033[0m "
                      f"{info['cpu']:>4.1f}% {info['ram']:>4.1f}%")
        print("="*55 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def start_monitoring():
    print("="*55)
    print("  AI Interview Platform — Health Monitor")
    print(f"  {len(MODULES)} module(s) | check every {CHECK_INTERVAL}s")
    print("="*55)
    write_log("SYSTEM", f"Monitor started on {platform.system()}", severity="INFO")

    for t in [
        threading.Thread(target=_aggregator_loop,  daemon=True),
        threading.Thread(target=_log_scanner_loop, daemon=True),
        threading.Thread(target=_status_printer,   daemon=True),
    ]:
        t.start()

    for cfg in MODULES:
        threading.Thread(target=monitor_module, args=(cfg,), daemon=True).start()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        write_log("SYSTEM", "Monitor stopped", severity="INFO")
        print("\n[Stopped]")


if __name__ == "__main__":
    start_monitoring()
