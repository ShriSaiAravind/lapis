"""
Delegates code generation to a stronger coder-specific model for tasks the
primary orchestrator model (qwen3:4b-instruct) struggles with — medium-sized
projects, harder LeetCode problems, anything needing real reasoning about
code rather than boilerplate. Three interchangeable backends:

  - local:      qwen2.5-coder:7b via Ollama, no network, no API key
  - openrouter: openai/gpt-oss-20b:free (with an 'openrouter/free' fallback)
  - groq:       qwen/qwen3.6-27b via GroqCloud's OpenAI-compatible endpoint,
                fast and free-tier friendly

generate_and_write_code / _api / _groq each write the coder model's output
directly to disk themselves, rather than returning it as text for the
orchestrator to retype into write_file/write_project_file. This matters: on
a small orchestrator model, retyping a large code block from context is
unreliable — lines get dropped, comprehensions get mangled, and past a
certain distance in the conversation the model starts reconstructing from
memory instead of copying exactly. Writing deterministically in Python
removes that failure mode completely, since neither model is responsible
for faithfully reproducing the code — the coder model generates it once,
and this function is the only thing that ever touches the file.

call_coder_backend() is the shared dispatcher — it's also used directly by
tools/codereviewtools.py, since code review needs the same three backends
but returns raw text instead of writing a file.
"""

import re
import ollama
import requests

from config import (
    MODEL, CODER_MODEL,
    OPENROUTER_API_KEY, CODER_MODEL_API, OPENROUTER_URL, CODER_MODEL_API_FALLBACK,
    GROQ_API_KEY, CODER_MODEL_GROQ, GROQ_URL,
)
from tools.basictools import write_file
from tools.projecttools import write_project_file


CODER_SYSTEM_PROMPT = (
    "You are an expert software engineer. Write correct, complete, working "
    "code for the following task. Do not explain unless asked. Return the "
    "full code in a single fenced code block, with necessary imports. If "
    "it's a LeetCode-style problem, instantiate the Solution class and "
    "print a call with example input so it's runnable as-is."
)


def _strip_code_fence(text):
    """Extract code from a single markdown fence if present, otherwise
    return the text unchanged."""
    match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _post_to_openai_compatible(url, api_key, model_id, task_description, system_prompt=None, max_tokens=4000, timeout=60):
    """Shared caller for any OpenAI-chat-completions-compatible endpoint —
    covers both OpenRouter and Groq, since Groq's /openai/v1 endpoint uses
    the exact same request/response shape."""
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt or CODER_SYSTEM_PROMPT},
                {"role": "user", "content": task_description},
            ],
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{url} error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    message = data.get("choices", [{}])[0].get("message", {})
    content = message.get("content") or message.get("reasoning")
    if not content:
        raise RuntimeError(f"Empty response from {data.get('model', model_id)} — raw: {message}")

    print(f"  (routed to: {data.get('model', model_id)})")
    return content


def _call_local(task_description, system_prompt=None):
    ollama.chat(model=MODEL, messages=[], keep_alive=0)

    response = ollama.chat(
        model=CODER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt or CODER_SYSTEM_PROMPT},
            {"role": "user", "content": task_description},
        ],
        options={"num_predict": 2000, "num_ctx": 4000},
        keep_alive=0,
    )
    return response.message.content


def _call_openrouter(task_description, system_prompt=None):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env — OpenRouter coder requires it.")
    try:
        return _post_to_openai_compatible(OPENROUTER_URL, OPENROUTER_API_KEY, CODER_MODEL_API, task_description, system_prompt=system_prompt)
    except RuntimeError as e:
        print(f"  ({CODER_MODEL_API} failed ({e}) — falling back to {CODER_MODEL_API_FALLBACK})")
        return _post_to_openai_compatible(OPENROUTER_URL, OPENROUTER_API_KEY, CODER_MODEL_API_FALLBACK, task_description, system_prompt=system_prompt)


def _call_groq(task_description, system_prompt=None):
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in .env — Groq coder requires it.")
    # qwen/qwen3.6-27b supports a larger output budget than the free
    # OpenRouter models above; give it more room, especially useful for
    # whole-repo review responses.
    return _post_to_openai_compatible(GROQ_URL, GROQ_API_KEY, CODER_MODEL_GROQ, task_description, system_prompt=system_prompt, max_tokens=6000)


def call_coder_backend(backend, task_description, system_prompt=None):
    """Single dispatcher across all three coder backends. Returns raw
    model output (NOT code-fence-stripped) — callers that want a file's
    worth of code should strip fences themselves via _strip_code_fence;
    callers that want prose (like code review) can use the text as-is.

    Args:
        backend: 'local', 'openrouter', or 'groq'
        task_description: the user-turn content sent to the coder model
        system_prompt: optional override of CODER_SYSTEM_PROMPT

    Returns:
        The model's raw text response

    Raises:
        RuntimeError if the backend's required API key is missing, or the
        request itself fails
    """
    backend = (backend or "local").lower()
    if backend == "groq":
        return _call_groq(task_description, system_prompt)
    if backend == "openrouter":
        return _call_openrouter(task_description, system_prompt)
    if backend == "local":
        return _call_local(task_description, system_prompt)
    raise RuntimeError(f"Unknown coder backend '{backend}' — use 'local', 'openrouter', or 'groq'.")


