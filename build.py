#!/usr/bin/env python3
"""Сборка установщиков Entware full_offline_app и base из официального архива."""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import status

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
DIST = ROOT / "dist"
RUNTIME = ROOT / "runtime"
APPS = ROOT / "apps"
UA = "Entware-builder/1.0"

ARCHES = {
    "aarch64": {
        "installer": "https://bin.entware.net/aarch64-k3.10/installer/aarch64-installer.tar.gz",
        "feed": "https://bin.entware.net/aarch64-k3.10",
        "mirrors": (
            "http://mirrors.bfsu.edu.cn/entware/aarch64-k3.10",
            "http://mirrors.nju.edu.cn/entware/aarch64-k3.10",
        ),
        "custom": "https://sw.ext.io/ent/installers/aarch64_installer_dropbear_custom_offline.tar.gz",
        "ipk_arch": "aarch64-3.10",
    },
    "mipsel": {
        "installer": "https://bin.entware.net/mipselsf-k3.4/installer/mipsel-installer.tar.gz",
        "feed": "https://bin.entware.net/mipselsf-k3.4",
        "mirrors": (
            "http://mirrors.bfsu.edu.cn/entware/mipselsf-k3.4",
            "http://mirrors.nju.edu.cn/entware/mipselsf-k3.4",
        ),
        "custom": "https://sw.ext.io/ent/installers/mipsel_installer_dropbear_custom_offline.tar.gz",
        "ipk_arch": "mipsel-3.4",
    },
    "mips": {
        "installer": "https://bin.entware.net/mipssf-k3.4/installer/mips-installer.tar.gz",
        "feed": "https://bin.entware.net/mipssf-k3.4",
        "mirrors": (
            "http://mirrors.bfsu.edu.cn/entware/mipssf-k3.4",
            "http://mirrors.nju.edu.cn/entware/mipssf-k3.4",
        ),
        "custom": "https://sw.ext.io/ent/installers/mips_installer_dropbear_custom_offline.tar.gz",
        "ipk_arch": "mips-3.4",
    },
}

# Список официального bin/install плюс curl, wget-ssl, ca-certificates.
SEED_PACKAGES = [
    "libgcc",
    "libc",
    "libpthread",
    "librt",
    "entware-release",
    "findutils",
    "grep",
    "ldconfig",
    "locales",
    "opkg",
    "zoneinfo-asia",
    "zoneinfo-europe",
    "opt-ndmsv2",
    "dropbear",
    "poorbox",
    "busybox",
    "curl",
    "wget-ssl",
    "ca-certificates",
]

SKIP_DEPS = {"kernel"}

FLASHKEEN_FEEDS = {
    "nfqws2-keenetic.conf": "src/gz nfqws2-keenetic https://nfqws.github.io/nfqws2-keenetic/all\n",
    "nfqws-keenetic-web.conf": "src/gz nfqws-keenetic-web https://nfqws.github.io/nfqws-keenetic-web/all\n",
    "usque-keenetic.conf": "src/gz usque-keenetic https://side-effect-tm.github.io/usque-keenetic/all\n",
}

LOCAL_INSTALL = r"""logger -t installer '[2/5] Установка основных пакетов из архива...'
_ipk_dir=/opt/installer-pkgs
_cf_entware_cleanup_installer_pkgs() {
    rm -f /tmp/entware-opkg.err 2>/dev/null || true
    rm -rf "$_ipk_dir" 2>/dev/null || true
}
if [ ! -f "$_ipk_dir/order" ]; then
	logger -t installer 'Critical error: Нет списка локальных пакетов.'
	logger -t installer 'Выход из установки.'
    _cf_entware_cleanup_installer_pkgs
	exit 1
fi
while IFS= read -r _ipk || [ -n "$_ipk" ]; do
	_ipk=$(printf '%s' "$_ipk" | tr -d '\r')
	[ -n "$_ipk" ] || continue
	if [ ! -f "$_ipk_dir/$_ipk" ]; then
		logger -t installer "Critical error: Нет файла пакета \"$_ipk\"."
		logger -t installer 'Выход из установки.'
        _cf_entware_cleanup_installer_pkgs
		exit 1
	fi
	logger -t installer "Info: Устанавливается пакет \"$_ipk\"..."
	if ! opkg install "$_ipk_dir/$_ipk" >/tmp/entware-opkg.err 2>&1; then
		logger -t installer "Critical error: Во время установки пакета \"$_ipk\" произошла ошибка."
		while IFS= read -r _line || [ -n "$_line" ]; do
			logger -t installer "$_line"
		done < /tmp/entware-opkg.err
		logger -t installer 'Выход из установки.'
        _cf_entware_cleanup_installer_pkgs
		exit 1
	fi
	logger -t installer "Info: Пакет \"$_ipk\" установлен."
done < "$_ipk_dir/order"
_cf_entware_cleanup_installer_pkgs

"""

AFTER_HOOK = (
    "if [ -x /opt/usr/local/sbin/entware-after.sh ]; then\n"
    "\t/opt/usr/local/sbin/entware-after.sh\n"
    "fi\n\n"
)


