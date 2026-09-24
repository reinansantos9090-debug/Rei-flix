"""Explicit, non-destructive recovery service for an inconsistent local database.

Recovery is an exceptional path. It validates an incoming Rei-Flix backup with
the existing BackupService, preserves the current database as a safety copy, and
only replaces the database after the replacement has passed SQLite integrity and
foreign-key checks. Authentication is preserved when the damaged database can
still be read; if it cannot, recovery restore is refused rather than silently
losing the current account.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path


class RecoveryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)


class RecoveryService:
    def __init__(self, store):
        self.store = store

    def diagnose(self) -> dict:
        path = Path(self.store.db_path)
        report = {
            "required": False,
            "database_path": str(path),
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else 0,
            "quick_check": None,
            "foreign_key_ok": None,
            "error": None,
        }
        if not path.is_file():
            report["required"] = True
            report["error"] = "database_missing"
            return report
        try:
            with sqlite3.connect(str(path)) as con:
                quick = con.execute("PRAGMA quick_check").fetchone()
                report["quick_check"] = str(quick[0] if quick else "")
                report["foreign_key_ok"] = con.execute(
                    "PRAGMA foreign_key_check"
                ).fetchone() is None
        except Exception as exc:
            report["error"] = str(exc)
        report["required"] = (
            str(report.get("quick_check") or "").strip().casefold() != "ok"
            or report.get("foreign_key_ok") is False
            or bool(report.get("error"))
        )
        return report

    def diagnostic_bytes(self) -> bytes:
        return (json.dumps(self.diagnose(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    def create_safety_snapshot(self) -> str:
        source = Path(self.store.db_path)
        if not source.is_file():
            raise RecoveryError("RECOVERY_DATABASE_MISSING", "O banco atual não existe para criar um snapshot de segurança.")
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        target = Path(self.store.backup_dir) / f"recovery-snapshot-{stamp}.sqlite3"
        index = 1
        while target.exists():
            target = Path(self.store.backup_dir) / f"recovery-snapshot-{stamp}-{index}.sqlite3"
            index += 1
        shutil.copy2(source, target)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(source) + suffix)
            if sidecar.is_file():
                shutil.copy2(sidecar, Path(str(target) + suffix))
        return str(target)

    @staticmethod
    def _read_account(db_path: str) -> list[tuple[str, str]]:
        with sqlite3.connect(db_path) as con:
            rows = con.execute("SELECT key,value FROM account ORDER BY key").fetchall()
        return [(str(key), str(value)) for key, value in rows]

    @staticmethod
    def _write_account(db_path: str, rows: list[tuple[str, str]]) -> None:
        if not rows:
            return
        with sqlite3.connect(db_path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS account (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            con.executemany(
                "INSERT INTO account(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                rows,
            )
            con.commit()

    def restore_backup(self, raw: bytes) -> dict:
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            raise RecoveryError("RECOVERY_BACKUP_INVALID", "O backup selecionado está vazio.")

        from core.backup import BackupService

        backup = BackupService(self.store)
        preview = backup.inspect_bytes(bytes(raw))

        try:
            account_rows = self._read_account(self.store.db_path)
        except Exception as exc:
            raise RecoveryError(
                "RECOVERY_AUTH_PRESERVATION_FAILED",
                "O banco atual não pode ser lido com segurança para preservar a autenticação. "
                "O restore foi recusado para evitar perda de autenticação.",
            ) from exc

        safety = self.create_safety_snapshot()

        tempdir = tempfile.TemporaryDirectory(prefix=".reiflix-recovery-", dir=self.store.backup_dir)
        created_assets: list[str] = []
        try:
            input_zip = Path(tempdir.name) / "backup.zip"
            input_zip.write_bytes(bytes(raw))
            extracted, mappings, created_assets, restore_temp = backup._prepare_restore(str(input_zip))
            try:
                self._write_account(extracted, account_rows)
                with sqlite3.connect(extracted) as con:
                    quick = con.execute("PRAGMA integrity_check").fetchone()
                    if str(quick[0] if quick else "").strip().casefold() != "ok":
                        raise RecoveryError("RECOVERY_VALIDATION_FAILED", "O banco restaurado falhou no integrity_check.")
                    if con.execute("PRAGMA foreign_key_check").fetchone():
                        raise RecoveryError("RECOVERY_VALIDATION_FAILED", "O banco restaurado possui foreign keys inválidas.")
                    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                replacement = Path(self.store.db_path)
                replacement_tmp = replacement.with_name(replacement.name + ".recovery.tmp")
                shutil.copy2(extracted, replacement_tmp)
                with open(replacement_tmp, "rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(replacement_tmp, replacement)
                for suffix in ("-wal", "-shm"):
                    stale = Path(str(replacement) + suffix)
                    if stale.exists():
                        stale.unlink()
                verification = self.diagnose()
                if verification["required"]:
                    raise RecoveryError(
                        "RECOVERY_VALIDATION_FAILED",
                        "O banco restaurado não passou na validação final.",
                    )
            finally:
                restore_temp.cleanup()
        except Exception:
            for path in created_assets:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            try:
                shutil.copy2(safety, self.store.db_path)
            except Exception:
                pass
            raise
        finally:
            tempdir.cleanup()

        return {
            "preview": preview,
            "safety_snapshot": safety,
            "report": self.diagnose(),
            "restart_required": True,
        }
