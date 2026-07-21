"""User home for iglegais: config, env, helix workspace."""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("IGLEGAIS_HOME", Path.home() / ".iglegais"))
ENV_FILE = HOME / ".env"
HELIX_DIR = HOME / "helix"
DEFAULT_HELIX_URL = "http://localhost:6969"


def ensure_home() -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    return HOME


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def env_lookup(*keys: str) -> str | None:
    """Prefer process env, then ~/.iglegais/.env, then cwd/.env."""
    for key in keys:
        val = os.environ.get(key)
        if val:
            return val
    candidates = [ENV_FILE, Path.cwd() / ".env"]
    here = Path(__file__).resolve().parent
    candidates.extend([here.parent / ".env", here / ".env"])
    for path in candidates:
        data = read_env_file(path)
        for key in keys:
            if data.get(key):
                return data[key]
    return None


def helix_url() -> str:
    return env_lookup("HELIX_URL", "IGLEGAIS_HELIX_URL") or DEFAULT_HELIX_URL


def write_env_key(key: str, value: str) -> Path:
    """Upsert KEY=value in ~/.iglegais/.env."""
    ensure_home()
    lines: list[str] = []
    found = False
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return ENV_FILE
