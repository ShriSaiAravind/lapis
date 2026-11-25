import os
from config import OLLAMA_API_KEY
os.environ["OLLAMA_API_KEY"] = OLLAMA_API_KEY

import ollama
from ollama import web_fetch, web_search
from config import MODEL, CODER_MODEL, get_sysprompt, OPENROUTER_API_KEY, GROQ_API_KEY, CODER_MODEL_GROQ
from config import TOOLS, CODER_BACKEND_TOOLS, TOOL_CATEGORIES, DEFAULT_CATEGORIES
from utilities import deploy_tool, extract_tool_calls

import threading
import itertools
import time
from rich.console import Console
from rich.markdown import Markdown

console = Console()

# Set based on your actual measured VRAM fit — with OLLAMA_KV_CACHE_TYPE=q8_0
# and qwen2.5-coder:7b, 16000 was the tested value. Adjust if you switch
# models or requantize; verify with `ollama ps` after a real task.
CTX_LIMIT = 16000

SPINNER_PHRASES = [
    "cooking up a response...",
    "thinking hard...",
    "giving you the best answer...",
    "on it...",
    "brewing something good...",
    "connecting the dots...",
    "working my magic...",
    "almost there...",
]

SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def run_spinner(stop_event):
    phrase_cycle = itertools.cycle(SPINNER_PHRASES)
    char_cycle = itertools.cycle(SPINNER_CHARS)
    phrase = next(phrase_cycle)
    phrase_timer = time.time()
    while not stop_event.is_set():
        if time.time() - phrase_timer > 3:
            phrase = next(phrase_cycle)
            phrase_timer = time.time()
        char = next(char_cycle)
        line = f"{char} {phrase}"
        print(f"\r{line:<50}", end="", flush=True)
        time.sleep(0.1)
    print("\r" + " " * 50 + "\r", end="", flush=True)


def chat_with_spinner(messages, tools, options, keep_alive):
    result = [None]
    error = [None]

    def target():
        try:
            result[0] = ollama.chat(
                model=MODEL,
                messages=messages,
                tools=tools,
                options=options,
                keep_alive=keep_alive,
            )
        except Exception as e:
            error[0] = e

    stop_event = threading.Event()
    spinner_thread = threading.Thread(target=run_spinner, args=(stop_event,), daemon=True)
    spinner_thread.start()

    t = threading.Thread(target=target)
    t.start()
    t.join()

    stop_event.set()
    spinner_thread.join()

    if error[0]:
        raise error[0]
    return result[0]


def build_active_tools(coder_backend: str, active_categories=None):
    """Builds the tool list actually exposed to the model this turn.

    Filters on two axes:
      1. Coder backend — exactly one of generate_and_write_code /
         generate_and_write_code_api / generate_and_write_code_groq stays,
         per CODER_BACKEND_TOOLS, same as before.
      2. Tool categories — only tools belonging to an active category are
         included at all. This is the actual token-shaving part: a tool
         that's filtered out here never gets its docstring/schema sent to
         the model, instead of always paying for every tool's schema on
         every single turn regardless of whether the session ever touches
         Spotify, git, etc.

    active_categories defaults to DEFAULT_CATEGORIES if not given.
    web_search/web_fetch are always appended — not gated behind a
    category toggle.
    """
    if active_categories is None:
        active_categories = DEFAULT_CATEGORIES

    active_coder_name = CODER_BACKEND_TOOLS.get(coder_backend, "generate_and_write_code")
    excluded_coder_names = set(CODER_BACKEND_TOOLS.values()) - {active_coder_name}

    allowed_names = set()
    for cat in active_categories:
        allowed_names.update(TOOL_CATEGORIES.get(cat, []))
    allowed_names -= excluded_coder_names

    tools = [t for t in TOOLS.values() if t.__name__ in allowed_names]
    return tools + [web_search, web_fetch]