def http_get(url: str, timeout: float = 60) -> bytes:
    headers = {"User-Agent": UA}
    if url.startswith("https://api.github.com/"):
        tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
            headers["Accept"] = "application/vnd.github+json"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:240].replace("\n", " ")
        raise RuntimeError(f"HTTP {exc.code}: {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Сеть: {url}: {exc}") from exc


def cached_get(url: str, dest: Path, timeout: float = 60) -> bytes:
    if dest.is_file() and dest.stat().st_size > 0:
        return dest.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.part")
    try:
        data = http_get(url, timeout=timeout)
        tmp.write_bytes(data)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest.read_bytes()
    return data


def read_text(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8")


_flashkeen_layout: tuple[Path, Path, Path] | None = None


def flashkeen_layout() -> tuple[Path, Path, Path]:
    """Скрипт, каталог IPK и qbittorrent-setup.

    Локально это соседняя папка flashkeen. На GitHub Actions — каталог,
    который собрал fetch_flashkeen.py из релиза Flashkeen.
    """
    global _flashkeen_layout
    if _flashkeen_layout is not None:
        return _flashkeen_layout
    roots: list[Path] = []
    env = os.environ.get("FLASHKEEN_ROOT", "").strip()
    if env:
        roots.append(Path(env))
    roots.append(ROOT.parent / "flashkeen")
    roots.append(ROOT / ".flashkeen")
    seen: set[Path] = set()
    for root in roots:
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        tree_script = root / "online" / "flashkeen"
        tree_qbt = root / "installers" / "qbittorrent-setup"
        if tree_script.is_file() and tree_qbt.is_file():
            _flashkeen_layout = (tree_script, root / "offline" / "dist", tree_qbt)
            return _flashkeen_layout
        flat_script = root / "flashkeen"
        flat_qbt = root / "qbittorrent-setup"
        if flat_script.is_file() and flat_qbt.is_file():
            _flashkeen_layout = (flat_script, root, flat_qbt)
            return _flashkeen_layout
    raise SystemExit(
        "Не найден Flashkeen. Нужна папка flashkeen рядом с проектом или переменная FLASHKEEN_ROOT."
    )


def flashkeen_version() -> str:
    script, _, _ = flashkeen_layout()
    text = read_text(script)
    for line in text.splitlines():
        if line.startswith('FLASHKEEN_VERSION="') and line.endswith('"'):
            return line.split('"', 2)[1]
    raise SystemExit(f"Не найден FLASHKEEN_VERSION в {script}")


def parse_packages(raw: str, base_url: str) -> dict[str, dict[str, str]]:
    pkgs: dict[str, dict[str, str]] = {}
    cur: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            name = cur.get("Package")
            if name:
                cur["base_url"] = base_url
                pkgs[name] = cur
            cur = {}
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            cur[key.strip()] = val.strip()
    name = cur.get("Package")
    if name:
        cur["base_url"] = base_url
        pkgs[name] = cur
    return pkgs


def dep_names(depends: str) -> list[str]:
    names: list[str] = []
    for part in depends.split(","):
        token = part.strip()
        if not token:
            continue
        name = token.split()[0].split("(")[0].strip()
        if name and name not in SKIP_DEPS:
            names.append(name)
    return names


def load_index(arch: str) -> dict[str, dict[str, str]]:
    cfg = ARCHES[arch]
    bases = [cfg["feed"], *cfg["mirrors"]]
    last: Exception | None = None
    for base in bases:
        timeout = 25.0 if base == cfg["feed"] else 60.0
        try:
            digest = hashlib.sha256((base + "/Packages.gz").encode()).hexdigest()[:16]
            raw = cached_get(base + "/Packages.gz", CACHE / "index" / f"{digest}.gz", timeout=timeout)
            text = decode_packages(raw)
            print(f"  Packages.gz: {base}", flush=True)
            return parse_packages(text, base)
        except (RuntimeError, OSError, gzip.BadGzipFile) as exc:
            last = exc
            print(f"  Packages.gz не открылся: {base}")
    raise SystemExit(f"Нет Packages.gz для {arch}: {last}")


def adapt_seeds(index: dict[str, dict[str, str]], seeds: list[str]) -> list[str]:
    """Имена из официального bin/install. В текущем репозитории opt-ndmsv2 сменён на entware-opt."""
    out: list[str] = []
    for name in seeds:
        if name in index:
            out.append(name)
            continue
        if name == "opt-ndmsv2" and "entware-opt" in index:
            print("  opt-ndmsv2 в репозитории нет, беру entware-opt")
            out.append("entware-opt")
            continue
        if name == "poorbox":
            print("  poorbox в репозитории нет, остаётся busybox")
            continue
        print(f"  предупреждение: пакета {name} нет в индексе, пропускаю")
    return out


def resolve_closure(index: dict[str, dict[str, str]], seeds: list[str]) -> list[str]:
    wanted: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in seen or name in SKIP_DEPS:
            return
        if name not in index:
            print(f"  предупреждение: пакета {name} нет в индексе, пропускаю")
            return
        seen.add(name)
        for dep in dep_names(index[name].get("Depends", "")):
            add(dep)
        wanted.append(name)

    for seed in seeds:
        add(seed)
    return wanted


ARCH_APP_FEEDS = {
    "aarch64": {
        "hydra": "https://ground-zerro.github.io/release/keenetic/aarch64-k3.10",
        "awg": "http://repo.hoaxisr.ru/aarch64-k3.10",
        "feedly": "https://spatiumstas.github.io/feedly/aarch64-3.10",
        "smart": "https://raw.githubusercontent.com/snakelair/Keenetic/main/entware/aarch64-3.10",
    },
    "mipsel": {
        "hydra": "https://ground-zerro.github.io/release/keenetic/mipselsf-k3.4",
        "awg": "http://repo.hoaxisr.ru/mipsel-k3.4",
        "feedly": "https://spatiumstas.github.io/feedly/mipsel-3.4",
        "smart": "https://raw.githubusercontent.com/snakelair/Keenetic/main/entware/mipsel-3.4",
    },
    "mips": {
        "hydra": "https://ground-zerro.github.io/release/keenetic/mipssf-k3.4",
        "awg": "http://repo.hoaxisr.ru/mips-k3.4",
        "feedly": "https://spatiumstas.github.io/feedly/mips-3.4",
        "smart": "https://raw.githubusercontent.com/snakelair/Keenetic/main/entware/mips-3.4",
    },
}

SHARED_APP_FEEDS = {
    "nfqws2": "https://nfqws.github.io/nfqws2-keenetic/all",
    "nfqwsweb": "https://nfqws.github.io/nfqws-keenetic-web/all",
}

NFQWS_MENU_URL = "https://raw.githubusercontent.com/rndnaame/nfqws-menu/main/nfqws-menu.sh"


def decode_packages(raw: bytes) -> str:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def dep_groups(depends: str) -> list[list[str]]:
    groups: list[list[str]] = []
    for part in depends.split(","):
        alts: list[str] = []
        for alt in part.split("|"):
            token = alt.strip()
            if not token:
                continue
            name = token.split("(")[0].strip().split()[0]
            if name:
                alts.append(name)
        if alts:
            groups.append(alts)
    return groups


def resolve_pkg(index: dict[str, dict[str, str]], name: str) -> str | None:
    if name in index:
        return name
    found: list[str] = []
    for pkg, meta in index.items():
        for part in meta.get("Provides", "").split(","):
            token = part.strip().split("(")[0].strip()
            token = token.split()[0] if token else ""
            if token == name:
                found.append(pkg)
    if not found:
        return None
    found.sort(key=lambda pkg: (0 if pkg == name or pkg.startswith(name) else 1, len(pkg), pkg))
    return found[0]


def app_closure(index: dict[str, dict[str, str]], seeds: list[str]) -> list[str]:
    wanted: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in SKIP_DEPS:
            return
        resolved = resolve_pkg(index, name)
        if resolved is None:
            raise SystemExit(f"Нет пакета {name}")
        if resolved != name and resolved not in seen:
            print(f"  {name} -> {resolved}")
        if resolved in seen:
            return
        seen.add(resolved)
        for alts in dep_groups(index[resolved].get("Depends", "")):
            chosen: str | None = None
            for alt in alts:
                if alt in SKIP_DEPS or resolve_pkg(index, alt):
                    chosen = alt
                    break
            if chosen is None:
                raise SystemExit(f"Нет зависимости {alts} у {resolved}")
            add(chosen)
        wanted.append(resolved)

    for seed in seeds:
        add(seed)
    return wanted


def load_feed(url: str, cache_key: str) -> dict[str, dict[str, str]]:
    dest = CACHE / "feeds" / cache_key
    if dest.is_file() and dest.stat().st_size > 0:
        raw = dest.read_bytes()
    else:
        raw = None
        last: Exception | None = None
        for suffix in ("/Packages.gz", "/Packages"):
            try:
                raw = http_get(url.rstrip("/") + suffix, timeout=60)
                break
            except (RuntimeError, OSError) as exc:
                last = exc
        if not raw:
            raise SystemExit(f"Нет индекса {url}: {last}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    return parse_packages(decode_packages(raw), url.rstrip("/"))


def merge_app_index(arch: str, entware: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    merged = dict(entware)
    feeds = {**ARCH_APP_FEEDS[arch], **SHARED_APP_FEEDS}
    for key, url in feeds.items():
        cache_key = f"{key}.pkg" if key in SHARED_APP_FEEDS else f"{arch}-{key}.pkg"
        idx = load_feed(url, cache_key)
        added = 0
        for name, meta in idx.items():
            if name not in merged:
                merged[name] = meta
                added += 1
        print(f"  фид {key}: +{added}")
    return merged


def fetch_ipk(meta: dict[str, str]) -> tuple[str, bytes]:
    filename = Path(meta["Filename"]).name
    url = meta["base_url"].rstrip("/") + "/" + meta["Filename"].lstrip("/")
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    dest = CACHE / "apps" / digest / filename
    if not dest.is_file() or dest.stat().st_size == 0:
        print(f"  пакет {filename}", flush=True)
    return filename, cached_get(url, dest, timeout=180)


def emit_app(
    folder: str,
    seeds: list[str],
    index: dict[str, dict[str, str]],
    skip: set[str],
    order_name: str,
) -> tuple[list[tuple[str, bytes, int]], set[str]]:
    closure = app_closure(index, seeds)
    missing = [name for name in seeds if resolve_pkg(index, name) not in closure]
    if missing:
        raise SystemExit(f"{folder}: не собраны {missing}")
    seed_names = {resolve_pkg(index, name) for name in seeds}
    files: list[tuple[str, bytes, int]] = []
    lines: list[str] = []
    used: set[str] = set()
    vendored: set[str] = set()
    needed = [name for name in closure if name not in skip]
    blobs: dict[str, tuple[str, bytes]] = {}
    if needed:
        workers = min(8, len(needed))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for name, blob in zip(needed, pool.map(lambda item: fetch_ipk(index[item]), needed)):
                blobs[name] = blob
    for name in closure:
        if name in skip:
            continue
        filename, data = blobs[name]
        rel = filename if name in seed_names else f"deps/{filename}"
        if rel in used:
            raise SystemExit(f"{folder}: повтор файла {rel}")
        used.add(rel)
        vendored.add(name)
        lines.append(rel)
        files.append((f"Soft/{folder}/{rel}", data, 0o644))
    if not lines:
        raise SystemExit(f"{folder}: пустой список {order_name}")
    files.append((f"Soft/{folder}/{order_name}", ("\n".join(lines) + "\n").encode("utf-8"), 0o644))
    print(f"  {folder}/{order_name}: {len(lines)} пакетов")
    return files, vendored


def qbt_offline(arch: str) -> list[tuple[str, bytes, int]]:
    if arch == "aarch64":
        raw = http_get(
            "https://api.github.com/repos/userdocs/qbittorrent-nox-static/releases/latest",
            timeout=60,
        )
        data = json.loads(raw.decode("utf-8"))
        tag = str(data.get("tag_name") or "")
        version = tag[8:] if tag.startswith("release-") else tag
        version = version.split("_v", 1)[0]
        asset = None
        for item in data.get("assets") or []:
            name = str(item.get("name") or "")
            if name.startswith("aarch64") and name.endswith("qbittorrent-nox"):
                asset = item
                break
        if not asset:
            raise SystemExit(f"В релизе {tag} нет aarch64-qbittorrent-nox")
        asset_name = str(asset["name"])
        url = str(asset["browser_download_url"])
        dest = CACHE / "qbt" / asset_name
        blob = cached_get(url, dest, timeout=180)
    else:
        suf = "mipsel" if arch == "mipsel" else "mips"
        base = ARCHES[arch]["feed"].rstrip("/") + "/test"
        html = http_get(base + "/", timeout=60).decode("utf-8", "replace")
        names = re.findall(rf"qbittorrent-[0-9][^\"'<> ]*_{suf}\.tar\.gz", html)
        if not names:
            raise SystemExit(f"В {base} нет архива qBittorrent для {suf}")

        def ver_key(name: str) -> tuple[int, ...]:
            match = re.search(rf"qbittorrent-(.+?)_{suf}\.tar\.gz$", name)
            body = match.group(1) if match else name
            return tuple(int(part) for part in re.findall(r"\d+", body))

        asset_name = max(names, key=ver_key)
        match = re.search(rf"qbittorrent-(.+?)_{suf}\.tar\.gz$", asset_name)
        version = match.group(1) if match else asset_name
        url = base + "/" + asset_name
        dest = CACHE / "qbt" / asset_name
        blob = cached_get(url, dest, timeout=180)
    print(f"  qBittorrent {version} ({asset_name}, {len(blob)} байт)")
    root = "Soft/qbittorrent/offline"
    return [
        (f"{root}/version", (version + "\n").encode("utf-8"), 0o644),
        (f"{root}/asset", (asset_name + "\n").encode("utf-8"), 0o644),
        (f"{root}/{asset_name}", blob, 0o644),
    ]


def patch_qbt_setup(script: str) -> str:
    old_resolve = (
        '    qbt_ok "Архитектура: $QBT_ARCH"\n'
        "\n"
        '    qbt_info "Ищу последнюю версию..."\n'
        "    if ! resolve_latest; then\n"
        '        qbt_err "Не удалось определить последнюю версию для $QBT_ARCH"\n'
        "        exit 1\n"
        "    fi\n"
        '    qbt_ok "Доступно: qBittorrent $QBT_VERSION"\n'
        """    printf '  источник: %s\\n' "$QBT_SOURCE_URL"\n"""
    )
    new_resolve = (
        '    qbt_ok "Архитектура: $QBT_ARCH"\n'
        "\n"
        '    if [ -f /opt/Soft/qbittorrent/offline/version ]; then\n'
        "        QBT_VERSION=$(head -n 1 /opt/Soft/qbittorrent/offline/version | tr -d '\\r')\n"
        "        QBT_ASSET_NAME=$(head -n 1 /opt/Soft/qbittorrent/offline/asset | tr -d '\\r')\n"
        '        QBT_SOURCE_URL="offline"\n'
        '        qbt_ok "В архиве: qBittorrent $QBT_VERSION"\n'
        "    else\n"
        '        qbt_info "Ищу последнюю версию..."\n'
        "        if ! resolve_latest; then\n"
        '            qbt_err "Не удалось определить последнюю версию для $QBT_ARCH"\n'
        "            exit 1\n"
        "        fi\n"
        '        qbt_ok "Доступно: qBittorrent $QBT_VERSION"\n'
        """        printf '  источник: %s\\n' "$QBT_SOURCE_URL"\n"""
        "    fi\n"
    )
    old_download = (
        '    _dl="$WORK_DIR/download.bin"\n'
        "\n"
        '    download_file "$QBT_SOURCE_URL" "$_dl" || return 1\n'
    )
    new_download = (
        '    _dl="$WORK_DIR/download.bin"\n'
        "\n"
        '    _offline=""\n'
        "    for _cand in /opt/Soft/qbittorrent/offline/*; do\n"
        '        [ -f "$_cand" ] || continue\n'
        '        case "$(basename "$_cand")" in\n'
        "            version|asset) continue ;;\n"
        "        esac\n"
        "        _offline=$_cand\n"
        "        break\n"
        "    done\n"
        '    if [ -n "$_offline" ]; then\n'
        '        cp -f "$_offline" "$_dl" || return 1\n'
        "    else\n"
        '        download_file "$QBT_SOURCE_URL" "$_dl" || return 1\n'
        "    fi\n"
    )
    if old_resolve not in script or old_download not in script:
        raise SystemExit("Не удалось встроить локальный qBittorrent в установщик")
    return script.replace(old_resolve, new_resolve, 1).replace(old_download, new_download, 1)


def bundle_soft(
    arch: str,
    entware: dict[str, dict[str, str]],
    base_names: set[str],
) -> list[tuple[str, bytes, int]]:
    print("  программы full")
    index = merge_app_index(arch, entware)
    files: list[tuple[str, bytes, int]] = []
    hydra, _ = emit_app("hydraroute-neo", ["hrneo", "hrweb", "hrdns"], index, base_names, "order")
    awg, _ = emit_app("awg-manager", ["awg-manager"], index, base_names, "order")
    nfq, nfq_names = emit_app("nfqws2-keenetic", ["nfqws2-keenetic"], index, base_names, "order")
    web, _ = emit_app(
        "nfqws2-keenetic",
        ["nfqws-keenetic-web"],
        index,
        base_names | nfq_names,
        "web-order",
    )
    static, _ = emit_app("web4static", ["web4static"], index, base_names, "order")
    photo, _ = emit_app("smart-photo", ["smart-photo"], index, base_names, "order")
    files.extend(hydra)
    files.extend(awg)
    files.extend(nfq)
    files.extend(web)
    files.extend(static)
    files.extend(photo)
    menu = cached_get(NFQWS_MENU_URL, CACHE / "apps" / "nfqws-menu.sh", timeout=60)
    menu = menu.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    files.append(("Soft/nfqws-menu/nfqws-menu.sh", menu, 0o755))
    files.extend(qbt_offline(arch))
    return files


def download_ipks(arch: str, names: list[str], index: dict[str, dict[str, str]]) -> list[tuple[str, Path]]:
    dest_dir = CACHE / "ipk" / arch
    dest_dir.mkdir(parents=True, exist_ok=True)

    def one(name: str) -> tuple[str, Path]:
        meta = index[name]
        filename = Path(meta["Filename"]).name
        dest = dest_dir / filename
        package_path = meta["Filename"].lstrip("/")
        bases = (meta["base_url"], ARCHES[arch]["feed"], *ARCHES[arch]["mirrors"])
        urls = list(dict.fromkeys(base.rstrip("/") + "/" + package_path for base in bases))
        if not dest.is_file() or dest.stat().st_size == 0:
            print(f"  пакет {filename}", flush=True)
        last_error: RuntimeError | None = None
        for url in urls:
            try:
                cached_get(url, dest)
                break
            except RuntimeError as exc:
                last_error = exc
                print(f"  источник пакета недоступен, пробую следующий: {url}", flush=True)
        else:
            if last_error is not None:
                raise last_error
            raise RuntimeError(f"Нет источников для пакета {filename}")
        return filename, dest

    workers = min(8, max(1, len(names)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, names))


def src_names(text: str) -> set[str]:
    names: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in ("src/gz", "src"):
            names.add(parts[1])
    return names


def custom_feed_files(arch: str) -> dict[str, bytes]:
    cfg = ARCHES[arch]
    print(f"  фиды из {cfg['custom']}")
    blob = cached_get(cfg["custom"], CACHE / "custom" / f"{arch}.tar.gz", timeout=120)
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name.lstrip("./")
            if not name.startswith("etc/opkg/") or not name.endswith(".conf"):
                continue
            if not member.isfile():
                continue
            base = name.rsplit("/", 1)[-1]
            data = tar.extractfile(member)
            if data is None:
                continue
            files[base] = data.read().replace(b"\r\n", b"\n")
    if not files:
        raise SystemExit(f"В кастомном архиве {arch} нет etc/opkg/*.conf")
    known: set[str] = set()
    for body in files.values():
        known |= src_names(body.decode("utf-8", "replace"))
    for fname, text in FLASHKEEN_FEEDS.items():
        names = src_names(text)
        if names & known:
            continue
        files[fname] = text.encode("utf-8")
        known |= names
        print(f"  добавлен фид Flashkeen: {fname}")
    return files


def patch_install(script: str) -> str:
    marker = "logger -t installer '[2/5]"
    start = script.find(marker)
    end = script.find("logger -t installer 'Info: Установка пакетов прошла успешно!'")
    if start < 0 or end < 0 or end < start:
        raise SystemExit("Не найден блок установки пакетов в bin/install")
    comment = "# opkg update\n"
    comment_at = script.rfind(comment, 0, start)
    if comment_at >= 0 and start - comment_at < 80:
        start = comment_at
    script = script[:start] + LOCAL_INSTALL + script[end:]
    needle = "rm /opt/etc/init.d/doinstall\n"
    if needle not in script:
        raise SystemExit("Не найден rm doinstall в bin/install")
    if "entware-after.sh" not in script:
        script = script.replace(needle, AFTER_HOOK + needle, 1)
    if "installer-pkgs" not in script:
        raise SystemExit("Патч bin/install не применился")
    return script


def member_name(member: tarfile.TarInfo) -> str:
    return member.name.lstrip("./").rstrip("/")


def add_bytes(tar: tarfile.TarFile, arcname: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mode = mode
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    tar.addfile(info, io.BytesIO(data))


def add_dir(tar: tarfile.TarFile, arcname: str) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    tar.addfile(info)


def ensure_dirs(tar: tarfile.TarFile, arcname: str, seen: set[str]) -> None:
    parts = [p for p in arcname.split("/") if p]
    acc = ""
    for part in parts[:-1]:
        acc = f"{acc}/{part}" if acc else part
        if acc not in seen:
            seen.add(acc)
            add_dir(tar, acc)


def file_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def extra_files(
    arch: str,
    variant: str,
    ipks: list[tuple[str, Path]],
    feeds: dict[str, bytes],
    app_files: list[tuple[str, bytes, int]],
) -> list[tuple[str, bytes, int]]:
    files: list[tuple[str, bytes, int]] = []
    order = "\n".join(name for name, _ in ipks) + "\n"
    files.append(("installer-pkgs/order", order.encode("utf-8"), 0o644))
    for name, path in ipks:
        files.append((f"installer-pkgs/{name}", path.read_bytes(), 0o644))
    for fname, body in feeds.items():
        files.append((f"etc/opkg/{fname}", body if body.endswith(b"\n") else body + b"\n", 0o644))

    if variant == "full":
        files.append(("usr/local/sbin/entware-after.sh", file_bytes(RUNTIME / "entware-after-full.sh"), 0o755))
        files.append(("usr/local/sbin/entware-login.sh", file_bytes(RUNTIME / "entware-login-full.sh"), 0o755))
        files.append(("usr/local/sbin/entware-remove-soft.sh", file_bytes(RUNTIME / "entware-remove-soft.sh"), 0o755))
        files.append(("usr/local/sbin/soft-index.sh", file_bytes(RUNTIME / "soft-index.sh"), 0o755))
        files.append(("Soft/menu.sh", file_bytes(RUNTIME / "menu.sh"), 0o755))
        files.append(("Soft/install-local.sh", file_bytes(RUNTIME / "install-local.sh"), 0o755))
        files.append(("Soft/Soft list.txt", file_bytes(ROOT / "Soft-list.txt"), 0o644))
        for app in sorted(p for p in APPS.iterdir() if p.is_dir()):
            install = app / "install.sh"
            if install.is_file():
                files.append((f"Soft/{app.name}/install.sh", file_bytes(install), 0o755))
        _, dist, qbt = flashkeen_layout()
        files.append(("Soft/qbittorrent/install.sh", patch_qbt_setup(file_bytes(qbt).decode("utf-8")).encode("utf-8"), 0o755))
        files.extend(app_files)
        ipk = dist / f"flashkeen_{flashkeen_version()}_{ARCHES[arch]['ipk_arch']}.ipk"
        if not ipk.is_file():
            raise SystemExit(f"Нет IPK Flashkeen: {ipk}")
        files.append((f"Soft/flashkeen/{ipk.name}", ipk.read_bytes(), 0o644))
    else:
        files.append(("usr/local/sbin/entware-after.sh", file_bytes(RUNTIME / "entware-after-base.sh"), 0o755))
        files.append(("usr/local/sbin/entware-login.sh", file_bytes(RUNTIME / "entware-login-base.sh"), 0o755))
        _, dist, _ = flashkeen_layout()
        ipk = dist / f"flashkeen_{flashkeen_version()}_{ARCHES[arch]['ipk_arch']}.ipk"
        if not ipk.is_file():
            raise SystemExit(f"Нет IPK Flashkeen: {ipk}")
        files.append((f"usr/local/flashkeen/{ipk.name}", ipk.read_bytes(), 0o644))
    return files


def fast_gzip() -> bool:
    try:
        from isal import igzip  # noqa: F401

        return True
    except ImportError:
        return False


def ensure_fast_gzip() -> str:
    if fast_gzip():
        return "igzip"
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "isal"], check=False)
    return "igzip" if fast_gzip() else "gzip"


def gzip_compress(data: bytes) -> bytes:
    if fast_gzip():
        from isal import igzip

        return igzip.compress(data, compresslevel=1)
    return gzip.compress(data, compresslevel=1)


def archive_path(arch: str, variant: str) -> Path:
    label = "full" if variant == "full" else "base"
    return DIST / f"{arch}-{label}-installer.tar.gz"


def build_one(
    arch: str,
    variant: str,
    official: Path,
    ipks: list[tuple[str, Path]],
    feeds: dict[str, bytes],
    app_files: list[tuple[str, bytes, int]],
) -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    out_path = archive_path(arch, variant)
    print(f"  архив {out_path.name}", flush=True)
    extras = extra_files(arch, variant, ipks, feeds, app_files if variant == "full" else [])
    seen_dirs: set[str] = set()
    tar_buf = io.BytesIO()
    with tarfile.open(official, "r:gz") as src, tarfile.open(fileobj=tar_buf, mode="w|") as dst:
        replaced = False
        for member in src.getmembers():
            if member.isdir():
                seen_dirs.add(member_name(member))
            name = member_name(member)
            if name == "bin/install" and member.isfile():
                raw = src.extractfile(member)
                if raw is None:
                    raise SystemExit("Пустой bin/install")
                script = raw.read().replace(b"\r\n", b"\n").decode("utf-8")
                patched = patch_install(script).encode("utf-8")
                add_bytes(dst, "bin/install", patched, 0o755)
                replaced = True
                continue
            if member.isfile() or member.islnk():
                extracted = src.extractfile(member) if member.isfile() else None
                dst.addfile(copy.copy(member), extracted)
            else:
                dst.addfile(copy.copy(member))
        if not replaced:
            raise SystemExit(f"В официальном архиве {arch} нет bin/install")
        for arcname, data, mode in extras:
            ensure_dirs(dst, arcname, seen_dirs)
            add_bytes(dst, arcname, data, mode)
    out_path.write_bytes(gzip_compress(tar_buf.getvalue()))
    verify(out_path, variant)


def verify(path: Path, variant: str) -> None:
    want = {"bin/install", "etc/opkg.conf"}
    if variant == "full":
        want |= {
            "Soft/hydraroute-neo/install.sh",
            "Soft/z2k/install.sh",
            "Soft/qbittorrent/install.sh",
            "Soft/usque/install.sh",
        }
    names: set[str] = set()
    files: dict[str, bytes] = {}
    with tarfile.open(path, "r|gz") as tar:
        for member in tar:
            name = member_name(member)
            names.add(name)
            if name in want and member.isfile():
                extracted = tar.extractfile(member)
                if extracted is not None:
                    files[name] = extracted.read()
    if "bin/install" not in files or "etc/opkg.conf" not in files:
        raise SystemExit(f"{path.name}: не читаются bin/install или opkg.conf")
    text = files["bin/install"].decode("utf-8", "replace")
    opkg_conf = files["etc/opkg.conf"].decode("utf-8", "replace")
    hydra_text = files.get("Soft/hydraroute-neo/install.sh", b"").decode("utf-8", "replace")
    z2k_text = files.get("Soft/z2k/install.sh", b"").decode("utf-8", "replace")
    qbt_text = files.get("Soft/qbittorrent/install.sh", b"").decode("utf-8", "replace")
    usque_text = files.get("Soft/usque/install.sh", b"").decode("utf-8", "replace")
    need = {
        "bin/install",
        "etc/opkg.conf",
        "installer-pkgs/order",
        "usr/local/sbin/entware-after.sh",
        "usr/local/sbin/entware-login.sh",
        "etc/opkg/feedly.conf",
        "etc/opkg/nfqws2-keenetic.conf",
    }
    if variant == "full":
        need |= {
            "Soft/menu.sh",
            "Soft/install-local.sh",
            "Soft/Soft list.txt",
            "Soft/qbittorrent/install.sh",
            "Soft/qbittorrent/offline/version",
            "Soft/hydraroute-neo/order",
            "Soft/awg-manager/order",
            "Soft/nfqws2-keenetic/order",
            "Soft/nfqws2-keenetic/web-order",
            "Soft/nfqws-menu/nfqws-menu.sh",
            "Soft/web4static/order",
            "Soft/smart-photo/order",
            "Soft/usque/install.sh",
            "Soft/z2k/install.sh",
            "usr/local/sbin/entware-remove-soft.sh",
        }
    else:
        if any(n.startswith("Soft/") for n in names):
            raise SystemExit(f"В base попала папка Soft: {path}")
    missing = sorted(n for n in need if n not in names)
    if missing:
        raise SystemExit(f"{path.name}: нет {missing}")
    if "installer-pkgs" not in text:
        raise SystemExit(f"{path.name}: bin/install без локальных пакетов")
    head = text.split("Установка пакетов прошла успешно", 1)[0]
    if "opkg update >/dev/null" in head:
        raise SystemExit(f"{path.name}: в шаге установки остался opkg update")
    if "src/gz entware " not in opkg_conf or "src/gz keendev " not in opkg_conf:
        raise SystemExit(f"{path.name}: официальные фиды в opkg.conf изменены")
    if variant == "full":
        if "soft_install_order" not in hydra_text or "zerrolabs" in hydra_text or "curl " in hydra_text:
            raise SystemExit(f"{path.name}: HydraRoute всё ещё качается из сети")
        if "z2k.sh" not in z2k_text:
            raise SystemExit(f"{path.name}: установщик z2k изменён")
        if "offline/version" not in qbt_text:
            raise SystemExit(f"{path.name}: qBittorrent без локального файла")
        if "opkg install usque-keenetic" not in usque_text:
            raise SystemExit(f"{path.name}: Usque больше не ставится из сети")
        if not any(n.startswith("Soft/hydraroute-neo/hrneo_") and n.endswith(".ipk") for n in names):
            raise SystemExit(f"{path.name}: нет пакета hrneo")
        if not any(n.startswith("Soft/awg-manager/awg-manager_") and n.endswith(".ipk") for n in names):
            raise SystemExit(f"{path.name}: нет пакета awg-manager")
        if any(n.startswith("Soft/usque/") and n.endswith(".ipk") for n in names):
            raise SystemExit(f"{path.name}: Usque попал в архив")
    print(f"  проверен {path.name}", flush=True)


def official_tar(arch: str) -> Path:
    cfg = ARCHES[arch]
    dest = CACHE / "official" / f"{arch}-installer.tar.gz"
    print(f"  официальный архив {cfg['installer']}", flush=True)
    cached_get(cfg["installer"], dest, timeout=120)
    return dest


def build_job(job: tuple[str, str]) -> str:
    arch, variant = job
    title = f"{arch} {variant}"
    status.group(title)
    try:
        print(f"шаг: индекс Entware {arch}", flush=True)
        index = load_index(arch)
        print(f"шаг: пакеты Entware {arch}", flush=True)
        names = resolve_closure(index, adapt_seeds(index, SEED_PACKAGES))
        ipks = download_ipks(arch, names, index)
        if variant == "full":
            print(f"шаг: программы full {arch}", flush=True)
            app_files = bundle_soft(arch, index, set(names))
        else:
            app_files = []
        print(f"шаг: фиды {arch}", flush=True)
        feeds = custom_feed_files(arch)
        print(f"шаг: официальный установщик {arch}", flush=True)
        official = official_tar(arch)
        print(f"шаг: упаковка {title}", flush=True)
        build_one(arch, variant, official, ipks, feeds, app_files)
        out = archive_path(arch, variant)
        line = f"{title}: {out} ({out.stat().st_size} байт)"
        print(f"готово {line}", flush=True)
        return line
    except Exception:
        status.fail(f"упало на {title}")
        status.dump_exc()
        raise
    finally:
        status.endgroup()


def main() -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    version = flashkeen_version()
    jobs = [(arch, variant) for arch in ("aarch64", "mipsel", "mips") for variant in ("full", "base")]
    workers = min(len(jobs), os.cpu_count() or 1)
    gzip_kind = ensure_fast_gzip()
    status.say(f"Flashkeen {version}, gzip {gzip_kind}, ядер {workers}")
    DIST.mkdir(parents=True, exist_ok=True)
    for leftover in (DIST / "full_offline_app", DIST / "base"):
        if leftover.is_dir():
            shutil.rmtree(leftover)
    lines: list[str] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(build_job, job): job for job in jobs}
        for future in as_completed(pending):
            job = pending[future]
            title = f"{job[0]} {job[1]}"
            try:
                lines.append(future.result())
            except Exception as exc:
                status.fail(f"архив {title} не собрался: {exc}")
                raise SystemExit(1) from exc
    status.say("Все шесть архивов собраны")
    for line in lines:
        print(line, flush=True)
    open_dist()


def open_dist() -> None:
    if os.name != "nt":
        return
    try:
        os.startfile(DIST)  # type: ignore[attr-defined]
    except OSError as exc:
        print(f"Не удалось открыть {DIST}: {exc}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        status.dump_exc()
        raise SystemExit(1)
