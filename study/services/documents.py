from dataclasses import dataclass
import hashlib
import re

from pypdf import PdfReader


MAX_PAGES = 500
MAX_EXTRACTED_CHARS = 5_000_000
CHUNK_SIZE = 1_200
CHUNK_OVERLAP = 180


class DocumentError(ValueError):
    """A document failed a safe-upload or extraction requirement."""


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    text: str


def sha256_file(upload) -> str:
    digest = hashlib.sha256()
    for block in upload.chunks():
        digest.update(block)
    upload.seek(0)
    return digest.hexdigest()


def extract_pdf(upload) -> list[ExtractedPage]:
    upload.seek(0)
    if upload.read(5) != b"%PDF-":
        upload.seek(0)
        raise DocumentError("This file does not appear to be a valid PDF.")
    upload.seek(0)
    try:
        reader = PdfReader(upload, strict=True)
        if reader.is_encrypted:
            raise DocumentError("Password-protected PDFs are not supported. Remove the password and upload again.")
        if not reader.pages or len(reader.pages) > MAX_PAGES:
            raise DocumentError(f"PDFs must contain between 1 and {MAX_PAGES} pages.")
        pages: list[ExtractedPage] = []
        total_chars = 0
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").replace("\x00", "").strip()
            total_chars += len(text)
            if total_chars > MAX_EXTRACTED_CHARS:
                raise DocumentError("The extracted text is too large to process safely.")
            pages.append(ExtractedPage(number=number, text=text))
        if not any(page.text for page in pages):
            raise DocumentError("No selectable text was found. Scanned PDFs need OCR before upload.")
        return pages
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("The PDF could not be read. Check that it is not damaged and try again.") from exc


def make_chunks(page: ExtractedPage) -> list[str]:
    normalized = re.sub(r"\s+", " ", page.text).strip()
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary
        value = normalized[start:end].strip()
        if value:
            chunks.append(value)
        if end >= len(normalized):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks
