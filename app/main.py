from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import is_database_configured, SessionLocal, settings
from app.routers.admin import router as admin_router
from app.routers.admin_auth import router as admin_auth_router
from app.routers.complaints import router as complaints_router
from app.services.storage import LOCAL_UPLOAD_DIR, USE_S3
from app.services.escalation import run_sla_escalation_check
from app.services.admin_cleanup import purge_stale_unverified_admins


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(complaints_router)
app.include_router(admin_auth_router)
app.include_router(admin_router)

scheduler = BackgroundScheduler()

def escalation_job():
    db = SessionLocal()
    try:
        print("[Scheduler] Running SLA escalation check...")
        run_sla_escalation_check(db)
    except Exception as e:
        print("[Scheduler ERROR]", e)
    finally:
        db.close()


def admin_cleanup_job():
    db = SessionLocal()
    try:
        deleted = purge_stale_unverified_admins(
            db,
            ttl_hours=settings.admin_unverified_ttl_hours,
        )
        if deleted:
            print(f"[Scheduler] Removed {deleted} stale unverified admin account(s)")
    except Exception as e:
        print("[Scheduler ERROR][AdminCleanup]", e)
    finally:
        db.close()

scheduler.add_job(escalation_job, "interval", minutes=5)
scheduler.add_job(admin_cleanup_job, "interval", minutes=settings.admin_cleanup_interval_minutes)
if not scheduler.running:
    scheduler.start()


# Serve uploaded images at /uploads/** when using local filesystem storage
# when USE_S3=true this block is skipped, cause images are served directly from S3
if not USE_S3:
    LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(LOCAL_UPLOAD_DIR)), name="uploads")


@app.get("/")
def root():
    return {"message": "root"}


@app.get("/health")
def health_check():
    return {"status": "ok", "database_configured": is_database_configured()}