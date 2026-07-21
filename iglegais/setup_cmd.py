"""One-command bootstrap for iglegais.

  pip install iglegais && iglegais-setup

Installs/configures Helix (local graph DB), writes ~/.iglegais/.env,
and wires Claude Code / Grok MCP when those CLIs are present.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .home import (
    DEFAULT_HELIX_URL,
    ENV_FILE,
    HELIX_DIR,
    HOME,
    ensure_home,
    env_lookup,
    helix_url,
    write_env_key,
)

HELIX_REPO = "HelixDB/helix-db"
HELIX_INSTALL_SH = "https://install.helix-db.com"


# ── tiny UI ──────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ! {msg}")


def _info(msg: str) -> None:
    print(f"  · {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── Helix CLI ────────────────────────────────────────────────────────

def _helix_bin() -> str | None:
    return _which("helix")


def _platform_helix_asset() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        raise RuntimeError(f"unsupported arch: {machine}")

    if system == "linux":
        return f"helix-{arch}-unknown-linux-gnu"
    if system == "darwin":
        return f"helix-{arch}-apple-darwin"
    if system == "windows":
        return f"helix-{arch}-pc-windows-msvc.exe"
    raise RuntimeError(f"unsupported OS: {system}")


def _github_latest_helix_url() -> tuple[str, str]:
    api = f"https://api.github.com/repos/{HELIX_REPO}/releases/latest"
    req = urllib.request.Request(api, headers={"User-Agent": "iglegais-setup"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    tag = data["tag_name"]
    want = _platform_helix_asset()
    for asset in data.get("assets", []):
        name = asset["name"]
        if name == want or name.endswith(want) or want in name:
            return tag, asset["browser_download_url"]
    # fallback: construct common release URL pattern
    return tag, (
        f"https://github.com/{HELIX_REPO}/releases/download/{tag}/{want}"
    )


def install_helix_cli() -> str:
    """Return path to helix binary, installing if needed."""
    existing = _helix_bin()
    if existing:
        _ok(f"helix already installed ({existing})")
        return existing

    _info("helix CLI not found — installing…")
    ensure_home()
    bindir = HOME / "bin"
    bindir.mkdir(parents=True, exist_ok=True)

    # Prefer official install script on Unix
    if platform.system() != "Windows" and _which("bash") and _which("curl"):
        env = os.environ.copy()
        # helix installer respects -d
        r = _run(
            ["bash", "-c", f'curl -fsSL "{HELIX_INSTALL_SH}" | bash -s -- -d "{bindir}"'],
            timeout=180,
        )
        if r.returncode == 0 and (bindir / "helix").exists():
            _ok(f"helix installed to {bindir}")
            return str(bindir / "helix")
        if r.stderr:
            _warn(r.stderr.strip()[:300])

    # Cross-platform: download release binary
    try:
        tag, url = _github_latest_helix_url()
        _info(f"downloading helix {tag}…")
        name = "helix.exe" if platform.system() == "Windows" else "helix"
        dest = bindir / name
        req = urllib.request.Request(url, headers={"User-Agent": "iglegais-setup"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        if platform.system() != "Windows":
            dest.chmod(0o755)
        _ok(f"helix installed to {dest}")
        # put on PATH for this process
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
        return str(dest)
    except Exception as e:
        _fail(f"could not auto-install helix: {e}")
        print(
            "\n  Install Helix manually, then re-run iglegais-setup:\n"
            f"    curl -fsSL {HELIX_INSTALL_SH} | bash\n"
            "    https://docs.helix-db.com\n",
            file=sys.stderr,
        )
        sys.exit(1)


def ensure_helix_running(helix: str, disk: bool = True) -> None:
    url = helix_url()
    if _port_up(url):
        _ok(f"helix already responding at {url}")
        return

    HELIX_DIR.mkdir(parents=True, exist_ok=True)
    if not (HELIX_DIR / "helix.toml").exists():
        _info(f"initializing helix project in {HELIX_DIR}")
        r = _run([helix, "init"], cwd=str(HELIX_DIR), timeout=60)
        if r.returncode != 0:
            # some versions init differently; keep going if start works
            _warn((r.stderr or r.stdout or "helix init failed").strip()[:200])

    cmd = [helix, "start", "dev"]
    if disk:
        cmd.append("--disk")
    _info(f"starting helix: {' '.join(cmd)}")
    r = _run(cmd, cwd=str(HELIX_DIR), timeout=180)
    if r.returncode != 0:
        # try without --disk if unsupported
        if disk and "--disk" in (r.stderr or ""):
            r = _run([helix, "start", "dev"], cwd=str(HELIX_DIR), timeout=180)
        if r.returncode != 0:
            _fail((r.stderr or r.stdout or "helix start failed").strip()[:400])
            _warn("is Docker running? Helix local instances usually need it.")
            sys.exit(1)

    if not _wait_for(url, timeout=60):
        _fail(f"helix started but {url} never came up")
        sys.exit(1)
    _ok(f"helix up at {url}")


def _port_up(url: str) -> bool:
    try:
        # any response (even 404) means the server is listening
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "iglegais"})
        urllib.request.urlopen(req, timeout=2)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def _wait_for(url: str, timeout: float = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_up(url):
            return True
        time.sleep(1)
    return False


# ── API key ──────────────────────────────────────────────────────────

def ensure_api_key(key_arg: str | None, non_interactive: bool) -> None:
    existing = env_lookup("CEREBRAS_API_KEY")
    if key_arg:
        write_env_key("CEREBRAS_API_KEY", key_arg)
        os.environ["CEREBRAS_API_KEY"] = key_arg
        _ok(f"saved CEREBRAS_API_KEY to {ENV_FILE}")
        return
    if existing:
        _ok("CEREBRAS_API_KEY already set (edge inference enabled)")
        return
    if non_interactive:
        _warn(
            "no CEREBRAS_API_KEY — remember() still stores memories, "
            "but causal edges won't be inferred until you set one"
        )
        _info(f"  setx CEREBRAS_API_KEY your-key   or write {ENV_FILE}")
        return
    print()
    print("  Causal edge inference needs a free LLM key (Cerebras works).")
    print("  Get one: https://cloud.cerebras.ai")
    print("  Press Enter to skip (you can add it later).")
    try:
        key = input("  CEREBRAS_API_KEY: ").strip()
    except EOFError:
        key = ""
    if key:
        write_env_key("CEREBRAS_API_KEY", key)
        os.environ["CEREBRAS_API_KEY"] = key
        _ok(f"saved to {ENV_FILE}")
    else:
        _warn("skipped — storage works; auto-edges off until key is set")


# ── MCP wiring ───────────────────────────────────────────────────────

def wire_mcp(skip: bool) -> None:
    if skip:
        _info("skipped MCP wiring (--no-mcp)")
        return

    wired = False
    # Claude Code
    if _which("claude"):
        # remove old then add (idempotent-ish)
        _run(["claude", "mcp", "remove", "iglegais"], timeout=30)
        r = _run(
            ["claude", "mcp", "add", "iglegais", "--", "iglegais"],
            timeout=30,
        )
        if r.returncode != 0:
            # fallback: python -m
            r = _run(
                [
                    "claude", "mcp", "add", "iglegais", "--",
                    sys.executable, "-m", "iglegais.server",
                ],
                timeout=30,
            )
        if r.returncode == 0:
            _ok("wired Claude Code MCP (iglegais)")
            wired = True
        else:
            _warn("claude mcp add failed — run: claude mcp add iglegais -- iglegais")
    else:
        _info("claude CLI not found (skip Claude MCP)")

    # Grok
    if _which("grok"):
        _run(["grok", "mcp", "remove", "iglegais"], timeout=30)
        r = _run(
            [
                "grok", "mcp", "add", "iglegais", "--",
                sys.executable, "-m", "iglegais.server",
            ],
            timeout=30,
        )
        if r.returncode == 0:
            _ok("wired Grok MCP (iglegais)")
            wired = True
        else:
            _warn(
                "grok mcp add failed — run: "
                f"grok mcp add iglegais -- {sys.executable} -m iglegais.server"
            )
    else:
        _info("grok CLI not found (skip Grok MCP)")

    # Cursor: write project-agnostic user note; cursor uses mcp.json
    cursor_cfg = Path.home() / ".cursor" / "mcp.json"
    if cursor_cfg.parent.is_dir():
        try:
            data = json.loads(cursor_cfg.read_text(encoding="utf-8")) if cursor_cfg.is_file() else {}
            servers = data.setdefault("mcpServers", {})
            servers["iglegais"] = {
                "command": sys.executable,
                "args": ["-m", "iglegais.server"],
            }
            cursor_cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            _ok(f"wired Cursor MCP ({cursor_cfg})")
            wired = True
        except Exception as e:
            _warn(f"could not update Cursor mcp.json: {e}")

    if not wired:
        _warn("no assistant CLI found. add manually:")
        print(f"    claude mcp add iglegais -- iglegais")
        print(f"    grok mcp add iglegais -- {sys.executable} -m iglegais.server")


# ── smoke ────────────────────────────────────────────────────────────

def smoke_test() -> None:
    try:
        from .mg import MemoryGraph

        mg = MemoryGraph()
        mg.setup()
        _ok("memory graph reachable (index ok)")
    except Exception as e:
        _warn(f"smoke test failed (helix up but schema/setup error): {e}")


# ── main ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="iglegais-setup",
        description="One-command setup: Helix DB + env + MCP wiring for iglegais.",
    )
    p.add_argument("--key", help="CEREBRAS_API_KEY (optional, for edge inference)")
    p.add_argument("--no-mcp", action="store_true", help="don't wire assistant MCPs")
    p.add_argument("--no-disk", action="store_true", help="helix in-memory (data wiped on stop)")
    p.add_argument("-y", "--yes", action="store_true", help="non-interactive (skip prompts)")
    p.add_argument("--skip-helix", action="store_true", help="assume Helix is already running")
    args = p.parse_args(argv)

    print()
    print("  iglegais setup")
    print("  memory that answers why, not just what")
    print()

    ensure_home()
    _ok(f"home: {HOME}")

    write_env_key("HELIX_URL", env_lookup("HELIX_URL") or DEFAULT_HELIX_URL)

    if not args.skip_helix:
        helix = install_helix_cli()
        ensure_helix_running(helix, disk=not args.no_disk)
    else:
        if _port_up(helix_url()):
            _ok(f"using existing helix at {helix_url()}")
        else:
            _fail(f"no helix at {helix_url()} and --skip-helix set")
            sys.exit(1)

    ensure_api_key(args.key, non_interactive=args.yes)
    wire_mcp(skip=args.no_mcp)
    smoke_test()

    print()
    print("  done. your assistant now has: remember · recall · why")
    print()
    print("  try in Claude / Grok / Cursor:")
    print('    "remember: the deploy failed because of a race in migrations"')
    print('    "why did the deploy fail?"')
    print()
    print(f"  config:  {ENV_FILE}")
    print(f"  helix:   {helix_url()}")
    print(f"  stop DB: helix stop dev   (from {HELIX_DIR})")
    print()


if __name__ == "__main__":
    main()
