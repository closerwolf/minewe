"""GitHub Actions 端：连上服务器的 /ws，地址一变就改 index.html 并提交。"""
import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path

import websockets

WS_URL = os.environ["WS_URL"]
INDEX = Path("index.html")
DEADLINE = time.monotonic() + float(os.environ.get("LISTEN_SECONDS", 20880))
URL_RE = re.compile(r"^https://[a-z0-9.]+\.lhr\.life$")


def pinned_url() -> str | None:
    m = re.search(r'const API_BASE_URL = "([^"]*)"', INDEX.read_text())
    return m.group(1) if m else None


def apply_url(url: str) -> bool:
    text = INDEX.read_text()
    new = re.sub(r'(const API_BASE_URL = ")[^"]*', lambda m: m.group(1) + url, text)
    if new == text:
        return False
    INDEX.write_text(new)
    return True


def commit(url: str) -> None:
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", "index.html"], check=True)
    if subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", f"chore: point API_BASE_URL at {url}"], check=True)
    for _ in range(3):
        if subprocess.run(["git", "push"]).returncode == 0:
            return
        subprocess.run(["git", "pull", "--rebase", "--autostash"])
    raise SystemExit("git push failed after retries")


async def main() -> None:
    backoff = 1
    while time.monotonic() < DEADLINE:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
                print("connected", flush=True)
                backoff = 1
                while time.monotonic() < DEADLINE:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=120)
                    except asyncio.TimeoutError:
                        continue
                    url = json.loads(msg).get("url")
                    if url and URL_RE.match(url) and url != pinned_url():
                        print("update ->", url, flush=True)
                        if apply_url(url):
                            commit(url)
        except Exception as exc:  # 断线重连
            print("connection error:", exc, flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


asyncio.run(main())
