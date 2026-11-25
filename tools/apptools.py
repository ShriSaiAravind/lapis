from tools.basictools import *
import os
import re
from config import BASE_DIR, NOTES_DIR


def _is_inside_base(path):
    return os.path.abspath(path).startswith(os.path.abspath(BASE_DIR))


def excel_create(filename, headers=None, subfolder=""):
    """Create a new empty Excel file, optionally with header row.

    Args:
        filename: Just the filename e.g. data.xlsx
        headers: Optional list of column headers e.g. ["Name", "Age", "Email"]
        subfolder: Optional subfolder inside agent folder

    Returns:
        Confirmation message with full path
    """
    try:
        import openpyxl
    except ImportError:
        return "Error: openpyxl is not installed. Run: pip install openpyxl"

    base = os.path.join(BASE_DIR, subfolder) if subfolder else NOTES_DIR
    if not _is_inside_base(base):
        return f"Error: cannot write outside {BASE_DIR}"

    os.makedirs(base, exist_ok=True)
    full_path = os.path.join(base, os.path.basename(filename))

    wb = openpyxl.Workbook()
    ws = wb.active
    if headers:
        ws.append(headers)
    wb.save(full_path)
    return f"Excel file created: {full_path}"


def excel_read(filename, subfolder="", sheet=None):
    """Read all cell values from an Excel file (.xlsx).

    Args:
        filename: Just the filename e.g. data.xlsx
        subfolder: Optional subfolder hint
        sheet: Sheet name to read — leave empty for the first sheet

    Returns:
        A text table of the sheet contents
    """
    try:
        import openpyxl
    except ImportError:
        return "Error: openpyxl is not installed. Run: pip install openpyxl"

    full_path = os.path.join(BASE_DIR, subfolder, filename) if subfolder else find_file(filename)
    if not full_path or not os.path.exists(full_path):
        return f"Error: {filename} not found"
    if not _is_inside_base(full_path):
        return f"Error: cannot read outside {BASE_DIR}"

    wb = openpyxl.load_workbook(full_path, data_only=True)
    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append("\t".join("" if v is None else str(v) for v in row))
    return f"Sheet: {ws.title}\n" + "\n".join(rows) if rows else "Empty sheet"


def excel_write_cell(filename, cell, value, subfolder="", sheet=None):
    """Write a value to a specific cell in an Excel file.
    Creates the file if it doesn't exist.

    Args:
        filename: Just the filename e.g. data.xlsx
        cell: Cell reference e.g. A1, B3
        value: Value to write into the cell
        subfolder: Optional subfolder
        sheet: Sheet name — leave empty for the first sheet

    Returns:
        Confirmation message
    """
    try:
        import openpyxl
    except ImportError:
        return "Error: openpyxl is not installed. Run: pip install openpyxl"

    base = os.path.join(BASE_DIR, subfolder) if subfolder else NOTES_DIR
    if not _is_inside_base(base):
        return f"Error: cannot write outside {BASE_DIR}"

    os.makedirs(base, exist_ok=True)
    full_path = os.path.join(base, os.path.basename(filename))

    if os.path.exists(full_path):
        wb = openpyxl.load_workbook(full_path)
    else:
        wb = openpyxl.Workbook()

    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
    ws[cell] = value
    wb.save(full_path)
    return f"Written '{value}' to {cell} in {full_path}"


def excel_add_row(filename, row_data, subfolder="", sheet=None):
    """Append a new row of data to an Excel file.
    Creates the file if it doesn't exist.

    Args:
        filename: Just the filename e.g. data.xlsx
        row_data: List of values for the new row e.g. ["Alice", 30, "Engineer"]
        subfolder: Optional subfolder
        sheet: Sheet name — leave empty for the first sheet

    Returns:
        Confirmation message
    """
    try:
        import openpyxl
    except ImportError:
        return "Error: openpyxl is not installed. Run: pip install openpyxl"

    base = os.path.join(BASE_DIR, subfolder) if subfolder else NOTES_DIR
    if not _is_inside_base(base):
        return f"Error: cannot write outside {BASE_DIR}"

    os.makedirs(base, exist_ok=True)
    full_path = os.path.join(base, os.path.basename(filename))

    if os.path.exists(full_path):
        wb = openpyxl.load_workbook(full_path)
    else:
        wb = openpyxl.Workbook()

    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
    ws.append(row_data)
    wb.save(full_path)
    return f"Row {row_data} appended to {full_path}"

_INLINE_PATTERN = re.compile(r"(\*\*.+?\*\*|\*.+?\*|_.+?_)")


def add_inline_runs(paragraph, text):
    """Split a line on **bold**/*italic*/_italic_ markers and add each
    piece as its own run with the right formatting, instead of leaving
    the literal asterisks/underscores in the text."""
    for token in _INLINE_PATTERN.split(text):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**") and len(token) > 4:
            paragraph.add_run(token[2:-2]).bold = True
        elif token.startswith("*") and token.endswith("*") and len(token) > 2:
            paragraph.add_run(token[1:-1]).italic = True
        elif token.startswith("_") and token.endswith("_") and len(token) > 2:
            paragraph.add_run(token[1:-1]).italic = True
        else:
            paragraph.add_run(token)


