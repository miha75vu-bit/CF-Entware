"""Решать, нужен ли новый релиз CF-Entware.

Релиз создаётся, только если с прошлой сборки изменилось одно из трёх:
Flashkeen, HydraRoute (hrneo, hrweb, hrdns) или базовый набор Entware,
который кладётся в архив. Отдельного релиза раз в месяц нет.
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
MARKER = "<!-- cf-sources"
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


def parse_marker(body: str) -> dict[str, object] | None:
    start = body.find(MARKER)
    if start < 0:
        return None
    start = body.find("\n", start)
    end = body.find("\n-->", start)
    if start < 0 or end < 0:
        return None
    try:
        data = json.loads(body[start:end])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def previous_fingerprint() -> dict[str, object] | None:
    url = f"https://api.github.com/repos/{gh_api.repo()}/releases/latest"
    try:
        release = gh_api.get_json(url)
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    if not isinstance(release, dict):
        return None
    for asset in release.get("assets") or []:
        if asset.get("name") != "fingerprint.json":
            continue
        raw = gh_api.download(str(asset["browser_download_url"]))
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict):
            return data
    return parse_marker(str(release.get("body") or ""))


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
        lines.append(f"Flashkeen: {old.get('flashkeen')} → {new.get('flashkeen')}")

    old_hydra = old.get("hydra") if isinstance(old.get("hydra"), dict) else {}
    new_hydra = new.get("hydra") if isinstance(new.get("hydra"), dict) else {}
    for arch in ("aarch64", "mipsel", "mips"):
        before = old_hydra.get(arch) if isinstance(old_hydra, dict) else None
        after = new_hydra.get(arch) if isinstance(new_hydra, dict) else None
        before = before if isinstance(before, dict) else {}
        after = after if isinstance(after, dict) else {}
        bits = [
            f"{name} {before.get(name)} → {after.get(name)}"
            for name in HYDRA_NAMES
            if before.get(name) != after.get(name)
        ]
        if bits:
            lines.append(f"HydraRoute {arch}: " + ", ".join(bits))

    old_inst = old.get("entware_installer") if isinstance(old.get("entware_installer"), dict) else {}
    new_inst = new.get("entware_installer") if isinstance(new.get("entware_installer"), dict) else {}
    old_pkgs = old.get("entware_packages") if isinstance(old.get("entware_packages"), dict) else {}
    new_pkgs = new.get("entware_packages") if isinstance(new.get("entware_packages"), dict) else {}
    for arch in ("aarch64", "mipsel", "mips"):
        if old_inst.get(arch) != new_inst.get(arch):
            lines.append(f"Entware {arch}: обновился официальный установщик")
        before = old_pkgs.get(arch) if isinstance(old_pkgs, dict) else None
        after = new_pkgs.get(arch) if isinstance(new_pkgs, dict) else None
        before = before if isinstance(before, dict) else {}
        after = after if isinstance(after, dict) else {}
        names = sorted(set(before) | set(after))
        changed = [name for name in names if before.get(name) != after.get(name)]
        if not changed:
            continue
        shown = ", ".join(f"{name} {before.get(name, 'нет')} → {after.get(name, 'нет')}" for name in changed[:6])
        if len(changed) > 6:
            shown += f" и ещё {len(changed) - 6}"
        lines.append(f"Entware {arch}: {shown}")
    return lines


def notes(old: dict[str, object] | None, new: dict[str, object], lines: list[str]) -> str:
    if old is None:
        hydra = new.get("hydra")
        aarch64 = hydra.get("aarch64") if isinstance(hydra, dict) else None
        aarch64 = aarch64 if isinstance(aarch64, dict) else {}
        parts = [f"{name} {aarch64.get(name)}" for name in HYDRA_NAMES]
        text = [
            "Первая сборка.",
            "",
            f"Flashkeen: {new.get('flashkeen')}",
            "HydraRoute: " + ", ".join(parts),
        ]
    else:
        text = ["Обновилось:", "", *[f"- {line}" for line in lines]]
    text.extend(["", MARKER, json.dumps(new, ensure_ascii=False, sort_keys=True, indent=2), "-->", ""])
    return "\n".join(text)


def main() -> None:
    status.say("Сверяю Flashkeen, HydraRoute и Entware")
    current = fingerprint()
    previous = previous_fingerprint()
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
