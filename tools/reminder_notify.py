
import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import BASE_DIR

TASK_PREFIX = "LapisReminder_"
REMINDERS_STORE = os.path.join(BASE_DIR, "reminders.json")
SNOOZE_MINUTES = 10


def _show_toast(text):
    try:
        from win11toast import toast

        def on_click(args):
            choice = args.get("arguments") if isinstance(args, dict) else None
            if choice == "snooze":
                from tools.remindertools import set_reminder_in
                set_reminder_in(text, SNOOZE_MINUTES)

        toast(
            "Lapis Reminder",
            text,
            buttons=[
                {"activationType": "protocol", "arguments": "snooze", "content": f"Snooze {SNOOZE_MINUTES} min"},
                {"activationType": "protocol", "arguments": "dismiss", "content": "Dismiss"},
            ],
            audio="ms-winsoundevent:Notification.Reminder",
            on_click=on_click,
        )
    except Exception:
        # win11toast missing, or any WinRT/COM hiccup on this build —
        # fail silently rather than crash the scheduled task
        pass


def _cleanup(reminder_id):
    try:
        if os.path.exists(REMINDERS_STORE):
            with open(REMINDERS_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data = [r for r in data if r.get("id") != reminder_id]
            with open(REMINDERS_STORE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass

    subprocess.run(
        ["schtasks", "/delete", "/tn", f"{TASK_PREFIX}{reminder_id}", "/f"],
        capture_output=True,
    )


def main():
    if len(sys.argv) < 3:
        return
    text, reminder_id = sys.argv[1], sys.argv[2]
    _show_toast(text)  # blocks until clicked or the toast times out/dismisses
    _cleanup(reminder_id)


if __name__ == "__main__":
    main()