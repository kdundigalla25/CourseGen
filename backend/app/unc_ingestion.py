"""Manual UNC subject import. Stage validated catalog data and review-only offerings."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import httpx

from app.curriculum import DATA_ROOT
from app.ingestion import publish_snapshot
from app.unc_catalog import parse_catalog, soup_for
from app.unc_fetch import PublicCollector, atomic_write
from app.unc_sections import parse_sections


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def compare_reports(previous, current):
    if not all(isinstance(report.get('catalog_fingerprints'),dict) and isinstance(report.get('offering_rows'),list) for report in (previous,current)):
        raise ValueError('Prior report is missing comparison fields; create a baseline with the current adapter')
    if any(previous.get(k)!=current.get(k) for k in ('subject','edition','term')):
        raise ValueError('Compare reports for the same subject, edition and target term')
    def changes(old,new):
        return dict(added=sorted(new.keys()-old.keys()),removed=sorted(old.keys()-new.keys()),
                    changed=sorted(k for k in old.keys() & new.keys() if old[k]!=new[k]))
    def sections(report):
        values = {}
        for row in report['offering_rows']:
            copy = dict(row,section=dict(row['section']))
            copy['section'].pop('source_snapshot_id')
            values[copy['section']['id']] = fingerprint(copy)
        return values
    return dict(courses=changes(previous['catalog_fingerprints'],current['catalog_fingerprints']),
                sections=changes(sections(previous),sections(current)))


def collect(collector, *, subject, edition, term_name=None):
    if not re.fullmatch('[A-Z]{2,5}',subject) or not re.fullmatch(r'20\d{2}-20\d{2}',edition):
        raise ValueError('Use an uppercase subject and catalog edition YYYY-YYYY')
    source = collector.request(f'https://catalog.unc.edu/courses/{subject.lower()}/')
    snapshot = parse_catalog(source.content,subject=subject,edition=edition,retrieved_at=source.retrieved_at)
    report = dict(adapter_version='unc-subject-import-1',subject=subject,edition=edition,
        catalog_snapshot_id=snapshot.id,catalog_course_count=len(snapshot.courses),
        designation_count=len(snapshot.designations),offering_rows=[],
        catalog_fingerprints={c.id:fingerprint(dict(
            definition=c.model_dump(mode='json',exclude={'source_snapshot_id'}),
            attributes=sorted(d.attribute_id for d in snapshot.designations if d.course_id==c.id))) for c in snapshot.courses},
        limitations=['Catalog definitions do not establish semester availability or eligibility.',
                    'Course designations belong to this catalog edition, independently of a student\'s entering-cohort curriculum.',
                    'No verified section component/linkage information; no scheduling bundles are created.'])
    if term_name:
        if not re.fullmatch(r'20\d{2} (Spring|Fall|Summer I|Summer II)',term_name):
            raise ValueError('Unsupported term-name syntax')
        url = 'https://reports.unc.edu/class-search/'
        # On replay, no CSRF token is needed: the exact public query has its own cached receipt.
        key = f'{subject}:{term_name}'
        data = None
        if not collector.offline:
            form = collector.request(url,fresh=True)
            soup = soup_for(form.content)
            token = soup.select_one('input[name=csrfmiddlewaretoken]')
            terms = soup.select_one('#json_terms')
            subjects = soup.select_one('#json_subjects')
            if not token or not terms or not subjects or term_name not in json.loads(terms.string) or subject not in json.loads(subjects.string):
                raise ValueError('Requested subject/term is unavailable or the public form changed')
            # Use the normal fresh public form and its cookie, never synthesize a token.
            data = dict(csrfmiddlewaretoken=token['value'],term=term_name,subject=subject,catalog_number='')
        receipt = collector.request(url,method='POST',data=data,key=key,headers={'Referer':url})
        source_id = f'unc-class-search-{receipt.content_sha256[:16]}'
        rows = parse_sections(receipt.content,subject=subject,term_name=term_name,source_id=source_id)
        report.update(term=term_name,offering_source=dict(id=source_id,url=url,method='POST',
            filters=dict(subject=subject,term=term_name),retrieved_at=receipt.retrieved_at.isoformat(),
            content_sha256=receipt.content_sha256,adapter_version='unc-class-search-html-1'),
            section_count=len(rows),course_count=len({row.course_id for row in rows}),
            unknown_time_count=sum(row.section.meetings[0].kind=='unknown' for row in rows),
            courses_missing_from_catalog=sorted({row.course_id for row in rows}-{c.id for c in snapshot.courses}),
            offering_rows=[row.model_dump(mode='json') for row in rows])
    return snapshot, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject',required=True)
    parser.add_argument('--edition',required=True)
    parser.add_argument('--term',help='Optional public class-search term, for a review-only section report')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--cache',type=Path,default=DATA_ROOT/'source-cache'/'unc-import')
    parser.add_argument('--directory',type=Path,default=DATA_ROOT/'staging')
    parser.add_argument('--compare-report',type=Path,help='Prior report for an explicit added/removed/changed-record diff')
    args = parser.parse_args()
    if args.offline and args.refresh: parser.error('Choose offline replay or refresh, not both')
    collector = PublicCollector(args.cache,offline=args.offline,refresh=args.refresh)
    try:
        snapshot,report = collect(collector,subject=args.subject,edition=args.edition,term_name=args.term)
        if args.compare_report:
            if args.compare_report.stat().st_size>10*1024*1024: raise ValueError('Prior report exceeds 10 MB')
            report['changes'] = compare_reports(json.loads(args.compare_report.read_text(encoding='utf-8')),report)
        # Nothing is staged until every requested response has parsed completely.
        digest = hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()[:16]
        catalog = publish_snapshot(snapshot,args.directory/'catalogs')
        output = args.directory/'reports'/f'{snapshot.id}-{digest}.json'
        atomic_write(output,(json.dumps(report,indent=2)+'\n').encode())
        print(f'Validated catalog: {len(snapshot.courses)} courses, {len(snapshot.designations)} designations; {catalog}')
        if args.term: print(f'Review-only offerings: {report["section_count"]} sections; {report["unknown_time_count"]} with unknown times; 0 verified bundles')
        print('Report:',output)
        print('Staged only. Existing published datasets are unchanged.')
        return 0
    except (ValueError,OSError,KeyError,TypeError,httpx.HTTPError) as exc:
        print(f'Import failed ({type(exc).__name__}); no new dataset was published. Check source access, format and query coverage.')
        return 1
    finally:
        collector.close()


if __name__=='__main__':
    raise SystemExit(main())
