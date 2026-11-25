import os
import sys
import json
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta

from config import BASE_DIR

REMINDERS_STORE = os.path.join(BASE_DIR, "reminders.json")
TASK_PREFIX = "LapisReminder_"
NOTIFY_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminder_notify.py")


def load_reminders():
    if not os.path.exists(REMINDERS_STORE):
        return []
    try:
        with open(REMINDERS_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_reminders(data):
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(REMINDERS_STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def pythonw():
    """Prefer pythonw.exe next to the current interpreter so the reminder
    fires without flashing a console window."""
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


import tempfile

def create_scheduled_task(reminder_id, text, dt):
    if not shutil.which("powershell"):
        return False, "Error: PowerShell not found — required for reliable scheduling."

    task_name = f"{TASK_PREFIX}{reminder_id}"
    safe_text = text.replace('"', "'").replace("`", "'")
    username = os.environ.get("USERNAME", "")

    # Named Get-Date params avoid any locale-dependent date parsing entirely
    ps_script = f'''
$Action = New-ScheduledTaskAction -Execute '{pythonw()}' -Argument '"{NOTIFY_SCRIPT}" "{safe_text}" "{reminder_id}"'
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date -Year {dt.year} -Month {dt.month} -Day {dt.day} -Hour {dt.hour} -Minute {dt.minute} -Second 0)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName '{task_name}' -Action $Action -Trigger $Trigger -Settings $Settings -User '{username}' -Force | Out-Null
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
        f.write(ps_script)
        script_path = f.name

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True,
            text=True,
        )
    finally:
        os.remove(script_path)

    if result.returncode != 0:
        return False, f"Error creating scheduled task: {result.stderr.strip() or result.stdout.strip()}"
    return True, task_name

def set_reminder(text, when):
    """Schedule a Windows toast reminder for an exact future date and time.

    Args:
        text: What to remind about, e.g. 'Call the dentist'
        when: Exact date and time as 'YYYY-MM-DD HH:MM' in 24-hour format,
              e.g. '2026-08-07 14:30'. Compute this yourself from today's
              date (given in the system prompt) and whatever the user said —
              'tomorrow at 2pm', 'next Monday morning', etc.

    Returns:
        Confirmation message with the reminder id, or an error message
    """
    try:
        dt = datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return f"Error: '{when}' isn't in 'YYYY-MM-DD HH:MM' format."

    if dt <= datetime.now():
        return f"Error: {when} is in the past. Pick a future date/time."

    reminder_id = uuid.uuid4().hex[:8]
    ok, info = create_scheduled_task(reminder_id, text, dt)
    if not ok:
        return info

    reminders = load_reminders()
    reminders.append({
        "id": reminder_id,
        "text": text,
        "when": dt.strftime("%Y-%m-%d %H:%M"),
        "task_name": info,
    })
    save_reminders(reminders)

    return f"Reminder set for {dt.strftime('%Y-%m-%d %H:%M')} — '{text}' (id: {reminder_id})"


def set_reminder_in(text, minutes):
    """Schedule a Windows toast reminder a number of minutes from now. Use
    this for relative reminders like 'remind me in 20 minutes' instead of
    computing an exact datetime yourself.

    Args:
        text: What to remind about, e.g. 'Take the laundry out'
        minutes: How many minutes from now to fire the reminder

    Returns:
        Confirmation message with the reminder id, or an error message
    """
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "Error: minutes must be an integer."
    if minutes <= 0:
        return "Error: minutes must be positive."

    dt = datetime.now() + timedelta(minutes=minutes)
    return set_reminder(text, dt.strftime("%Y-%m-%d %H:%M"))


def list_reminders():
    """List every reminder currently scheduled and not yet fired.

    Returns:
        A list of reminders with id, fire time, and text — or a message
        saying none are scheduled
    """
    reminders = load_reminders()
    if not reminders:
        return "No reminders currently scheduled."
    reminders.sort(key=lambda r: r["when"])
    return "\n".join(f"[{r['id']}] {r['when']} — {r['text']}" for r in reminders)


def cancel_reminder(reminder_id):
    """Cancel a scheduled reminder before it fires.

    Args:
        reminder_id: The id shown by list_reminders, e.g. 'a1b2c3d4'

    Returns:
        Confirmation message or error
    """
    reminders = load_reminders()
    match = next((r for r in reminders if r["id"] == reminder_id), None)
    if not match:
        return f"Error: no reminder found with id '{reminder_id}'"

    subprocess.run(
        ["schtasks", "/delete", "/tn", match["task_name"], "/f"],
        capture_output=True,
        text=True,
    )

    reminders = [r for r in reminders if r["id"] != reminder_id]
    save_reminders(reminders)
    return f"Reminder cancelled: '{match['text']}' (was set for {match['when']})"