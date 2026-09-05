"""Mirrors: backend/src/modules/code-analysis/project-inspector.ts"""
import os

from app.modules.code_analysis.dependency_analyzer import detect_dependencies
from app.modules.code_analysis.framework_detector import detect_framework
from app.modules.code_analysis.language_detector import detect_language
from app.modules.code_analysis.symbol_indexer import build_symbol_index

_ENTRY_POINT_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt",
    "go.mod", "Cargo.toml", "pom.xml",
}


async def inspect_project(root: str) -> dict:
    language = await detect_language(root)
    framework = await detect_framework(root)
    dependencies = await detect_dependencies(root)
    symbols = await build_symbol_index(root)

    try:
        top_level = os.listdir(root)
    except OSError:
        top_level = []

    return {
        "language": language,
        "framework": framework,
        "dependencies": dependencies,
        "symbolCount": len(symbols),
        "entryPoints": [name for name in top_level if name in _ENTRY_POINT_NAMES],
        "root": os.path.abspath(root),
    }