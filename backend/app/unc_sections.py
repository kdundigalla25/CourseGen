"""Parse the normal public class-search table without inferring component links."""
from datetime import datetime
import re

from app.models import Meeting, Model, Section
from app.unc_catalog import normalized, soup_for

HEADERS = ['Subject','Catalog Number','Same As','Class Section','Class Number','Description','Term','Hours','Meeting Dates','Schedule','Instruction Type','Available Seats']


class OfferingRow(Model):
    course_id: str
    same_as: str
    section: Section
    instruction_text: str
    schedule_text: str
    date_text: str


def expand_rows(table):
    """Expand rowspans within each tbody; reject holes, overlaps and truncation."""
    output = []
    for body in table.select('tbody'):
        pending = {}
        for row in body.select(':scope > tr'):
            values = [None] * len(HEADERS)
            next_pending = {}
            for col,(remaining,value) in pending.items():
                values[col] = value
                if remaining > 1: next_pending[col] = (remaining-1,value)
            position = 0
            for cell in row.select(':scope > td'):
                while position < len(values) and values[position] is not None: position += 1
                span = int(cell.get('rowspan','1'))
                if position == len(values) or cell.get('colspan','1') != '1' or not 1 <= span <= 10000:
                    raise ValueError('Unsupported search-table cell span')
                value = normalized(cell)
                values[position] = value
                if span > 1: next_pending[position] = (span-1,value)
                position += 1
            if any(value is None for value in values):
                raise ValueError('Incomplete search-table row')
            output.append(values)
            pending = next_pending
        if pending: raise ValueError('Truncated search-table rowspan')
    return output


def parse_meetings(schedule, dates):
    bounds = {}
    if dates not in ('','None','TBA'):
        match = re.fullmatch(r'(\d{2}/\d{2}/\d{4}) - (\d{2}/\d{2}/\d{4})',dates)
        if not match: raise ValueError('Unsupported meeting-date format')
        bounds = dict(start_date=datetime.strptime(match[1],'%m/%d/%Y').date(),end_date=datetime.strptime(match[2],'%m/%d/%Y').date())
    if schedule in ('','None','TBA'):
        return [Meeting(kind='unknown',**bounds)]
    match = re.fullmatch(r'([MTWHFSU]+) (\d{2}:\d{2} [AP]M)-(\d{2}:\d{2} [AP]M)',schedule)
    if not match: raise ValueError('Unsupported meeting schedule; review source formatting')
    tokens = re.findall(r'TH|[MTWFSU]',match[1])
    if ''.join(tokens) != match[1] or len(set(tokens)) != len(tokens):
        raise ValueError('Unsupported or duplicate weekday notation')
    def minute(value):
        stamp = datetime.strptime(value,'%I:%M %p')
        return stamp.hour*60+stamp.minute
    return [Meeting(kind='timed',weekday={'M':0,'T':1,'W':2,'TH':3,'F':4,'S':5,'U':6}[day],
        start_minute=minute(match[2]),end_minute=minute(match[3]),**bounds) for day in tokens]


def parse_sections(content: bytes, *, subject: str, term_name: str, source_id: str) -> list[OfferingRow]:
    if not content.rstrip().lower().endswith(b'</html>'):
        raise ValueError('Class-search HTML is truncated or lacks its document terminator')
    soup = soup_for(content)
    table = soup.select_one('#results-table')
    if not table or [normalized(h) for h in table.select('thead th')] != HEADERS:
        raise ValueError('Missing or changed class-search table headers')
    if soup.select('[rel=next], .pagination'):
        raise ValueError('Unexpected pagination; result completeness needs verification')
    counts = re.search(r'Found\s+(\d+)\s+course\(s\),\s*(\d+)\s+section\(s\)',soup.get_text(' ',strip=True))
    if not counts: raise ValueError('Missing source result counts')
    rows = expand_rows(table)
    if len(rows) != int(counts[2]): raise ValueError('Section count differs from source total')
    if len({(row[0],row[1]) for row in rows}) != int(counts[1]): raise ValueError('Course count differs from source total')
    result, seen = [], set()
    term_id = 'unc-' + term_name.lower().replace(' ','-')
    for row in rows:
        sub,number,same_as,section,class_id,title,term,hours,dates,schedule,mode,seats = row
        if sub != subject or term != term_name or not re.fullmatch(r'\d{2,3}[A-Z]?',number):
            raise ValueError('Unexpected subject, term or catalog number in results')
        if not re.fullmatch(r'\d+',class_id) or not section or class_id in seen:
            raise ValueError('Missing or duplicate class identifier')
        if not re.fullmatch(r'\d+(?:\.\d+)?',hours):
            raise ValueError('Variable/unknown section credits need explicit review')
        seen.add(class_id)
        meetings = parse_meetings(schedule,dates)
        result.append(OfferingRow(course_id=f'{sub} {number}',same_as=same_as,instruction_text=mode,
            schedule_text=schedule,date_text=dates,section=Section(id=f'{term_id}-{class_id}',term_id=term_id,
                course_id=f'{sub} {number}',number=section,source_snapshot_id=source_id,meetings=meetings,
                component='other',linkage_status='unknown',credit_value=float(hours))))
    return result
