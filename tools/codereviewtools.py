"""
Code review tools — send a single file or a whole cloned repo's code to a
cloud coder model (Groq or OpenRouter) for review and suggested changes.

Review output is returned as TEXT ONLY — nothing on disk is touched until
the user approves and apply_code_review is called explicitly. This mirrors
the "read before you write" pattern used elsewhere (list_project_files /
read_project_file before write_project_file): the model shows suggestions,
the user decides, then a separate, deliberate write happens.

Operates on files inside a cloned repo (see tools/gittools.py — repos live
under REPOS_DIR) or, for repo_name left empty, any standalone file already
somewhere in the agent folder.
"""

import os

from config import BASE_DIR, REPOS_DIR
from tools.basictools import find_file
from tools.codegentools import call_coder_backend

REVIEW_SYSTEM_PROMPT = (
    "You are an expert code reviewer. Review the code you're given for "
    "bugs, security issues, unclear naming, missing error handling, and "
    "style problems. For each issue: say which file and roughly which "
    "line/function, what's wrong, and a concrete fix. If you're proposing "
    "a rewrite of a full file, put the complete new file content in a "
    "fenced code block labeled with the filename directly above it, so it "
    "can be applied directly. Don't rewrite files that don't need changes, "
    "and don't invent issues just to have something to say."
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
DEFAULT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".rb", ".php", ".html", ".css", ".sql", ".json",
    ".yaml", ".yml", ".md",
}


def _is_inside_base(path):
    return os.path.abspath(path).startswith(os.path.abspath(BASE_DIR))


def _resolve_repo_path(repo_name, relative_path=""):
    """Resolve repo_name (+ optional relative_path within it) to real
    paths, refusing anything that escapes the repo folder via '..' or an
    absolute path. Returns (repo_root, full_path) or (None, None)."""
    repo_root = os.path.abspath(os.path.join(REPOS_DIR, os.path.basename(repo_name)))
    if not _is_inside_base(repo_root):
        return None, None
    full_path = os.path.abspath(os.path.join(repo_root, relative_path)) if relative_path else repo_root
    if not (full_path == repo_root or full_path.startswith(repo_root + os.sep)):
        return None, None
    return repo_root, full_path


def _read_capped(full_path, max_chars=20000):
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError as e:
        return None, f"Error reading {full_path}: {e}"
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n...[truncated, {len(content)} chars total]"
    return content, None


def list_repo_files(repo_name):
    """List every file inside a cloned repo, so you know what's there
    before reviewing or editing anything. Call this before review_repo on
    an unfamiliar repo if you're not sure what paths/extensions exist.

    Args:
        repo_name: The repo folder name under the repos directory (as
                   returned by git_clone)

    Returns:
        A listing of every file's path relative to the repo root
    """
    repo_root, _ = _resolve_repo_path(repo_name)
    if not repo_root or not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."

    lines = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_root = os.path.relpath(root, repo_root)
        for f in sorted(files):
            rel = f if rel_root == "." else os.path.join(rel_root, f)
            lines.append(rel)
    return "\n".join(lines) if lines else "Repo is empty."

def read_repo_file(repo_name, filepath):
    """Read the raw text content of ONE file inside a cloned repo. Use
    this whenever you just need to SEE what's in a file — to explain it,
    summarize it, or decide what to change — not to get review feedback.
    This is the repo equivalent of read_file/read_project_file; those
    tools cannot see inside a cloned repo, only this one can.

    Args:
        repo_name: The repo folder name (from git_clone), e.g.
                   'basic-search-engine'
        filepath: Path to the file relative to the repo root, e.g.
                  'nlp/stemming.py'

    Returns:
        The file's full text content, or an error message
    """
    repo_root, full_path = _resolve_repo_path(repo_name, filepath)
    if not repo_root:
        return f"Error: '{filepath}' escapes the repo folder"
    if not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."
    if not full_path or not os.path.exists(full_path):
        return f"Error: {filepath} not found in repo '{repo_name}'. Call list_repo_files to check the exact path."

    content, err = _read_capped(full_path, max_chars=20000)
    if err:
        return err
    return content

