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
