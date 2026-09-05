"""Mirrors: backend/src/modules/code-analysis/language-detector.ts"""
import os

_EXT_LANG = {
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".py": "Python", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".sql": "SQL", ".css": "CSS", ".html": "HTML",
}
_SKIP_DIRS = {"node_modules"}


async def detect_language(root: str) -> str:
    try:
        top_level = os.listdir(root)
    except OSError:
        return "Unknown"

    if "package.json" in top_level:
        return "JavaScript"
    if "pyproject.toml" in top_level or "requirements.txt" in top_level:
        return "Python"
    if "go.mod" in top_level:
        return "Go"
    if "Cargo.toml" in top_level:
        return "Rust"
    if "pom.xml" in top_level or "build.gradle" in top_level:
        return "Java"

    counts: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            lang = _EXT_LANG.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1

    if not counts:
        return "Unknown"
    return max(counts.items(), key=lambda kv: kv[1])[0]