"""Tests for PDF deadline extraction (app/parsers/pdf_parser.py)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.database.repository import Repository
from app.parsers.pdf_parser import (
    RELIABLE_CONFIDENCE,
    analyse_text_for_deadline,
    extract_deadline_from_pdf,
)

TZ = ZoneInfo("Asia/Kolkata")


def build_pdf(text: str) -> bytes:
    """Build a minimal valid one-page PDF containing the given text."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_strong_keyword_with_datetime():
    text = (
        "MCA Assignment 1 Instructions. Please read carefully. "
        "Due Date: 20/09/2026 11:59 PM. Late submissions will not be accepted."
    )
    match = analyse_text_for_deadline(text, TZ)
    assert match is not None
    assert match.confidence >= 0.85
    assert match.deadline == datetime(2026, 9, 20, 23, 59)
    assert "Due Date" in match.snippet


def test_strong_keyword_date_only():
    text = "The assignment deadline is 25/09/2026 for all students."
    match = analyse_text_for_deadline(text, TZ)
    assert match is not None
    assert match.deadline == datetime(2026, 9, 25, 0, 0)
    assert RELIABLE_CONFIDENCE <= match.confidence < 0.9


def test_weak_keyword_still_reliable():
    text = "Please submit the report by 25/09/2026."
    match = analyse_text_for_deadline(text, TZ)
    assert match is not None
    assert match.confidence >= RELIABLE_CONFIDENCE
    assert match.deadline == datetime(2026, 9, 25, 0, 0)


def test_date_without_keyword_is_not_reliable():
    text = "The class will be held on 25/09/2026 in room 204."
    assert analyse_text_for_deadline(text, TZ) is None


def test_bare_date_falls_back_to_na():
    text = "Course outline version 2, revised 25/09/2026 by the committee."
    assert analyse_text_for_deadline(text, TZ) is None


def test_no_dates_returns_none():
    assert analyse_text_for_deadline("No dates in this document at all.", TZ) is None
    assert analyse_text_for_deadline("", TZ) is None
    assert analyse_text_for_deadline(None, TZ) is None


def test_picks_best_candidate():
    text = (
        "Classes resume on 01/10/2026. However, the assignment "
        "Submission Deadline: 18/09/2026 11:59 PM sharp."
    )
    match = analyse_text_for_deadline(text, TZ)
    assert match is not None
    assert match.deadline == datetime(2026, 9, 18, 23, 59)


def test_record_sheet_table_dates():
    """Record-sheet pattern: given date + submission end date side by side."""
    text = (
        "MCA 1st SEMESTER ASSIGNMENT 2 RECORD SHEET. Course: MCA Year: 2026-2027. "
        "Subject Name: Software Engineering. Assignment given date "
        "21-09-2026 27-09-2026 Assignment submission end date. "
        "1. Explain Structured System Analysis and Design Methodology (SSADM)."
    )
    match = analyse_text_for_deadline(text, TZ)
    assert match is not None
    # The submission end date wins, NOT the given date.
    assert match.deadline == datetime(2026, 9, 27)
    assert match.confidence >= RELIABLE_CONFIDENCE


def test_record_sheet_negative_marker_only():
    """A date whose only marker is 'given date' is not a deadline -> N/A."""
    text = "Assignment given date 21-09-2026. Keep this record for reference."
    match = analyse_text_for_deadline(text, TZ)
    assert match is None  # given date alone -> below reliable confidence


def test_ocr_fallback_used_for_image_pdf(tmp_path):
    """When pypdf finds no text, the OCR layer is invoked with the images."""
    import app.parsers.pdf_parser as pdf_parser

    fake_image_pdf = b"%PDF-1.4 fake"
    calls: list[bytes] = []

    def fake_extract(_bytes: bytes, max_pages: int = 15) -> str:
        return "   "  # no usable text layer

    def fake_ocr_layers(pdf_bytes: bytes, max_pages: int = 5) -> str:
        calls.append(pdf_bytes)
        return (
            "Software Engineering Assignment 2 Record Sheet. "
            "Assignment given date 21-09-2026 27-09-2026 "
            "Assignment submission end date."
        )

    original_extract = pdf_parser.extract_pdf_text
    original_layers = pdf_parser._ocr_text_layers
    pdf_parser.extract_pdf_text = fake_extract
    pdf_parser._ocr_text_layers = fake_ocr_layers
    try:
        match = pdf_parser.extract_deadline_from_pdf(fake_image_pdf, TZ)
    finally:
        pdf_parser.extract_pdf_text = original_extract
        pdf_parser._ocr_text_layers = original_layers

    assert calls == [fake_image_pdf]
    assert match is not None
    assert match.deadline == datetime(2026, 9, 27)


