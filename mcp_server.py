import os
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from common import INPUT_DIR, OUTPUT_DIR, JOB_DIR, ensure_dirs, read_job

ensure_dirs()

mcp = FastMCP(
    "MarkItDown Offline",
    instructions=(
        "Dịch vụ chuyển đổi tài liệu offline. "
        "Upload tài liệu qua REST API trước, sau đó dùng UUID để tra cứu. "
        "Không truyền đường dẫn hệ thống hoặc yêu cầu thực thi lệnh."
    ),
)

def valid_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("file_id phải là UUID hợp lệ")

@mcp.tool()
def list_conversion_jobs() -> list[dict]:
    """Liệt kê job và trạng thái hiện tại."""
    jobs = []
    for path in JOB_DIR.glob("*.json"):
        job = read_job(path)
        if not job:
            continue
        jobs.append({
            "file_id": job.get("id"),
            "original_name": job.get("original_name"),
            "status": job.get("status"),
            "created_at": job.get("created_at"),
            "expires_at": job.get("expires_at"),
        })
    return sorted(jobs, key=lambda x: x.get("created_at") or "", reverse=True)[:100]

@mcp.tool()
def get_conversion_status(file_id: str) -> dict:
    """Lấy trạng thái queued, processing, completed hoặc failed."""
    job_id = valid_uuid(file_id)
    job = read_job(JOB_DIR / f"{job_id}.json")
    if not job:
        raise ValueError("Không tìm thấy job hoặc job đã hết hạn")

    return {
        "file_id": job_id,
        "original_name": job.get("original_name"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "expires_at": job.get("expires_at"),
        "error": job.get("error"),
        "output_available": (
            job.get("status") == "completed"
            and bool(job.get("output_path"))
        ),
    }

@mcp.tool()
def get_conversion_result(file_id: str) -> dict:
    """Lấy nội dung Markdown khi job hoàn tất; tối đa 100.000 ký tự."""
    job_id = valid_uuid(file_id)
    job = read_job(JOB_DIR / f"{job_id}.json")
    if not job:
        raise ValueError("Không tìm thấy job hoặc job đã hết hạn")

    if job.get("status") != "completed" or not job.get("output_path"):
        return {
            "file_id": job_id,
            "status": job.get("status"),
            "message": "Tài liệu chưa chuyển đổi xong.",
        }

    output_name = Path(job["output_path"]).name
    output_path = (OUTPUT_DIR / output_name).resolve()

    if output_path.parent != OUTPUT_DIR.resolve() or not output_path.is_file():
        raise ValueError("Không tìm thấy file Markdown hoặc file đã hết hạn")

    content = output_path.read_text(encoding="utf-8")
    return {
        "file_id": job_id,
        "status": "completed",
        "markdown": content[:100000],
        "truncated": len(content) > 100000,
        "total_characters": len(content),
    }

if __name__ == "__main__":
    os.environ.setdefault("FASTMCP_HOST", "0.0.0.0")
    os.environ.setdefault("FASTMCP_PORT", "8096")
    os.environ.setdefault("FASTMCP_STREAMABLE_HTTP_PATH", "/mcp")
    mcp.run(transport="streamable-http")