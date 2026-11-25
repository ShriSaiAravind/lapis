"""
Git tools — clone, commit, push/pull for repos kept under REPOS_DIR
(BASE_DIR/repos). Shells out to the real git CLI via subprocess, same
pattern as run_python_file/run_project_entrypoint — no GitPython
dependency needed for what these cover.

These are real, mutating git operations (commit/push especially) — the
sysprompt tells the model to only call git_commit/git_push when the user
actually asked for them, but that's a prompt-level convention, not
enforced here the way the risky-keyword gate covers basictools/apptools.
"""

import os
import re
import subprocess

from config import BASE_DIR, REPOS_DIR


def _is_inside_base(path):
    return os.path.abspath(path).startswith(os.path.abspath(BASE_DIR))


def _repo_root(repo_name):
    return os.path.abspath(os.path.join(REPOS_DIR, os.path.basename(repo_name)))


def _run_git(args, cwd, timeout=60):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, "Error: git is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return None, f"Error: git {' '.join(args)} timed out after {timeout}s"

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return None, f"Error running git {' '.join(args)}: {output.strip()[:800]}"
    return output.strip(), None


def _default_repo_name_from_url(repo_url):
    name = repo_url.rstrip("/").split("/")[-1]
    return re.sub(r"\.git$", "", name)


def git_clone(repo_url, folder_name=""):
    """Clone a git repository into the repos folder, so it can be
    reviewed, edited, and committed to. Use review_repo/review_code_file
    afterward to look at the code, and git_commit/git_push once changes
    are made and approved.

    Args:
        repo_url: The repository URL, e.g.
                  'https://github.com/owner/repo.git'
        folder_name: Optional local folder name to clone into — leave
                     empty to use the repo's own name from the URL

    Returns:
        Confirmation message with the repo_name to use for further
        review/git calls, or an error message
    """
    folder_name = os.path.basename(folder_name) if folder_name else _default_repo_name_from_url(repo_url)
    target = _repo_root(folder_name)

    if not _is_inside_base(target):
        return f"Error: cannot clone outside {BASE_DIR}"
    if os.path.exists(target):
        return f"Error: '{folder_name}' already exists at {target} — use a different folder_name, or git_pull if you just want to update it."

    os.makedirs(REPOS_DIR, exist_ok=True)
    output, err = _run_git(["clone", repo_url, target], cwd=REPOS_DIR, timeout=180)
    if err:
        return err
    return f"Cloned {repo_url} into {target}. Use repo_name='{folder_name}' for every further review/git call on it."


def git_status(repo_name):
    """Show the working tree status of a cloned repo — changed, staged,
    and untracked files. Check this before committing to see what will
    actually be included.

    Args:
        repo_name: The repo folder name (from git_clone)

    Returns:
        The output of 'git status', or an error message
    """
    repo_root = _repo_root(repo_name)
    if not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."
    output, err = _run_git(["status", "--short", "--branch"], cwd=repo_root)
    if err:
        return err
    return output if output else "Working tree clean — nothing to commit."


def git_diff(repo_name, filepath=""):
    """Show unstaged changes in a cloned repo, optionally scoped to one
    file. Useful to sanity-check edits before committing, including
    edits made via apply_code_review.

    Args:
        repo_name: The repo folder name (from git_clone)
        filepath: Optional path relative to the repo root to scope the
                  diff to one file

    Returns:
        The diff output, or a message if there are no changes
    """
    repo_root = _repo_root(repo_name)
    if not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."
    args = ["diff"] + ([filepath] if filepath else [])
    output, err = _run_git(args, cwd=repo_root)
    if err:
        return err
    max_chars = 4000
    if output and len(output) > max_chars:
        output = output[:max_chars] + f"\n...[truncated, {len(output)} chars total]"
    return output if output else "No changes."


def git_commit(repo_name, message, add_all=True):
    """Stage and commit changes in a cloned repo. This performs a real
    commit — only call this when the user has actually asked for a
    commit, not automatically after every file edit.

    Args:
        repo_name: The repo folder name (from git_clone)
        message: The commit message
        add_all: If True (default), stages all changes ('git add -A')
                 before committing. If False, only already-staged changes
                 are committed.

    Returns:
        Confirmation message with the commit output, or an error message
    """
    repo_root = _repo_root(repo_name)
    if not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."

    if add_all:
        _, err = _run_git(["add", "-A"], cwd=repo_root)
        if err:
            return err

    output, err = _run_git(["commit", "-m", message], cwd=repo_root)
    if err:
        return err
    return f"Committed in '{repo_name}': {output}"


def git_push(repo_name, remote="origin", branch=""):
    """Push committed changes to a remote. Requires the repo to already
    have credentials configured for the remote (credential manager, SSH
    key, or a token embedded in the remote URL) — this tool does not
    handle authentication itself.

    Args:
        repo_name: The repo folder name (from git_clone)
        remote: Remote name, default 'origin'
        branch: Branch to push — leave empty to push the current branch

    Returns:
        Confirmation message, or an error message (auth failures show up
        as a non-zero git exit code with git's own error text)
    """
    repo_root = _repo_root(repo_name)
    if not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."

    args = ["push", remote] + ([branch] if branch else [])
    output, err = _run_git(args, cwd=repo_root, timeout=120)
    if err:
        return err
    suffix = f"/{branch}" if branch else ""
    return f"Pushed '{repo_name}' to {remote}{suffix}" + (f": {output}" if output else "")


def git_pull(repo_name, remote="origin", branch=""):
    """Pull the latest changes for a cloned repo from its remote.

    Args:
        repo_name: The repo folder name (from git_clone)
        remote: Remote name, default 'origin'
        branch: Branch to pull — leave empty for the current branch's
                default upstream

    Returns:
        Confirmation message with pull output, or an error message
    """
    repo_root = _repo_root(repo_name)
    if not os.path.exists(repo_root):
        return f"Error: repo '{repo_name}' not found. Call git_clone first."

    args = ["pull", remote] + ([branch] if branch else [])
    output, err = _run_git(args, cwd=repo_root, timeout=120)
    if err:
        return err
    return f"Pulled '{repo_name}': {output}"


def list_cloned_repos():
    """List every repo currently cloned into the repos folder.

    Returns:
        A list of repo folder names, or a message if none are cloned
    """
    if not os.path.exists(REPOS_DIR):
        return "No repos cloned yet."
    entries = [d for d in os.listdir(REPOS_DIR) if os.path.isdir(os.path.join(REPOS_DIR, d))]
    return "\n".join(entries) if entries else "No repos cloned yet."