def test_ocr_fallback_no_engine_returns_none():
    """Without any OCR engine, an image PDF yields no deadline (no crash)."""
    import app.parsers.pdf_parser as pdf_parser

    def fake_extract(_bytes: bytes, max_pages: int = 15) -> str:
        return " "  # no text layer

    def fake_layers(_pdf_bytes: bytes, max_pages: int = 5) -> str:
        return ""  # no engine available

    original_extract, original_layers = pdf_parser.extract_pdf_text, pdf_parser._ocr_text_layers
    pdf_parser.extract_pdf_text = fake_extract
    pdf_parser._ocr_text_layers = fake_layers
    try:
        match = pdf_parser.extract_deadline_from_pdf(b"%PDF-1.4 fake", TZ)
    finally:
        pdf_parser.extract_pdf_text = original_extract
        pdf_parser._ocr_text_layers = original_layers
    assert match is None


def test_extract_deadline_from_real_pdf():
    pdf = build_pdf(
        "Data Structures Assignment 1. Due Date: 20/09/2026 11:59 PM. Total marks: 10."
    )
    match = extract_deadline_from_pdf(pdf, TZ)
    assert match is not None
    assert match.deadline == datetime(2026, 9, 20, 23, 59)
    assert match.confidence >= 0.85


def test_extract_deadline_from_invalid_pdf_returns_none():
    assert extract_deadline_from_pdf(b"this is not a pdf", TZ) is None


def test_pdf_cache_roundtrip(tmp_path):
    from app.database.connection import init_db

    settings_stub = type("S", (), {"database_url": f"sqlite:///{tmp_path / 't.db'}"})
    repo = Repository(init_db(settings_stub()))
    url = "https://example.com/assignment-1.pdf"

    assert repo.get_pdf_deadline(url) is None
    repo.save_pdf_deadline(
        url, datetime(2026, 9, 20, 23, 59), 0.9, "Due Date: 20/09/2026"
    )
    cached = repo.get_pdf_deadline(url)
    assert cached is not None
    assert cached.deadline == datetime(2026, 9, 20, 23, 59)
    assert cached.confidence == 0.9
    assert "Due Date" in cached.snippet

    # Upsert: negative result overwrites.
    repo.save_pdf_deadline(url, None)
    cached = repo.get_pdf_deadline(url)
    assert cached.deadline is None


def test_pdf_deadline_service_enrich(tmp_path):
    """Full service path: download PDF -> extract -> cache -> enrich record."""
    import asyncio

    from app.database.connection import init_db
    from app.services.pdf_deadline_service import PdfDeadlineService

    settings_stub = type(
        "S",
        (),
        {
            "database_url": f"sqlite:///{tmp_path / 't.db'}",
            "timezone": "Asia/Kolkata",
        },
    )()
    settings_stub.get_timezone = lambda: TZ
    repo = Repository(init_db(settings_stub))
    service = PdfDeadlineService(settings_stub, repo)

    pdf_bytes = build_pdf(
        "Assignment 4. Due Date: 25/10/2026 11:59 PM. Total marks: 10."
    )

    class _FakeResponse:
        ok = True

        async def body(self) -> bytes:
            return pdf_bytes

    class _FakeRequest:
        """Mimics playwright's APIRequestContext.get(...)."""

        def __init__(self, response):
            self._response = response

        async def get(self, url, *, timeout=None):
            return self._response

    class _FakePage:
        def __init__(self, response):
            self.context = type("C", (), {"request": _FakeRequest(response)})()

    url = "https://example.com/assignment-4.pdf"
    raw = {
        "title": "Assignment 4",
        "url": "https://example.com/classroom",
        "portal_id": "w-4",
        "description": "Classwork item of type document.",
        "deadline_text": None,
        "deadline_iso": None,
        "status": "PENDING",
        "source_url": url,
    }

    enriched = asyncio.run(service.enrich(_FakePage(_FakeResponse()), [raw]))
    assert enriched[0]["deadline_iso"] is not None
    assert "confidence" in enriched[0]["description"]

    cached = repo.get_pdf_deadline(url)
    assert cached is not None
    assert cached.deadline == datetime(2026, 10, 25, 23, 59)
    assert cached.confidence >= 0.85

    # Second pass uses the cache (no extra download needed).
    raw2 = dict(raw)
    enriched2 = asyncio.run(service.enrich(_FakePage(_FakeResponse()), [raw2]))
    assert enriched2[0]["deadline_iso"] == "2026-10-25T23:59:00"


