from config import DANGEROUS_KEYWORDS
from config import TOOLS
from ollama import web_fetch, web_search

BUILTIN_TOOLS = {
    "web_search": web_search,
    "web_fetch": web_fetch,
}


def _format_web_search_result(result, snippet_chars=200):
    """web_search returns objects whose .content field alone can run
    2000+ chars — naive str()-then-truncate (the old behavior) meant the
    url almost never survived the 3000-char cutoff, so the model had no
    real link to pass to open_url_in_chrome and started guessing URLs
    instead. This formats a compact, url-first list so every result's
    link reliably fits regardless of how long its content is."""
    items = getattr(result, "results", None)
    if items is None and isinstance(result, dict):
        items = result.get("results")
    if not items:
        return str(result)[:3000]

    lines = []
    for i, item in enumerate(items, 1):
        title = item.get("title") if isinstance(item, dict) else getattr(item, "title", "")
        url = item.get("url") if isinstance(item, dict) else getattr(item, "url", "")
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", "")
        snippet = (content or "").strip().replace("\n", " ")[:snippet_chars]
        lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")

    return "\n".join(lines)


def is_risky(args):
    return any(kw in str(args).lower() for kw in DANGEROUS_KEYWORDS)


def confirm_risky(name, args):
    print(f"Risky command detected in {name}({args})")
    return input("Allow? (y/n): ").strip().lower() == "y"


def deploy_tool(name, args, allowed_names=None):
    if allowed_names is not None and name not in allowed_names and name not in BUILTIN_TOOLS:
        return f"Error: '{name}' isn't enabled right now — enable its tool category first."

    if name in BUILTIN_TOOLS:
        try:
            result = BUILTIN_TOOLS[name](**args)
            if name == "web_search":
                return _format_web_search_result(result)
            return str(result)[:3000]
        except Exception as e:
            return f"Error using {name}: {str(e)}"

    if name not in TOOLS:
        return f"Error: unknown tool '{name}'"

    if is_risky(args):
        if not confirm_risky(name, args):
            return "User denied this action."

    try:
        result = TOOLS[name](**args)
    except TypeError as e:
        return (
            f"Error calling {name}({args}): {str(e)}. "
            f"Check the required arguments for {name} and try again."
        )
    except Exception as e:
        return f"Error using {name}: {str(e)}"

    return result