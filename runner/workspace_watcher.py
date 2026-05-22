from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
}


@dataclass(frozen=True)
class FileSnapshot:
    mtime_ns: int
    size: int


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def should_skip_directory(path: Path, excluded_dirs: set[str]) -> bool:
    return any(part in excluded_dirs for part in path.parts)


def build_snapshot(root: Path, excluded_dirs: Iterable[str]) -> dict[str, FileSnapshot]:
    excluded = set(excluded_dirs)
    snapshot: dict[str, FileSnapshot] = {}

    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)
        relative_parts = current_path.relative_to(root).parts if current_path != root else ()

        dirnames[:] = [
            name
            for name in dirnames
            if name not in excluded and not should_skip_directory(Path(*relative_parts, name), excluded)
        ]

        for filename in filenames:
            file_path = current_path / filename
            relative = Path(*relative_parts, filename)
            if should_skip_directory(relative, excluded):
                continue
            try:
                stat = file_path.stat()
            except OSError:
                continue
            snapshot[relative.as_posix()] = FileSnapshot(mtime_ns=stat.st_mtime_ns, size=stat.st_size)

    return snapshot


def diff_snapshots(
    previous: dict[str, FileSnapshot],
    current: dict[str, FileSnapshot],
) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []

    previous_keys = set(previous)
    current_keys = set(current)

    for file_path in sorted(current_keys - previous_keys):
        events.append(("file_created", file_path))

    for file_path in sorted(previous_keys - current_keys):
        events.append(("file_deleted", file_path))

    for file_path in sorted(previous_keys & current_keys):
        if previous[file_path] != current[file_path]:
            events.append(("file_modified", file_path))

    return events


def start_workspace_watcher(
    root: str,
    on_event: Callable[[str, str], None],
    stop_event: threading.Event,
    interval: float = 1.0,
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
) -> threading.Thread:
    root_path = Path(root).resolve()
    previous_snapshot = build_snapshot(root_path, excluded_dirs)

    def watch() -> None:
        nonlocal previous_snapshot

        while not stop_event.wait(interval):
            current_snapshot = build_snapshot(root_path, excluded_dirs)
            for event_type, file_path in diff_snapshots(previous_snapshot, current_snapshot):
                on_event(event_type, file_path)
            previous_snapshot = current_snapshot

    thread = threading.Thread(target=watch, name=f"watcher-{root_path.name}", daemon=True)
    thread.start()
    return thread
