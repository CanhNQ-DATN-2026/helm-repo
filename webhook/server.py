import asyncio
import logging
import os

logger = logging.getLogger(__name__)

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /app


async def _run_claude(prompt: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "claude", "--print", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKDIR,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        return "Analysis timed out after 5 minutes."

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")

    return stdout.decode().strip()
