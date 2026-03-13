# Design: File Transfer API

> **Status**: Proposal
> **Related**: File input support (base64-in-JSON via `/input`)

## Background

Currently, file uploads are handled inline via base64-encoded data URLs in the `/input` JSON payload (both HTTP POST and WebSocket). This works well for small files (<10MB) but has limitations for larger files and doesn't provide a way to retrieve uploaded files.

Files are saved to `.co/uploads/{filename}` on the server and referenced via system reminders that prompt the agent to use `read_file` or other tools.

## Problems to Solve

### 1. Large file support

Base64 encoding adds ~33% overhead, and embedding files in JSON payloads means the entire message must be buffered in memory. For files >10MB, a dedicated upload endpoint with streaming/multipart support would be more efficient.

### 2. File retrieval

There's currently no way to download or list files that were uploaded to an agent. Use cases:

- **Admin inspection**: Check what files an agent received (debugging)
- **Agent-generated files**: Agents may create output files that users want to download
- **Audit trail**: List all files associated with a session

### 3. File lifecycle management

No cleanup or expiration policy exists for uploaded files. Over time, `.co/uploads/` can grow unbounded.

## Proposed Options

### Option A: Admin-only endpoints (minimal, recommended first step)

```
GET  /admin/files              → list uploaded files (name, size, mtime)
GET  /admin/files/{filename}   → download a specific file
```

- Protected by `OPENONION_API_KEY` header (same as existing admin endpoints)
- Read-only, no upload via these endpoints (continue using `/input` for uploads)
- Simple to implement, covers debugging and inspection use cases

### Option B: Full file transfer API

```
POST   /files/upload           → multipart file upload, returns file ID/path
GET    /files/{id}             → download file by ID
GET    /files                  → list files (with optional session filter)
DELETE /files/{id}             → delete a file (admin only)
```

- Supports streaming/multipart uploads for large files
- File IDs instead of filenames (avoids collisions)
- Session-scoped file listing
- Separate auth: upload could be user-level, delete is admin-only

### Option C: Hybrid approach

Keep base64-in-JSON for small files (<5MB), add multipart endpoint for large files:

```
POST /input                    → existing flow, base64 files in JSON (small files)
POST /files/upload             → multipart upload for large files, returns file reference
GET  /admin/files              → list/download (admin only)
```

The `/input` payload would accept either inline base64 data or a file reference from a prior upload.

## Considerations

- **Auth model**: Should file download require admin auth or can regular users download their own uploads?
- **File scoping**: Per-session vs per-agent file storage
- **Size limits**: Current default is 10MB max per file, 50MB total. Should dedicated endpoint support larger?
- **Cleanup policy**: TTL-based expiration? Manual cleanup? Session-scoped lifecycle?
- **Security**: Path traversal is already handled (`Path(name).name`), but file IDs would be safer than filenames

## Current Implementation Reference

- File handling: `agent.py` saves to `.co/uploads/`, adds system reminder
- Validation: `host/routes.py` `validate_files()` checks count, size, total size
- Config: `max_file_size`, `max_files`, `max_total_file_size` in host server config
- Tests: `tests/unit/test_agent.py`, `test_host_routes.py`, `test_asgi_http.py`

## Recommendation

Start with **Option A** (admin-only read endpoints) — it's the simplest starting point that covers debugging needs. Evolve to **Option C** if large file support becomes necessary. This follows the project philosophy: *"keep simple things simple, make complicated things possible."*
