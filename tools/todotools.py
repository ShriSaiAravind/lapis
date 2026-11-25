import os
import json
import uuid
from datetime import datetime

from config import BASE_DIR

TODOS_STORE = os.path.join(BASE_DIR, "todos.json")


def load_todos():
    if not os.path.exists(TODOS_STORE):
        return []
    try:
        with open(TODOS_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_todos(data):
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(TODOS_STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_todo(text, priority=""):
    """Add a new item to the to-do list. Unlike reminders, this has no
    fire time — it's a plain checklist item to track until marked done.

    Args:
        text: What needs doing, e.g. 'Renew car insurance'
        priority: Optional — 'high', 'medium', 'low', or leave empty

    Returns:
        Confirmation message with the todo id
    """
    todos = load_todos()
    todo_id = uuid.uuid4().hex[:8]
    todos.append({
        "id": todo_id,
        "text": text,
        "priority": priority.lower().strip(),
        "done": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "completed_at": None,
    })
    save_todos(todos)
    tag = f" [{priority}]" if priority else ""
    return f"Added todo{tag}: '{text}' (id: {todo_id})"


def list_todos(include_done=False):
    """List to-do items — pending items by default, optionally including
    completed ones too.

    Args:
        include_done: If True, also show completed items. Default False
                      (pending only).

    Returns:
        A formatted list of todos, or a message if there are none
    """
    todos = load_todos()
    if not include_done:
        todos = [t for t in todos if not t["done"]]

    if not todos:
        return "No pending todos." if not include_done else "No todos at all."

    priority_order = {"high": 0, "medium": 1, "low": 2, "": 3}
    todos.sort(key=lambda t: (t["done"], priority_order.get(t["priority"], 3)))

    lines = []
    for t in todos:
        mark = "[x]" if t["done"] else "[ ]"
        tag = f" ({t['priority']})" if t["priority"] else ""
        lines.append(f"{mark} {t['text']}{tag} — id: {t['id']}")
    return "\n".join(lines)


def complete_todo(todo_id):
    """Mark a to-do item as done.

    Args:
        todo_id: The id shown by list_todos, e.g. 'a1b2c3d4'

    Returns:
        Confirmation message or error
    """
    todos = load_todos()
    match = next((t for t in todos if t["id"] == todo_id), None)
    if not match:
        return f"Error: no todo found with id '{todo_id}'"

    match["done"] = True
    match["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_todos(todos)
    return f"Marked done: '{match['text']}'"


def delete_todo(todo_id):
    """Permanently delete a to-do item, done or not.

    Args:
        todo_id: The id shown by list_todos, e.g. 'a1b2c3d4'

    Returns:
        Confirmation message or error
    """
    todos = load_todos()
    match = next((t for t in todos if t["id"] == todo_id), None)
    if not match:
        return f"Error: no todo found with id '{todo_id}'"

    todos = [t for t in todos if t["id"] != todo_id]
    save_todos(todos)
    return f"Deleted todo: '{match['text']}'"


def clear_completed_todos():
    """Remove all completed to-do items at once, keeping only pending ones.

    Returns:
        Confirmation message with how many were cleared
    """
    todos = load_todos()
    done_count = sum(1 for t in todos if t["done"])
    todos = [t for t in todos if not t["done"]]
    save_todos(todos)
    return f"Cleared {done_count} completed todo(s)."