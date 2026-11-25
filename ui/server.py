"""
Lightweight local web UI for Lapis, streamed over Server-Sent Events (SSE).

Mirrors the loop in agent.run_agent_multiturn — same tool dispatch, same
repeated-call loop guard, same context-limit check — just re-expressed as
a generator so a browser tab can watch it happen live instead of reading
it off stdout. The CLI (`python main.py convo`) still works exactly as
before; this is an additional, optional way in.

Run with:  python -m ui.server
Then open: http://127.0.0.1:5000
"""

import json
import os
import threading
import webbrowser

import ollama
from flask import Flask, Response, request, send_from_directory

from config import (
    MODEL, OPENROUTER_API_KEY, GROQ_API_KEY, get_sysprompt, TOOLS,
    CODER_BACKEND_TOOLS, TOOL_CATEGORIES, TOOL_CATEGORY_META, DEFAULT_CATEGORIES,
)
from utilities import deploy_tool, extract_tool_calls
from agent import build_active_tools

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")

CTX_LIMIT = 16000
REPEAT_LIMIT = 2

# NOTE: single global conversation, same as the CLI — Lapis is a personal,
# single-user assistant, so there's no session/auth layer here. If you
# ever expose this beyond localhost, that assumption needs revisiting.
state = {
    "messages": [{"role": "system", "content": get_sysprompt(coder_backend="local")}],
    "coder_backend": "local",
    "active_categories": set(DEFAULT_CATEGORIES),
    "total_in": 0,
    "total_out": 0,
    "recent_calls": [],
}
state_lock = threading.Lock()


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _backend_available(backend):
    if backend == "openrouter":
        return bool(OPENROUTER_API_KEY)
    if backend == "groq":
        return bool(GROQ_API_KEY)
    return True  # local always available


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/state")
def get_state():
    with state_lock:
        return {
            "coder_backend": state["coder_backend"],
            "active_categories": sorted(state["active_categories"]),
            "total_in": state["total_in"],
            "total_out": state["total_out"],
            "openrouter_available": bool(OPENROUTER_API_KEY),
            "groq_available": bool(GROQ_API_KEY),
        }


@app.route("/api/tool-categories")
def get_tool_categories():
    """Returns the full category catalog (id/label/logo placeholder) plus
    which ones are currently active, so the composer dropdown can render
    itself without hardcoding the category list client-side."""
    with state_lock:
        active = sorted(state["active_categories"])
    return {"categories": TOOL_CATEGORY_META, "active": active}


@app.route("/api/toggle-categories", methods=["POST"])
def toggle_categories():
    """Replaces the active tool-category set wholesale with whatever the
    dropdown currently has checked. Unknown ids are silently dropped
    rather than erroring, since the frontend and TOOL_CATEGORIES should
    always agree — but a stale client shouldn't be able to smuggle in an
    unrecognized category name."""
    categories = (request.json or {}).get("categories", [])
    valid = set(TOOL_CATEGORIES.keys())
    selected = {c for c in categories if c in valid}
    with state_lock:
        state["active_categories"] = selected
    return {"ok": True, "active": sorted(selected)}


@app.route("/api/clear", methods=["POST"])
def clear():
    with state_lock:
        state["coder_backend"] = "local"
        state["active_categories"] = set(DEFAULT_CATEGORIES)
        state["messages"] = [{"role": "system", "content": get_sysprompt(coder_backend="local")}]
        state["total_in"] = 0
        state["total_out"] = 0
        state["recent_calls"] = []
    return {"ok": True}


@app.route("/api/toggle-coder", methods=["POST"])
def toggle_coder():
    backend = (request.json or {}).get("coder_backend", "local")
    if backend not in CODER_BACKEND_TOOLS:
        return {"ok": False, "error": f"Unknown coder_backend '{backend}'"}, 400
    if not _backend_available(backend):
        missing = "OPENROUTER_API_KEY" if backend == "openrouter" else "GROQ_API_KEY"
        return {"ok": False, "error": f"{missing} not set in .env"}, 400

    with state_lock:
        state["coder_backend"] = backend
        state["messages"][0]["content"] = get_sysprompt(coder_backend=backend)
    return {"ok": True}


