import asyncio
import json
import sys
from contextlib import suppress

from fastapi import FastAPI, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from typing import Literal
from app.schedule_export import ScheduleExportRequest, ExportError, calendar_bytes, record_bytes

from app.audit_parser import parse_pages
from app.audit_review import InvalidReview, review
from app.catalog import available_terms, find_snapshot, search_courses, section_options
from app.catalog_models import AvailableTerm, CourseSearchResult, SectionOptions
from app.curriculum import load_rule_packs, resolve_reviewed
from app.recommendation_models import RecommendationRequest, RecommendationResult
from app.recommendations import recommend
from app.scheduling import generate_schedules
from app.scheduling_models import ScheduleRequest, ScheduleResult
from app.rule_models import AvailableCurricula, CurriculumResolution
from app.models import AuditDraft, ErrorResponse, ExtractedPage, ReviewedAudit, ReviewRequest

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
EXTRACTION_TIMEOUT = 15

ERRORS = {
    "invalid_pdf": "Choose a PDF document with a valid PDF signature.",
    "encrypted_pdf": "This PDF is password protected. Export an unencrypted copy to continue.",
    "too_many_pages": "This version supports PDFs with up to 25 pages.",
    "empty_pdf": "This PDF has no pages.",
    "too_much_text": "This document exceeds the supported extraction size.",
    "unreadable_pdf": "The PDF could not be read. Try exporting a fresh copy.",
    "extraction_timeout": "Extraction took too long. Try a smaller PDF or a fresh export.",
    "file_too_large": "Choose a PDF smaller than 10 MB.",
    "no_text": "No readable text was found. Scanned PDFs and OCR are not supported yet.",
    "worker_unavailable": "PDF extraction is temporarily unavailable. Please try again.",
}


def error(code: str, status: int = 422):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": ERRORS[code]}})


