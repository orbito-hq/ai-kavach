import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.pipeline import run_scan

app = FastAPI(title="AI Kavach", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    db.init_db()


@app.post("/api/scans")
async def create_scan(
    background_tasks: BackgroundTasks,
    repo_url: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    if not repo_url and not file:
        raise HTTPException(400, "Provide either repo_url or a zip file upload")
    if repo_url and file:
        raise HTTPException(400, "Provide only one of repo_url or file")

    scan_id = str(uuid.uuid4())
    source = repo_url if repo_url else file.filename
    zip_bytes = await file.read() if file else None

    db.create_scan(scan_id, source, datetime.now(timezone.utc).isoformat())
    background_tasks.add_task(run_scan, scan_id, source, zip_bytes, repo_url)

    return {"scan_id": scan_id, "status": "PENDING"}


@app.get("/api/scans")
def list_scans():
    return db.list_scans()


@app.get("/api/scans/{scan_id}")
def get_scan(scan_id: str):
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


@app.get("/api/scans/{scan_id}/findings")
def get_findings(scan_id: str):
    if not db.get_scan(scan_id):
        raise HTTPException(404, "Scan not found")
    return db.list_findings(scan_id)


@app.get("/api/findings/{finding_id}")
def get_finding(finding_id: str):
    finding = db.get_finding(finding_id)
    if not finding:
        raise HTTPException(404, "Finding not found")
    return finding
