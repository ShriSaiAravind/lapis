import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
import os

from config import EMAIL_USER, EMAIL_PASS, IMAP_SERVER, SMTP_SERVER, SMTP_PORT


def _decode(value):
    if not value:
        return ""
    decoded, encoding = decode_header(value)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(encoding or "utf-8", errors="ignore")
    return decoded


def read_recent_emails(count=5, folder="INBOX"):
    """Read the most recent emails — sender, subject, and a short preview.

    Args:
        count: How many recent emails to fetch, default 5
        folder: Mailbox folder to read from, default INBOX

    Returns:
        A summary of recent emails, most recent first
    """
    try:
        count = int(count)
    except (TypeError, ValueError):
        return "Error: count must be an integer."
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select(folder)

        status, data = mail.search(None, "ALL")
        if status != "OK":
            return "Error: could not search mailbox"

        ids = data[0].split()[-count:]
        if not ids:
            return "No emails found"

        results = []
        for eid in reversed(ids):
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            subject = _decode(msg["Subject"])
            from_ = _decode(msg.get("From"))
            date_ = msg.get("Date", "")

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode(errors="ignore")
                        except Exception:
                            body = ""
                        break
            else:
                try:
                    body = msg.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    body = ""

            preview = " ".join(body.strip().split())[:200]
            results.append(f"From: {from_}\nDate: {date_}\nSubject: {subject}\nPreview: {preview}")

        mail.logout()
        return "\n\n---\n\n".join(results)

    except imaplib.IMAP4.error as e:
        return f"Error: IMAP login/search failed — {str(e)}"
    except Exception as e:
        return f"Error reading emails: {str(e)}"


def search_emails(sender_or_subject, count=5, folder="INBOX"):
    """Search for emails from a specific sender or matching a subject —
    use this for questions like 'have I gotten any mail from X yet'.

    Args:
        sender_or_subject: Name, email address, or subject keyword to search for
        count: Max number of matching emails to return, default 5
        folder: Mailbox folder to search, default INBOX

    Returns:
        Matching emails with sender, subject, date, and preview — or a
        message saying nothing was found
    """
    try:
        count = int(count)  
    except (TypeError, ValueError):
        return "Error: count must be an integer."
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select(folder)

        query = f'(OR FROM "{sender_or_subject}" SUBJECT "{sender_or_subject}")'
        status, data = mail.search(None, query)
        if status != "OK":
            return "Error: search failed"

        ids = data[0].split()[-count:]
        if not ids:
            mail.logout()
            return f"No emails found from/about '{sender_or_subject}'"

        results = []
        for eid in reversed(ids):
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            subject = _decode(msg["Subject"])
            from_ = _decode(msg.get("From"))
            date_ = msg.get("Date", "")

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode(errors="ignore")
                        except Exception:
                            body = ""
                        break
            else:
                try:
                    body = msg.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    body = ""

            preview = " ".join(body.strip().split())[:200]
            results.append(f"From: {from_}\nDate: {date_}\nSubject: {subject}\nPreview: {preview}")

        mail.logout()
        return "\n\n---\n\n".join(results)

    except imaplib.IMAP4.error as e:
        return f"Error: IMAP login/search failed — {str(e)}"
    except Exception as e:
        return f"Error searching emails: {str(e)}"


def send_email(to, subject, body):
    """Send an email. This performs a real send — the risky-action
    confirmation gate will prompt for a yes/no before this actually fires.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain-text email body

    Returns:
        Confirmation message or error
    """
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, [to], msg.as_string())

        return f"Email sent to {to} with subject '{subject}'"

    except smtplib.SMTPAuthenticationError:
        return "Error: SMTP authentication failed — check EMAIL_USER/EMAIL_PASS (must be an app password)"
    except Exception as e:
        return f"Error sending email: {str(e)}"

if __name__ == "__main__":
    print(read_recent_emails())