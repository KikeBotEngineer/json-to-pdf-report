from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import charts, metrics, pdf
from app.models import ReportRequest

MAX_BODY_BYTES = 5 * 1024 * 1024


class BodyLimit:
    """Reject request bodies over MAX_BODY_BYTES with 413, with or without Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and not length.isdigit():
            response = JSONResponse({"detail": "invalid content-length"}, status_code=400)
            return await response(scope, receive, send)
        if length is not None and int(length) > MAX_BODY_BYTES:
            response = JSONResponse({"detail": "payload too large"}, status_code=413)
            return await response(scope, receive, send)

        seen = 0

        async def limited_receive():
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > MAX_BODY_BYTES:
                raise HTTPException(413, "payload too large")
            return message

        await self.app(scope, limited_receive, send)


app = FastAPI(title="json-to-pdf-report")
app.add_middleware(BodyLimit)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Default 422 echoes each offending "input"; on a 5 MB body that reflects it back.
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/report",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF report"}},
)
def report(req: ReportRequest) -> Response:
    m, df = metrics.compute(req)
    images = charts.build(df, req.period.start, req.period.end)
    return Response(
        pdf.build(req, m, images),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="report.pdf"'},
    )
