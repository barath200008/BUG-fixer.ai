"""Mirrors: backend/src/modules/workspace/workspace.service.ts"""
import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.errors.app_error import AppError
from app.common.utils.safe_path import resolve_safe_path
from app.models.context import Workspace
from app.models.project import Project
from app.modules.workspace.schemas import (
    ExecResult,
    GitStatusEntry,
    GitStatusResult,
    SearchMatch,
    TreeNode,
)

SKIP_DIRS = {".git", "node_modules", ".venv", "dist", "build"}
SEARCH_SKIP_DIRS = SKIP_DIRS | {"sandbox-work"}
SEARCH_MAX_MATCHES = 200
SEARCH_MAX_FILE_BYTES = 1_000_000
SEARCH_MAX_FILES = 2000


async def workspace_for(db: AsyncSession, user_id: str, workspace_id: str) -> Workspace:
    stmt = (
        select(Workspace)
        .join(Project, Workspace.projectId == Project.id)
        .where(Workspace.id == workspace_id, Project.ownerId == user_id)
        .options(selectinload(Workspace.project))
    )
    ws = (await db.execute(stmt)).scalar_one_or_none()
    if ws is None:
        raise AppError(404, "WORKSPACE_NOT_FOUND", "Workspace was not found")
    return ws


def _walk(root: str, current: str, depth: int) -> list[TreeNode]:
    if depth > 20:
        return []
    result: list[TreeNode] = []
    try:
        entries = list(os.scandir(current))
    except FileNotFoundError:
        return []
    for entry in entries:
        if entry.name in SKIP_DIRS:
            continue
        full = os.path.join(current, entry.name)
        rel = os.path.relpath(full, root)
        if entry.is_dir():
            result.append(TreeNode(name=entry.name, path=rel, type="folder", children=_walk(root, full, depth + 1)))
        else:
            result.append(TreeNode(name=entry.name, path=rel, type="file"))
    result.sort(key=lambda n: (0 if n.type == "folder" else 1, n.name.lower()))
    return result


async def tree(db: AsyncSession, user_id: str, workspace_id: str) -> list[TreeNode]:
    ws = await workspace_for(db, user_id, workspace_id)
    return await asyncio.to_thread(_walk, ws.rootPath, ws.rootPath, 0)


async def read_file(db: AsyncSession, user_id: str, workspace_id: str, file: str) -> dict:
    ws = await workspace_for(db, user_id, workspace_id)
    target = resolve_safe_path(ws.rootPath, file)
    if not os.path.isfile(target):
        raise AppError(400, "NOT_A_FILE", "The requested path is not a file")
    if os.path.getsize(target) > 2_000_000:
        raise AppError(413, "FILE_TOO_LARGE", "Workspace file exceeds the editor limit")
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    return {"path": file, "content": content}


async def write_file(db: AsyncSession, user_id: str, workspace_id: str, file: str, content: str) -> dict:
    ws = await workspace_for(db, user_id, workspace_id)
    if len(content) > 5_000_000:
        raise AppError(413, "CONTENT_TOO_LARGE", "File content exceeds the editor limit")
    target = resolve_safe_path(ws.rootPath, file)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return {"path": file}


# --- Terminal: runs inside the Docker sandbox (Phase 5). Interim: not yet available. ---
async def exec_command(db: AsyncSession, user_id: str, workspace_id: str, command: str) -> ExecResult:
    await workspace_for(db, user_id, workspace_id)
    if not command.strip():
        raise AppError(400, "EMPTY_COMMAND", "Command is required")
    raise AppError(
        501,
        "SANDBOX_NOT_AVAILABLE",
        "The sandboxed terminal ships in Phase 5 (Docker sandbox module) of this conversion",
    )


def _collect_searchable_files(root: str, current: str, depth: int, out: list[str]) -> None:
    if depth > 20 or len(out) >= SEARCH_MAX_FILES:
        return
    try:
        entries = list(os.scandir(current))
    except FileNotFoundError:
        return
    for entry in entries:
        if entry.name in SEARCH_SKIP_DIRS:
            continue
        full = os.path.join(current, entry.name)
        if entry.is_dir():
            _collect_searchable_files(root, full, depth + 1, out)
        else:
            out.append(full)
        if len(out) >= SEARCH_MAX_FILES:
            return


def _search(root: str, query: str) -> list[SearchMatch]:
    needle = query.lower()
    files: list[str] = []
    _collect_searchable_files(root, root, 0, files)
    matches: list[SearchMatch] = []
    for file in files:
        if len(matches) >= SEARCH_MAX_MATCHES:
            break
        try:
            if os.path.getsize(file) > SEARCH_MAX_FILE_BYTES:
                continue
            with open(file, "r", encoding="utf-8") as f:
                lines = f.read().split("\n")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines):
            if needle in line.lower():
                matches.append(
                    SearchMatch(file=os.path.relpath(file, root), line=i + 1, preview=line.strip()[:200])
                )
                if len(matches) >= SEARCH_MAX_MATCHES:
                    break
    return matches


async def search_workspace(db: AsyncSession, user_id: str, workspace_id: str, query: str) -> list[SearchMatch]:
    ws = await workspace_for(db, user_id, workspace_id)
    trimmed = query.strip()
    if not trimmed:
        raise AppError(400, "EMPTY_QUERY", "Search query is required")
    return await asyncio.to_thread(_search, ws.rootPath, trimmed)


# --- Source control: real git status/diff/commit via the git CLI ---


async def _run_git(cwd: str, args: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="replace")


async def _ensure_git_repo(root: str) -> None:
    if os.path.isdir(os.path.join(root, ".git")):
        return
    await _run_git(root, ["init"])
    await _run_git(root, ["config", "user.email", "dev@bugfixer.local"])
    await _run_git(root, ["config", "user.name", "BugFixer Dev"])
    await _run_git(root, ["add", "-A"])
    await _run_git(root, ["commit", "-m", "Initial workspace snapshot", "--allow-empty"])


async def git_status(db: AsyncSession, user_id: str, workspace_id: str) -> GitStatusResult:
    ws = await workspace_for(db, user_id, workspace_id)
    await _ensure_git_repo(ws.rootPath)
    branch_out = await _run_git(ws.rootPath, ["rev-parse", "--abbrev-ref", "HEAD"])
    status_out = await _run_git(ws.rootPath, ["status", "--porcelain=v1"])
    entries = [
        GitStatusEntry(status=line[:2].strip(), path=line[3:])
        for line in status_out.split("\n")
        if line
    ]
    return GitStatusResult(branch=branch_out.strip() or "main", entries=entries)


async def git_diff(db: AsyncSession, user_id: str, workspace_id: str, file: str | None) -> str:
    ws = await workspace_for(db, user_id, workspace_id)
    await _ensure_git_repo(ws.rootPath)
    args = ["diff", "--", file] if file else ["diff"]
    return await _run_git(ws.rootPath, args)


async def git_commit(db: AsyncSession, user_id: str, workspace_id: str, message: str) -> dict:
    ws = await workspace_for(db, user_id, workspace_id)
    await _ensure_git_repo(ws.rootPath)
    await _run_git(ws.rootPath, ["add", "-A"])
    trimmed = message.strip() or "Workspace update"
    proc = await asyncio.create_subprocess_exec(
        "git", "commit", "-m", trimmed, cwd=ws.rootPath,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return {"committed": proc.returncode == 0}
