from fastapi import FastAPI

app = FastAPI(title="json-to-pdf-report")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
