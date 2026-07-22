"""Background runner for the full data-refresh chain (Parts A -> B -> C -> D).

Each stage below is an existing, independently-runnable CLI script that
calls ``sys.exit()`` on completion/failure and does its own file logging —
that is safe as a subprocess but would kill the whole API process if
imported and called in-process. So this module launches each stage as a
real OS subprocess, sequentially, on a background thread, and exposes its
progress through an in-memory status object that the API polls.

Chain (unchanged scripts, just orchestrated from one place):
  1. Part A  scripts/ingestion/run_all_sources.py       (pull fresh source data)
  2. Part B  python -m scripts.pipeline.run_pipeline     (normalize/dedup/NLP/store)
  3. Part C  python -m scripts.knowledge_graph.cli        (load into Neo4j)
  3.5 Part D (train)  python -m scripts.risk_prediction.cli --train
             (only inserted when no model artifact exists yet on this machine —
             `models/` is gitignored so a fresh checkout has none)
  4. Part D  python -m scripts.risk_prediction.cli --predict --write-back
             (refresh RiskAssessment scores that Part G's Early Risk Alerts read)
"""

from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.risk_prediction.config import RiskPredictionConfig

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "logs"

FIXED_STAGES: tuple[tuple[str, list[str]], ...] = (
    ("Part A: ingest source data", [sys.executable, "scripts/ingestion/run_all_sources.py"]),
    ("Part B: normalize & process", [sys.executable, "-m", "scripts.pipeline.run_pipeline"]),
    ("Part C: load knowledge graph", [sys.executable, "-m", "scripts.knowledge_graph.cli"]),
)

TRAIN_STAGE: tuple[str, list[str]] = (
    "Part D: train risk model (first run only)",
    [sys.executable, "-m", "scripts.risk_prediction.cli", "--train"],
)

PREDICT_STAGE: tuple[str, list[str]] = (
    "Part D: refresh risk scores",
    [sys.executable, "-m", "scripts.risk_prediction.cli", "--predict", "--write-back"],
)


def _build_stages() -> list[tuple[str, list[str]]]:
    """Insert a training stage only when no model artifact exists yet."""
    stages = list(FIXED_STAGES)
    try:
        model_path = RiskPredictionConfig.from_env().model_path
    except Exception:  # noqa: BLE001 — fall back to always training if config can't load
        model_path = None
    if model_path is None or not model_path.exists():
        stages.append(TRAIN_STAGE)
    stages.append(PREDICT_STAGE)
    return stages


@dataclass
class RefreshStatus:
    state: str = "idle"  # idle | running | completed | failed
    current_stage: str | None = None
    stage_index: int = 0
    stage_count: int = len(FIXED_STAGES) + 1
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    log_file: str | None = None
    triggered_by: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "current_stage": self.current_stage,
            "stage_index": self.stage_index,
            "stage_count": self.stage_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "log_file": self.log_file,
            "triggered_by": self.triggered_by,
        }


class PipelineRefreshManager:
    """Serializes and tracks one data-refresh chain run at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = RefreshStatus()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status.summary()

    def start(self, triggered_by: str) -> bool:
        """Start the refresh chain in the background. Returns False if already running."""
        with self._lock:
            if self._status.state == "running":
                return False
            stages = _build_stages()
            LOG_DIR.mkdir(exist_ok=True)
            log_path = LOG_DIR / f"system_refresh_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
            self._status = RefreshStatus(
                state="running",
                current_stage=stages[0][0],
                stage_index=1,
                stage_count=len(stages),
                started_at=datetime.now(timezone.utc).isoformat(),
                log_file=str(log_path.relative_to(BASE_DIR)),
                triggered_by=triggered_by,
            )
        thread = threading.Thread(target=self._run_chain, args=(log_path, stages), daemon=True)
        thread.start()
        return True

    def _run_chain(self, log_path: Path, stages: list[tuple[str, list[str]]]) -> None:
        with log_path.open("w", encoding="utf-8") as log_handle:
            for index, (label, command) in enumerate(stages, start=1):
                with self._lock:
                    self._status.current_stage = label
                    self._status.stage_index = index
                log_handle.write(f"\n===== [{index}/{len(stages)}] {label} =====\n")
                log_handle.flush()
                try:
                    result = subprocess.run(
                        command,
                        cwd=BASE_DIR,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        timeout=3600,
                    )
                except Exception as exc:  # noqa: BLE001
                    self._finish(state="failed", error=f"{label}: {exc}")
                    return
                if result.returncode != 0:
                    self._finish(
                        state="failed",
                        error=f"{label} exited with code {result.returncode}. See {log_path.name}.",
                    )
                    return
        self._finish(state="completed", error=None)

    def _finish(self, state: str, error: str | None) -> None:
        with self._lock:
            self._status.state = state
            self._status.error = error
            self._status.finished_at = datetime.now(timezone.utc).isoformat()
            self._status.current_stage = None


refresh_manager = PipelineRefreshManager()
