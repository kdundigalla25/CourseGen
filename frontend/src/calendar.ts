import type { components } from './api/schema';
type Schedule = components['schemas']['CandidateSchedule'];
type Term = components['schemas']['Term'];
export const weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
export const clock = (minute: number) => `${String(Math.floor(minute / 60)).padStart(2,'0')}:${String(minute % 60).padStart(2,'0')}`;
export const shiftDate = (value: string, days: number) => new Date(Date.parse(`${value}T00:00:00Z`) + days * 86400000).toISOString().slice(0,10);
export const monday = (value: string) => shiftDate(value, -((new Date(`${value}T00:00:00Z`).getUTCDay()+6)%7));
export function firstWeek(schedules: Schedule[], term: Term) {
  const dates = schedules.flatMap(s => s.courses.flatMap(c => c.sections.flatMap(section => section.meetings.flatMap(m => m.start_date ? [m.start_date] : [])))).sort();
  return term.start_date ? monday(term.start_date) : dates[0] ? monday(dates[0]) : '';
}
export function events(schedule: Schedule, term: Term, week: string) {
  return schedule.courses.flatMap((course, color) => course.sections.flatMap(section => section.meetings.flatMap((meeting,index) => {
    if (meeting.kind !== 'timed') return [];
    const start = meeting.start_date || term.start_date;
    const end = meeting.end_date || term.end_date;
    const date = week ? shiftDate(week, meeting.weekday!) : '';
    if (date && ((start && date < start) || (end && date > end))) return [];
    return [{ id:`${section.id}-${index}`, course:course.course_id, section:section.number,
      title:course.title, location:section.location, weekday:meeting.weekday!,
      start:meeting.start_minute!, end:meeting.end_minute!, date, uncertain:!start || !end,
      range:start && end ? `${start} through ${end}` : 'Dates need verification', color }];
  })));
}