def run_agent(task: str):

    messages = [
        {"role": "system", "content": get_sysprompt()},
        {"role": "user", "content": f"/no_think {task}"},
    ]

    # Single-shot CLI invocation (`lapis "do x"`) has no interactive
    # session to toggle categories in — always runs with the defaults.
    active_categories = set(DEFAULT_CATEGORIES)

    while True:
        tools = build_active_tools("local", active_categories)
        allowed_names = {t.__name__ for t in tools}

        response = chat_with_spinner(
            messages=messages,
            tools=tools,
            options={"num_predict": 4096, "think": False, "num_ctx": CTX_LIMIT},
            keep_alive="2m",
        )

        msg = response.message
        messages.append(msg)

        if msg.tool_calls:
            for call in msg.tool_calls:
                name = call.function.name
                args = call.function.arguments
                console.print(f"[dim]⚙ {name}({args})[/dim]")
                result = deploy_tool(name, args, allowed_names=allowed_names)
                messages.append({"role": "tool", "content": result})

        else:
            calls = extract_tool_calls(msg.content or "")
            if calls:
                for name, args in calls:
                    console.print(f"[dim]⚙ [FAKE] {name}({args})[/dim]")
                    result = deploy_tool(name, args, allowed_names=allowed_names)
                    messages.append({"role": "tool", "content": result})
                continue
            console.print(Markdown(msg.content))
            break

    ollama.chat(model=MODEL, messages=[], keep_alive=0)


def _print_category_help():
    console.print("\n[bold]Tool categories:[/bold]")
    for cat, names in TOOL_CATEGORIES.items():
        console.print(f"  [cyan]{cat:<11}[/cyan] — {', '.join(names)}")
    console.print()


