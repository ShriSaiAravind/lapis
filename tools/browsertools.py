"""
Browser-facing tools — for anything the user wants to SEE live in a browser
rather than have summarized as text (stock prices, live scores, YouTube videos).

These are distinct from web_search/web_fetch: those return text content for
the model to read and summarize. These tools instead open a real browser
window so the human can look at live, visual, or interactive results
themselves — e.g. a stock chart, a live scoreboard, or an actual video.
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import time
import webbrowser
import urllib.parse

import requests


def _find_chrome():
    """Locate the Chrome executable. Returns None if not found."""
    candidates = [
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def open_url_in_chrome(url):
    """Open a specific URL in Google Chrome. Falls back to the system default
    browser if Chrome isn't found.

    Args:
        url: The full URL to open, e.g. 'https://example.com'

    Returns:
        Confirmation message
    """
    chrome_exe = _find_chrome()
    if chrome_exe:
        subprocess.Popen([chrome_exe, url])
        return f"Opened in Chrome: {url}"

    webbrowser.open(url)
    return f"Chrome not found — opened in default browser instead: {url}"


def open_leetcode_problem(problem_name):
    """Open a specific LeetCode problem page directly, e.g. 'Two Sum' opens
    leetcode.com/problems/two-sum/ — not a search results page. Looks the
    problem up against LeetCode's real problem list rather than guessing —
    this matters for numbered references ('problem 420'), since models
    cannot reliably recall which of ~3000 numbers maps to which title.
    If the model's own guessed title is wrong, this corrects it. Use this
    whenever the user names a specific LeetCode problem, instead of
    open_site_search or a manual web_search.

    Args:
        problem_name: The problem title and/or number, e.g. 'Two Sum',
                       '420', '420. Strong Password Checker', 'problem 76'

    Returns:
        Confirmation message with the URL opened and the verified title —
        if the number/title didn't match anything in LeetCode's list, the
        message says so explicitly rather than opening a guessed link
    """
    raw = problem_name.strip()
    num_match = re.search(r"\d+", raw)
    index = _load_leetcode_index()

    slug = None
    verified_title = None

    if index:
        # A leading number is ground truth — LeetCode's own list is the
        # source of truth for number->title, never the model's guess.
        if num_match:
            entry = index["by_number"].get(num_match.group())
            if entry:
                slug = entry["slug"]
                verified_title = entry["title"]

        if not slug:
            title_part = re.sub(r"^\s*#?\d+[\.\)]?\s*", "", raw).strip().lower()
            slug = index["by_title"].get(title_part)
            if slug:
                verified_title = title_part.title()

            if not slug:
                close = difflib.get_close_matches(title_part, index["by_title"].keys(), n=1, cutoff=0.75)
                if close:
                    slug = index["by_title"][close[0]]
                    verified_title = close[0].title()

    if not slug:
        return (
            f"Couldn't find a LeetCode problem matching '{problem_name}' in LeetCode's "
            f"problem list — not opening a guessed URL, since that's how the last one "
            f"ended up on a 404/wrong page. Try the exact title, or check the number."
        )

    url = f"https://leetcode.com/problems/{slug}/"
    result = open_url_in_chrome(url)
    return f"{result} — verified title: {verified_title}"


_LEETCODE_CACHE_TTL = 7 * 24 * 3600  # 1 week — LeetCode's problem list rarely changes


def _leetcode_cache_path():
    from config import BASE_DIR
    return os.path.join(BASE_DIR, ".cache", "leetcode_problems.json")


def _load_leetcode_index():
    """Fetches LeetCode's full problem list (number, title, slug for every
    problem) from its public API and caches it locally. This replaces
    relying on the model's own memory of number->title mappings, which is
    not reliable, and replaces naive title->slug string mangling, which
    breaks on punctuation-heavy titles. Returns None if both the cache and
    a fresh fetch fail (e.g. no network) — callers fall back accordingly."""
    cache_path = _leetcode_cache_path()

    try:
        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < _LEETCODE_CACHE_TTL:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    try:
        resp = requests.get("https://leetcode.com/api/problems/all/", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        # network unavailable — fall back to a stale cache if one exists,
        # rather than failing outright
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    by_number = {}
    by_title = {}
    for pair in data.get("stat_status_pairs", []):
        stat = pair.get("stat", {})
        num = stat.get("frontend_question_id")
        slug = stat.get("question__title_slug")
        title = stat.get("question__title")
        if num is None or not slug or not title:
            continue
        by_number[str(num)] = {"slug": slug, "title": title}
        by_title[title.lower()] = slug

    index = {"by_number": by_number, "by_title": by_title}

    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(index, f)
    except OSError:
        pass

    return index


def open_github_repo(owner, repo):
    """Open a specific GitHub repository page directly, e.g. owner='torvalds',
    repo='linux' opens github.com/torvalds/linux — not a search results page.
    Use this whenever the user names both an owner/org and a repo.

    Args:
        owner: The GitHub username or org, e.g. 'facebook'
        repo: The repository name, e.g. 'react'

    Returns:
        Confirmation message with the URL opened
    """
    owner = owner.strip().strip("/")
    repo = repo.strip().strip("/")
    url = f"https://github.com/{owner}/{repo}"
    return open_url_in_chrome(url)


def open_github_user(username):
    """Open a specific GitHub user or org profile page directly.

    Args:
        username: The GitHub username or org, e.g. 'torvalds'

    Returns:
        Confirmation message with the URL opened
    """
    username = username.strip().strip("/")
    url = f"https://github.com/{username}"
    return open_url_in_chrome(url)


def search_in_browser(query):
    """Open a live Google search for the query directly in the browser, so the
    user can see current results themselves. Use this for anything the user
    wants to SEE visually and that changes often — stock prices, live sports
    scores, weather, current prices — rather than a text summary.

    Args:
        query: The search query, e.g. 'AAPL stock price' or
               'India vs Australia score'

    Returns:
        Confirmation message
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}"
    return open_url_in_chrome(url)


