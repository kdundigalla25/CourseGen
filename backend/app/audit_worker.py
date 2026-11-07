"""Short-lived extraction worker. Input/output are pipes; no student files are saved."""
import io
import json
import re
import sys

from pypdf import PdfReader

MAX_PAGES = 25
MAX_CHARACTERS = 200_000


def extract(data: bytes) -> dict:
    if not data.startswith(b"%PDF-"):
        return {"error": "invalid_pdf"}
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return {"error": "encrypted_pdf"}
        if len(reader.pages) > MAX_PAGES:
            return {"error": "too_many_pages"}
        if not reader.pages:
            return {"error": "empty_pdf"}
        pages = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            total += len(text)
            if total > MAX_CHARACTERS:
                return {"error": "too_much_text"}
            pages.append(text)
    except Exception:
        return {"error": "unreadable_pdf"}

    # Remove the observed Tracker identity preamble, including repeated page headers.
    first = pages[0].splitlines()
    marker = next((i for i, line in enumerate(first) if "Program Requirement" in line), None)
    preamble = {line.strip() for line in first[:marker] if line.strip()} if marker is not None else set()
    cleaned = []
    for index, text in enumerate(pages):
        lines = text.splitlines()
        # Later pages split the name/PID across lines, unlike the first-page preamble.
        # The observed university banner terminates that page-local identity header.
        banner = next((i for i, line in enumerate(lines[:12]) if "UNIVERSITY OF NORTH CAROLINA" in line), None)
        if banner is not None:
            lines = lines[banner + 1:]
        if index == 0 and marker is not None:
            start = next((i for i, line in enumerate(lines) if "Program Requirement" in line), 0)
            lines = lines[start:]
        lines = [line for line in lines if line.strip() not in preamble]
        lines = [line for line in lines if not re.match(r"\s*(?:student\s*(?:name|id)|pid|name)\s*:", line, re.I)]
        text = re.sub(r"(?<!\d)\d{9}(?!\d)", "[identifier removed]", "\n".join(lines))
        cleaned.append({"number": index + 1, "text": text})
    return {"pages": cleaned}


if __name__ == "__main__":
    result = extract(sys.stdin.buffer.read(10 * 1024 * 1024 + 1))
    sys.stdout.write(json.dumps(result))
