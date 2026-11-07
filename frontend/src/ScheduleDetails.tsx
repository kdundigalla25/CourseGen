import type { components } from './api/schema';
import { weekdays as days, clock as time } from './calendar';
export function ScheduleDetails({ schedule }: { schedule: components['schemas']['CandidateSchedule'] }) {
  return <>
        {schedule.courses.map(course => <div key={course.course_id} className="scheduled-course"><strong>{course.course_id} · {course.title}</strong><p className="caption">{course.credits} credits for this course combination</p>{course.possible_requirement_labels.length>0 && <p className="caption">Possible contribution: {course.possible_requirement_labels.join('; ')}. Combined fulfillment is not verified.</p>}
          {course.sections.map(section => <div className="section-meetings" key={section.id}><span>Section {section.number} · {section.component}{section.instructor ? ` · ${section.instructor}` : ''}{section.location ? ` · ${section.location}` : ''}</span><ul>{section.meetings.map((meeting,index) => <li key={index}>{meeting.kind==='timed' ? `${days[meeting.weekday!]} ${time(meeting.start_minute!)}–${time(meeting.end_minute!)}` : meeting.kind==='asynchronous' ? 'Asynchronous — no fixed meeting time' : 'Meeting time needs verification'}{meeting.start_date ? ` · ${meeting.start_date} through ${meeting.end_date}` : ''}</li>)}</ul></div>)}
        </div>)}
  </>;
}