SITE_SEARCH_TEMPLATES = {
    #search engines
    "google": "https://www.google.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",

    # shopping
    "amazon": "https://www.amazon.com/s?k={query}",
    "flipkart": "https://www.flipkart.com/search?q={query}",
    "ebay": "https://www.ebay.com/sch/i.html?_nkw={query}",
    "etsy": "https://www.etsy.com/search?q={query}",

    # vdos
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "spotify": "https://open.spotify.com/search/{query}",
    "netflix": "https://www.netflix.com/search?q={query}",
    "imdb": "https://www.imdb.com/find/?q={query}",

    # prog
    "github": "https://github.com/search?q={query}",
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    "leetcode": "https://leetcode.com/search/?q={query}",

    "huggingface": "https://huggingface.co/models?search={query}",
    "npm": "https://www.npmjs.com/search?q={query}",
    "pypi": "https://pypi.org/search/?q={query}",
    "mdn": "https://developer.mozilla.org/search?q={query}",

    # general info
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",

    # socials
    "twitter": "https://twitter.com/search?q={query}",
    "x": "https://twitter.com/search?q={query}",

    # maps
    "maps": "https://www.google.com/maps/search/{query}",
    "google maps": "https://www.google.com/maps/search/{query}",
}


SITE_ALIASES = {
    "yt": "youtube",
    "gh": "github",
    "wiki": "wikipedia",
    "hf": "huggingface",
    "gmaps": "google maps",
}


def open_site_search(site, query):
    """Search for something on a specific website and open the results in
    Chrome.

    Use this for general browsing requests without a specific named target:
      - "pull up water bottles on amazon"
      - "search python tutorials on youtube"
      - "look up wireless earbuds on flipkart"

    For a NAMED, specific target, prefer the dedicated tools instead —
    open_leetcode_problem for a named LeetCode problem, open_github_repo /
    open_github_user for a named repo or user. For anything else specific
    without a predictable URL, call web_search first to find the exact
    page, then open_url_in_chrome with that URL — don't stop at a search
    results page for something the user named specifically.

    Args:
        site: Website name (amazon, github, reddit, youtube, etc.)
        query: Search query

    Returns:
        Confirmation message.
    """

    site_key = site.lower().strip()

    # normalize URLs if the model accidentally passes one
    site_key = site_key.replace("https://", "")
    site_key = site_key.replace("http://", "")
    site_key = site_key.replace("www.", "")
    site_key = site_key.rstrip("/")

    # normalize aliases
    site_key = SITE_ALIASES.get(site_key, site_key)

    encoded_query = urllib.parse.quote_plus(query)

    if site_key in SITE_SEARCH_TEMPLATES:
        url = SITE_SEARCH_TEMPLATES[site_key].format(query=encoded_query)
    else:
        # fallback: Google search scoped to the requested site
        scoped = urllib.parse.quote_plus(f"site:{site_key} {query}")
        url = f"https://www.google.com/search?q={scoped}"

    return open_url_in_chrome(url)


def play_youtube_video(query):
    """Search YouTube for a query and open the top result so it plays in the
    browser. Use this whenever the user asks to watch, play, or see a video
    on a topic.

    Args:
        query: What to search for on YouTube, e.g. 'lofi hip hop radio' or
               'python decorators explained'

    Returns:
        Confirmation message with the video URL opened, or an error if
        yt-dlp isn't installed or no results were found.
    """
    try:
        import yt_dlp
    except ImportError:
        return "Error: yt-dlp is not installed. Run: pip install yt-dlp"

    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": True,
    }

    search_query = f"ytsearch1:{query}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
    except Exception as e:
        return f"Error searching YouTube for '{query}': {str(e)}"

    entries = info.get("entries") if info else None
    if not entries:
        return f"No YouTube results found for '{query}'"

    video_id = entries[0].get("id")
    if not video_id:
        return f"Found a result for '{query}' but couldn't extract its video ID"

    url = f"https://www.youtube.com/watch?v={video_id}"
    title = entries[0].get("title", "")

    result = open_url_in_chrome(url)
    return f"{result} — Now playing: {title}" if title else result