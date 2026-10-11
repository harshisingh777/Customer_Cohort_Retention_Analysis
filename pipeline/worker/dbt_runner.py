"""Runs `dbt build` into the *_build schemas and summarises the results."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.config import get_env, to_psycopg_url

DBT_DIR = Path(__file__).resolve().parents[1] / "dbt"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_\-]{16,}$")


@dataclass
class DbtResult:
    ok: bool
    returncode: int
    duration_s: float
    models: int = 0
    tests_passed: int = 0
    tests_warned: int = 0
    failures: list[dict] = field(default_factory=list)
    log_tail: str = ""

    def as_json(self) -> dict:
        return {
            "ok": self.ok,
            "models": self.models,
            "tests_passed": self.tests_passed,
            "tests_warned": self.tests_warned,
            "failures": self.failures,
        }


def dbt_env() -> dict[str, str]:
    env = get_env()
    url = urlparse(to_psycopg_url(env.pipeline_database_url))
    if not _SAFE_KEY.match(env.pii_key):
        raise RuntimeError(
            "PII_KEY must be at least 16 characters of [A-Za-z0-9_-] (use a random hex string)"
        )
    out = dict(os.environ)
    out.update(
        {
            "DBT_HOST": url.hostname or "localhost",
            "DBT_PORT": str(url.port or 5432),
            "DBT_USER": unquote(url.username or ""),
            "DBT_PASSWORD": unquote(url.password or ""),
            "DBT_DBNAME": url.path.lstrip("/") or "retention",
            # Session setting read by macros/pii.sql. libpq applies it at connect time.
            "PGOPTIONS": f"-c retention.pii_key={env.pii_key}",
            "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        }
    )
    if "sslmode=require" in env.pipeline_database_url:
        out["DBT_SSLMODE"] = "require"
    return out


def run_dbt(
    command: str, dbt_vars: dict, select: str | None = None, timeout: int = 3600
) -> DbtResult:
    with tempfile.TemporaryDirectory(prefix="dbt-") as tmp:
        dbt_bin = (
            shutil.which("dbt", path=str(Path(sys.executable).parent))
            or shutil.which("dbt")
            or "dbt"
        )
        args = [
            dbt_bin,
            "--no-use-colors",
            command,
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--target",
            "build",
            "--target-path",
            str(Path(tmp) / "target"),
            "--log-path",
            str(Path(tmp) / "logs"),
            "--vars",
            json.dumps(dbt_vars),
        ]
        if select:
            args += ["--select", select]
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            args, env=dbt_env(), capture_output=True, text=True, timeout=timeout, check=False
        )
        results_path = Path(tmp) / "target" / "run_results.json"
        res = DbtResult(
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            duration_s=0.0,
            log_tail=(proc.stdout + proc.stderr)[-6000:],
        )
        if results_path.exists():
            data = json.loads(results_path.read_text(encoding="utf-8"))
            res.duration_s = data.get("elapsed_time", 0.0)
            for r in data.get("results", []):
                uid: str = r["unique_id"]
                status = r["status"]
                if uid.startswith("model."):
                    res.models += status == "success"
                elif uid.startswith(("test.", "unit_test.")):
                    if status == "pass":
                        res.tests_passed += 1
                    elif status == "warn":
                        res.tests_warned += 1
                if status in ("error", "fail", "runtime error"):
                    res.failures.append(
                        {
                            "node": uid.split(".", 2)[-1],
                            "status": status,
                            "message": (r.get("message") or "")[:500],
                            "failures": r.get("failures"),
                        }
                    )
        if not results_path.exists() and proc.returncode != 0:
            res.failures.append({"node": "dbt", "status": "error", "message": res.log_tail[-800:]})
        res.ok = res.ok and not res.failures
        return res
