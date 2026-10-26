"""Небольшие запросы к GitHub API для проверки и публикации CF-Entware."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

UA = "CF-Entware"


def token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "miha75vu-bit/CF-Entware")


def request(url: str, method: str = "GET", accept: str = "application/vnd.github+json") -> tuple[int, bytes]:
    headers = {"User-Agent": UA, "Accept": accept}
    tok = token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body[:400]!r}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Сеть: {url}: {exc}") from exc


def get_json(url: str) -> object:
    _, data = request(url)
    return json.loads(data.decode("utf-8"))


def download(url: str) -> bytes:
    _, data = request(url, accept="application/octet-stream")
    return data


def delete(url: str) -> None:
    request(url, method="DELETE")
