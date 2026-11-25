import os
import subprocess

from config import BASE_DIR

PROJECTS_DIR = os.path.join(BASE_DIR, "projects")


def _project_root(project_name):
    return os.path.abspath(os.path.join(PROJECTS_DIR, os.path.basename(project_name)))


def _safe_join(project_root, relative_path):
    """Join a relative path onto project_root, refusing anything that
    escapes it via '..' or an absolute path."""
    full_path = os.path.abspath(os.path.join(project_root, relative_path))
    if not full_path.startswith(project_root):
        return None
    return full_path


def create_project(project_name, description=""):
    """Create a new project folder for a multi-file task.
       Only use this when the task requires multiple related files
       that import or depend on one another.
    
       Do NOT use this for:
        - a single Python script
        - a LeetCode solution
        - one HTML file
        - one Markdown file
        - one config file

For standalone files, use write_file instead.
    Args:
        project_name: Short folder name, e.g. 'todo_app' — no path separators
        description: One-line description of what the project does

    Returns:
        Confirmation message with the project path
    """
    project_name = os.path.basename(project_name)
    full_path = os.path.join(PROJECTS_DIR, project_name)
    os.makedirs(full_path, exist_ok=True)

    manifest = os.path.join(full_path, "PROJECT.md")
    if not os.path.exists(manifest):
        with open(manifest, "w", encoding="utf-8") as f:
            f.write(f"# {project_name}\n\n{description}\n\n## Files\n")

    return (
        f"Project created at: {full_path}. "
        f"Use exactly project_name='{project_name}' for all further file operations "
        f"on this project."
    )


def list_project_files(project_name):
    """List all files currently in a project, with a short preview of each.
    ALWAYS call this before writing new files into an existing project so
    you know what's already there and don't duplicate work or break imports.

    Args:
        project_name: The project folder name

    Returns:
        A listing of files with the first few lines of each
    """
    project_root = _project_root(project_name)
    if not os.path.exists(project_root):
        return f"Error: project '{project_name}' doesn't exist. Call create_project first."

    out = []
    for root, _, files in os.walk(project_root):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, project_root)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    preview_lines = f.readlines()[:5]
                preview = "".join(preview_lines)
            except (UnicodeDecodeError, PermissionError):
                preview = "(binary or unreadable)"
            out.append(f"--- {rel} ---\n{preview}")
    return "\n\n".join(out) if out else "Project is empty — no files yet."


def read_project_file(project_name, filename):
    """Read the full content of one file inside a project.
    Call this before writing a file that imports/uses another file in the
    same project, so you get exact names and signatures right.

    Args:
        project_name: The project folder name
        filename: Relative path within the project, e.g. 'src/utils.py'

    Returns:
        Full file content
    """
    project_root = _project_root(project_name)
    full_path = _safe_join(project_root, filename)
    if full_path is None:
        return f"Error: {filename} escapes the project folder"
    if not os.path.exists(full_path):
        return f"Error: {filename} not found in project '{project_name}'"

    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def write_project_file(project_name, filename, content):
    """Write or overwrite a file inside a project.

    Args:
        project_name: The project folder name (must already exist — call
                       create_project first)
        filename: Relative path within the project, e.g. 'src/utils.py'
                  — subfolders are auto-created
        content: Full file content

    Returns:
        Confirmation with full path
    """
    project_root = _project_root(project_name)
    if not os.path.exists(project_root):
        return f"Error: project '{project_name}' doesn't exist. Call create_project first."

    full_path = _safe_join(project_root, filename)
    if full_path is None:
        return f"Error: {filename} escapes the project folder"

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Written: {full_path}"


def delete_project_file(project_name, filename):
    """Delete a single file inside a project (e.g. to remove a scrapped draft).

    Args:
        project_name: The project folder name
        filename: Relative path within the project

    Returns:
        Confirmation or error message
    """
    project_root = _project_root(project_name)
    full_path = _safe_join(project_root, filename)
    if full_path is None:
        return f"Error: {filename} escapes the project folder"
    if not os.path.exists(full_path):
        return f"Error: {filename} not found in project '{project_name}'"

    os.remove(full_path)
    return f"Deleted: {full_path}"


def run_project_entrypoint(project_name, entrypoint="main.py"):
    """Run a project's entrypoint file with the working directory set to
    the project root, so intra-project imports resolve correctly.

    Args:
        project_name: The project folder name
        entrypoint: The file to run relative to the project root, e.g. 'main.py'

    Returns:
        stdout/stderr from running the project (truncated if very long)
    """
    project_root = _project_root(project_name)
    full_path = _safe_join(project_root, entrypoint)
    if full_path is None:
        return f"Error: {entrypoint} escapes the project folder"
    if not os.path.exists(full_path):
        return f"Error: {entrypoint} not found in project '{project_name}'"

    try:
        result = subprocess.run(
            ["python", entrypoint],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "Error: script timed out after 30s (possible infinite loop)"

    output = result.stdout or result.stderr or "Ran with no output"
    MAX_CHARS = 4000
    if len(output) > MAX_CHARS:
        output = output[:MAX_CHARS] + f"\n...[truncated, {len(output)} chars total]"
    return output