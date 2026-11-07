from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.ingestion import publish_snapshot, validate_file
from app.unc_catalog import parse_catalog
from app.unc_fetch import MAX_BYTES, PublicCollector, Receipt
from app.unc_ingestion import collect, compare_reports
from app.unc_sections import parse_meetings, parse_sections

FIXTURES = Path(__file__).parent/'fixtures'/'unc'
STAMP = datetime(2026,11,7,tzinfo=timezone.utc)
CATALOG = (FIXTURES/'catalog.html').read_bytes()
SECTIONS = (FIXTURES/'sections.html').read_bytes()


def catalog(content=CATALOG,**kwargs):
    return parse_catalog(content,subject='COMP',edition=kwargs.get('edition','2026-2027'),retrieved_at=STAMP)


def sections(content=SECTIONS):
    return parse_sections(content,subject='COMP',term_name='2027 Spring',source_id='search')


def test_catalog_fields_designations_and_no_fabricated_offerings(tmp_path):
    result = catalog()
    assert len(result.courses)==4
    course = next(c for c in result.courses if c.id=='COMP 110')
    assert course.title=='Introduction to Programming' and course.credits_min==course.credits_max==3
    assert course.prerequisite_text=='Synthetic prerequisite text.'
    assert any(c.credits_min==0.5 and c.credits_max==21 for c in result.courses)
    assert {(d.course_id,d.attribute_id) for d in result.designations} >= {('COMP 110','FC-QUANT'),('COMP 380','FC-VALUES')}
    assert result.sources[0].content_sha256==hashlib.sha256(CATALOG).hexdigest()
    assert result.sources[0].retrieved_at==STAMP.isoformat()
    assert result.classification=='public' and not result.terms and not result.sections and not result.bundles
    assert validate_file(publish_snapshot(result,tmp_path))==result
    assert catalog()==catalog()


@pytest.mark.parametrize('content',[
    CATALOG.replace(b'2026-2027 Academic Catalog',b'2025-2026 Academic Catalog'),
    CATALOG.replace(b'detail-code',b'new-code'),
    CATALOG.replace(b'3 Credits.',b'Contact department for credits.'),
    CATALOG.replace(b'FC-QUANT.',b'FC-QUANT or FC-VALUES.'),
    CATALOG.replace(b'COMPUTER SCIENCE (COMP)',b'MATHEMATICS (MATH)'),
    CATALOG+b'<a rel="next">Next</a>',
    CATALOG+CATALOG,
    b'<html>Access denied</html>',
])
def test_catalog_structure_or_edition_changes_fail_closed(content):
    with pytest.raises(ValueError): catalog(content)


def test_rowspan_expansion_counts_identifiers_and_thursday():
    rows=sections()
    assert [r.course_id for r in rows]==['COMP 110']*3+['COMP 116']
    assert rows[1].section.number=='002'
    assert rows[0].section.id=='unc-2027-spring-3301'
    assert [m.weekday for m in rows[2].section.meetings]==[1,3]
    assert rows[0].section.meetings[0].start_minute==545
    assert rows[0].section.meetings[0].start_date.isoformat()=='2027-01-06'
    assert all(r.section.linkage_status=='unknown' and r.section.component=='other' for r in rows)
    assert all(r.section.instructor is None and r.section.location is None for r in rows)


@pytest.mark.parametrize('content',[
    SECTIONS.replace(b'4 section(s)',b'5 section(s)'),
    SECTIONS.replace(b'2 course(s)',b'3 course(s)'),
    SECTIONS.replace(b'rowspan="4"',b'rowspan="5"'),
    SECTIONS.replace(b'Available Seats',b'Seats'),
    SECTIONS.replace(b'2027 Spring',b'2026 Fall'),
    SECTIONS.replace(b'4850',b'3301'),
    SECTIONS.replace(b'MWF 09:05 AM-09:55 AM',b'New unknown time format'),
    SECTIONS+b'<a rel="next">Next</a>',
])
def test_search_truncation_schema_and_wrong_query_are_rejected(content):
    with pytest.raises(ValueError): sections(content)


def test_no_time_does_not_mean_asynchronous_and_dates_remain_explicit():
    meeting=parse_meetings('None','01/06/2027 - 05/06/2027')[0]
    assert meeting.kind=='unknown' and meeting.start_date and meeting.start_minute is None
    assert parse_meetings('TBA','None')[0].kind=='unknown'
    with pytest.raises(ValueError): parse_meetings('MWF 09:55 AM-09:05 AM','None')


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_collector_robots_cache_offline_hash_and_failure_retention(tmp_path):
    requests=[]
    def handler(req):
        requests.append(req)
        if req.url.path=='/robots.txt': return httpx.Response(200,text='User-agent: *\nDisallow: /archives/\nCrawl-delay: 2')
        return httpx.Response(200,content=CATALOG)
    collector=PublicCollector(tmp_path,client=client_for(handler),pause=lambda _:None)
    url='https://catalog.unc.edu/courses/comp/'
    first=collector.request(url)
    assert len(requests)==2 and collector.minimum_interval==2
    assert collector.request(url)==first and len(requests)==2
    collector.offline=True
    assert collector.request(url)==first
    with pytest.raises(ValueError,match='No cached source'): collector.request('https://catalog.unc.edu/courses/math/')
    collector.close()
    collector=PublicCollector(tmp_path,refresh=True,client=client_for(lambda _:httpx.Response(503)),pause=lambda _:None)
    with pytest.raises(httpx.HTTPStatusError): collector.request(url)
    collector.offline=True
    assert collector.request(url)==first
    (tmp_path/f'{first.content_sha256}.html').write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='integrity'): collector.request(url)
    collector.close()