def _stream_one_model_turn(messages, tools, options):
    """Streams one model turn. Yields SSE-ready (event, data) tuples for
    text tokens as they arrive. Returns the fully assembled message dict
    (with tool_calls if any) via the mutable `result` holder, since
    generators can't both yield and return a value cleanly pre-3.3-style."""
    stream = ollama.chat(
        model=MODEL,
        messages=messages,
        tools=tools,
        options=options,
        stream=True,
        keep_alive="10m",
    )

    accumulated_content = ""
    final_message = None
    usage = {"prompt_eval_count": 0, "eval_count": 0}

    for chunk in stream:
        piece = chunk.message.content or ""
        if piece:
            accumulated_content += piece
            yield ("token", {"text": piece})

        # tool_calls, when present, land on the message object directly —
        # Ollama doesn't stream them incrementally, they arrive whole.
        if chunk.message.tool_calls:
            final_message = chunk.message

        if chunk.done:
            usage["prompt_eval_count"] = chunk.prompt_eval_count or 0
            usage["eval_count"] = chunk.eval_count or 0
            if final_message is None:
                final_message = chunk.message
                if not final_message.content:
                    final_message.content = accumulated_content

    yield ("__final__", {"message": final_message, "usage": usage})


@app.route("/api/chat", methods=["POST"])
def chat():
    user_text = (request.json or {}).get("message", "").strip()
    if not user_text:
        return {"error": "empty message"}, 400

    def generate():
        with state_lock:
            state["messages"].append({"role": "user", "content": f"/no_think {user_text}"})
            coder_backend = state["coder_backend"]
            active_categories = set(state["active_categories"])

        tools = build_active_tools(coder_backend, active_categories)
        allowed_names = {t.__name__ for t in tools}
        options = {"num_predict": 4096, "think": False, "num_ctx": CTX_LIMIT, "repeat_penalty": 1.15}

        try:
            while True:
                final_message = None
                usage = None

                for event, data in _stream_one_model_turn(state["messages"], tools, options):
                    if event == "token":
                        yield _sse("token", data)
                    elif event == "__final__":
                        final_message = data["message"]
                        usage = data["usage"]

                with state_lock:
                    state["messages"].append(final_message)
                    state["total_in"] = usage["prompt_eval_count"] or state["total_in"]
                    state["total_out"] += usage["eval_count"] or 0

                if state["total_in"] >= CTX_LIMIT:
                    yield _sse("error", {"message": "Context limit reached. Click Clear to start a new session."})
                    yield _sse("done", {})
                    return

                tool_calls = final_message.tool_calls
                if not tool_calls:
                    fake_calls = extract_tool_calls(final_message.content or "")
                    if fake_calls:
                        for name, args in fake_calls:
                            yield _sse("tool_call", {"name": name, "args": args})
                            result = deploy_tool(name, args, allowed_names=allowed_names)
                            with state_lock:
                                state["messages"].append({"role": "tool", "content": result})
                            yield _sse("tool_result", {"name": name, "result": str(result)[:2000]})
                        continue
                    yield _sse("done", {})
                    return

                stuck = False
                for call in tool_calls:
                    name = call.function.name
                    args = call.function.arguments
                    signature = (name, str(args))

                    with state_lock:
                        state["recent_calls"].append(signature)
                        state["recent_calls"] = state["recent_calls"][-6:]
                        repeat_count = state["recent_calls"].count(signature)

                    if repeat_count > REPEAT_LIMIT:
                        with state_lock:
                            state["messages"].append({
                                "role": "tool",
                                "content": (
                                    f"STOP: You already called {name} with these exact arguments "
                                    f"and it succeeded. Do not repeat it. Move on or report success."
                                ),
                            })
                        yield _sse("warning", {"message": f"Blocked repeated call to {name} — nudged the model to move on."})
                        if repeat_count > REPEAT_LIMIT + 2:
                            stuck = True
                        continue

                    yield _sse("tool_call", {"name": name, "args": args})
                    result = deploy_tool(name, args, allowed_names=allowed_names)
                    with state_lock:
                        state["messages"].append({"role": "tool", "content": result})
                    yield _sse("tool_result", {"name": name, "result": str(result)[:2000]})

                if stuck:
                    yield _sse("error", {"message": "Model appears stuck repeating the same tool call. Try rephrasing."})
                    yield _sse("done", {})
                    return
                # loop again — model gets tool results and continues

        except Exception as e:
            yield _sse("error", {"message": str(e)})
            yield _sse("done", {})

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


def run_ui(host="127.0.0.1", port=5000, open_browser=True):
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    run_ui()