def write_markdown_content(doc, content):
    """Append markdown-formatted content to an open Document as real docx
    elements: '#'/'##'/'###' become headings, '- '/'* ' become bulleted
    list items, '1. ' becomes numbered list items, **/_ become bold/
    italic runs. Consecutive plain-text lines with no blank line between
    them are joined into a single paragraph, matching normal markdown
    paragraph behavior instead of one line == one paragraph."""
    lines = content.replace("\r\n", "\n").split("\n")
    buffer = []

    def flush():
        if buffer:
            p = doc.add_paragraph()
            add_inline_runs(p, " ".join(buffer).strip())
            buffer.clear()

    for raw_line in lines:
        stripped = raw_line.strip()

        if not stripped:
            flush()
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.*)", stripped)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            doc.add_heading(heading_match.group(2).strip(), level=level)
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)", stripped)
        if bullet_match:
            flush()
            p = doc.add_paragraph(style="List Bullet")
            add_inline_runs(p, bullet_match.group(1))
            continue

        numbered_match = re.match(r"^\d+[\.\)]\s+(.*)", stripped)
        if numbered_match:
            flush()
            p = doc.add_paragraph(style="List Number")
            add_inline_runs(p, numbered_match.group(1))
            continue

        if re.match(r"^-{3,}$|^\*{3,}$", stripped):
            flush()  # horizontal rule — no direct docx equivalent, skip
            continue

        buffer.append(stripped)

    flush()


def word_create(filename, content="", subfolder=""):
    """Create a new Word document (.docx) with optional initial content.
    Content is interpreted as markdown — '# '/'## ' headings, '- '
    bullets, '1. ' numbered lists, **bold**, *italic* all render as real
    Word formatting, not literal markdown characters.

    Args:
        filename: Just the filename e.g. report.docx
        content: Optional initial content, markdown-formatted
        subfolder: Optional subfolder

    Returns:
        Confirmation message with full path
    """
    try:
        from docx import Document
    except ImportError:
        return "Error: python-docx is not installed. Run: pip install python-docx"

    base = os.path.join(BASE_DIR, subfolder) if subfolder else NOTES_DIR
    if not _is_inside_base(base):
        return f"Error: cannot write outside {BASE_DIR}"

    os.makedirs(base, exist_ok=True)
    full_path = os.path.join(base, os.path.basename(filename))

    doc = Document()
    if content:
        write_markdown_content(doc, content)
    doc.save(full_path)
    return f"Word document created: {full_path}"


def word_read(filename, subfolder=""):
    """Read all text from a Word document (.docx).

    Args:
        filename: Just the filename e.g. report.docx
        subfolder: Optional subfolder hint

    Returns:
        The full text content of the document
    """
    try:
        from docx import Document
    except ImportError:
        return "Error: python-docx is not installed. Run: pip install python-docx"

    full_path = os.path.join(BASE_DIR, subfolder, filename) if subfolder else find_file(filename)
    if not full_path or not os.path.exists(full_path):
        return f"Error: {filename} not found"
    if not _is_inside_base(full_path):
        return f"Error: cannot read outside {BASE_DIR}"

    doc = Document(full_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    return text if text.strip() else "Document is empty"


def word_append(filename, text, subfolder=""):
    """Append markdown-formatted content to an existing Word document —
    same formatting rules as word_create (headings, bullets, bold, etc.
    render as real Word formatting).

    Args:
        filename: Just the filename e.g. report.docx
        text: The content to append, markdown-formatted
        subfolder: Optional subfolder hint

    Returns:
        Confirmation message
    """
    try:
        from docx import Document
    except ImportError:
        return "Error: python-docx is not installed. Run: pip install python-docx"

    full_path = os.path.join(BASE_DIR, subfolder, filename) if subfolder else find_file(filename)
    if not full_path or not os.path.exists(full_path):
        return f"Error: {filename} not found"
    if not _is_inside_base(full_path):
        return f"Error: cannot write outside {BASE_DIR}"

    doc = Document(full_path)
    write_markdown_content(doc, text)
    doc.save(full_path)
    return f"Content appended to {full_path}"


def word_replace(filename, find, replace, subfolder=""):
    """Find and replace text throughout a Word document.

    Args:
        filename: Just the filename e.g. report.docx
        find: The text to search for
        replace: The text to replace it with
        subfolder: Optional subfolder hint

    Returns:
        Confirmation message with count of replacements made
    """
    try:
        from docx import Document
    except ImportError:
        return "Error: python-docx is not installed. Run: pip install python-docx"

    full_path = os.path.join(BASE_DIR, subfolder, filename) if subfolder else find_file(filename)
    if not full_path or not os.path.exists(full_path):
        return f"Error: {filename} not found"
    if not _is_inside_base(full_path):
        return f"Error: cannot write outside {BASE_DIR}"

    doc = Document(full_path)
    count = 0
    for para in doc.paragraphs:
        if find in para.text:
            for run in para.runs:
                if find in run.text:
                    run.text = run.text.replace(find, replace)
                    count += 1
    doc.save(full_path)
    return f"Replaced {count} occurrence(s) of '{find}' with '{replace}' in {full_path}"