import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from common import (
    INPUT_DIR, OUTPUT_DIR, JOB_DIR, ensure_dirs,
    atomic_json, read_job, cleanup_expired, iso_now,
)

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "1"))
CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "30"))
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "3300"))

def process(job_path: Path):
    job = read_job(job_path)
    if not job or job.get("status") != "queued":
        return

    job_id = job.get("id")
    input_name = job.get("input_path", "")

    if not job_id or Path(input_name).name != input_name or not input_name:
        job.update(status="failed", error="Invalid job or input path",
                   finished_at=iso_now())
        atomic_json(job_path, job)
        return

    source = INPUT_DIR / input_name
    if not source.is_file():
        job.update(status="failed", error="Input file not found",
                   finished_at=iso_now())
        atomic_json(job_path, job)
        return

    job.update(status="processing", started_at=iso_now())
    atomic_json(job_path, job)

    output_name = f"{job_id}.md"
    output_path = OUTPUT_DIR / output_name
    temp_output = OUTPUT_DIR / f".{job_id}.partial.md"

    try:
        result = subprocess.run(
            [
                sys.executable, "/app/convert_one.py",
                "--input", str(source),
                "--output", str(temp_output),
            ],
            capture_output=True,
            text=True,
            timeout=JOB_TIMEOUT_SECONDS,
            check=False,
        )

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Conversion failed")
            raise RuntimeError(message[-1500:])

        if not temp_output.is_file():
            raise RuntimeError("Converter did not create output")

        os.replace(temp_output, output_path)

        # Không tạo lại job nếu job đã hết hạn trong khi convert.
        current = read_job(job_path)
        if current is None:
            output_path.unlink(missing_ok=True)
            return

        current.update(
            status="completed",
            output_path=output_name,
            output_bytes=output_path.stat().st_size,
            finished_at=iso_now(),
        )
        atomic_json(job_path, current)

    except subprocess.TimeoutExpired:
        temp_output.unlink(missing_ok=True)
        job.update(
            status="failed",
            error=f"Job timeout after {JOB_TIMEOUT_SECONDS} seconds",
            finished_at=iso_now(),
        )
        atomic_json(job_path, job)

    except Exception as exc:
        temp_output.unlink(missing_ok=True)
        job.update(
            status="failed",
            error=f"{type(exc).__name__}: {exc}"[:1800],
            finished_at=iso_now(),
        )
        atomic_json(job_path, job)

def main():
    ensure_dirs()
    print("MarkItDown worker started", flush=True)
    last_cleanup = 0.0

    while True:
        now = time.monotonic()

        if now - last_cleanup >= CLEANUP_INTERVAL:
            cleanup_expired()
            last_cleanup = now

        # Chỉ một Worker xử lý tuần tự; triển khai nhiều replica cần khóa job.
        for path in sorted(
            JOB_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
        ):
            try:
                job = read_job(path)
                if job and job.get("status") == "queued":
                    process(path)
            except Exception:
                traceback.print_exc()

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()