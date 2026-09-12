# Production Deployment Configuration (Phase 17.1)

This directory contains production configuration templates and automation units for deploying the **AI Interview Simulator** to an Azure Linux VM (Ubuntu 22.04/24.04 LTS on Standard_B1s).

---

## 1. Hard Production Invariants

1. **No Production Data on Developer Laptop**:
   - The production database and its backups exist on the Azure VM (`/data/interview.db` and local retention backups at `/var/backups/interview-simulator`) and in the private Azure Blob backup container (`interview-backups` in `stinterviewbackupsprod`).
   - No production data is copied or synchronized to the developer laptop; the developer laptop uses only local mock databases (`backend/interview.db`) and synthetic test fixtures.
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

# Azure Blob Off-VM Disaster Recovery (Non-secret config; auth via Managed Identity)
AZURE_STORAGE_ACCOUNT=stinterviewbackupsprod
AZURE_STORAGE_CONTAINER=interview-backups

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

## 5. Off-VM Disaster Recovery Architecture (Azure Blob Storage)

The AI Interview Simulator employs a two-tier disaster recovery architecture:

1. **Tier 1 — Local Online Backups**:
   - Resides on the VM at `/var/backups/interview-simulator`.
   - Created via `sqlite3.Connection.backup()` while the database is online and active.
   - Verified with `PRAGMA integrity_check;` before gzip compression.
   - Pruned automatically using a 14-day rolling retention policy.
   - Protects against transaction errors, logical corruption, and application-level issues.

2. **Tier 2 — Off-VM Replication (Azure Blob Storage)**:
   - Storage Account: `stinterviewbackupsprod` (Standard, LRS, Hot, TLS 1.2 minimum).
   - Container: `interview-backups` (Private, no anonymous access).
   - Replicates the verified, compressed local backup archive to Azure Blob Storage immediately upon creation.
   - Protects against total VM loss, disk corruption, hypervisor failure, or accidental deletion.

### Current Disaster-Recovery Limitations & Evolution
- **Historical Same-Disk Limitation**: In the initial single-tier deployment topology, backups resided on the same VM managed disk. Tier 2 Azure Blob replication provides true off-VM disaster recovery, resolving the single-disk failure mode.
- **Data Privacy Invariant**: The production database and its backups exist on the Azure VM and in the private Azure Blob backup container. Production interview data must **not** be synced or backed up to local developer laptops. All backup, verification, and restore operations execute on the Azure VM and target only the VM filesystem and the private Azure Blob backup container.

### Authentication & Zero-Credential Security
- **Authentication Method**: Microsoft Entra / System-Assigned Managed Identity via `azure.identity.DefaultAzureCredential`.
- **Assigned RBAC Role**: `Storage Blob Data Contributor` scoped to `stinterviewbackupsprod`.
- **Zero Secrets Stored**: No storage account keys, connection strings, SAS tokens, or credentials exist in `.env.production`, source code, or logs.
- **Data Privacy Invariant**: The production database and its backups exist on the Azure VM and in the private Azure Blob backup container. Production database data is **never** copied, downloaded, or synced to developer laptops. All backup and restore operations execute on the Azure VM and target only the VM filesystem and the private Azure Blob backup container.

### Azure Portal Prerequisites & Cloud Infrastructure
- **Storage Account**: `stinterviewbackupsprod` (Standard performance, LRS replication, Hot tier, Minimum TLS 1.2, Storage account key access disabled).
- **Container**: `interview-backups` (Private / no anonymous public access).
- **Managed Identity**: VM `interview-simulator-vm-korea` has System-Assigned Managed Identity enabled.
- **RBAC Role Assignment**: `Storage Blob Data Contributor` granted to the VM's Managed Identity at the storage account scope.
- **Production Environment Variables** (in `/opt/ai-interview-simulator/.env.production`):
  ```bash
  AZURE_STORAGE_ACCOUNT=stinterviewbackupsprod
  AZURE_STORAGE_CONTAINER=interview-backups
  ```

### Backup Flow & Failure Handling Behavior
1. **Local Backup First**: SQLite online backup is performed via `sqlite3.Connection.backup()`, integrity verified with `PRAGMA integrity_check;`, compressed with gzip, and atomically finalized at `/var/backups/interview-simulator/`.
2. **Local Retention**: Aged local backups older than 14 days are pruned automatically.
3. **Azure Replication**: The verified gzip archive is uploaded to `interview-backups` using `DefaultAzureCredential`.
4. **Local Backup Protection on Failure**: If Azure upload fails due to network outage, credential expiration, or Azure downtime, the local backup archive is **never deleted**. It remains intact on the VM disk.
5. **Systemd Alerting**: On Azure upload failure, `scripts/backup_db.py` logs the error and exits with code 1 (nonzero), causing systemd to flag the unit as failed so monitoring tools immediately detect the issue.

### Safe VM-Side Operator Verification Commands

Verify remote backup blobs exist without downloading data to developer machines:

```bash
# List backup blobs in the private Azure container from the VM (metadata only):
/opt/ai-interview-simulator/.venv/bin/python scripts/backup_db.py list-azure-backups
```

### Staged Disaster Recovery Restore Procedure

To restore from an off-VM Azure Blob backup, the procedure enforces strict isolation:

```bash
# 1. Staged Restore to an isolated path (does NOT overwrite live /data/interview.db):
/opt/ai-interview-simulator/.venv/bin/python scripts/backup_db.py restore \
  --from-azure-blob interview_backup_YYYYMMDD_HHMMSS.db.gz \
  --target-db /tmp/staged_restore_test.db

# 2. Verify integrity and structure of the staged database:
sqlite3 /tmp/staged_restore_test.db "PRAGMA integrity_check;"
sqlite3 /tmp/staged_restore_test.db "SELECT count(*) FROM questions;"

# 3. Clean up the staging database when testing:
rm -f /tmp/staged_restore_test.db

# 4. Production replacement (requires explicit --force flag and deliberate operator execution):
# Stop service before live database replacement:
# sudo systemctl stop interview-simulator
# /opt/ai-interview-simulator/.venv/bin/python scripts/backup_db.py restore \
#   --from-azure-blob interview_backup_YYYYMMDD_HHMMSS.db.gz \
#   --target-db /data/interview.db --force
# sudo systemctl start interview-simulator
```

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
