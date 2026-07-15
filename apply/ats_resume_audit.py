from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pydantic import BaseModel, Field

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_STANDARD_SECTIONS = {
    "summary": {"summary", "professional summary", "executive profile"},
    "experience": {"experience", "professional experience", "work experience"},
    "skills": {"skills", "technical skills", "core skills"},
    "education": {"education"},
}


class AtsResumeAudit(BaseModel):
    path: str
    text_extraction_succeeded: bool
    extracted_character_count: int
    has_tables: bool = False
    has_text_boxes: bool = False
    has_multiple_columns: bool = False
    has_headers_or_footers: bool = False
    recognized_sections: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    keyword_coverage: float | None = None
    issues: list[str] = Field(default_factory=list)


def _xml(root_bytes: bytes) -> ElementTree.Element:
    return ElementTree.fromstring(root_bytes)


def _document_text(root: ElementTree.Element) -> tuple[str, list[str]]:
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_W}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t":
                parts.append(node.text or "")
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in {f"{_W}br", f"{_W}cr"}:
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs), paragraphs


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE))


def audit_docx(path: str | Path, required_keywords: list[str] | None = None) -> AtsResumeAudit:
    """Inspect deterministic ATS risks in a DOCX without estimating interview probability."""
    resume_path = Path(path)
    if resume_path.suffix.casefold() != ".docx":
        raise ValueError("ATS document audit currently supports .docx files only")

    try:
        with zipfile.ZipFile(resume_path) as archive:
            names = set(archive.namelist())
            document_name = "word/document.xml"
            if document_name not in names:
                raise ValueError("DOCX is missing word/document.xml")
            root = _xml(archive.read(document_name))
            text, paragraphs = _document_text(root)

            has_tables = next(root.iter(f"{_W}tbl"), None) is not None
            has_text_boxes = next(root.iter(f"{_W}txbxContent"), None) is not None
            has_multiple_columns = False
            for columns in root.iter(f"{_W}cols"):
                try:
                    count = int(columns.attrib.get(f"{_W}num", "1"))
                except ValueError:
                    count = 1
                if count > 1:
                    has_multiple_columns = True
                    break
            has_headers_or_footers = any(
                name.startswith("word/header") or name.startswith("word/footer") for name in names
            )
    except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError) as exc:
        raise ValueError("DOCX could not be parsed; it may be corrupt or encrypted") from exc

    normalized_headings = {re.sub(r"[^a-z ]", "", p.casefold()).strip() for p in paragraphs}
    recognized = [
        section
        for section, aliases in _STANDARD_SECTIONS.items()
        if normalized_headings & aliases
    ]
    required = list(dict.fromkeys(k.strip().casefold() for k in required_keywords or [] if k.strip()))
    matched = [keyword for keyword in required if _contains_phrase(text, keyword)]
    missing = [keyword for keyword in required if keyword not in matched]
    coverage = round(len(matched) / len(required), 3) if required else None

    issues: list[str] = []
    if not text.strip():
        issues.append("No extractable resume text was found; the document may be image-based or corrupt.")
    if has_tables:
        issues.append("Tables detected; some ATS parsers may read cell content out of order.")
    if has_text_boxes:
        issues.append("Text boxes detected; their contents may be skipped by ATS parsers.")
    if has_multiple_columns:
        issues.append("Multiple columns detected; reading order may be ambiguous.")
    if has_headers_or_footers:
        issues.append("Header/footer content detected; keep essential contact details in the document body.")
    for section in ("experience", "skills", "education"):
        if section not in recognized:
            issues.append(f"No standard ATS-recognized {section} section heading was detected.")

    return AtsResumeAudit(
        path=str(resume_path),
        text_extraction_succeeded=bool(text.strip()),
        extracted_character_count=len(text),
        has_tables=has_tables,
        has_text_boxes=has_text_boxes,
        has_multiple_columns=has_multiple_columns,
        has_headers_or_footers=has_headers_or_footers,
        recognized_sections=recognized,
        matched_keywords=matched,
        missing_keywords=missing,
        keyword_coverage=coverage,
        issues=issues,
    )
