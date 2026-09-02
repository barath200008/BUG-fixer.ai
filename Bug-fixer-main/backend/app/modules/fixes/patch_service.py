"""Mirrors: backend/src/modules/fixes/{diff.service,patch.service}.ts"""
import os

import aiofiles

from app.common.utils.safe_path import resolve_safe_path


def count_changed_lines(diff: str) -> int:
    count = 0
    for line in diff.split("\n"):
        if (line.startswith("+") and not line.startswith("+++")) or (
            line.startswith("-") and not line.startswith("---")
        ):
            count += 1
    return count


async def read_workspace_file(root: str, file: str) -> str:
    target = resolve_safe_path(root, file)
    async with aiofiles.open(target, "r", encoding="utf-8") as f:
        return await f.read()


async def write_workspace_file(root: str, file: str, content: str) -> str:
    target = resolve_safe_path(root, file)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    async with aiofiles.open(target, "w", encoding="utf-8") as f:
        await f.write(content)
    return target


def apply_simple_replacement(original: str, old_text: str, new_text: str) -> str:
    if old_text not in original:
        raise ValueError("Original code context was not found")
    return original.replace(old_text, new_text, 1)
