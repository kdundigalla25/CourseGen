"""Stateless exports. Revalidate inputs before selecting a server-generated option."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from app.models import Model
from app.scheduling_models import ScheduleRequest


class ScheduleExportRequest(Model):
    schedule_request: ScheduleRequest
    schedule_id: str = Field(min_length=1, max_length=128)
    fallback_start: date | None = None
    fallback_end: date | None = None

    @model_validator(mode='after')
    def dates(self):
        if (self.fallback_start is None) != (self.fallback_end is None):
            raise ValueError('Supply both fallback dates')
        if self.fallback_start and not 0 <= (self.fallback_end - self.fallback_start).days <= 366:
            raise ValueError('Date range must be ordered and at most 366 days')
        return self


class ExportError(ValueError):
    pass


EXPORT_LIMITS = ('Planning assistance only. Verify eligibility, seats and requirement counting. '
                 'Meetings follow supplied weekday/date patterns; holidays, cancellations and exams are not inferred.')


def text(value):
    return str(value).replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def fold(line):
    """RFC 5545 content lines, capped at 75 UTF-8 octets including continuation space."""
    parts, chunk = [], ''
    for char in line:
        if len((chunk + char).encode('utf-8')) > 75:
            parts.append(chunk)
            chunk = ' '
        chunk += char
    return '\r\n'.join([*parts, chunk])


def utc_time(day, minute, zone):
    naive = datetime.combine(day, time()) + timedelta(minutes=minute)
    candidates = {naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                  for fold in (0, 1)
                  if naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive}
    if len(candidates) != 1:
        raise ExportError('A meeting falls in an ambiguous or nonexistent daylight-saving time. Verify its actual time before exporting.')
    return candidates.pop().strftime('%Y%m%dT%H%M%SZ')


def calendar_bytes(schedule, result, term, request):
    zone = ZoneInfo(result.timezone)
    asynchronous = [c.course_id for c in schedule.courses if any(m.kind == 'asynchronous' for s in c.sections for m in s.meetings)]
    description = f'{result.notice}\n{EXPORT_LIMITS}\nSnapshot: {result.snapshot_id} ({result.snapshot_digest})'
    if asynchronous:
        description += '\nAsynchronous (no calendar events): ' + ', '.join(asynchronous)
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Course Planner//Schedule Export 1//EN',
             'CALSCALE:GREGORIAN', 'X-WR-CALNAME:' + text(f'{term.name} — preferred schedule'),
             'X-WR-TIMEZONE:' + text(result.timezone), 'X-WR-CALDESC:' + text(description)]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    count = 0
    for course in schedule.courses:
        for section in course.sections:
            for index, meeting in enumerate(section.meetings):
                if meeting.kind != 'timed':
                    continue
                start = meeting.start_date or term.start_date or request.fallback_start
                end = meeting.end_date or term.end_date or request.fallback_end
                if not start or not end:
                    raise ExportError('Meeting dates are missing. Supply a start and end date to export the calendar.')
                if not 0 <= (end - start).days <= 366:
                    raise ExportError('Calendar date ranges must be ordered and no longer than 366 days.')
                day = start + timedelta(days=(meeting.weekday - start.weekday()) % 7)
                while day <= end:
                    count += 1
                    if count > 5000:
                        raise ExportError('This schedule exceeds the supported calendar size.')
                    uid = hashlib.sha256(f'{result.snapshot_digest}|{schedule.id}|{section.id}|{index}|{day}'.encode()).hexdigest()
                    detail = f'{description}\n{course.title}\nSection {section.number} ({section.component})'
                    if section.instructor:
                        detail += '\nInstructor: ' + section.instructor
                    lines.extend(['BEGIN:VEVENT', f'UID:{uid}@course-planner.local', f'DTSTAMP:{stamp}',
                                  'DTSTART:' + utc_time(day, meeting.start_minute, zone),
                                  'DTEND:' + utc_time(day, meeting.end_minute, zone),
                                  'SUMMARY:' + text(f'{course.course_id} · {section.number}'),
                                  'DESCRIPTION:' + text(detail)])
                    if section.location:
                        lines.append('LOCATION:' + text(section.location))
                    lines.append('END:VEVENT')
                    day += timedelta(days=7)
    if not count:
        raise ExportError('This option has no dated fixed meetings. Use JSON or print to keep its asynchronous courses.')
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(fold(line) for line in lines) + '\r\n').encode('utf-8')


def record_bytes(schedule, result, term, request):
    # Deliberately omit the reviewed audit, raw text, student history and audit revision.
    record = dict(schema_version=1, schedule=schedule.model_dump(mode='json'),
                  term=term.model_dump(mode='json'), timezone=result.timezone,
                  snapshot_id=result.snapshot_id, snapshot_digest=result.snapshot_digest,
                  rule_revisions=result.rule_revisions, classification=result.classification,
                  notice=result.notice, sources=[s.model_dump(mode='json') for s in result.sources],
                  preferences=request.schedule_request.preferences.model_dump(mode='json'),
                  fallback_dates=dict(start=request.fallback_start, end=request.fallback_end),
                  warnings=[*result.warnings, EXPORT_LIMITS])
    return json.dumps(record, ensure_ascii=False, indent=2, default=str).encode('utf-8')