@pytest.mark.parametrize('status',[302,401,403,429])
def test_restrictions_redirects_and_rate_limits_stop(tmp_path,status):
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=='/robots.txt': return httpx.Response(200,text='User-agent: *\nAllow: /')
        return httpx.Response(status,headers={'Location':'https://other.example/'})
    collector=PublicCollector(tmp_path,client=client_for(handler),pause=lambda _:None)
    with pytest.raises((httpx.HTTPStatusError,ValueError)): collector.request('https://catalog.unc.edu/courses/comp/')
    assert calls==['/robots.txt','/courses/comp/']
    assert not list(tmp_path.glob('*.html')) or all(p.read_bytes()!=CATALOG for p in tmp_path.glob('*.html'))
    collector.close()


def test_disallowed_robots_and_url_allowlist(tmp_path):
    collector=PublicCollector(tmp_path,client=client_for(lambda _:httpx.Response(200,text='User-agent: *\nDisallow: /courses/')),pause=lambda _:None)
    with pytest.raises(ValueError,match='robots'): collector.request('https://catalog.unc.edu/courses/comp/')
    for url in ['http://catalog.unc.edu/courses/comp/','https://catalog.unc.edu/archives/','https://example.com/courses/comp/','https://catalog.unc.edu/courses/comp/?q=1']:
        with pytest.raises(ValueError,match='canonical'): collector.request(url)
    collector.close()


def test_large_response_rejected(tmp_path):
    collector=PublicCollector(tmp_path,client=client_for(lambda req:httpx.Response(200,content=b'User-agent: *\nAllow: /' if req.url.path=='/robots.txt' else b'x'*(MAX_BYTES+1))),pause=lambda _:None)
    with pytest.raises(ValueError,match='10 MB'): collector.request('https://catalog.unc.edu/courses/comp/')
    collector.close()


def test_public_form_submission_and_offline_replay_keep_query_provenance(tmp_path):
    calls=[]
    def handler(req):
        calls.append((req.method,req.url.path))
        if req.url.path=='/robots.txt': return httpx.Response(404)
        if req.url.host=='catalog.unc.edu': return httpx.Response(200,content=CATALOG)
        if req.method=='GET':
            return httpx.Response(200,text='<input name="csrfmiddlewaretoken" value="public-form-token"><script id="json_terms">["2027 Spring"]</script><script id="json_subjects">["COMP"]</script>',headers={'Set-Cookie':'csrftoken=public-form-token; Path=/'})
        assert b'term=2027+Spring' in req.content and b'csrfmiddlewaretoken=public-form-token' in req.content
        assert req.headers['referer']=='https://reports.unc.edu/class-search/'
        assert 'csrftoken=public-form-token' in req.headers['cookie']
        return httpx.Response(200,content=SECTIONS)
    collector=PublicCollector(tmp_path,client=client_for(handler),pause=lambda _:None)
    snapshot,report=collect(collector,subject='COMP',edition='2026-2027',term_name='2027 Spring')
    assert report['section_count']==4 and report['courses_missing_from_catalog']==['COMP 116']
    assert not snapshot.terms and not snapshot.bundles
    assert report['offering_source']['filters']==dict(subject='COMP',term='2027 Spring')
    assert 'public-form-token' not in json.dumps(report)
    collector.offline=True
    assert collect(collector,subject='COMP',edition='2026-2027',term_name='2027 Spring')==(snapshot,report)
    assert sum(method=='POST' for method,path in calls)==1
    collector.close()


def test_refresh_diff_ignores_source_receipts_but_reports_real_changes():
    previous=dict(subject='COMP',edition='2026-2027',term='2027 Spring',
        catalog_fingerprints={'COMP 110':'old','COMP 116':'same'},
        offering_rows=[row.model_dump(mode='json') for row in sections()])
    current=json.loads(json.dumps(previous))
    for row in current['offering_rows']: row['section']['source_snapshot_id']='new-retrieval'
    assert not compare_reports(previous,current)['sections']['changed']
    current['catalog_fingerprints']={'COMP 110':'new','COMP 210':'added'}
    current['offering_rows'][0]['section']['meetings'][0]['start_minute']=600
    removed=current['offering_rows'].pop()['section']['id']
    difference=compare_reports(previous,current)
    assert difference['courses']==dict(added=['COMP 210'],removed=['COMP 116'],changed=['COMP 110'])
    assert difference['sections']==dict(added=[],removed=[removed],changed=['unc-2027-spring-3301'])
    with pytest.raises(ValueError): compare_reports(previous,{**current,'term':'2026 Fall'})
    with pytest.raises(ValueError): compare_reports({},current)