def run_agent_multiturn() -> None:
    coder_backend = "local"
    active_categories = set(DEFAULT_CATEGORIES)
    messages = [
        {"role": "system", "content": get_sysprompt(coder_backend=coder_backend)},
    ]

    total_in = 0
    total_out = 0

    print(
        "what we doin?? type 'exit' to quit, 'clear' to reset conversation, "
        "'usage' to see token count, 'use local' / 'use openrouter' / 'use groq' "
        "to switch coder backend, 'tools' to see active/available tool categories, "
        "'enable <category>' / 'disable <category>' to change which tools are exposed "
        "to the model this session, 'help' for the full command list.\n"
    )

    while True:
        try:
            task = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break

        if not task:
            continue

        low = task.lower()

        if low in ("exit", "quit", "q"):
            print("bye")
            break

        if low == "clear":
            coder_backend = "local"
            active_categories = set(DEFAULT_CATEGORIES)
            messages = [{"role": "system", "content": get_sysprompt(coder_backend=coder_backend)}]
            total_in = 0
            total_out = 0
            print("Conversation cleared.\n")
            continue

        if low == "usage":
            print(f"Tokens so far: {total_in} in / {total_out} out\n")
            continue

        if low == "help":
            print(
                "Commands:\n"
                "  exit / quit / q      — quit Lapis\n"
                "  clear                — reset conversation, coder backend, and tool categories\n"
                "  usage                — show token usage so far\n"
                "  use local            — switch coder backend to local qwen2.5-coder:7b\n"
                "  use openrouter       — switch coder backend to OpenRouter (needs OPENROUTER_API_KEY)\n"
                "  use groq             — switch coder backend to Groq (needs GROQ_API_KEY)\n"
                "  tools                — list active and available tool categories\n"
                "  enable <category>    — add a tool category to this session\n"
                "  disable <category>   — remove a tool category from this session\n"
                "  help                 — show this message\n"
            )
            _print_category_help()
            print(f"Currently active categories: {sorted(active_categories)}\n")
            continue

        if low == "tools":
            print(f"Active categories:    {sorted(active_categories)}")
            print(f"Available categories: {sorted(TOOL_CATEGORIES.keys())}")
            print("Use 'enable <category>' / 'disable <category>' to change this, or 'help' for details.\n")
            continue

        if low.startswith("enable "):
            cat = low[len("enable "):].strip()
            if cat not in TOOL_CATEGORIES:
                print(f"Unknown category '{cat}'. Available: {sorted(TOOL_CATEGORIES.keys())}\n")
            elif cat in active_categories:
                print(f"'{cat}' is already enabled.\n")
            else:
                active_categories.add(cat)
                print(f"Enabled '{cat}'. Active categories: {sorted(active_categories)}\n")
            continue

        if low.startswith("disable "):
            cat = low[len("disable "):].strip()
            if cat not in TOOL_CATEGORIES:
                print(f"Unknown category '{cat}'. Available: {sorted(TOOL_CATEGORIES.keys())}\n")
            elif cat not in active_categories:
                print(f"'{cat}' is already disabled.\n")
            else:
                active_categories.discard(cat)
                print(f"Disabled '{cat}'. Active categories: {sorted(active_categories)}\n")
            continue

        if low in ("use openrouter", "use api key"):
            if not OPENROUTER_API_KEY:
                print("Error: OPENROUTER_API_KEY not set in .env — can't switch to OpenRouter coder.\n")
                continue
            coder_backend = "openrouter"
            messages[0]["content"] = get_sysprompt(coder_backend=coder_backend)
            print("Switched to OpenRouter coder. Say 'use local' or 'use groq' to switch again.\n")
            continue
        if low == "use groq":
            if not GROQ_API_KEY:
                print("Error: GROQ_API_KEY not set in .env — can't switch to Groq coder.\n")
                continue
            coder_backend = "groq"
            messages[0]["content"] = get_sysprompt(coder_backend=coder_backend)
            print(f"Switched to Groq coder ({CODER_MODEL_GROQ}). Say 'use local' or 'use openrouter' to switch again.\n")
            continue
        if low == "use local":
            coder_backend = "local"
            messages[0]["content"] = get_sysprompt(coder_backend=coder_backend)
            print(f"Switched back to local coder ({CODER_MODEL}).\n")
            continue

        messages.append({"role": "user", "content": f"/no_think {task}"})

        # Tracks the last few (name, args) signatures so we can detect a
        # model looping on an identical tool call instead of moving on.
        recent_calls = []
        REPEAT_LIMIT = 2  # allow the same call twice, block the 3rd

        while True:
            tools = build_active_tools(coder_backend, active_categories)
            allowed_names = {t.__name__ for t in tools}

            response = chat_with_spinner(
                messages=messages,
                tools=tools,
                options={"num_predict": 4096, "think": False, "num_ctx": CTX_LIMIT, "repeat_penalty": 1.15},
                keep_alive="10m",
            )

            msg = response.message
            total_in = response.prompt_eval_count or total_in
            total_out += response.eval_count or 0
            messages.append(msg)

            if total_in >= CTX_LIMIT:
                print("Context limit reached. Type 'clear' to start a new session.\n")
                break

            if msg.tool_calls:
                stuck = False
                for call in msg.tool_calls:
                    name = call.function.name
                    args = call.function.arguments
                    signature = (name, str(args))

                    recent_calls.append(signature)
                    recent_calls = recent_calls[-6:]  # keep it bounded

                    if recent_calls.count(signature) > REPEAT_LIMIT:
                        console.print(
                            f"[yellow]⚠ Detected repeated identical call to {name} — "
                            f"blocking to break loop[/yellow]"
                        )
                        messages.append({
                            "role": "tool",
                            "content": (
                                f"STOP: You already called {name} with these exact arguments "
                                f"and it succeeded. Do not repeat it. Move on to the next step "
                                f"in your plan, or if the task is complete, report success to the user."
                            ),
                        })
                        # if it's still repeating after the STOP correction,
                        # the model is genuinely stuck — don't just contain
                        # it forever, bail out of the turn entirely
                        if recent_calls.count(signature) > REPEAT_LIMIT + 2:
                            stuck = True
                        continue

                    console.print(f"[dim]⚙ {name}({args})[/dim]")
                    result = deploy_tool(name, args, allowed_names=allowed_names)

                    console.print("[cyan]----- TOOL RETURN -----[/cyan]")
                    print(repr(result))
                    console.print("[cyan]-----------------------[/cyan]")

                    messages.append({"role": "tool", "content": result})

                if stuck:
                    console.print(
                        "[red]⚠ Model appears stuck repeating the same tool call — "
                        "ending this turn. Try rephrasing your request or breaking it "
                        "into smaller steps.[/red]"
                    )
                    break
                continue

            fake_calls = extract_tool_calls(msg.content or "")
            if fake_calls:
                for name, args in fake_calls:
                    signature = (name, str(args))
                    recent_calls.append(signature)
                    recent_calls = recent_calls[-6:]

                    if recent_calls.count(signature) > REPEAT_LIMIT:
                        console.print(
                            f"[yellow]⚠ Detected repeated identical call to {name} — "
                            f"blocking to break loop[/yellow]"
                        )
                        messages.append({
                            "role": "tool",
                            "content": (
                                f"STOP: You already called {name} with these exact arguments "
                                f"and it succeeded. Do not repeat it. Move on to the next step "
                                f"in your plan, or if the task is complete, report success to the user."
                            ),
                        })
                        continue

                    console.print(f"[dim]⚙ [FAKE] {name}({args})[/dim]")
                    result = deploy_tool(name, args, allowed_names=allowed_names)
                    messages.append({"role": "tool", "content": result})
                continue

            console.print(Markdown(msg.content))
            print()
            break

    ollama.chat(model=MODEL, messages=[], keep_alive=0)
    print(f"Total tokens: {total_in} in / {total_out} out")