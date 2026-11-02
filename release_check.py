"""Решать, нужен ли новый релиз CF-Entware.

Релиз создаётся только при изменениях в Flashkeen, HydraRoute или Entware.
Ежедневная проверка сверяет только эти три источника.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import build
import gh_api
import status

ROOT = Path(__file__).resolve().parent
OUT = ROOT / ".release"
MSK = timezone(timedelta(hours=3))
HYDRA_NAMES = ("hrneo", "hrweb", "hrdns")


def canon(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def set_output(name: str, value: str) -> None:
    print(f"{name}={value}", flush=True)
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{name}={value}\n")


def fresh_index(bases: list[str]) -> dict[str, dict[str, str]]:
    last: Exception | None = None
    for base in bases:
        for suffix in ("/Packages.gz", "/Packages"):
            url = base.rstrip("/") + suffix
            try:
                raw = build.http_get(url, timeout=90)
                print(f"  индекс {url}", flush=True)
                return build.parse_packages(build.decode_packages(raw), base.rstrip("/"))
            except (RuntimeError, OSError) as exc:
                last = exc
    raise SystemExit(f"Нет индекса пакетов: {last}")


def installer_stamp(url: str) -> dict[str, str]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": gh_api.UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        headers = resp.headers
        return {
            "etag": headers.get("ETag", ""),
            "last_modified": headers.get("Last-Modified", ""),
            "length": headers.get("Content-Length", ""),
        }


def fingerprint() -> dict[str, object]:
    release = gh_api.get_json("https://api.github.com/repos/miha75vu-bit/Flashkeen/releases/latest")
    if not isinstance(release, dict) or not release.get("tag_name"):
        raise SystemExit("GitHub не отдал последний релиз Flashkeen")
    print(f"Flashkeen {release['tag_name']}", flush=True)

    hydra: dict[str, dict[str, str]] = {}
    for arch, feeds in build.ARCH_APP_FEEDS.items():
        index = fresh_index([feeds["hydra"]])
        hydra[arch] = {}
        for name in HYDRA_NAMES:
            if name not in index:
                raise SystemExit(f"В HydraRoute {arch} нет пакета {name}")
            hydra[arch][name] = index[name].get("Version", "")

    installers: dict[str, dict[str, str]] = {}
    packages: dict[str, dict[str, str]] = {}
    for arch, cfg in build.ARCHES.items():
        print(f"Entware {arch}", flush=True)
        installers[arch] = installer_stamp(cfg["installer"])
        index = fresh_index([cfg["feed"], *cfg["mirrors"]])
        seeds = build.adapt_seeds(index, build.SEED_PACKAGES)
        names = build.resolve_closure(index, seeds)
        packages[arch] = {name: index[name].get("Version", "") for name in names}

    return {
        "flashkeen": str(release["tag_name"]),
        "hydra": hydra,
        "entware_installer": installers,
        "entware_packages": packages,
    }


def latest_release() -> dict[str, object] | None:
    url = f"https://api.github.com/repos/{gh_api.repo()}/releases/latest"
    try:
        release = gh_api.get_json(url)
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    return release if isinstance(release, dict) else None


def previous_fingerprint(release: dict[str, object] | None) -> dict[str, object] | None:
    if release is None:
        return None
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") != "fingerprint.json":
            continue
        raw = gh_api.download(str(asset["browser_download_url"]))
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict):
            return data
    return None


def published_today(release: dict[str, object] | None) -> bool:
    if release is None:
        return False
    published_at = release.get("published_at")
    if not isinstance(published_at, str):
        return False
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published.astimezone(MSK).date() == datetime.now(MSK).date()


def existing_tags() -> set[str]:
    found: set[str] = set()
    page = 1
    while True:
        url = f"https://api.github.com/repos/{gh_api.repo()}/tags?per_page=100&page={page}"
        batch = gh_api.get_json(url)
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            if isinstance(item, dict) and item.get("name"):
                found.add(str(item["name"]))
        if len(batch) < 100:
            break
        page += 1
    return found


def next_tag() -> str:
    day = datetime.now(MSK).strftime("%Y.%m.%d")
    taken = existing_tags()
    if day not in taken:
        return day
    number = 2
    while f"{day}-{number}" in taken:
        number += 1
    return f"{day}-{number}"


def changed_lines(old: dict[str, object], new: dict[str, object]) -> list[str]:
    lines: list[str] = []
    if old.get("flashkeen") != new.get("flashkeen"):
        lines.append("Flashkeen")
    if old.get("hydra") != new.get("hydra"):
        lines.append("HydraRoute")
    if (
        old.get("entware_installer") != new.get("entware_installer")
        or old.get("entware_packages") != new.get("entware_packages")
    ):
        lines.append("Entware")
    return lines


def notes(old: dict[str, object] | None, new: dict[str, object], lines: list[str]) -> str:
    if old is None:
        text = ["Первая сборка.", "", "Источники: Entware, Flashkeen, HydraRoute."]
    else:
        text = ["Изменилось: " + ", ".join(lines) + "."]
    return "\n".join([*text, ""])


def main() -> None:
    status.say("Сверяю Flashkeen, HydraRoute и Entware")
    current = fingerprint()
    latest = latest_release()
    previous = previous_fingerprint(latest)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fingerprint.json").write_text(
        json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if previous is not None and canon(previous) == canon(current):
        status.say("Без изменений: релиз не нужен")
        set_output("publish", "false")
        return
    lines = [] if previous is None else changed_lines(previous, current)
    if previous is not None and not lines:
        status.say("Без изменений: релиз не нужен")
        set_output("publish", "false")
        return
    if published_today(latest):
        status.say("Релиз уже публиковался сегодня по Москве: лимит 1 релиз в сутки")
        set_output("publish", "false")
        return
    tag = next_tag()
    (OUT / "notes.md").write_text(notes(previous, current, lines), encoding="utf-8", newline="\n")
    (OUT / "plan.json").write_text(
        json.dumps({"tag": tag, "title": f"CF-Entware {tag}"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    status.say(f"Нужен релиз {tag}")
    for line in lines:
        status.say(line)
    set_output("publish", "true")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        status.fail(str(exc))
        status.dump_exc()
        raise SystemExit(1) from exc