class BodyLimitMiddleware:
    """Cap actual received bytes, including multipart bodies without Content-Length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in {"/api/v1/audits/parse", "/api/v1/audits/review", "/api/v1/curricula/resolve", "/api/v1/recommendations", "/api/v1/schedules/generate", "/api/v1/schedules/export/ics", "/api/v1/schedules/export/json"}:
            return await self.app(scope, receive, send)
        limit = MAX_REQUEST_BYTES if scope["path"].endswith("/parse") else 2 * 1024 * 1024
        received = 0
        messages = []
        # Bound the body before the multipart parser can spool uploaded files.
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            received += len(message.get("body", b""))
            if received > limit:
                response = error("file_too_large", 413) if scope["path"].endswith("/parse") else JSONResponse(status_code=413, content={"error": {"code": "review_too_large", "message": "This review exceeds the supported request size."}})
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(messages)

        async def limited_receive():
            return next(iterator)

        await self.app(scope, limited_receive, send)


app = FastAPI(title="UNC Course Planner", version="0.6.0")
app.add_middleware(BodyLimitMiddleware)
# Bound concurrent extraction processes as well as per-process duration.
worker_slots = asyncio.Semaphore(2)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo uploaded content or student input in validation errors.
    message = "A PDF file is required in the file field." if request.url.path.endswith("/parse") else "Some request fields are invalid. Check the values and try again."
    fields = [".".join(str(part) for part in item['loc']) for item in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": message, "fields": fields}})


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "stage": "calendar_comparison_and_export"}


@app.post("/api/v1/audits/parse", response_model=AuditDraft,
          responses={413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def parse_audit(file: UploadFile):
    try:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_UPLOAD_BYTES:
        return error("file_too_large", 413)
    if not data.startswith(b"%PDF-"):
        return error("invalid_pdf")

    async with worker_slots:
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "app.audit_worker",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(data), EXTRACTION_TIMEOUT)
            if process.returncode:
                return error("worker_unavailable", 503)
            result = json.loads(stdout)
        except TimeoutError:
            return error("extraction_timeout")
        except (OSError, ValueError):
            return error("worker_unavailable", 503)
        finally:
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

    if "error" in result:
        return error(result["error"])
    pages = [ExtractedPage(**page) for page in result["pages"]]
    text = "\n".join(page.text for page in pages)
    if not text.strip():
        return error("no_text")
    return parse_pages(pages)


@app.post("/api/v1/audits/review", response_model=ReviewedAudit,
          responses={422: {"model": ErrorResponse}})
def confirm_review(request: ReviewRequest):
    try:
        return review(request)
    except InvalidReview as exc:
        return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": exc.message, "fields": exc.fields}})


def data_error(code: str, message: str, status: int):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})


@app.get('/api/v1/curricula', response_model=AvailableCurricula)
def curricula():
    try:
        return load_rule_packs()
    except (ValueError, OSError):
        return data_error('invalid_rule_data', 'Curriculum definitions could not be loaded. Check the local rule packs.', 503)


@app.post('/api/v1/curricula/resolve', response_model=CurriculumResolution,
          responses={422: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})
def resolve_reviewed_curriculum(request: ReviewedAudit):
    try:
        return resolve_reviewed(request, load_rule_packs())
    except InvalidReview as exc:
        return data_error(exc.code, exc.message, 422)
    except (ValueError, OSError):
        return data_error('invalid_rule_data', 'Curriculum definitions could not be loaded. Check the local rule packs.', 503)


@app.get('/api/v1/terms', response_model=list[AvailableTerm])
def terms():
    try:
        return available_terms()
    except (ValueError, OSError):
        return data_error('invalid_catalog_data', 'A course dataset failed validation. Check the local imported data.', 503)


@app.get('/api/v1/courses', response_model=CourseSearchResult)
def courses(snapshot_id: str, q: str = '', term_id: str | None = None,
            attribute_id: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    try:
        return search_courses(find_snapshot(snapshot_id), query=q, term_id=term_id,
                              attribute_id=attribute_id, offset=offset, limit=limit)
    except LookupError as exc:
        return data_error('not_found', str(exc), 404)
    except (ValueError, OSError):
        return data_error('invalid_catalog_data', 'A course dataset failed validation. Check the local imported data.', 503)


@app.get('/api/v1/courses/{course_id}/sections', response_model=SectionOptions)
def sections(course_id: str, snapshot_id: str, term_id: str):
    try:
        return section_options(find_snapshot(snapshot_id), course_id, term_id)
    except LookupError as exc:
        return data_error('not_found', str(exc), 404)
    except (ValueError, OSError):
        return data_error('invalid_catalog_data', 'A course dataset failed validation. Check the local imported data.', 503)


@app.post('/api/v1/recommendations', response_model=RecommendationResult,
          responses={422: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})
def recommendations(request: RecommendationRequest):
    try:
        return recommend(request.reviewed, find_snapshot(request.snapshot_id), request.term_id, load_rule_packs())
    except InvalidReview as exc:
        return data_error(exc.code, exc.message, 422)
    except LookupError as exc:
        return data_error('not_found', str(exc), 404)
    except (ValueError, OSError):
        return data_error('invalid_planning_data', 'Course or curriculum data could not be loaded. Check the local datasets and rule packs.', 503)


@app.post('/api/v1/schedules/generate', response_model=ScheduleResult,
          responses={422: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})
def schedules(request: ScheduleRequest):
    try:
        return generate_schedules(request, find_snapshot(request.snapshot_id), load_rule_packs())
    except InvalidReview as exc:
        return data_error(exc.code, exc.message, 422)
    except LookupError as exc:
        return data_error('not_found', str(exc), 404)
    except (ValueError, OSError):
        return data_error('invalid_planning_data', 'Course or curriculum data could not be loaded. Check the local datasets and rule packs.', 503)


@app.post('/api/v1/schedules/export/{format}', response_class=Response,
          responses={422: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})
def export_schedule(format: Literal['ics', 'json'], request: ScheduleExportRequest):
    try:
        query = request.schedule_request
        # Export must be tied to the dataset and rules the user actually reviewed.
        if not query.expected_snapshot_digest or query.rule_revisions is None:
            raise ExportError('Regenerate schedules before exporting so data and rule versions can be checked.')
        snapshot = find_snapshot(query.snapshot_id)
        result = generate_schedules(query, snapshot, load_rule_packs())
        chosen = next((s for s in result.schedules if s.id == request.schedule_id), None)
        if chosen is None:
            return data_error('schedule_not_found', 'This option is no longer in these results. Regenerate schedules and choose an option again.', 404)
        term = next(t for t in snapshot.terms if t.id == query.term_id)
        data = calendar_bytes(chosen, result, term, request) if format == 'ics' else record_bytes(chosen, result, term, request)
        # Hashing avoids putting arbitrary source IDs into response headers or filenames.
        import hashlib
        name = hashlib.sha256(chosen.id.encode()).hexdigest()[:12]
        return Response(data, media_type='text/calendar; charset=utf-8' if format == 'ics' else 'application/json',
                        headers={'Content-Disposition': f'attachment; filename="preferred-schedule-{name}.{format}"',
                                 'Cache-Control': 'no-store'})
    except ExportError as exc:
        return data_error('export_unavailable', str(exc), 422)
    except InvalidReview as exc:
        return data_error(exc.code, exc.message, 422)
    except LookupError:
        return data_error('not_found', 'The selected course dataset or term is unavailable.', 404)
    except (ValueError, OSError):
        return data_error('invalid_planning_data', 'Course or curriculum data could not be loaded. Check the local datasets and rule packs.', 503)