def generate_and_write_code(task_description, filename, project_name=None, subfolder=""):
    """Delegate a coding task to a stronger LOCAL coder-specific model
    (qwen2.5-coder:7b, via Ollama) and write its output DIRECTLY to disk —
    no retyping involved. Use this instead of writing code yourself for
    anything beyond basic boilerplate: medium-sized projects, non-trivial
    algorithms, or hard LeetCode-style problems.

    Args:
        task_description: A clear, complete description of what code to
                           write — language, requirements, constraints,
                           function signatures if relevant. If this file
                           depends on another file already written in the
                           same project, first call read_project_file on
                           that file and include the relevant parts
                           (imports, class names, function signatures)
                           directly in this description.
        filename: The filename to write, e.g. 'routes.py' or
                  'threesum.py'. For project files, use just the filename
                  — do not include the project folder in the path.
        project_name: ONLY set this if the file is one part of a
                      multi-file project already created with
                      create_project (e.g. a Flask app with routes.py,
                      models.py, etc.). For a single standalone file like
                      one LeetCode solution — even if the user says "put
                      it in the X folder" — that is just a folder, use
                      subfolder instead, NOT project_name. Do not call
                      create_project just to satisfy this parameter.
        subfolder: Use this for a single standalone file, including
                   LeetCode/competitive-programming solutions, when the
                   user names a folder to save it in (e.g. "save it in
                   the leetcode folder" → subfolder='leetcode'). Leave
                   empty to save to the file's existing location or the
                   default notes folder. Do not set both project_name and
                   subfolder.
    """
    try:
        code = _strip_code_fence(call_coder_backend("local", task_description))
    except Exception as e:
        return f"Error generating code with {CODER_MODEL}: {str(e)}"

    if project_name:
        return write_project_file(project_name, filename, code)
    return write_file(filename, code, subfolder=subfolder)


def generate_and_write_code_api(task_description, filename, project_name=None, subfolder=""):
    """Delegate a coding task to a cloud-hosted, much larger coder model
    (Qwen3 Coder 480B via OpenRouter's free tier) and write its output
    DIRECTLY to disk — same behavior as generate_and_write_code, but using
    a far stronger model over the network instead of your local 7B model.
    No local VRAM impact, no model swap. Free tier: 50 requests/day (1000
    after a one-time $10 credit top-up), 20 requests/minute.

    Args:
        task_description: A clear, complete description of what code to
                           write — same guidance as generate_and_write_code.
        filename: The filename to write, e.g. 'routes.py'.
        project_name: If part of a project created with create_project.
        subfolder: For standalone files only, not project files.

    Returns:
        Confirmation message with the file path, or an error message
    """
    try:
        code = _strip_code_fence(call_coder_backend("openrouter", task_description))
    except Exception as e:
        return f"Error generating code via OpenRouter ({CODER_MODEL_API}): {str(e)}"

    if project_name:
        return write_project_file(project_name, filename, code)
    return write_file(filename, code, subfolder=subfolder)


def generate_and_write_code_groq(task_description, filename, project_name=None, subfolder=""):
    """Delegate a coding task to Qwen 3.6 27B on GroqCloud and write its
    output DIRECTLY to disk — same behavior as generate_and_write_code,
    but using Groq's hosted inference (very fast, generous free tier)
    instead of your local 7B model. Requires GROQ_API_KEY in .env.

    Args:
        task_description: A clear, complete description of what code to
                           write — same guidance as generate_and_write_code.
        filename: The filename to write, e.g. 'routes.py'.
        project_name: If part of a project created with create_project.
        subfolder: For standalone files only, not project files.

    Returns:
        Confirmation message with the file path, or an error message
    """
    try:
        code = _strip_code_fence(call_coder_backend("groq", task_description))
    except Exception as e:
        return f"Error generating code via Groq ({CODER_MODEL_GROQ}): {str(e)}"

    if project_name:
        return write_project_file(project_name, filename, code)
    return write_file(filename, code, subfolder=subfolder)


# def generate_code_with_coder(task_description):
#     """Delegate a coding task to a stronger coder-specific model
#     (qwen2.5-coder:7b) and get the code back as text, WITHOUT writing it
#     to a file. Only use this if you specifically need to inspect, modify,
#     or combine the code before deciding where it goes — otherwise prefer
#     generate_and_write_code, which writes it directly and avoids retyping
#     errors.

#     Args:
#         task_description: A clear, complete description of what code to
#                            write.

#     Returns:
#         The generated code as text, with markdown fences already stripped
#     """
#     try:
#         return _strip_code_fence(call_coder_backend("local", task_description))
#     except Exception as e:
#         return f"Error generating code with {CODER_MODEL}: {str(e)}"