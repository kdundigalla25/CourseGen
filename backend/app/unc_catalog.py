"""Strict parser for canonical UNC CourseLeaf subject HTML; no network activity."""
import hashlib
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.catalog_models import CatalogSnapshot, CourseDesignation
from app.models import Course, SourceSnapshot

ADAPTER_VERSION = 'unc-catalog-html-1'


def normalized(node):
    return ' '.join(node.get_text(' ', strip=True).split()) if node else ''


def soup_for(content: bytes):
    if len(content) > 10 * 1024 * 1024:
        raise ValueError('Source HTML exceeds 10 MB')
    return BeautifulSoup(content.decode('utf-8', errors='strict'), 'html.parser')


def parse_catalog(content: bytes, *, subject: str, edition: str, retrieved_at: datetime) -> CatalogSnapshot:
    if not re.fullmatch(r'[A-Z]{2,5}', subject) or not re.fullmatch(r'20\d{2}-20\d{2}', edition):
        raise ValueError('Use an uppercase UNC subject and explicit catalog edition')
    if not content.rstrip().lower().endswith(b'</html>'):
        raise ValueError('Catalog HTML is truncated or lacks its document terminator')
    soup = soup_for(content)
    if normalized(soup.select_one('#edition')) != f'{edition} Academic Catalog':
        raise ValueError('Catalog edition is absent or differs from the requested edition')
    heading = normalized(soup.select_one('h1'))
    if not heading.endswith(f'({subject})'):
        raise ValueError('Subject heading differs from the requested subject')
    blocks = soup.select('.courseblock')
    if not blocks or soup.select('[rel=next], .pagination'):
        raise ValueError('Missing course blocks or unexpected pagination; review the source structure')
    digest = hashlib.sha256(content).hexdigest()
    revision = hashlib.sha256((digest + retrieved_at.isoformat()).encode()).hexdigest()[:16]
    identity = f'unc-{subject.lower()}-{edition}-{revision}'
    source = SourceSnapshot(id=identity, source_url=f'https://catalog.unc.edu/courses/{subject.lower()}/',
        retrieved_at=retrieved_at.isoformat(), classification='public', edition=edition,
        content_sha256=digest, adapter_version=ADAPTER_VERSION)
    courses, designations = [], []
    for block in blocks:
        def single(selector, required=True):
            nodes = block.select(selector)
            if len(nodes) > 1 or (required and len(nodes) != 1):
                raise ValueError(f'Unexpected catalog field structure: {selector}')
            return normalized(nodes[0]) if nodes else ''
        code = single('.detail-code').removesuffix('.')
        if not re.fullmatch(re.escape(subject) + r' \d{2,3}[A-Z]?', code):
            raise ValueError('Invalid or out-of-subject course identifier')
        title = single('.detail-title').removesuffix('.')
        credits = re.fullmatch(r'(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))? Credits?\.',single('.detail-hours'))
        if not title or not credits:
            raise ValueError(f'Missing title or unsupported credit format for {code}')
        requisite = single('.detail-requisites',False)
        repeat = single('.detail-repeat_rules',False)
        courses.append(Course(id=code,title=title,edition=edition,source_snapshot_id=source.id,
            credits_min=float(credits[1]),credits_max=float(credits[2] or credits[1]),
            description=' '.join(normalized(p) for p in block.select('p.courseblockextra')) or None,
            prerequisite_text=requisite.removeprefix('Requisites:').strip() or None,
            repeatable=bool(repeat and 'May be repeated for credit.' in repeat)))
        attribute_text = single('.detail-idea_action',False)
        if attribute_text:
            prefix = 'IDEAs in Action Gen Ed:'
            if not attribute_text.startswith(prefix):
                raise ValueError('Unrecognized Gen Ed designation label')
            values = attribute_text[len(prefix):].strip().removesuffix('.')
            attributes = [a.strip() for a in values.split(',')]
            if not all(re.fullmatch(r'[A-Z][A-Z0-9-]*',a) for a in attributes) or len(set(attributes)) != len(attributes):
                raise ValueError('Unrecognized or duplicate Gen Ed designation syntax')
            designations.extend(CourseDesignation(course_id=code,edition=edition,attribute_id=a,source_snapshot_id=source.id) for a in attributes)
    return CatalogSnapshot(id=identity,classification='public',created_at=retrieved_at,sources=[source],
        description=f'UNC {subject}, {edition}: catalog definitions only; no semester offerings or verified enrollment eligibility.',
        courses=courses,designations=designations,terms=[],sections=[],bundles=[])
