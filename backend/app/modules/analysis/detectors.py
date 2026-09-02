"""Mirrors: backend/src/modules/analysis/detectors/{build.detector,runtime.detector}.ts"""
import json
import os


async def detect_build_command(root: str, language: str) -> str:
    if language in ("JavaScript", "TypeScript"):
        pkg_path = os.path.join(root, "package.json")
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            scripts = pkg.get("scripts", {})
            return "npm run build" if scripts.get("build") else "npm install --ignore-scripts"
        except (FileNotFoundError, json.JSONDecodeError):
            return "npm install --ignore-scripts"
    if language == "Python":
        return "python -m compileall -q ."
    if language == "Go":
        return "go test ./..."
    if language == "Rust":
        return "cargo check"
    return 'echo "No supported build command detected"'


async def detect_test_command(root: str, language: str) -> str:
    if language == "Python":
        if os.path.exists(os.path.join(root, "pytest.ini")):
            return "pytest"
        if os.path.exists(os.path.join(root, "pyproject.toml")):
            return "pytest"
        return "python -m unittest"
    if language in ("JavaScript", "TypeScript"):
        pkg_path = os.path.join(root, "package.json")
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            if pkg.get("scripts", {}).get("test"):
                return "npm test"
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return "npm test -- --runInBand"
    if language == "Go":
        return "go test ./..."
    if language == "Rust":
        return "cargo test"
    return 'echo "No supported test command detected"'
