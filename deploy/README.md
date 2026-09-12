# Production Deployment Configuration (Phase 17.1)

This directory contains production configuration templates and automation units for deploying the **AI Interview Simulator** to an Azure Linux VM (Ubuntu 22.04/24.04 LTS on Standard_B1s).

---

## 1. Hard Production Invariants

1. **No Production Data on Developer Laptop**:
   - The developer laptop uses local/mock databases (`backend/interview.db`).
   - Production sets `DATABASE_PATH=/data/interview.db` on the VM's persistent disk.
   - `interview.db` is strictly ignored by Git and is never uploaded or transferred.
2. **Process Supervision**:
   - Managed by systemd (`interview-simulator.service`).
   - Runs as non-root user `azureuser`.
   - Single Uvicorn worker (`--workers 1`).
   - Automatic restart within 5 seconds on crash.
3. **Inference Concurrency Protection**:
   - Module-level `threading.Semaphore(1)` gate in `backend/inference_gate.py`.
   - Serializes heavy ML inference (faster-whisper and MediaPipe) within the Uvicorn worker threads, preventing concurrent memory spikes from exceeding 1 GB RAM.
4. **Swap Protection**:
   - 2 GB persistent swapfile (`/swapfile`, `vm.swappiness=10`) configured via `deploy/setup_swap.sh`.
5. **Nightly Online Backups**:
   - Automated via `interview-backup.timer` and `interview-backup.service` running `scripts/backup_db.py` daily at 02:00 UTC.
   - Uses SQLite online backup API (`sqlite3.Connection.backup()`), validates with `PRAGMA integrity_check`, compresses with gzip, and prunes archives older than 14 days.

---

## 2. Service Definitions

- `interview-simulator.service`: systemd service running FastAPI/Uvicorn.
- `interview-backup.service`: oneshot systemd backup task.
- `interview-backup.timer`: systemd timer triggering nightly backups at 02:00 UTC.
- `setup_swap.sh`: Shell script allocating and persisting 2 GB swap on the VM.

---

## 3. Production Environment File Template (`.env.production`)

Store at `/opt/ai-interview-simulator/.env.production` (permissions `chmod 600`):

```bash
# Core Environment
ENVIRONMENT=production
AUTH_SECRET_KEY=generate-a-strong-random-hex-string-at-least-32-chars
COOKIE_SECURE=true
UVICORN_WORKERS=1

# Database Persistence
DATABASE_PATH=/data/interview.db
BACKUP_DIR=/var/backups/interview-simulator

# Optional Gemini API Key (falls back to deterministic engine if unset)
GEMINI_API_KEY=your-gemini-api-key-here

# Machine Learning Runtime
WHISPER_MODEL_SIZE=base.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```
