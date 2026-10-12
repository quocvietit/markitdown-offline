# MarkItDown Offline

An offline-capable document-to-Markdown conversion service built with Microsoft MarkItDown, FastAPI, Docker, and the Model Context Protocol (MCP).

The service provides a Web UI, REST API, background worker, and MCP server for integration with AI agents and MCP-compatible applications.

## Features

- Convert supported documents into Markdown.
- Upload one document per conversion job.
- Assign a unique UUID to each job.
- Track real-time job states: `queued`, `processing`, `completed`, and `failed`.
- Download converted Markdown files.
- Automatically clean up expired input files, results, and job metadata.
- Expose MCP tools for listing jobs, checking status, and retrieving Markdown content.
- Build a Docker image for deployment in offline environments.
- Deploy using Docker Compose or Kubernetes.

## Architecture

```text
                       User / AI Agent
                              |
                  +-----------+-----------+
                  |                       |
                Web UI                MCP Client
                  |                       |
                  v                       v
              Web / REST API          MCP Server
                  |                       |
                  +-----------+-----------+
                              |
                        Shared Storage
                              |
                         Job Metadata
                              |
                              v
                            Worker
                              |
                              v
                          MarkItDown
                              |
                              v
                       Markdown Output
```

### Components

| Component | Responsibility | Port |
|---|---|---:|
| Web | Upload documents, view job status, download results | 8095 |
| Worker | Process queued conversion jobs | None |
| MCP Server | Expose conversion-related MCP tools | 8096 |

All components share the `/data` directory.

## Project Structure

```text
markitdown-offline/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── BUILD.md
├── common.py
├── web.py
├── worker.py
├── convert_one.py
├── mcp_server.py
├── data/
│   ├── inbox/
│   ├── outbox/
│   └── jobs/
└── k8s/
    └── markitdown.yaml
```

| File or directory | Purpose |
|---|---|
| `Dockerfile` | Builds the application image |
| `docker-compose.yml` | Runs the Web, Worker, and MCP services |
| `requirements.txt` | Declares Python dependencies |
| `common.py` | Shared configuration, job storage, and cleanup utilities |
| `web.py` | Web UI and REST API |
| `worker.py` | Processes queued jobs and updates job status |
| `convert_one.py` | Converts one document to Markdown |
| `mcp_server.py` | MCP server implementation |
| `data/inbox/` | Input documents |
| `data/outbox/` | Converted Markdown files |
| `data/jobs/` | JSON job metadata |
| `k8s/markitdown.yaml` | Kubernetes deployment manifest |

## Requirements

- Docker Engine or Docker Desktop.
- Docker Compose v2 for Compose deployments.
- Sufficient disk space for the image and document storage.
- For Kubernetes, a cluster with suitable persistent storage and access to the application image.

Python does not need to be installed on the host. Python and application dependencies are installed inside the image.

## Quick Start

### 1. Build the image

Build the image on a development machine with access to the required package repositories:

```bash
docker build -t markitdown-offline:1.1.0 .
```

Verify that the image exists:

```bash
docker image inspect markitdown-offline:1.1.0
```

### 2. Start the services

Ensure that the deployment Compose file references the existing image and does not contain a `build:` section.

For each service, use:

```yaml
image: markitdown-offline:1.1.0
pull_policy: never
```

Keep the remaining service configuration, including ports, volumes, environment variables, security settings, and resource limits.

Start the application:

```bash
docker compose up -d
```

Check the services:

```bash
docker compose ps
docker compose logs --tail 100 markitdown-web
docker compose logs --tail 100 markitdown-worker
docker compose logs --tail 100 markitdown-mcp
```

### 3. Open the application

| Service | URL |
|---|---|
| Web UI | http://127.0.0.1:8095 |
| MCP endpoint | http://127.0.0.1:8096/mcp |

These addresses assume the current Compose configuration publishes the ports on the host loopback interface.

For offline deployment, the image must already exist on the target machine. See [BUILD.md](BUILD.md) for image distribution and offline deployment instructions.

## Document Conversion Workflow