def review_code_file(filepath, repo_name="", instructions="", backend="groq"):
    """Send ONE file to a cloud coder model for review. Works on a file
    inside a cloned repo (pass repo_name + a path relative to the repo
    root) or any standalone file already in the agent folder (leave
    repo_name empty and pass just the filename). This only returns
    suggestions as TEXT — nothing is written to disk. Show the review to
    the user; if they want a suggested rewrite applied, call
    apply_code_review next with the content the model proposed.

    Args:
        filepath: Path to the file. If repo_name is set, this is relative
                  to the repo root, e.g. 'src/utils.py'. Otherwise just
                  the filename, e.g. 'main.py'.
        repo_name: The repo folder name (from git_clone) if this file
                   lives inside a cloned repo. Leave empty otherwise.
        instructions: Optional extra guidance, e.g. 'focus on security'
                      or 'check for race conditions'
        backend: Which cloud model to use — 'groq' (default, fast) or
                 'openrouter'. 'local' works but reviews are weaker.

    Returns:
        The model's review as text, or an error message
    """
    if repo_name:
        repo_root, full_path = _resolve_repo_path(repo_name, filepath)
        if not repo_root:
            return f"Error: '{filepath}' escapes the repo folder"
        if not full_path or not os.path.exists(full_path):
            return f"Error: {filepath} not found in repo '{repo_name}'"
        display_name = f"{repo_name}/{filepath}"
    else:
        full_path = find_file(os.path.basename(filepath))
        if not full_path:
            return f"Error: {filepath} not found anywhere in {BASE_DIR}"
        display_name = os.path.basename(full_path)

    content, err = _read_capped(full_path)
    if err:
        return err

    prompt = (
        f"Review this file: {display_name}\n\n"
        + (f"Focus: {instructions}\n\n" if instructions else "")
        + f"```\n{content}\n```"
    )

    try:
        return call_coder_backend(backend, prompt, system_prompt=REVIEW_SYSTEM_PROMPT)
    except Exception as e:
        return f"Error reviewing {display_name} via {backend}: {str(e)}"


def review_repo(repo_name, instructions="", backend="groq", extensions=None, max_files=40, max_total_chars=60000):
    """Send an entire cloned repo (or a filtered slice of it) to a cloud
    coder model for review. Gathers files up to a size budget, since even
    fast models have context limits — for a huge repo, narrow it with
    'extensions' or review key files individually with review_code_file
    instead. Returns suggestions as TEXT only; nothing is written.

    Args:
        repo_name: The repo folder name under the repos directory (from
                   git_clone)
        instructions: Optional guidance, e.g. 'just check the API routes'
        backend: 'groq' (default) or 'openrouter'
        extensions: Optional list of extensions to include, e.g.
                    ['.py', '.js'] — leave empty for sensible defaults
                    (common source file types, skips binaries/configs)
        max_files: Cap on how many files to include, default 40
        max_total_chars: Cap on total characters sent to the model,
                         default 60000

    Returns:
        The model's review as text, or an error message
    """
    repo_root, _ = _resolve_repo_path(repo_name)
    if not repo_root or not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."

    ext_filter = {e.lower() for e in extensions} if extensions else DEFAULT_EXTENSIONS

    chunks = []
    total_chars = 0
    files_included = 0

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if files_included >= max_files or total_chars >= max_total_chars:
            break
        for fname in sorted(files):
            if files_included >= max_files or total_chars >= max_total_chars:
                break
            _, ext = os.path.splitext(fname)
            if ext.lower() not in ext_filter:
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, repo_root)
            content, err = _read_capped(full_path, max_chars=8000)
            if err or content is None:
                continue
            chunk = f"--- {rel_path} ---\n{content}"
            if total_chars + len(chunk) > max_total_chars:
                remaining = max_total_chars - total_chars
                if remaining <= 200:
                    break
                chunk = chunk[:remaining] + "\n...[truncated]"
            chunks.append(chunk)
            total_chars += len(chunk)
            files_included += 1

    if not chunks:
        return f"No reviewable files found in '{repo_name}' (checked extensions: {sorted(ext_filter)})"

    prompt = (
        f"Review this repository ({files_included} file(s) shown, repo: {repo_name}).\n\n"
        + (f"Focus: {instructions}\n\n" if instructions else "")
        + "\n\n".join(chunks)
    )

    try:
        review = call_coder_backend(backend, prompt, system_prompt=REVIEW_SYSTEM_PROMPT)
    except Exception as e:
        return f"Error reviewing repo '{repo_name}' via {backend}: {str(e)}"

    note = (
        f"\n\n[Reviewed {files_included} file(s), ~{total_chars} chars — the repo may have more "
        f"files than fit here; narrow with 'extensions' or review individually for full coverage.]"
    )
    return review + note


def apply_code_review(repo_name, filepath, new_content):
    """Overwrite one file inside a cloned repo with reviewed/corrected
    content — use this ONLY after showing the review to the user and
    getting their go-ahead on a specific rewrite. This performs a real
    overwrite, so pass the COMPLETE intended file content, not a diff or
    a partial snippet. Follow up with git_diff/git_status if the user
    wants to sanity-check what changed before committing.

    Args:
        repo_name: The repo folder name under the repos directory
        filepath: Path to the file relative to the repo root, e.g.
                  'src/utils.py' — the file must already exist (this
                  applies a reviewed rewrite, it doesn't create new files)
        new_content: The full new content to write

    Returns:
        Confirmation message with the file path, or an error message
    """
    repo_root, full_path = _resolve_repo_path(repo_name, filepath)
    if not repo_root:
        return f"Error: '{filepath}' escapes the repo folder"
    if not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."
    if full_path is None or not os.path.exists(full_path):
        return f"Error: {filepath} not found in repo '{repo_name}' — apply_code_review only overwrites existing files."

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return f"Applied review changes to: {full_path}"