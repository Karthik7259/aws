from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from app.database import settings

USE_S3: bool = settings.use_s3
LOCAL_UPLOAD_DIR: Path = Path(settings.upload_dir)

S3_BUCKET: str = settings.aws_bucket
S3_REGION: str = settings.aws_region
LOCAL_BASE_URL: str = settings.local_base_url


def save_complaint_image(file_bytes: bytes, original_filename: str, ticket_id: str) -> str:
    ext = Path(original_filename).suffix.lower() or ".jpg"
    safe_name = f"{ticket_id}_{uuid.uuid4().hex[:8]}{ext}"
    key = f"complaints/{ticket_id}/{safe_name}"

    if USE_S3:
        return _save_s3(file_bytes, key)
    return _save_local(file_bytes, key)


def get_image_url(storage_key: str) -> str | None:
    if not storage_key:
        return None
    if USE_S3:
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{storage_key}"
    base = LOCAL_BASE_URL.rstrip("/")
    return f"{base}/uploads/{storage_key}"


def delete_complaint_image(storage_key: str) -> None:
    if not storage_key:
        return
    if USE_S3:
        _delete_s3(storage_key)
    else:
        _delete_local(storage_key)

def _save_local(file_bytes: bytes, key: str) -> str:
    dest = LOCAL_UPLOAD_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file_bytes)
    return key


def _delete_local(key: str) -> None:
    target = LOCAL_UPLOAD_DIR / key
    if target.exists():
        target.unlink()
    try:
        target.parent.rmdir()
    except OSError:
        pass

# S3 backend (only imported when USE_S3=true; keeps boto3 optional)

def _save_s3(file_bytes: bytes, key: str) -> str:
    import boto3  # type: ignore
    import mimetypes

    content_type, _ = mimetypes.guess_type(key)
    content_type = content_type or "application/octet-stream"

    s3 = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


def _delete_s3(key: str) -> None:
    import boto3  # type: ignore

    s3 = boto3.client("s3", region_name=S3_REGION)
    s3.delete_object(Bucket=S3_BUCKET, Key=key)