def test_pdf_deadline_service_caches_non_pdf_payload(tmp_path):
    """HTML subject pages are validated once and never re-downloaded."""
    import asyncio

    from app.database.connection import init_db
    from app.services.pdf_deadline_service import NOT_PDF_CONFIDENCE, PdfDeadlineService

    settings_stub = type(
        "S",
        (),
        {
            "database_url": f"sqlite:///{tmp_path / 't.db'}",
            "timezone": "Asia/Kolkata",
        },
    )()
    settings_stub.get_timezone = lambda: TZ
    repo = Repository(init_db(settings_stub))
    service = PdfDeadlineService(settings_stub, repo)

    downloads = []

    class _FakeHtmlResponse:
        ok = True

        async def body(self) -> bytes:
            downloads.append(1)
            return b"<html><body>subject page</body></html>"

    class _FakeRequest:
        def __init__(self, response):
            self._response = response

        async def get(self, url, *, timeout=None):
            return self._response

    class _FakePage:
        def __init__(self, response):
            self.context = type("C", (), {"request": _FakeRequest(response)})()

    url = "https://example.com/subject-page"
    raw = {
        "title": "Assignment 1",
        "url": "https://example.com/classroom",
        "portal_id": "w-1",
        "deadline_text": None,
        "deadline_iso": None,
        "status": "PENDING",
        "source_url": url,
    }

    enriched = asyncio.run(service.enrich(_FakePage(_FakeHtmlResponse()), [raw]))
    assert enriched[0]["deadline_iso"] is None  # N/A fallback
    assert len(downloads) == 1

    cached = repo.get_pdf_deadline(url)
    assert cached is not None
    assert cached.deadline is None
    assert cached.confidence == NOT_PDF_CONFIDENCE

    # Second sync must not download again.
    asyncio.run(service.enrich(_FakePage(_FakeHtmlResponse()), [dict(raw)]))
    assert len(downloads) == 1


def test_parser_version_bump_forces_reanalysis(tmp_path):
    """Cached results from an older parser are re-analysed after a bump."""
    import asyncio

    from app.database.connection import init_db
    from app.parsers.pdf_parser import PARSER_VERSION
    from app.services.pdf_deadline_service import PdfDeadlineService

    settings_stub = type(
        "S",
        (),
        {
            "database_url": f"sqlite:///{tmp_path / 't.db'}",
            "timezone": "Asia/Kolkata",
        },
    )()
    settings_stub.get_timezone = lambda: TZ
    repo = Repository(init_db(settings_stub))
    service = PdfDeadlineService(settings_stub, repo)

    pdf_bytes = build_pdf("Assignment 1. Due Date: 25/10/2026 11:59 PM.")

    class _FakeResponse:
        ok = True

        async def body(self) -> bytes:
            return pdf_bytes

    class _FakeRequest:
        def __init__(self, response):
            self._response = response

        async def get(self, url, *, timeout=None):
            return self._response

    class _FakePage:
        def __init__(self, response):
            self.context = type("C", (), {"request": _FakeRequest(response)})()

    url = "https://example.com/assignment-1.pdf"
    raw = {
        "title": "Assignment 1",
        "url": "https://example.com/classroom",
        "portal_id": "w-1",
        "deadline_text": None,
        "deadline_iso": None,
        "status": "PENDING",
        "source_url": url,
    }

    # Simulate an old parser that found nothing (older version, no deadline).
    repo.save_pdf_deadline(url, None, 0.0, None, PARSER_VERSION - 1)

    enriched = asyncio.run(service.enrich(_FakePage(_FakeResponse()), [raw]))
    assert enriched[0]["deadline_iso"] is not None  # re-analysed successfully
    row = repo.get_pdf_deadline(url)
    assert row.parser_version == PARSER_VERSION
    assert row.deadline is not None

    # Now the cache is current: a second pass must NOT re-download.
    enriched2 = asyncio.run(service.enrich(_FakePage(_FakeResponse()), [dict(raw)]))
    assert enriched2[0]["deadline_iso"] == enriched[0]["deadline_iso"]


def test_normalize_assignment_preserves_document_source_url():
    from app.parsers.assignment_parser import normalize_assignment

    raw = {
        "title": "Assignment 1",
        "url": "https://example.com/classroom/123",
        "source_url": "/uploads/assignment-1",
        "portal_id": "work-1",
        "description": "Document assignment.",
        "deadline_text": None,
        "deadline_iso": "2026-09-20T23:59:00",
        "status": "PENDING",
    }
    normalized = normalize_assignment(raw, "subject-1", TZ)
    assert normalized is not None
    assert normalized["source_url"] == "/uploads/assignment-1"
