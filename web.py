import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, FileResponse

from common import (
    INPUT_DIR, OUTPUT_DIR, JOB_DIR, MAX_FILE_MB, RETENTION_SECONDS,
    ALLOWED, ensure_dirs, safe_original_name, atomic_json,
    read_job, iso_now, cleanup_expired,
)

ensure_dirs()
app = FastAPI(title="MarkItDown Offline", docs_url=None, redoc_url=None)

CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "30"))
_last_cleanup = 0.0

PAGE = r"""
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MarkItDown Offline</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#07111f;color:#eaf2ff;font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:1000px;margin:auto;padding:32px 18px}
h1{font-size:clamp(28px,4vw,40px);margin:6px 0}
p,.muted{color:#93a8c4}
.panel{background:#101d30;border:1px solid #253751;border-radius:16px;padding:22px;margin:18px 0}
input,button{padding:12px;border-radius:9px}
input{background:#091629;color:white;border:1px dashed #45658b;max-width:100%;width:100%}
button,.download{background:#60a5fa;color:#07111f;font-weight:800;border:0;padding:11px 16px;border-radius:9px;cursor:pointer;text-decoration:none;display:inline-block}
button:disabled{opacity:.5}
.upload{display:grid;grid-template-columns:1fr auto;gap:12px}
table{border-collapse:collapse;width:100%;min-width:650px}
th,td{text-align:left;border-bottom:1px solid #253751;padding:12px 8px;vertical-align:top}
th{font-size:12px;color:#93a8c4}
.wrap{overflow-x:auto}.small{font-size:11px;color:#93a8c4;overflow-wrap:anywhere}
.status{display:inline-block;border-radius:99px;padding:4px 9px;font-size:12px;background:#26364a}
.queued{color:#fbbf24}.processing{color:#93c5fd}.completed{color:#4ade80}.failed{color:#fb7185}
.message{min-height:24px;color:#bfdbfe;margin-top:12px}
@media(max-width:600px){.upload{grid-template-columns:1fr}main{padding:20px 12px}.panel{padding:15px}}
</style>
</head>
<body><main>
<div class="muted">LOCAL DOCUMENT PROCESSING</div>
<h1>MarkItDown Offline</h1>
<p>Upload một tài liệu, theo dõi job và tải Markdown khi hoàn tất.</p>
<section class="panel">
<h2>Upload tài liệu</h2>
<p class="muted">Mỗi lần một file · Giới hạn <span id="limit">100</span> MB · Tự xóa sau 1 giờ.</p>
<form id="uploadForm">
<div class="upload">
<input id="fileInput" type="file" required
accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.html,.htm,.txt,.json,.xml,.epub,.png,.jpg,.jpeg">
<button id="uploadBtn" type="submit">Upload & Convert</button>
</div>
</form>
<div id="message" class="message" role="status"></div>
<p class="small">Định dạng: PDF, Word, PowerPoint, Excel, CSV, HTML, TXT, JSON, XML, EPUB và ảnh.</p>
</section>
<section class="panel">
<h2>Jobs gần đây</h2>
<p class="muted">Tự làm mới mỗi 3 giây. UUID dùng để tra cứu job và kết quả.</p>
<div class="wrap"><table>
<thead><tr><th>File / UUID</th><th>Trạng thái</th><th>Thời gian</th><th>Kết quả</th></tr></thead>
<tbody id="jobs"><tr><td colspan="4">Đang tải…</td></tr></tbody>
</table></div>
</section>
</main>
<script>
const $=id=>document.getElementById(id);
const labels={queued:"Đang chờ",processing:"Đang xử lý",completed:"Hoàn tất",failed:"Thất bại"};
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function fmt(s){return s?new Date(s).toLocaleString():"—";}
function size(n){return n==null?"":n<1048576?(n/1024).toFixed(1)+" KB":(n/1048576).toFixed(1)+" MB";}
async function refresh(){
 try{
  const r=await fetch("/api/jobs",{cache:"no-store"});
  const d=await r.json();$("limit").textContent=d.max_file_mb;
  const jobs=d.jobs||[];
  $("jobs").innerHTML=jobs.length?jobs.map(j=>`<tr>
   <td><b>${esc(j.original_name)}</b><div class="small">${esc(j.id)}</div>
   <div class="small">Hết hạn: ${esc(fmt(j.expires_at))}</div>
   ${j.error?`<div class="small" style="color:#fb7185">${esc(j.error)}</div>`:""}</td>
   <td><span class="status ${esc(j.status)}">${esc(labels[j.status]||j.status)}</span></td>
   <td>${esc(fmt(j.created_at))}<div class="small">${esc(size(j.input_bytes))}</div></td>
   <td>${j.status==="completed"?`<a class="download" href="/api/jobs/${encodeURIComponent(j.id)}/download">Tải .md</a>`:"—"}</td>
  </tr>`).join(""):'<tr><td colspan="4">Chưa có job.</td></tr>';
 }catch(e){$("message").textContent="Không đọc được trạng thái job; đang thử lại.";}
}
$("uploadForm").addEventListener("submit",async e=>{
 e.preventDefault();
 const file=$("fileInput").files[0];if(!file)return;
 $("uploadBtn").disabled=true;$("message").textContent="Đang upload…";
 try{
  const fd=new FormData();fd.append("file",file);
  const r=await fetch("/api/upload",{method:"POST",body:fd});
  const d=await r.json();
  if(!r.ok)throw new Error(d.detail||"Upload thất bại");
  $("message").textContent=`Đã tạo job ${d.id}`;
  $("fileInput").value="";await refresh();
 }catch(err){$("message").textContent=err.message||"Có lỗi khi upload";}
 finally{$("uploadBtn").disabled=false;}
});
refresh();setInterval(refresh,3000);
</script>
</body>
</html>
"""

