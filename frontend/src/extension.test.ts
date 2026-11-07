// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
// The extension is plain JS so it can be loaded unpacked without a build step.
// @ts-ignore no TS declaration needed for the standalone Chrome script
import { captureExpandedSections } from '../../extension/capture.js';

const details=(number='4696')=>`<article><div>001 - LEC (${number}) A MoWeFr 11:15 am 12:05 pm</div><div class="details">
<section><h4>INFORMATION</h4><div><span>Class Number:</span><span>${number}</span></div>
<div>Career: Undergraduate</div><div>Session: Session A</div><div>Units: 3 units</div><div>Grading: Undergrad - graded</div>
<div>Description: Synthetic course description.</div><div>Enrollment Requirements: Synthetic prerequisite.</div><div>Class Attributes: First-Year Appropriate</div></section>
<section><h4>DETAILS</h4><div>Instructor: Synthetic Instructor</div><div>Dates: 01/06/2027 - 05/06/2027</div>
<div>Meets: MoWeFr 11:15AM - 12:05PM</div><div>Instruction Mode: In-Person (On Campus)</div><div>Room: Example Room 101</div>
<div>Campus: UNC Chapel Hill</div><div>Location: UNC Chapel Hill</div><div>Components: Lecture Required</div></section>
<section><h4>AVAILABILITY</h4><div>Status: Wait List</div><div>Seats Open: 0/65</div><div>Wait List Open: 997/999</div></section>
<section><h4>ADDITIONAL LINKS</h4><a>Simple Syllabus</a></section></div><button>Enroll</button></article>`;

function setup(html=details()) {
  vi.stubGlobal('window',{...window,location:new URL('https://pa.cc.unc.edu/psp/paprd/EMPLOYEE/SA/WEBLIB_HCX_GN.H_DASHBOARD.FieldFormula.IScript_Main?term=2272&secret=excluded')});
  document.body.innerHTML=`<aside>PRIVATE STUDENT NAME 123456789</aside><h2>System Programming Fundamentals | COMP 211</h2>${html}`;
  vi.spyOn(Element.prototype,'getClientRects').mockReturnValue([{}] as unknown as DOMRectList);
  Object.defineProperty(HTMLElement.prototype,'innerText',{configurable:true,get(){return this.textContent;}});
}
afterEach(()=>{document.body.replaceChildren();vi.restoreAllMocks();vi.unstubAllGlobals();});

test('capture extracts screenshot-shaped details and excludes navigation, inputs and URL query',()=>{
  setup();const result=captureExpandedSections('2027 Spring');
  expect(result.errors).toEqual([]);expect(result.records).toHaveLength(1);
  const record=result.records[0];
  expect(record.course_id).toBe('COMP 211');expect(record.class_number).toBe('4696');
  expect(record.component).toBe('lecture');expect(record.section_number).toBe('001');
  expect(record.meetings.map((m: {weekday:number})=>m.weekday)).toEqual([0,2,4]);
  expect(record.meetings[0]).toMatchObject({start_minute:675,end_minute:725,start_date:'2027-01-06',end_date:'2027-05-06'});
  expect(record.seats).toEqual({open:0,capacity:65});expect(record.waitlist).toEqual({open:997,capacity:999});
  expect(record.attributes_text).toBe('First-Year Appropriate');expect(record.components_text).toBe('Lecture Required');
  expect(record.linkage_status).toBe('unknown');expect(record.term_verification).toBe('user_entered');
  expect(JSON.stringify(result)).not.toMatch(/PRIVATE|123456789|secret=|Simple Syllabus/);
});
test('Tuesday and Thursday and fractional credits remain distinct',()=>{
  setup(details().replace('MoWeFr 11:15AM - 12:05PM','TuTh 11:00AM - 12:15PM').replace('3 units','0.5 units'));
  const record=captureExpandedSections('2027 Spring').records[0];
  expect(record.meetings.map((m: {weekday:number})=>m.weekday)).toEqual([1,3]);expect(record.credits).toBe(0.5);
});
test('unknown or multiple meeting patterns are retained for review rather than dropped silently',()=>{
  setup(details().replace('MoWeFr 11:15AM - 12:05PM','TBA'));
  const record=captureExpandedSections('2027 Spring').records[0];
  expect(record.meetings).toEqual([{kind:'unknown'}]);expect(record.warnings.length).toBeGreaterThan(0);
});
test('collapsed details, unrelated hosts and malformed counts fail without recording guessed sections',()=>{
  setup('<div>001 - LEC (4696)</div>');expect(captureExpandedSections('2027 Spring').records).toEqual([]);
  setup(details().replace('0/65','66/65'));expect(captureExpandedSections('2027 Spring').records).toEqual([]);
  setup();window.location=new URL('https://example.com/psp/test') as unknown as Location;
  expect(captureExpandedSections('2027 Spring').records).toEqual([]);
});
test('captures multiple expanded sections without mixing fields or course headings',()=>{
  setup(details()+'<h2>Data Structures and Analysis | COMP 210</h2>'+details('5501'));
  const records=captureExpandedSections('2027 Spring').records;
  expect(records.map((r:{course_id:string})=>r.course_id)).toEqual(['COMP 211','COMP 210']);
});
