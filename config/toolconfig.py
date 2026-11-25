from tools import *

# This is the ONLY TOOLS dict in the codebase — do not redefine it in
# tools/basictools.py or anywhere else, or you'll get silent shadowing
# depending on import order.
TOOLS = {
    "write_file": write_file,
    "open_file_in_notepad": open_file_in_notepad,
    "open_in_vscode": open_in_vscode,
    "read_file": read_file,
    "list_stuff": list_stuff,
    "open_app": open_app,
    "run_python_file": run_python_file,
    "create_folder": create_folder,
    "find_file_tool": find_file_tool,
    "list_folder_tree": list_folder_tree,

    "excel_read": excel_read,
    "excel_create": excel_create,
    "excel_write_cell": excel_write_cell,
    "excel_add_row": excel_add_row,

    "word_create": word_create,
    "word_read": word_read,
    "word_append": word_append,
    "word_replace": word_replace,

    # multi-file project tools
    "create_project": create_project,
    "list_project_files": list_project_files,
    "read_project_file": read_project_file,
    "write_project_file": write_project_file,
    "delete_project_file": delete_project_file,
    "run_project_entrypoint": run_project_entrypoint,

    # browser tools
    "open_url_in_chrome": open_url_in_chrome,
    "search_in_browser": search_in_browser,
    "open_site_search": open_site_search,
    "play_youtube_video": play_youtube_video,
    "open_leetcode_problem": open_leetcode_problem,
    "open_github_repo": open_github_repo,
    "open_github_user": open_github_user,

    # email tools
    "read_recent_emails": read_recent_emails,
    "search_emails": search_emails,
    "send_email": send_email,

    # reminder tools
    "set_reminder": set_reminder,
    "set_reminder_in": set_reminder_in,
    "list_reminders": list_reminders,
    "cancel_reminder": cancel_reminder,

    # todo tools
    "add_todo": add_todo,
    "list_todos": list_todos,
    "complete_todo": complete_todo,
    "delete_todo": delete_todo,
    "clear_completed_todos": clear_completed_todos,

    # spotify tools
    "play_song_on_spotify": play_song_on_spotify,
    "queue_song_on_spotify": queue_song_on_spotify,
    "play_playlist_on_spotify": play_playlist_on_spotify,
    "pause_spotify": pause_spotify,
    "skip_spotify": skip_spotify,

    # coding tools — only one of these three is exposed to the model per
    # session, see agent.build_active_tools / CODER_BACKEND_TOOLS
    "generate_and_write_code": generate_and_write_code,
    # "generate_code_with_coder": generate_code_with_coder,
    "generate_and_write_code_api": generate_and_write_code_api,
    "generate_and_write_code_groq": generate_and_write_code_groq,

    # code review tools
    "review_code_file": review_code_file,
    "review_repo": review_repo,
    "apply_code_review": apply_code_review,
    "list_repo_files": list_repo_files,
    "read_repo_file": read_repo_file,

    # git tools
    "git_clone": git_clone,
    "git_status": git_status,
    "git_diff": git_diff,
    "git_commit": git_commit,
    "git_push": git_push,
    "git_pull": git_pull,
    "list_cloned_repos": list_cloned_repos,
}


TOOL_CATEGORIES = {
    "files": [
        "write_file", "read_file", "open_file_in_notepad", "open_in_vscode",
        "list_stuff", "list_folder_tree", "create_folder", "find_file_tool",
        "run_python_file", "open_app",
    ],
    "office": [
        "excel_read", "excel_create", "excel_write_cell", "excel_add_row",
        "word_create", "word_read", "word_append", "word_replace",
    ],
    "projects": [
        "create_project", "list_project_files", "read_project_file",
        "write_project_file", "delete_project_file", "run_project_entrypoint",
    ],
    "web": [
        "open_url_in_chrome", "search_in_browser", "open_site_search",
        "play_youtube_video", "open_leetcode_problem", "open_github_repo",
        "open_github_user",
    ],
    "email": [
        "read_recent_emails", "search_emails", "send_email",
    ],
    "reminders": [
        "set_reminder", "set_reminder_in", "list_reminders", "cancel_reminder",
    ],
    "todos": [
        "add_todo", "list_todos", "complete_todo", "delete_todo", "clear_completed_todos",
    ],
    "spotify": [
        "play_song_on_spotify", "queue_song_on_spotify", "play_playlist_on_spotify",
        "pause_spotify", "skip_spotify",
    ],
    "coding": [
        "generate_and_write_code", "generate_and_write_code_api", "generate_and_write_code_groq",
    ],
    "codereview": [
        "review_code_file", "review_repo", "apply_code_review",
        "list_repo_files", "read_repo_file",
    ],
    "git": [
        "git_clone", "git_status", "git_diff", "git_commit", "git_push",
        "git_pull", "list_cloned_repos",
    ],
}

DEFAULT_CATEGORIES = {"files", "office", "spotify"}

ALWAYS_ON_TOOLS = {"web_search", "web_fetch"}

TOOL_CATEGORY_META = [
    {"id": "files", "label": "Files", "logo": None},
    {"id": "office", "label": "Office (Excel / Word)", "logo": None},
    {"id": "projects", "label": "Projects", "logo": None},
    {"id": "web", "label": "Web & Browser", "logo": None},
    {"id": "email", "label": "Email", "logo": None},
    {"id": "reminders", "label": "Reminders", "logo": None},
    {"id": "todos", "label": "Todos", "logo": None},
    {"id": "spotify", "label": "Spotify", "logo": None},
    {"id": "coding", "label": "Code Generation", "logo": None},
    {"id": "codereview", "label": "Code Review", "logo": None},
    {"id": "git", "label": "Git", "logo": None},
]