1. Open the Web UI.
2. Select and upload one document.
3. The service creates a job with a unique UUID.
4. The Worker picks up the queued job.
5. MarkItDown converts the document.
6. The Markdown output is saved in `data/outbox/`.
7. Download the result through the Web UI or REST API, or retrieve it through MCP.

### Job states

| State | Meaning |
|---|---|
| `queued` | Waiting for processing |
| `processing` | Conversion is in progress |
| `completed` | Conversion succeeded |
| `failed` | Conversion failed |

The UUID links the job metadata, input file, and output file.

## REST API

The Web service exposes the following endpoints.

### Upload a document

```http
POST /api/upload
Content-Type: multipart/form-data
```

Upload field:

```text
file=<document>
```

Example using PowerShell:

```powershell
curl.exe -X POST `
  -F "file=@C:\documents\report.pdf" `
  http://127.0.0.1:8095/api/upload
```

Save the UUID returned by the API.

### List jobs

```http
GET /api/jobs
```

### Get job status

```http
GET /api/jobs/{job_id}
```

### Download the Markdown result

```http
GET /api/jobs/{job_id}/download
```

Example:

```powershell
curl.exe -o result.md `
  http://127.0.0.1:8095/api/jobs/<UUID>/download
```

Replace `<UUID>` with the actual job ID. Check the job status before downloading the result.

## MCP Integration

### Endpoint and transport

```text
Endpoint:  http://127.0.0.1:8096/mcp
Transport: Streamable HTTP
```

The MCP server reads the same job metadata and output files as the Web application.

### Available tools

| Tool | Description |
|---|---|
| `list_conversion_jobs` | Lists up to 100 recent jobs |
| `get_conversion_status` | Retrieves the status of a job by UUID |
| `get_conversion_result` | Retrieves Markdown content for a completed job |

The result tool currently returns up to 100,000 characters and indicates whether the content was truncated.

### Typical MCP workflow

```text
Upload document through Web/API
              |
              v
          Receive UUID
              |
              v
    get_conversion_status(UUID)
              |
              v
       Wait for completion
              |
              v
    get_conversion_result(UUID)
              |
              v
       Consume Markdown
```

The current MCP server does not upload documents directly. Upload through the Web UI or REST API first, then use the UUID with the MCP tools.

### DSH integration

DSH uses its MCP client configuration in the applicable profile's `cordis.patch.yml`. The exact configuration depends on the installed DSH version and its MCP client schema.

Example configuration:

```yaml
- insert:
    - id: mcp-markitdown
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: markitdown
        transport: streamable-http
        url: http://127.0.0.1:8096/mcp
        headers: {}
        toolCallTimeoutMs: 60000
        failOnStartupError: true
