"""Оставить в списке релизов один выпуск на месяц, а старше года — один на год."""

from __future__ import annotations

import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import gh_api
import status

MSK = timezone(timedelta(hours=3))


def published(release: dict) -> datetime:
    raw = str(release.get("published_at") or release.get("created_at") or "")
    when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return when.astimezone(MSK)


def list_releases() -> list[dict]:
    found: list[dict] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{gh_api.repo()}/releases?per_page=100&page={page}"
        batch = gh_api.get_json(url)
        if not isinstance(batch, list) or not batch:
            break
        found.extend(item for item in batch if isinstance(item, dict) and not item.get("draft"))
        if len(batch) < 100:
            break
        page += 1
    return found


def keep_ids(releases: list[dict]) -> set[int]:
    if not releases:
        return set()
    ordered = sorted(releases, key=published, reverse=True)
    edge = datetime.now(MSK) - timedelta(days=365)
    kept: set[int] = {int(ordered[0]["id"])}
    month_best: dict[tuple[int, int], dict] = {}
    year_best: dict[int, dict] = {}
    for release in ordered:
        when = published(release)
        if when >= edge:
            key = (when.year, when.month)
            current = month_best.get(key)
            if current is None or when > published(current):
                month_best[key] = release
        else:
            current = year_best.get(when.year)
            if current is None or when > published(current):
                year_best[when.year] = release
    for release in (*month_best.values(), *year_best.values()):
        kept.add(int(release["id"]))
    return kept


def remove(release: dict) -> bool:
    repo = gh_api.repo()
    tag = str(release.get("tag_name") or "")
    name = tag or str(release.get("id"))
    ok = True
    try:
        gh_api.delete(f"https://api.github.com/repos/{repo}/releases/{release['id']}")
        print(f"удалён релиз {name}", flush=True)
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            print(f"не удалось удалить релиз {name}: {exc}", flush=True)
            ok = False
    if not tag:
        return ok
    quoted = urllib.parse.quote(tag, safe="")
    try:
        gh_api.delete(f"https://api.github.com/repos/{repo}/git/refs/tags/{quoted}")
        print(f"удалён тег {tag}", flush=True)
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc) and "HTTP 422" not in str(exc):
            print(f"не удалось удалить тег {tag}: {exc}", flush=True)
            ok = False
    return ok


def main() -> None:
    status.say("Проверяю список релизов")
    if not gh_api.token():
        raise SystemExit("Нет GITHUB_TOKEN, старые релизы не удалить")
    releases = list_releases()
    kept = keep_ids(releases)
    failed = False
    for release in releases:
        if int(release["id"]) in kept:
            print(f"остаётся {release.get('tag_name')}", flush=True)
            continue
        if not remove(release):
            failed = True
    if failed:
        raise SystemExit("Не все старые релизы удалось удалить")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        status.fail(str(exc))
        status.dump_exc()
        raise SystemExit(1) from exc
