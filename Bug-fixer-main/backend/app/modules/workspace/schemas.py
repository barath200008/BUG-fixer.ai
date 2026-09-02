from typing import Literal

from pydantic import BaseModel


class TreeNode(BaseModel):
    name: str
    path: str
    type: Literal["folder", "file"]
    children: list["TreeNode"] | None = None


TreeNode.model_rebuild()


class FileContent(BaseModel):
    path: str
    content: str


class WriteFileRequest(BaseModel):
    path: str
    content: str


class WriteFileResponse(BaseModel):
    path: str


class ExecRequest(BaseModel):
    command: str


class ExecResult(BaseModel):
    stdout: str
    stderr: str
    code: int
    durationMs: int


class SearchMatch(BaseModel):
    file: str
    line: int
    preview: str


class GitStatusEntry(BaseModel):
    path: str
    status: str


class GitStatusResult(BaseModel):
    branch: str
    entries: list[GitStatusEntry]


class GitDiffResponse(BaseModel):
    diff: str


class GitCommitRequest(BaseModel):
    message: str


class GitCommitResponse(BaseModel):
    committed: bool