```

Use `127.0.0.1` only when DSH runs on the same host and can access the published port.

If DSH runs in another container, configure a shared Docker network and use a reachable service address, for example:

```text
http://markitdown-mcp:8096/mcp
```

The hostname must resolve from the DSH container, and the containers must share a network that permits communication.

After applying the configuration, reload or restart the appropriate DSH profile and verify that the MCP tools are registered.

### Other MCP clients

Different MCP clients use different configuration formats. Do not assume that a single JSON configuration can be copied unchanged across all applications.

#### Cursor

For versions that support remote MCP servers through HTTP, a project-level `.cursor/mcp.json` may look like this:

```json
{
  "mcpServers": {
    "markitdown": {
      "url": "http://127.0.0.1:8096/mcp"
    }
  }
}
```

Validate the supported schema in your installed Cursor version.

#### Visual Studio Code

For versions supporting HTTP MCP servers, `.vscode/mcp.json` may look like this:

```json
{
  "servers": {
    "markitdown": {
      "type": "http",
      "url": "http://127.0.0.1:8096/mcp"
    }
  }
}
```

Check the MCP panel and verify that the server starts and exposes its tools.

#### Claude Desktop and other clients

If your client supports remote Streamable HTTP MCP connections, register the endpoint:

```text
http://127.0.0.1:8096/mcp
```

If the client only supports stdio-based MCP servers, use a compatible bridge or implement a stdio transport. The current `mcp_server.py` is configured for Streamable HTTP and should not be treated as a stdio server.

Refer to the client's official documentation for its exact configuration format and supported transport.

### MCP Inspector

Use [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) to test the MCP protocol independently of DSH or another AI client.

Verify that:

1. The server initializes successfully.
2. The server returns its tool list.
3. `list_conversion_jobs` works.
4. `get_conversion_status` returns the expected status for a valid UUID.
5. `get_conversion_result` returns Markdown for a completed job.

An open TCP port alone does not prove that the MCP handshake succeeds.

## Data Retention and Limits

The default configuration includes:

```text
MAX_FILE_MB=100
RETENTION_SECONDS=3600
POLL_SECONDS=1
CLEANUP_INTERVAL_SECONDS=30
JOB_TIMEOUT_SECONDS=3300
```

Adjust these values through the environment configuration supported by the application.

Expired input files, output files, and job metadata are removed by periodic cleanup. Deletion is not guaranteed to occur at the exact second the retention period expires.

## Kubernetes Deployment

The sample manifest is located at:

```text
k8s/markitdown.yaml
```

Before deployment:

1. Replace the placeholder image with the image available to your cluster.
2. Verify the storage backend supports the requested PVC access mode.
3. Confirm that the application can write to `/data` as UID/GID 10001.
4. Verify that your CNI enforces NetworkPolicy.
5. Configure access through an appropriate Service, Ingress, or Gateway.

Apply the manifest:

```bash
kubectl apply -f k8s/markitdown.yaml
kubectl -n markitdown get pods
kubectl -n markitdown get services
```

Access the Web UI using port forwarding:

```bash
kubectl -n markitdown port-forward svc/markitdown-web 8095:8095
```

Open:

```text
http://127.0.0.1:8095
```

Access MCP locally:

```bash
kubectl -n markitdown port-forward svc/markitdown-mcp 8096:8096
```

The local MCP endpoint becomes:

```text
http://127.0.0.1:8096/mcp
```

### Scaling considerations

- The Worker is designed for a single replica.
- Do not scale the Worker without implementing an atomic job-claiming or locking mechanism.
- Multiple Web/MCP replicas require shared storage and careful handling of concurrent cleanup and file access.
- `ReadWriteMany` support depends on the storage backend.
- NetworkPolicy enforcement depends on the cluster's CNI.

## Security

- Build the image before deploying to an offline environment.
- Do not mount the Docker socket into application containers.
- Apply CPU, memory, file-size, and execution-time limits.
- Run containers as non-root where possible.
- Keep writable access limited to required volumes and temporary directories.
- Restrict network access for the Worker.
- Validate filenames and allowed file extensions.
- Avoid exposing internal error details or sensitive content in logs.
- Add authentication and authorization before multi-user or external deployment.
- A UUID is an identifier, not an authorization mechanism.

Treat uploaded documents as untrusted input. Follow the security guidance in the [Microsoft MarkItDown project](https://github.com/microsoft/markitdown#security-considerations).

## Troubleshooting

### Container fails to start

```bash
docker compose ps
docker compose logs --tail 200 markitdown-mcp
```

Check dependency imports, SDK compatibility, port configuration, and filesystem permissions.

### MCP connection fails

Check:

- The endpoint includes `/mcp`.
- The server listens on `0.0.0.0:8096` inside the container.
- The published host port is correct.
- The client can reach the endpoint.
- The client supports Streamable HTTP.
- The server log does not show initialization or handshake errors.<!--  -->

### Job fails

```bash
docker compose logs --tail 200 markitdown-worker
```

Check the document format, file size, read/write permissions, conversion timeout, and required dependencies.

### Job remains queued

Verify that the Worker is running, that `/data/jobs` is shared correctly, and that the job JSON contains a valid `queued` status.

### Job is missing

The job may have expired and been removed by cleanup. Upload the document again if another conversion is required.

## Current Limitations

- One document per upload request.
- MCP does not currently expose a direct document-upload tool.
- MCP result content is limited to 100,000 characters per response.
- Authentication and per-user authorization are not built in.
- The Worker is intended to run as a single replica.
- Cleanup is periodic rather than exact to the second.
- Offline operation depends on all required dependencies being included in the image and network access being restricted appropriately.

## References

- [Microsoft MarkItDown](https://github.com/microsoft/markitdown)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector)
- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
