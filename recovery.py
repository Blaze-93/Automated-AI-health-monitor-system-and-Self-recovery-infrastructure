"""
recovery.py — Kills and restarts a crashed process. Has cooldown so it
doesn't keep restarting the same thing every 10 seconds.
"""

import psutil, subprocess, time, platform
from logger import write_log

COOLDOWN_SECONDS = 60   # don't retry same module within 60s
MAX_RETRIES      = 3

_last_recovery = {}     # { module_name: timestamp }


def fix_module(name):

    # Cooldown check
    since_last = time.time() - _last_recovery.get(name, 0)
    if since_last < COOLDOWN_SECONDS:
        write_log(name, f"Recovery skipped — cooldown ({int(COOLDOWN_SECONDS - since_last)}s left)",
                  severity="INFO")
        return "COOLDOWN_SKIPPED"

    _last_recovery[name] = time.time()
    write_log(name, "Recovery started", severity="WARNING")

    for attempt in range(1, MAX_RETRIES + 1):
        write_log(name, f"Attempt {attempt}/{MAX_RETRIES}", severity="WARNING")

        # Kill
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == name.lower():
                    proc.kill()
                    proc.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass

        time.sleep(2)

        # Restart
        try:
            if platform.system() == "Windows":
                subprocess.Popen(name, shell=True,
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen(name, shell=True, start_new_session=True)
        except Exception as e:
            write_log(name, f"Launch failed: {e}", severity="CRITICAL")
            continue

        # Verify it's running
        time.sleep(3)
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == name.lower():
                    write_log(name, f"Recovery successful on attempt {attempt}",
                              severity="RECOVERY")
                    return "RECOVERY_SUCCESSFUL"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        time.sleep(attempt * 2)   # back-off: 2s, 4s, 6s

    write_log(name, "All recovery attempts failed — manual action needed", severity="CRITICAL")
    return "RECOVERY_FAILED"
