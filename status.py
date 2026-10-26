"""Текущий шаг сборки: в лог GitHub и в сводку запуска."""

from __future__ import annotations

import os
import sys
import traceback


def say(text: str) -> None:
    print(text, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"- {text}\n")


def group(title: str) -> None:
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::group::{title}", flush=True)
    else:
        print(title, flush=True)


def endgroup() -> None:
    if os.environ.get("GITHUB_ACTIONS"):
        print("::endgroup::", flush=True)


def fail(text: str) -> None:
    print(text, file=sys.stderr, flush=True)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error::{text}", flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"\n**Ошибка:** {text}\n")


def dump_exc() -> None:
    text = traceback.format_exc()
    print(text, file=sys.stderr, flush=True)
    if os.environ.get("GITHUB_ACTIONS"):
        last = text.strip().splitlines()[-1] if text.strip() else "ошибка"
        print(f"::error::{last}", flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n```\n")
            handle.write(text)
            handle.write("```\n")
