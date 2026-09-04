"""Mirrors: backend/src/modules/sandbox/docker.service.ts"""
from app.modules.sandbox.container_manager import CommandResult, execute_in_docker


async def docker_execute(workspace: str, command: str) -> CommandResult:
    return await execute_in_docker(workspace, command)
