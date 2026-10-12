import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

INPUT_DIR = Path(os.getenv("INPUT_DIR", "/data/inbox"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/data/outbox"))
JOB_DIR = Path(os.getenv("JOB_DIR", "/data/jobs"))

MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "100"))
RETENTION_SECONDS = int(os.getenv("RETENTION_SECONDS", "3600"))

ALLOWED = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".csv", ".html", ".htm", ".txt", ".json",
    ".xml", ".epub", ".png", ".jpg", ".jpeg",
}

def ensure_dirs():
    for directory in (INPUT_DIR, OUTPUT_DIR, JOB_DIR):
        directory.mkdir(parents=True, exist_ok=True)

def iso_now():
    return datetime.now(timezone.utc).isoformat()

def safe_original_name(name: str) -> str:
    # Loại bỏ đường dẫn Windows/Unix do client gửi lên.
    name = name.replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._() -]+", "_", name)
    name = name.strip(" .")
    return (name or "upload")[:180]

def atomic_json(path: Path, data: dict):
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp, path)

def read_job(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

def cleanup_expired():
    """Xóa file đầu vào, kết quả và job sau RETENTION_SECONDS."""
    ensure_dirs()
    now = time.time()

    for job_path in JOB_DIR.glob("*.json"):
        job = read_job(job_path)

        if not job:
            try:
                if now - job_path.stat().st_mtime > RETENTION_SECONDS:
                    job_path.unlink(missing_ok=True)
            except OSError:
                pass
            continue

        created = job.get("created_at")
        try:
            created_at = datetime.fromisoformat(
                created.replace("Z", "+00:00")
            ).timestamp()
        except (ValueError, AttributeError, TypeError):
            created_at = job_path.stat().st_mtime

        if now - created_at < RETENTION_SECONDS:
            continue

        for key, directory in (
            ("input_path", INPUT_DIR),
            ("output_path", OUTPUT_DIR),
        ):
            value = job.get(key)
            if not value:
                continue

            # Chỉ cho phép xóa file trực tiếp nằm trong thư mục quản lý.
            candidate = (directory / Path(value).name).resolve()
            if candidate.parent == directory.resolve():
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass

        try:
            job_path.unlink(missing_ok=True)
        except OSError:
            pass

    # Dọn file tạm bị bỏ lại do container dừng đột ngột.
    for directory in (INPUT_DIR, OUTPUT_DIR, JOB_DIR):
        for path in directory.glob("*.tmp"):
            try:
                if now - path.stat().st_mtime > 60:
                    path.unlink(missing_ok=True)
            except OSError:
                pass