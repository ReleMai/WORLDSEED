from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path


class SessionDebugLog:
    """Low-overhead JSONL diagnostics for playtest sessions.

    The logger is intentionally append-only and bounded. It records engine
    commands, expensive stage timings, UI actions, warnings and exceptions
    without becoming another simulation authority.
    """

    def __init__(self, *, root: Path | None = None, engine_version: str = "", world: str = "") -> None:
        root = Path(root or Path.cwd() / "logs")
        root.mkdir(parents=True, exist_ok=True)
        stamp=time.strftime("%Y%m%d_%H%M%S")
        self.path=root/f"WORLDSEED_DEBUG_{stamp}_{os.getpid()}.jsonl"
        self.logger=logging.getLogger(f"worldseed.session.{id(self)}")
        self.logger.setLevel(logging.INFO);self.logger.propagate=False
        handler=RotatingFileHandler(self.path,maxBytes=8*1024*1024,backupCount=3,encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.handlers[:]=[handler]
        self.started=time.perf_counter()
        self.profiler=None
        self.event("session_start",engine_version=engine_version,world=world,python=sys.version.split()[0],pid=os.getpid())

    def event(self, kind: str, **data) -> None:
        payload={"t_ms":round((time.perf_counter()-self.started)*1000,3),"kind":str(kind)}
        for key,value in data.items():
            try:json.dumps(value);payload[key]=value
            except Exception:payload[key]=repr(value)
        self.logger.info(json.dumps(payload,separators=(",",":"),sort_keys=True))

    def exception(self, where: str, exc: BaseException | None = None, **data) -> None:
        self.event(
            "exception",where=where,error=repr(exc) if exc is not None else "",
            traceback=traceback.format_exc(),**data,
        )
        self.flush()

    @contextmanager
    def stage(self, name: str, *, warn_ms: float = 80.0, **data):
        start=time.perf_counter()
        try:
            yield
        except Exception as exc:
            elapsed=(time.perf_counter()-start)*1000
            self._profile_stage(name,elapsed)
            self.exception(name,exc,elapsed_ms=round(elapsed,3),**data)
            raise
        else:
            elapsed=(time.perf_counter()-start)*1000
            self._profile_stage(name,elapsed)
            self.event("stage",name=name,elapsed_ms=round(elapsed,3),slow=elapsed>=warn_ms,**data)

    def _profile_stage(self,name,elapsed_ms) -> None:
        profiler=self.profiler
        if profiler is not None and profiler.enabled:
            try:profiler.record('preparation.'+str(name),elapsed_ms)
            except Exception:pass

    def flush(self) -> None:
        for handler in self.logger.handlers:
            try:handler.flush()
            except Exception:pass


def debug_log_path(obj) -> str:
    debug=getattr(obj,"debug",None)
    return str(getattr(debug,"path",""))
