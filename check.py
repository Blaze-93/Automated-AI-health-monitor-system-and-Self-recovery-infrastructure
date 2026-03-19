"""
check.py — Health checker with three check types:

  "process"  — find by process name (e.g. notepad.exe)
               USE FOR: testing, standalone applications

  "http"     — ping an HTTP endpoint (e.g. http://localhost:8001/health)
               USE FOR: FastAPI / uvicorn services — tell team members to add
               a /health route that returns {"status": "ok"}

  "pidfile"  — read a .pid file the script writes on startup
               USE FOR: plain python scripts (llm_engine.py etc.)
               Tell team member to add 2 lines at the top of their script —
               see README.
"""

import psutil, time, os
import urllib.request, urllib.error


def check_module(cfg):
    """
    Run a health check based on cfg["check_type"].
    Returns: { status, pid, cpu, ram, issues }
    Status values: HEALTHY | WARNING | CRITICAL | DOWN
    """
    t = cfg.get("check_type", "process")
    if   t == "http":    return _check_http(cfg)
    elif t == "pidfile": return _check_pidfile(cfg)
    else:                return _check_process(cfg)


# ── Type 1: Process name ──────────────────────────────────────────────────────

def _check_process(cfg):
    proc = _find_by_name(cfg["name"])
    if proc is None:
        return _down([f"'{cfg['name']}' not found in running processes"])
    return _read_stats(proc, cfg)


def _find_by_name(name):
    for p in psutil.process_iter(["name", "pid"]):
        try:
            if p.info["name"] and p.info["name"].lower() == name.lower():
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


# ── Type 2: HTTP endpoint ─────────────────────────────────────────────────────
# Service must respond 200 to be HEALTHY.
# Team member adds to their FastAPI app:
#   @app.get("/health")
#   def health(): return {"status": "ok"}

def _check_http(cfg):
    url     = cfg["url"]
    timeout = cfg.get("timeout", 5)
    try:
        t0  = time.time()
        res = urllib.request.urlopen(url, timeout=timeout)
        ms  = round((time.time() - t0) * 1000, 1)

        if res.getcode() == 200:
            proc = _find_by_port(cfg.get("port"))
            if proc:
                return _read_stats(proc, cfg, extra={"response_ms": ms})
            return {"status": "HEALTHY", "pid": None,
                    "cpu": 0.0, "ram": 0.0, "issues": [], "response_ms": ms}
        return _down([f"HTTP {res.getcode()} from {url}"])

    except urllib.error.URLError as e:
        return _down([f"No response from {url} — service may be down"])
    except Exception as e:
        return _down([f"HTTP check error: {e}"])


def _find_by_port(port):
    if not port:
        return None
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.pid:
                return psutil.Process(conn.pid)
    except Exception:
        pass
    return None


# ── Type 3: PID file ──────────────────────────────────────────────────────────
# The Python script writes its own PID when it starts.
# Team member adds to the TOP of their script (e.g. llm_engine.py):
#
#   import os
#   os.makedirs("pids", exist_ok=True)
#   open("pids/llm_engine.pid", "w").write(str(os.getpid()))
#
# That's it. Two lines. Now we can find their exact process.

def _check_pidfile(cfg):
    path = cfg["pid_file"]

    if not os.path.exists(path):
        return _down([f"PID file not found: {path} — is the service running?"])

    try:
        pid = int(open(path).read().strip())
    except (ValueError, OSError):
        return _down([f"Could not read PID from {path}"])

    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return _down([f"PID {pid} is no longer running"])
        return _read_stats(proc, cfg)
    except psutil.NoSuchProcess:
        return _down([f"PID {pid} does not exist — process has stopped"])
    except psutil.AccessDenied:
        return _down([f"Access denied reading PID {pid}"])


# ── Shared helpers ────────────────────────────────────────────────────────────

def _read_stats(proc, cfg, extra=None):
    cpu_warn     = cfg.get("cpu_warn",     75)
    cpu_critical = cfg.get("cpu_critical", 90)
    mem_warn     = cfg.get("mem_warn",     75)
    mem_critical = cfg.get("mem_critical", 90)
    issues, status = [], "HEALTHY"

    try:
        proc.cpu_percent()
        time.sleep(0.3)
        cpu = proc.cpu_percent()
        ram = proc.memory_percent()
        pid = proc.pid

        if   cpu >= cpu_critical: status = "CRITICAL"; issues.append(f"CPU critical: {cpu:.1f}%")
        elif cpu >= cpu_warn:     status = "WARNING";  issues.append(f"CPU high: {cpu:.1f}%")
        if   ram >= mem_critical: status = "CRITICAL"; issues.append(f"RAM critical: {ram:.1f}%")
        elif ram >= mem_warn:
            if status != "CRITICAL": status = "WARNING"
            issues.append(f"RAM high: {ram:.1f}%")

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return _down(["Process disappeared during check"])

    result = {"status": status, "pid": pid, "cpu": cpu, "ram": ram, "issues": issues}
    if extra:
        result.update(extra)
    return result


def _down(issues):
    return {"status": "DOWN", "pid": None, "cpu": 0.0, "ram": 0.0, "issues": issues}
