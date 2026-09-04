"""Mirrors: backend/src/modules/ai/context-builder.ts"""
import json
import os

import aiofiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.errors.app_error import AppError
from app.models.bug import Bug
from app.models.context import ContextChunk, ContextDocument
from app.models.project import Project


async def build_ai_context(
    db: AsyncSession,
    project_id: str,
    bug_id: str | None = None,
    file_path: str | None = None,
    line_number: int | None = None,
    question: str | None = None,
) -> str:
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.contextDocuments).selectinload(ContextDocument.chunks)
        )
    )
    project = (await db.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise AppError(404, "PROJECT_NOT_FOUND", "Project was not found")

    bug = None
    if bug_id:
        bug_stmt = select(Bug).where(Bug.id == bug_id, Bug.projectId == project_id)
        bug = (await db.execute(bug_stmt)).scalar_one_or_none()
    else:
        bug_stmt = (
            select(Bug)
            .where(Bug.projectId == project_id)
            .order_by(Bug.updatedAt.desc())
            .limit(1)
        )
        bug = (await db.execute(bug_stmt)).scalar_one_or_none()

    source = ""
    if project.workspacePath and file_path:
        full = os.path.join(project.workspacePath, file_path)
        try:
            async with aiofiles.open(full, "r", encoding="utf-8") as f:
                source = await f.read()
        except (FileNotFoundError, UnicodeDecodeError, OSError):
            source = ""

    context_docs = []
    for doc in project.contextDocuments:
        chunks_sorted = sorted(doc.chunks, key=lambda c: c.ordinal)[:20]
        content = doc.contentText or "\n".join(c.content for c in chunks_sorted)
        context_docs.append({"name": doc.name, "type": doc.type, "content": content})

    payload = {
        "project": {
            "id": project.id,
            "name": project.name,
            "language": project.language,
            "framework": project.framework,
        },
        "bug": (
            {
                "id": bug.id,
                "code": bug.code,
                "title": bug.title,
                "description": bug.description,
                "severity": bug.severity,
                "component": bug.component,
                "filePath": bug.filePath,
                "lineNumber": bug.lineNumber,
                "stackTrace": bug.stackTrace,
            }
            if bug
            else None
        ),
        "question": question,
        "filePath": file_path,
        "lineNumber": line_number,
        "source": source,
        "contextDocuments": context_docs,
    }
    return json.dumps(payload, default=str)
