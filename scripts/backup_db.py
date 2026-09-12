"""
Production SQLite Online Backup, Azure Blob Off-VM Replication, and Restore Utility.

Uses Python's standard-library sqlite3.Connection.backup() API to create
atomic, non-blocking, online backups of SQLite databases operating in WAL mode,
and replicates verified compressed archives to Azure Blob Storage via
System-Assigned Managed Identity (DefaultAzureCredential).

Features:
- Online live backup without locking active readers/writers.
- Automated PRAGMA integrity_check validation before finalizing backup.
- Gzip compression of verified backup archives.
- Atomic file finalization via temporary staging files.
- Configurable retention pruning of aged backups.
- Azure Blob Storage off-VM replication using Managed Identity (DefaultAzureCredential).
- Zero storage account keys, SAS tokens, or connection strings required or supported.
- Safe restore with pre-validation, schema structure checks, and overwrite protection.
- Staged download and decompression for Azure Blob restore verification.
- Zero sensitive data logging (no schema or row content, tokens, or URLs logged).
"""

from __future__ import annotations

import argparse
import gzip
import logging
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("backup_db")

AZURE_STORAGE_ACCOUNT_ENV = "AZURE_STORAGE_ACCOUNT"
AZURE_STORAGE_CONTAINER_ENV = "AZURE_STORAGE_CONTAINER"
DEFAULT_AZURE_CONTAINER = "interview-backups"

REQUIRED_DATABASE_TABLES = (
    "questions",
    "interview_sessions",
    "session_turns",
    "answers",
    "evaluations",
)


class BackupPath(type(Path())):
    """Path subclass that carries optional Azure blob metadata while remaining a Path."""
    blob_name: str | None = None


def get_azure_blob_config(
    account_name: str | None = None,
    container_name: str | None = None,
) -> tuple[str, str] | None:
    """
    Resolves Azure Blob Storage configuration.

    Returns:
        tuple[str, str]: (account_name, container_name) if both are provided/configured.
        None: if neither account_name nor container_name is provided/configured.

    Raises:
        ValueError: if only one of account_name or container_name is configured.
    """
    acct = account_name or os.environ.get(AZURE_STORAGE_ACCOUNT_ENV)
    cont = container_name or os.environ.get(AZURE_STORAGE_CONTAINER_ENV)

    acct_clean = acct.strip() if acct and acct.strip() else None
    cont_clean = cont.strip() if cont and cont.strip() else None

    if not acct_clean and not cont_clean:
        return None

    if acct_clean and not cont_clean:
        raise ValueError(
            f"Azure configuration error: {AZURE_STORAGE_ACCOUNT_ENV} is configured ('{acct_clean}'), "
            f"but {AZURE_STORAGE_CONTAINER_ENV} is missing."
        )

    if cont_clean and not acct_clean:
        raise ValueError(
            f"Azure configuration error: {AZURE_STORAGE_CONTAINER_ENV} is configured ('{cont_clean}'), "
            f"but {AZURE_STORAGE_ACCOUNT_ENV} is missing."
        )

    return acct_clean, cont_clean


