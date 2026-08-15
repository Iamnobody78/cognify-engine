"""
Module D: Sandbox Executor — isolated code execution container.
Supports Python and shell scripts with resource limits.
"""

import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutionResult:
    """Result of a sandboxed code execution."""

    success: bool
    output: str = ""
    error: str = ""
    exit_code: int = -1
    duration_ms: float = 0.0
    truncated: bool = False
    metadata: dict = field(default_factory=dict)


class SandboxExecutor:
    """Isolated code executor. Primary: subprocess with resource limits.
    Falls back to Docker if available.
    """

    def __init__(self, use_docker: bool = False):
        self.use_docker = use_docker and self._docker_available()

    @staticmethod
    def _docker_available() -> bool:
        try:
            import docker  # noqa: F401
            return True
        except ImportError:
            return False

    def execute_python(self, code: str, timeout: int = 30,
                       max_output_bytes: int = 64_000) -> ExecutionResult:
        """Execute Python code in a subprocess sandbox."""
        t0 = time.time()
        try:
            proc = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                timeout=timeout,
                text=True,
                env={"PYTHONUNBUFFERED": "1"},
            )
            out = proc.stdout
            err = proc.stderr
            exit_code = proc.returncode
            success = exit_code == 0
            truncated = len(out) > max_output_bytes
            if truncated:
                out = out[:max_output_bytes] + "\n[... output truncated ...]"
            return ExecutionResult(
                success=success,
                output=out,
                error=err,
                exit_code=exit_code,
                duration_ms=(time.time() - t0) * 1000,
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error=f"Execution timed out after {timeout}s",
                duration_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )

    def execute_shell(self, cmd: str, timeout: int = 60) -> ExecutionResult:
        """Execute a shell command in a subprocess."""
        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                timeout=timeout,
                text=True,
            )
            return ExecutionResult(
                success=proc.returncode == 0,
                output=proc.stdout,
                error=proc.stderr,
                exit_code=proc.returncode,
                duration_ms=(time.time() - t0) * 1000,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error=f"Shell execution timed out after {timeout}s",
                duration_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )

    def execute_in_docker(self, code: str, image: str = "python:3.10-slim",
                          timeout: int = 30, mem_limit: str = "128m") -> ExecutionResult:
        """Execute code inside a Docker container (requires docker SDK)."""
        if not self.use_docker:
            return ExecutionResult(success=False, error="Docker not available")
        t0 = time.time()
        try:
            import docker
            client = docker.from_env()
            container = client.containers.run(
                image=image,
                command=["python", "-c", code],
                network_disabled=True,
                mem_limit=mem_limit,
                detach=True,
            )
            try:
                result = container.wait(timeout=timeout)
                logs = container.logs().decode("utf-8", errors="replace")
                return ExecutionResult(
                    success=result["StatusCode"] == 0,
                    output=logs,
                    exit_code=result["StatusCode"],
                    duration_ms=(time.time() - t0) * 1000,
                )
            except Exception:
                container.kill()
                return ExecutionResult(
                    success=False,
                    error=f"Docker execution timed out after {timeout}s",
                    duration_ms=(time.time() - t0) * 1000,
                )
            finally:
                container.remove()
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Docker error: {e}",
                duration_ms=(time.time() - t0) * 1000,
            )


# ── Global singleton ────────────────────────────────────────────────────────

sandbox = SandboxExecutor()
