"""
Production SQLite Online Backup and Restore Utility.

Uses Python's standard-library sqlite3.Connection.backup() API to create
atomic, non-blocking, online backups of SQLite databases operating in WAL mode.

Features:
- Online live backup without locking active readers/writers.
- Automated PRAGMA integrity_check validation before finalizing backup.
- Gzip compression of verified backup archives.
- Atomic file finalization via temporary staging files.
- Configurable retention pruning of aged backups.
- Safe restore with pre-validation and overwrite protection.
- Zero sensitive data logging (no schema or row content logged).
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

logger = logging.getLogger("backup_db")


def verify_database_integrity(db_path: Path | str) -> bool:
    """Runs PRAGMA integrity_check against a SQLite database file."""
    path = Path(db_path)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        conn = sqlite3.connect(path)
        cursor = conn.execute("PRAGMA integrity_check;")
        rows = cursor.fetchall()
        conn.close()
        return len(rows) == 1 and rows[0][0].strip().lower() == "ok"
    except Exception as e:
        logger.warning(f"Integrity check failed with exception: {e}")
        return False


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


def backup_database(
    source_db_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
    retention_days: int = 14,
) -> Path:
    """
    Executes a validated online backup of source_db_path into backup_dir.

    Steps:
    1. Opens source database connection.
    2. Backs up into temporary destination file using Connection.backup().
    3. Runs PRAGMA integrity_check on the temporary database.
    4. Compresses verified database with gzip into temporary .gz file.
    5. Atomically renames temporary .gz file to final timestamped archive.
    6. Prunes backups older than retention_days.

    Returns the Path to the finalized compressed backup archive.
    Raises RuntimeError on integrity or backup failure.
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

    # 7. Prune older backups
    prune_backups(target_dir, retention_days=retention_days)

    return final_gz


def restore_database(
    backup_file_path: Path | str,
    target_db_path: Path | str,
    force: bool = False,
) -> Path:
    """
    Safely restores a SQLite database from a compressed backup archive.

    Steps:
    1. Verifies source archive exists.
    2. Checks target_db_path does not exist (unless force=True).
    3. Decompresses archive to a temporary file.
    4. Validates restored temporary file with PRAGMA integrity_check.
    5. Atomically renames temporary file to target_db_path.

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

        # Atomically move to target
        os.replace(temp_restore, target_path)

    finally:
        if temp_restore.exists():
            try:
                temp_restore.unlink()
            except OSError:
                pass

    return target_path


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Interview Simulator SQLite Backup Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Run online database backup")
    backup_parser.add_argument("--source", default=None, help="Source database path")
    backup_parser.add_argument("--dest", default=None, help="Backup destination directory")
    backup_parser.add_argument(
        "--retention-days", type=int, default=14, help="Days of backups to retain (default: 14)"
    )

    restore_parser = subparsers.add_parser("restore", help="Restore database from backup archive")
    restore_parser.add_argument("--backup-file", required=True, help="Backup archive to restore from")
    restore_parser.add_argument("--target-db", required=True, help="Target database path")
    restore_parser.add_argument(
        "--force", action="store_true", help="Overwrite target database if it exists"
    )

    args = parser.parse_args()

    if args.command == "backup":
        try:
            archive = backup_database(
                source_db_path=args.source,
                backup_dir=args.dest,
                retention_days=args.retention_days,
            )
            print(f"Backup created successfully: {archive.name}")
            return 0
        except Exception as e:
            print(f"Backup failed: {e}", file=sys.stderr)
            return 1

    elif args.command == "restore":
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