def verify_database_integrity(db_path: Path | str) -> bool:
    """Runs PRAGMA integrity_check against a SQLite database file."""
    path = Path(db_path)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    conn = None
    try:
        conn = sqlite3.connect(path)
        cursor = conn.execute("PRAGMA integrity_check;")
        rows = cursor.fetchall()
        return len(rows) == 1 and rows[0][0].strip().lower() == "ok"
    except Exception as e:
        logger.warning(f"Integrity check failed with exception: {e}")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def verify_database_structure(db_path: Path | str) -> bool:
    """Verifies that the database contains the required core application tables."""
    path = Path(db_path)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    conn = None
    try:
        conn = sqlite3.connect(path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        return all(req in tables for req in REQUIRED_DATABASE_TABLES)
    except Exception as e:
        logger.warning(f"Structure verification failed with exception: {e}")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def prune_backups(backup_dir: Path | str, retention_days: int = 14) -> list[Path]:
    """Prunes backup files in backup_dir older than retention_days."""
    dir_path = Path(backup_dir)
    if not dir_path.is_dir():
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - (retention_days * 86400)
    pruned: list[Path] = []

    for f in dir_path.glob("interview_backup_*.db.gz"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                pruned.append(f)
        except OSError:
            pass

    return pruned


def upload_backup_to_azure_blob(
    backup_file_path: Path | str,
    account_name: str,
    container_name: str,
    credential: Any = None,
) -> str:
    """
    Uploads a verified local backup archive to Azure Blob Storage using DefaultAzureCredential.
    Never deletes or alters the local archive.
    Returns the uploaded blob name.
    """
    path = Path(backup_file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Local backup archive to upload not found at {path}")

    blob_name = path.name

    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(
            f"Azure Blob Storage dependencies not available. Install azure-storage-blob and azure-identity: {exc}"
        ) from exc

    if credential is None:
        credential = DefaultAzureCredential()

    account_url = f"https://{account_name}.blob.core.windows.net"

    try:
        blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        with open(path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        logger.info(f"Azure backup uploaded: {blob_name}")
        return blob_name
    except Exception as exc:
        logger.error(f"Failed to upload backup to Azure Blob Storage: {exc}")
        raise RuntimeError(f"Azure Blob upload failed for {blob_name}: {exc}") from exc


def download_backup_from_azure_blob(
    blob_name: str,
    destination_path: Path | str,
    account_name: str,
    container_name: str,
    credential: Any = None,
) -> Path:
    """
    Downloads a backup archive from Azure Blob Storage into destination_path using DefaultAzureCredential.
    """
    dest = Path(destination_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(
            f"Azure Blob Storage dependencies not available. Install azure-storage-blob and azure-identity: {exc}"
        ) from exc

    if credential is None:
        credential = DefaultAzureCredential()

    account_url = f"https://{account_name}.blob.core.windows.net"

    try:
        blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        with open(dest, "wb") as f_out:
            stream = blob_client.download_blob()
            stream.readinto(f_out)

        return dest
    except Exception as exc:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise RuntimeError(f"Azure Blob download failed for {blob_name}: {exc}") from exc


def list_azure_backups(
    account_name: str,
    container_name: str,
    credential: Any = None,
) -> list[dict[str, Any]]:
    """
    Lists backup blobs in the specified Azure container without downloading content.
    Returns metadata list: [{"name": str, "size": int, "last_modified": datetime}].
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError(f"Azure dependencies missing: {exc}") from exc

    if credential is None:
        credential = DefaultAzureCredential()

    account_url = f"https://{account_name}.blob.core.windows.net"
    blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
    container_client = blob_service_client.get_container_client(container_name)

    results: list[dict[str, Any]] = []
    for blob in container_client.list_blobs():
        results.append({
            "name": blob.name,
            "size": getattr(blob, "size", 0),
            "last_modified": getattr(blob, "last_modified", None),
        })
    return results


def backup_database(
    source_db_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
    retention_days: int = 14,
    azure_storage_account: str | None = None,
    azure_storage_container: str | None = None,
    azure_credential: Any = None,
) -> BackupPath:
    """
    Executes a validated online backup of source_db_path into backup_dir.
    If Azure Blob configuration is active, uploads the finalized archive to Azure Blob Storage.

    Returns the Path to the finalized compressed backup archive.
    If uploaded to Azure, the returned object has attribute .blob_name set.

    Raises:
        RuntimeError: on local backup failure, integrity failure, or Azure upload failure.
    """
    if source_db_path is None:
        env_db = os.environ.get("DATABASE_PATH")
        if env_db and env_db.strip():
            source_path = Path(env_db.strip()).resolve()
        else:
            source_path = Path(__file__).resolve().parent.parent / "backend" / "interview.db"
    else:
        source_path = Path(source_db_path).resolve()

    if not source_path.is_file():
        raise FileNotFoundError(f"Source database not found at {source_path}")

    if backup_dir is None:
        env_dir = os.environ.get("BACKUP_DIR")
        if env_dir and env_dir.strip():
            target_dir = Path(env_dir.strip()).resolve()
        else:
            target_dir = Path(__file__).resolve().parent.parent / "backups"
    else:
        target_dir = Path(backup_dir).resolve()

    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]

    temp_dest = target_dir / f".tmp_{timestamp}_{unique_id}.db"
    temp_gz = target_dir / f".tmp_{timestamp}_{unique_id}.db.gz"
    final_gz = target_dir / f"interview_backup_{timestamp}.db.gz"

    try:
        # 1-3. Perform online backup via standard library API
        src_conn = sqlite3.connect(source_path)
        dest_conn = sqlite3.connect(temp_dest)
        try:
            with dest_conn:
                src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            src_conn.close()

        # 4. Verify integrity of temporary destination before compression
        if not verify_database_integrity(temp_dest):
            raise RuntimeError(
                f"Backup integrity check failed for temporary database at {temp_dest}"
            )

        # 5. Compress verified backup
        with open(temp_dest, "rb") as f_in, gzip.open(temp_gz, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        # 6. Atomically finalize compressed archive
        os.replace(temp_gz, final_gz)

    finally:
        if temp_dest.exists():
            try:
                temp_dest.unlink()
            except OSError:
                pass
        if temp_gz.exists():
            try:
                temp_gz.unlink()
            except OSError:
                pass

    # 7. Prune older local backups
    prune_backups(target_dir, retention_days=retention_days)

    # 8. Check Azure Blob replication
    azure_config = get_azure_blob_config(azure_storage_account, azure_storage_container)
    uploaded_blob_name: str | None = None

    if azure_config is not None:
        acct_name, cont_name = azure_config
        # Note: Local backup remains intact even if upload fails
        uploaded_blob_name = upload_backup_to_azure_blob(
            backup_file_path=final_gz,
            account_name=acct_name,
            container_name=cont_name,
            credential=azure_credential,
        )

    result_path = BackupPath(final_gz)
    result_path.blob_name = uploaded_blob_name
    return result_path


def restore_database(
    backup_file_path: Path | str,
    target_db_path: Path | str,
    force: bool = False,
    verify_structure: bool = False,
) -> Path:
    """
    Safely restores a SQLite database from a compressed local backup archive.

    Steps:
    1. Verifies source archive exists.
    2. Checks target_db_path does not exist (unless force=True).
    3. Decompresses archive to a temporary file.
    4. Validates restored temporary file with PRAGMA integrity_check.
    5. Optionally validates schema structure with verify_database_structure.
    6. Atomically renames temporary file to target_db_path.

    Returns the Path to the restored database file.
    """
    backup_path = Path(backup_file_path).resolve()
    target_path = Path(target_db_path).resolve()

    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup file not found at {backup_path}")

    if target_path.exists() and not force:
        raise FileExistsError(
            f"Target database already exists at {target_path}. Use force=True to overwrite."
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_restore = target_path.parent / f".tmp_restore_{uuid.uuid4().hex[:8]}.db"

    try:
        # Decompress
        if backup_path.name.endswith(".gz"):
            with gzip.open(backup_path, "rb") as f_in, open(temp_restore, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(backup_path, temp_restore)

        # Validate integrity
        if not verify_database_integrity(temp_restore):
            raise RuntimeError(
                f"Restored database failed integrity check: {temp_restore}"
            )

        # Validate core schema structure if requested
        if verify_structure and not verify_database_structure(temp_restore):
            raise RuntimeError(
                f"Restored database failed structure check (missing core tables): {temp_restore}"
            )

        # Atomically move to target
        os.replace(temp_restore, target_path)

    finally:
        if temp_restore.exists():
            try:
                temp_restore.unlink()
            except OSError:
                pass

    return target_path


def restore_database_from_azure_blob(
    blob_name: str,
    target_db_path: Path | str,
    account_name: str,
    container_name: str,
    force: bool = False,
    staging_dir: Path | str | None = None,
    credential: Any = None,
) -> Path:
    """
    Safely restores a SQLite database from an Azure Blob archive.

    Steps:
    1. Checks target_db_path does not exist (unless force=True).
    2. Downloads blob into staging directory.
    3. Validates gzip integrity and decompresses into staging.
    4. Validates PRAGMA integrity_check and core table schema.
    5. Atomically places the verified database at target_db_path.
    6. Cleans up all staging and temporary download files.
    """
    target_path = Path(target_db_path).resolve()
    if target_path.exists() and not force:
        raise FileExistsError(
            f"Target database already exists at {target_path}. Use force=True to overwrite."
        )

    if staging_dir is None:
        stage_dir = target_path.parent
    else:
        stage_dir = Path(staging_dir).resolve()

    stage_dir.mkdir(parents=True, exist_ok=True)

    temp_gz = stage_dir / f".tmp_blob_download_{uuid.uuid4().hex[:8]}.db.gz"
    temp_db = stage_dir / f".tmp_blob_restore_{uuid.uuid4().hex[:8]}.db"

    try:
        # 1. Download to staging location
        download_backup_from_azure_blob(
            blob_name=blob_name,
            destination_path=temp_gz,
            account_name=account_name,
            container_name=container_name,
            credential=credential,
        )

        # 2. Verify gzip and decompress
        try:
            with gzip.open(temp_gz, "rb") as f_in, open(temp_db, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        except Exception as exc:
            raise RuntimeError(f"Downloaded Azure Blob archive is corrupt or not valid gzip: {exc}") from exc

        # 3. Validate SQLite integrity
        if not verify_database_integrity(temp_db):
            raise RuntimeError(
                f"Restored database failed SQLite integrity check: {temp_db}"
            )

        # 4. Validate schema structure
        if not verify_database_structure(temp_db):
            raise RuntimeError(
                f"Restored database failed structure check (missing core tables): {temp_db}"
            )

        # 5. Overwrite target check again before atomic rename
        if target_path.exists() and not force:
            raise FileExistsError(
                f"Target database already exists at {target_path}. Use force=True to overwrite."
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_db, target_path)

    finally:
        if temp_gz.exists():
            try:
                temp_gz.unlink()
            except OSError:
                pass
        if temp_db.exists():
            try:
                temp_db.unlink()
            except OSError:
                pass

    return target_path


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Interview Simulator SQLite Backup Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- BACKUP ---
    backup_parser = subparsers.add_parser("backup", help="Run online database backup")
    backup_parser.add_argument("--source", default=None, help="Source database path")
    backup_parser.add_argument("--dest", default=None, help="Backup destination directory")
    backup_parser.add_argument(
        "--retention-days", type=int, default=14, help="Days of backups to retain (default: 14)"
    )
    backup_parser.add_argument(
        "--upload-azure", action="store_true", default=False, help="Explicitly enable Azure Blob Storage upload"
    )
    backup_parser.add_argument(
        "--storage-account", default=None, help="Azure Storage Account name (or set AZURE_STORAGE_ACCOUNT)"
    )
    backup_parser.add_argument(
        "--container", default=None, help="Azure Blob container name (or set AZURE_STORAGE_CONTAINER)"
    )

    # --- RESTORE ---
    restore_parser = subparsers.add_parser("restore", help="Restore database from backup archive")
    restore_parser.add_argument("--backup-file", default=None, help="Local backup archive to restore from")
    restore_parser.add_argument(
        "--from-azure-blob", default=None, help="Blob name in Azure Blob Storage container to restore from"
    )
    restore_parser.add_argument(
        "--storage-account", default=None, help="Azure Storage Account name (or set AZURE_STORAGE_ACCOUNT)"
    )
    restore_parser.add_argument(
        "--container", default=None, help="Azure Blob container name (or set AZURE_STORAGE_CONTAINER)"
    )
    restore_parser.add_argument("--target-db", required=True, help="Target database path")
    restore_parser.add_argument(
        "--force", action="store_true", help="Overwrite target database if it exists"
    )

    # --- LIST BLOBS ---
    list_parser = subparsers.add_parser("list-azure-backups", help="List backup blobs in Azure Storage container")
    list_parser.add_argument(
        "--storage-account", default=None, help="Azure Storage Account name (or set AZURE_STORAGE_ACCOUNT)"
    )
    list_parser.add_argument(
        "--container", default=None, help="Azure Blob container name (or set AZURE_STORAGE_CONTAINER)"
    )

    args = parser.parse_args()

    if args.command == "backup":
        try:
            # Check if Azure upload was explicitly flagged or if Azure config is present
            acct = args.storage_account
            cont = args.container
            if args.upload_azure and not acct and not os.environ.get(AZURE_STORAGE_ACCOUNT_ENV):
                print(
                    "Error: --upload-azure specified but AZURE_STORAGE_ACCOUNT is not provided.",
                    file=sys.stderr,
                )
                return 1

            archive = backup_database(
                source_db_path=args.source,
                backup_dir=args.dest,
                retention_days=args.retention_days,
                azure_storage_account=acct,
                azure_storage_container=cont,
            )
            print(f"Backup created successfully: {archive.name}")
            if getattr(archive, "blob_name", None):
                print(f"Azure backup uploaded: {archive.blob_name}")
            return 0
        except Exception as e:
            print(f"Backup failed: {e}", file=sys.stderr)
            return 1

    elif args.command == "restore":
        if args.from_azure_blob:
            try:
                azure_config = get_azure_blob_config(args.storage_account, args.container)
                if not azure_config:
                    print(
                        f"Error: Restoring from Azure Blob requires both {AZURE_STORAGE_ACCOUNT_ENV} "
                        f"and {AZURE_STORAGE_CONTAINER_ENV} (or CLI flags).",
                        file=sys.stderr,
                    )
                    return 1
                acct, cont = azure_config
                restored = restore_database_from_azure_blob(
                    blob_name=args.from_azure_blob,
                    target_db_path=args.target_db,
                    account_name=acct,
                    container_name=cont,
                    force=args.force,
                )
                print(f"Database restored successfully from Azure Blob: {restored}")
                return 0
            except Exception as e:
                print(f"Azure Blob restore failed: {e}", file=sys.stderr)
                return 1
        elif args.backup_file:
            try:
                restored = restore_database(
                    backup_file_path=args.backup_file,
                    target_db_path=args.target_db,
                    force=args.force,
                )
                print(f"Database restored successfully: {restored}")
                return 0
            except Exception as e:
                print(f"Restore failed: {e}", file=sys.stderr)
                return 1
        else:
            print(
                "Error: Either --backup-file (for local archive) or --from-azure-blob must be specified.",
                file=sys.stderr,
            )
            return 1

    elif args.command == "list-azure-backups":
        try:
            azure_config = get_azure_blob_config(args.storage_account, args.container)
            if not azure_config:
                print(
                    f"Error: Listing Azure backups requires both {AZURE_STORAGE_ACCOUNT_ENV} "
                    f"and {AZURE_STORAGE_CONTAINER_ENV}.",
                    file=sys.stderr,
                )
                return 1
            acct, cont = azure_config
            blobs = list_azure_backups(account_name=acct, container_name=cont)
            print(f"=== AZURE BACKUP BLOBS IN {cont} ({len(blobs)} total) ===")
            for b in blobs:
                print(f"- {b['name']} ({b['size']} bytes, modified {b['last_modified']})")
            return 0
        except Exception as e:
            print(f"Failed to list Azure backups: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
