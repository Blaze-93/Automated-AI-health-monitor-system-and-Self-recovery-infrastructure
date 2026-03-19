import json, os, datetime, time
from logging.handlers import RotatingFileHandler
import logging

os.makedirs("logs", exist_ok=True)
_h = RotatingFileHandler("logs/alerts.log", maxBytes=2*1024*1024, backupCount=5)
_l = logging.getLogger("alerts")
_l.setLevel(logging.DEBUG)
_l.addHandler(_h)

_last_sent = {}         # dedup: { title: timestamp }
DEDUP_SECONDS = 120     # same alert won't fire again within 2 minutes


def send_alert(title, message, severity="WARNING", source="monitor"):
    """Write alert to file and print a visible console block."""
    # Dedup
    if time.time() - _last_sent.get(title, 0) < DEDUP_SECONDS:
        return
    _last_sent[title] = time.time()

    alert = {
        "timestamp": datetime.datetime.now().isoformat(),
        "severity":  severity,
        "title":     title,
        "message":   message,
        "source":    source,
    }
    _l.info(json.dumps(alert))

    # Console block — hard to miss
    c = "\033[91m" if severity == "CRITICAL" else "\033[93m"
    r = "\033[0m"
    print(f"\n{c}{'='*55}")
    print(f"  !! ALERT [{severity}]  {alert['timestamp']}")
    print(f"  {title}")
    print(f"  {message}")
    print(f"{'='*55}{r}\n")

    # ─ To add email: uncomment and fill in _send_email() below ──
    # _send_email(alert)

    # ─ To add Slack: uncomment and fill in _send_slack() below ──
    # _send_slack(alert)


# def _send_email(alert):
      #need to add below lines to get email
#   ->  import smtplib
#   ->  from email.mime.text import MIMEText
#     msg = MIMEText(f"{alert['title']}\n\n{alert['message']}")
#     msg["Subject"] = f"[{alert['severity']}] {alert['title']}"
#     msg["From"]    = "your@email.com"
#     msg["To"]      = "admin@email.com"
#     with smtplib.SMTP("smtp.gmail.com", 587) as s:
#         s.starttls()
#         s.login("your@email.com", "app_password")
#         s.send_message(msg)


# def _send_slack(alert):
    # if need slack alert then need below  lines
#   ->  import urllib.request
#     payload = json.dumps({"text": f"*[{alert['severity']}]* {alert['title']}\n{alert['message']}"})
#     req = urllib.request.Request(
#         "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
#         data=payload.encode(), headers={"Content-Type": "application/json"})
#     urllib.request.urlopen(req, timeout=5)