def maybe_cleanup():
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup >= CLEANUP_INTERVAL:
        cleanup_expired()
        _last_cleanup = now

def job_view(job):
    return {
        "id": job.get("id"),
        "original_name": job.get("original_name"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "expires_at": job.get("expires_at"),
        "input_bytes": job.get("input_bytes"),
        "output_bytes": job.get("output_bytes"),
        "error": job.get("error"),
    }

@app.get("/", response_class=HTMLResponse)
def index():
    maybe_cleanup()
    return PAGE

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    maybe_cleanup()

    original = safe_original_name(file.filename or "upload")
    suffix = Path(original).suffix.lower()

    if suffix not in ALLOWED:
        raise HTTPException(415, f"Định dạng chưa hỗ trợ: {suffix or 'không có phần mở rộng'}")

    job_id = str(uuid.uuid4())
    stored_name = f"{job_id}{suffix}"
    input_path = INPUT_DIR / stored_name
    temp_path = INPUT_DIR / f".{job_id}.upload.tmp"
    size = 0

    try:
        # Đọc theo từng chunk, không nạp cả file vào RAM.
        with temp_path.open("xb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_MB * 1024 * 1024:
                    raise HTTPException(413, f"File vượt giới hạn {MAX_FILE_MB} MB")
                output.write(chunk)

        if size == 0:
            raise HTTPException(400, "File rỗng")

        # Chỉ chuyển file hoàn chỉnh vào inbox trước khi tạo job.
        temp_path.replace(input_path)

        created = datetime.now(timezone.utc)
        expires = created + timedelta(seconds=RETENTION_SECONDS)
        job = {
            "id": job_id,
            "original_name": original,
            "input_path": stored_name,
            "output_path": None,
            "status": "queued",
            "created_at": created.isoformat(),
            "expires_at": expires.isoformat(),
            "input_bytes": size,
        }

        # Worker chỉ quét *.json, không thể đọc job đang ghi dở.
        atomic_json(JOB_DIR / f"{job_id}.json", job)

        return {
            "id": job_id,
            "status": "queued",
            "original_name": original,
            "expires_at": expires.isoformat(),
        }

    except Exception:
        temp_path.unlink(missing_ok=True)
        input_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

@app.get("/api/jobs")
def list_jobs():
    maybe_cleanup()
    jobs = []
    for path in JOB_DIR.glob("*.json"):
        job = read_job(path)
        if job:
            jobs.append(job_view(job))
    jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {
        "jobs": jobs[:100],
        "max_file_mb": MAX_FILE_MB,
        "retention_seconds": RETENTION_SECONDS,
    }

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    maybe_cleanup()
    try:
        job_id = str(uuid.UUID(job_id))
    except ValueError:
        raise HTTPException(400, "UUID không hợp lệ")

    job = read_job(JOB_DIR / f"{job_id}.json")
    if not job:
        raise HTTPException(404, "Job không tồn tại hoặc đã hết hạn")
    return job_view(job)

@app.get("/api/jobs/{job_id}/download")
def download_result(job_id: str):
    maybe_cleanup()
    try:
        job_id = str(uuid.UUID(job_id))
    except ValueError:
        raise HTTPException(400, "UUID không hợp lệ")

    job = read_job(JOB_DIR / f"{job_id}.json")
    if not job:
        raise HTTPException(404, "Job không tồn tại hoặc đã hết hạn")
    if job.get("status") != "completed" or not job.get("output_path"):
        raise HTTPException(409, "Job chưa hoàn tất")

    output_name = Path(job["output_path"]).name
    output_path = (OUTPUT_DIR / output_name).resolve()

    if output_path.parent != OUTPUT_DIR.resolve() or not output_path.is_file():
        raise HTTPException(404, "Không tìm thấy kết quả")

    return FileResponse(
        output_path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{job_id}.md",
    )