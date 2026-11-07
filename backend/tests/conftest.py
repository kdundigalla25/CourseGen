import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.main import app


def make_pdf(pages: list[list[str]], password: str | None = None) -> bytes:
    """Synthetic text PDF: no original student records are embedded in tests."""
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        commands = ['BT /F1 10 Tf 40 750 Td 14 TL']
        for line in lines:
            escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            commands.append(f'({escaped}) Tj T*')
        commands.append('ET')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(commands).encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def client():
    with TestClient(app) as instance:
        yield instance


@pytest.fixture
def tracker():
    return make_pdf([
        ['Synthetic Student 123456789', 'Program Requirement', 'Undergraduate Career 2026 Fall', 'Catalog Year 2026-2027', 'Satisfied: First-Year Foundations'],
        ['Synthetic Student 123456789', 'Not Satisfied: Focus Capacities', 'Not Satisfied: Ways of Knowing'],
    ])
