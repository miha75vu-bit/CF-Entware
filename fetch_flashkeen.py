"""Скачать последний релиз Flashkeen: скрипт, три IPK и qbittorrent-setup из скрипта."""

from __future__ import annotations

import sys
from pathlib import Path

import gh_api
import status

ROOT = Path(__file__).resolve().parent
DEST = ROOT / ".flashkeen"
FLASHKEEN_REPO = "miha75vu-bit/Flashkeen"
IPK_ARCHES = ("aarch64-3.10", "mipsel-3.4", "mips-3.4")
QBT_BEGIN = "<<'FLASHKEEN_EMBEDDED_QBT'\n"
QBT_END = "\nFLASHKEEN_EMBEDDED_QBT\n"


def version_of(text: str) -> str:
    for line in text.splitlines():
        if line.startswith('FLASHKEEN_VERSION="') and line.endswith('"'):
            return line.split('"', 2)[1]
    raise SystemExit("В скачанном flashkeen нет FLASHKEEN_VERSION")


def extract_qbt(text: str) -> str:
    start = text.find(QBT_BEGIN)
    if start < 0:
        raise SystemExit("В релизе Flashkeen нет встроенного qbittorrent-setup")
    start += len(QBT_BEGIN)
    end = text.find(QBT_END, start)
    if end < 0:
        raise SystemExit("В релизе Flashkeen оборван qbittorrent-setup")
    body = text[start:end]
    if not body.endswith("\n"):
        body += "\n"
    return body


def main() -> None:
    url = f"https://api.github.com/repos/{FLASHKEEN_REPO}/releases/latest"
    release = gh_api.get_json(url)
    if not isinstance(release, dict):
        raise SystemExit("GitHub не отдал релиз Flashkeen")
    assets = {str(item.get("name")): item for item in release.get("assets") or []}
    script_asset = assets.get("flashkeen")
    if not script_asset:
        raise SystemExit(f"В релизе {release.get('tag_name')} нет файла flashkeen")
    status.say(f"Flashkeen {release.get('tag_name')}")
    script = gh_api.download(str(script_asset["browser_download_url"]))
    text = script.replace(b"\r\n", b"\n").replace(b"\r", b"\n").decode("utf-8")
    version = version_of(text)
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "flashkeen").write_bytes(text.encode("utf-8"))
    (DEST / "qbittorrent-setup").write_text(extract_qbt(text), encoding="utf-8", newline="\n")
    for arch in IPK_ARCHES:
        name = f"flashkeen_{version}_{arch}.ipk"
        asset = assets.get(name)
        if not asset:
            raise SystemExit(f"В релизе Flashkeen нет {name}")
        print(f"  {name}", flush=True)
        (DEST / name).write_bytes(gh_api.download(str(asset["browser_download_url"])))
    status.say(f"Flashkeen скачан в {DEST}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        status.fail(str(exc))
        status.dump_exc()
        raise SystemExit(1) from exc
