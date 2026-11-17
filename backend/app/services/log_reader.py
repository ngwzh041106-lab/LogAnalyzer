from pathlib import Path
import re
import subprocess

from app.models.log_source import LogSource


class LogReadError(Exception):
    """Raised when a configured log cannot be read."""


class LogReader:
    """Read a configured file or command output and apply line filters."""

    @staticmethod
    def _file_candidates(raw_path: str) -> list[Path]:
        path = raw_path.strip()
        candidates: list[Path] = []
        windows_drive = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
        if windows_drive:
            path = f"/mnt/{windows_drive.group(1).lower()}/{windows_drive.group(2).replace(chr(92), '/')}"
        requested = Path(path)
        if requested.is_absolute():
            candidates.append(requested)
            candidates.append(Path("/host") / requested.relative_to("/"))
        else:
            candidates.append(requested)
        return list(dict.fromkeys(candidates))

    @classmethod
    def _resolve_file(cls, raw_path: str) -> Path:
        candidates = cls._file_candidates(raw_path)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        searched = ", ".join(str(candidate) for candidate in candidates)
        raise LogReadError(f"Log file does not exist or is not readable: {raw_path} (checked: {searched})")

    def read(self, source: LogSource) -> str:
        if source.source_type == "command":
            if not source.command:
                raise LogReadError("Command source has no command configured")
            try:
                result = subprocess.run(
                    source.command, shell=True, capture_output=True, timeout=30, check=False
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise LogReadError(f"Unable to execute command: {exc}") from exc
            if result.returncode != 0:
                error = result.stderr.decode("utf-8", errors="replace").strip()
                raise LogReadError(f"Command exited with {result.returncode}: {error}")
            text = result.stdout.decode("utf-8", errors="replace")
            if source.read_mode == "tail_bytes":
                text = text.encode("utf-8")[-source.tail_bytes :].decode("utf-8", errors="replace")
            else:
                text = "".join(text.splitlines(keepends=True)[-source.tail_lines :])
        else:
            path = self._resolve_file(source.path)
            try:
                if source.read_mode == "tail_bytes":
                    with path.open("rb") as stream:
                        stream.seek(0, 2)
                        stream.seek(max(0, stream.tell() - source.tail_bytes))
                        text = stream.read().decode("utf-8", errors="replace")
                else:
                    with path.open("r", encoding="utf-8", errors="replace") as stream:
                        text = "".join(stream.readlines()[-source.tail_lines :])
            except OSError as exc:
                raise LogReadError(f"Unable to read log file: {source.path}: {exc}") from exc

        lines = text.splitlines()
        if source.include_patterns:
            includes = [item.strip() for item in source.include_patterns.splitlines() if item.strip()]
            lines = [line for line in lines if any(pattern in line for pattern in includes)]
        if source.exclude_patterns:
            excludes = [item.strip() for item in source.exclude_patterns.splitlines() if item.strip()]
            lines = [line for line in lines if not any(pattern in line for pattern in excludes)]
        return "\n".join(lines)
