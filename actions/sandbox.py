# actions/sandbox.py
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from typing import Optional

from actions.code_tracker import tracker


class PythonSandbox:
    def __init__(
        self,
        timeout: float = 15.0,
        max_output_chars: int = 150_000,
        python_executable: str = "python",
    ):
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.python_executable = python_executable

    def execute(self, code: str, timeout: Optional[float] = None) -> dict:
        timeout = timeout if timeout is not None else self.timeout
        start = time.perf_counter()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name

        stdout = ""
        stderr = ""
        returncode = -1
        success = False

        try:
            proc = subprocess.run(
                [self.python_executable, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            stdout = (proc.stdout or "")[: self.max_output_chars]
            stderr = (proc.stderr or "")[: self.max_output_chars]
            returncode = proc.returncode
            success = returncode == 0

        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "")[: self.max_output_chars] if isinstance(e.stdout, str) else ""
            stderr = f"Timeout after {timeout} seconds\n"
            if getattr(e, "stderr", None) and isinstance(e.stderr, str):
                stderr += e.stderr[: self.max_output_chars]
            returncode = -1
            success = False

        except Exception as e:
            stdout = ""
            stderr = f"Sandbox internal error: {type(e).__name__}: {e}"
            returncode = -2
            success = False

        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

        # Отправляем результат в Code Tracker → окно Code Monitor обновится автоматически
        tracker.add_record(
            code=code,
            output=stdout,
            error=stderr,
            is_success=success,
        )

        elapsed = time.perf_counter() - start

        return {
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "execution_time": round(elapsed, 4),
        }


# Имя, которое будем использовать в main.py
core_sandbox = PythonSandbox(timeout=15.0)