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

## 3. Production Environment Generation (`.env.production`)

Generate and store at `/opt/ai-interview-simulator/.env.production` (permissions `chmod 600`):

```bash
# Generate a cryptographically secure 32-byte hex secret and write configuration
AUTH_SECRET_KEY="$(openssl rand -hex 32)"

cat << EOF > /opt/ai-interview-simulator/.env.production
# Core Environment
ENVIRONMENT=production
AUTH_SECRET_KEY=${AUTH_SECRET_KEY}
COOKIE_SECURE=true
UVICORN_WORKERS=1

# Gemini API key — required for AI-powered evaluation/interviewer/coaching;
# leave unset only if intentionally using deterministic fallbacks.
GEMINI_API_KEY=

# Database Persistence
DATABASE_PATH=/data/interview.db
BACKUP_DIR=/var/backups/interview-simulator

# Machine Learning Runtime
WHISPER_MODEL_SIZE=base.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
EOF

chmod 600 /opt/ai-interview-simulator/.env.production
```

---

## 4. Production Smoke-Test & Verification Commands

After starting the services, perform actual operational verification:

### 1. Database & WAL Mode Verification
Do NOT check for the presence of `-wal` or `-shm` auxiliary files at an arbitrary inspection moment. In SQLite, these files may be checkpointed, removed, or recreated depending on database activity and checkpoints. Instead, verify database status and integrity directly via SQLite queries:

```bash
# Verify database file existence and secure permissions (azureuser:azureuser)
ls -la /data/interview.db

# Verify WAL mode is active
sqlite3 /data/interview.db "PRAGMA journal_mode;"
# Expected:
# wal

# Verify database integrity
sqlite3 /data/interview.db "PRAGMA integrity_check;"
# Expected:
# ok
```

### 2. Application Health Check
```bash
curl -i http://127.0.0.1:8000/health
# Expected: HTTP 200 OK
# {"status":"healthy","database":"connected"}
```

---

## 5. Current Disaster-Recovery Limitations

> [!WARNING]
> **Known Single-VM / Same-Disk Limitation**:
> In this initial deployment topology, both the primary database (`DATABASE_PATH=/data/interview.db`) and the automated backup directory (`BACKUP_DIR=/var/backups/interview-simulator`) reside on the virtual machine's primary managed disk.
>
> - **What Nightly Backups Protect Against**: Logical database corruption, application transaction errors, accidental deletions, SQLite schema errors, and application service crashes.
> - **What They Do NOT Protect Against**: Total VM destruction, catastrophic Azure managed disk failure, unrecoverable hypervisor crashes, or accidental VM deletion.
>
> This setup is an initial deployment foundation and must **not** be mistaken for full disaster recovery.
>
> **Future Off-VM Disaster Recovery**:
> A complete disaster-recovery architecture requires off-VM replication. Azure Blob Storage (or an encrypted remote object store) is the primary candidate, but its applicability and ongoing costs under the user's specific Azure for Students subscription allowance must be confirmed before provisioning.
>
> **Data Privacy Invariant**: Production interview data must **not** be synced or backed up to local developer laptops. Off-VM backups, once enabled, must reside strictly in an authenticated, encrypted, zero-cost cloud storage tier.

---

## 6. Python Runtime Compatibility & Pre-Flight Check

Before setting up the Python virtual environment, verify that the host Python interpreter is in the supported version range:

```bash
# Verify Python version (supported: Python 3.10 to 3.12)
python3 -c "
import sys
if sys.version_info < (3, 10) or sys.version_info >= (3, 13):
    print(f'ERROR: Unsupported Python version {sys.version.split()[0]}. The AI Interview Simulator requires Python 3.10 - 3.12 for MediaPipe, faster-whisper, and PyAV binary wheel compatibility.', file=sys.stderr)
    sys.exit(1)
print(f'Python {sys.version.split()[0]} is compatible.')
"
```

* **Validated Runtime Range**: **Python 3.10.x to 3.12.x**.
* **Reason**: Precompiled binary wheels for `mediapipe` (0.10.x) and `faster-whisper` (CTranslate2) on Linux x86_64 require Python <= 3.12. Ubuntu 22.04 LTS defaults to Python 3.10, and Ubuntu 24.04 LTS defaults to Python 3.12, both of which fall within this tested range.

---

## 7. Optional Zero-Cost SSH Hardening: fail2ban

To protect against automated SSH brute-force attacks at zero cost on the Ubuntu VM:

```bash
# Install fail2ban
sudo apt-get install -y fail2ban

# Enable and start service
sudo systemctl enable --now fail2ban

# Verify Fail2ban service and confirm sshd jail is active
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

* Confirm that the `sshd` jail is reported as active in the `fail2ban-client status` output.
* Ban durations, retry thresholds, and observation windows depend on the host operating system's package defaults and may be customized in `/etc/fail2ban/jail.local` if desired.
* Operates locally with zero out-of-pocket cost and zero conflict with UFW or systemd.

---

## 8. GitHub Repository Access & Authentication

* **Public Repository Assumption**:
  - The repository `https://github.com/AkshitBedi/Ai-Interview-Simulator.git` is **Public**.
  - Cloning over HTTPS works directly without credentials:
    ```bash
    git clone https://github.com/AkshitBedi/Ai-Interview-Simulator.git /opt/ai-interview-simulator
    ```
* **Private Repository Procedure (If Later Forked / Made Private)**:
  - If the repository is private, do **NOT** enter personal GitHub account credentials or save personal access tokens (PATs) on the VM.
  - Use an **SSH Deploy Key** with read-only permissions:
    1. On VM: `ssh-keygen -t ed25519 -f ~/.ssh/id_deploy_key -N "" -C "deploy-key-azure-vm"`
    2. In GitHub repository: **Settings → Deploy keys → Add deploy key** (read-only).
    3. Clone via SSH: `git clone git@github.com:AkshitBedi/Ai-Interview-Simulator.git /opt/ai-interview-simulator`.
