"""Mirrors: backend/src/modules/uploads/upload.service.ts"""
import hashlib
import os
import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors.app_error import AppError
from app.common.utils.safe_path import resolve_safe_path
from app.core.config import settings
from app.core.storage import project_storage_path
from app.models.project import Project


async def store_project_archive(
    db: AsyncSession, project_id: str, input_path: str, original_name: str
) -> dict:
    size = os.path.getsize(input_path)
    if size > settings.MAX_UPLOAD_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", "Uploaded archive exceeds the configured limit")

    target_dir = os.path.join(project_storage_path(project_id), "uploads")
    os.makedirs(target_dir, exist_ok=True, mode=0o750)

    filename = f"{uuid.uuid4()}-{os.path.basename(original_name)}"
    target = resolve_safe_path(target_dir, filename)

    sha256 = hashlib.sha256()
    with open(input_path, "rb") as src, open(target, "wb") as dst:
        while chunk := src.read(1024 * 1024):
            sha256.update(chunk)
            dst.write(chunk)
    os.chmod(target, 0o640)

    await db.execute(update(Project).where(Project.id == project_id).values(sourcePath=target))
    await db.commit()

    return {"storagePath": target, "sha256": sha256.hexdigest()}
