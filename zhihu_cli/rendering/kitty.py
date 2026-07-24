"""Kitty graphics backend implemented through ``kitten icat``."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .model import TerminalCapabilities


def _find_kitten() -> str | None:
    return shutil.which("kitten")


def _tmux_passthrough_enabled() -> bool:
    if not os.environ.get("TMUX"):
        return True
    for command in (
        ["tmux", "show-options", "-p", "-v", "allow-passthrough"],
        ["tmux", "show-options", "-g", "-v", "allow-passthrough"],
    ):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        value = result.stdout.strip().lower()
        if result.returncode == 0 and value:
            return value in {"on", "all"}
    return False


class KittyImageBackend:
    """Detect Kitty support and display cached image files."""

    _capability_cache: TerminalCapabilities | None = None

    def __init__(self, *, is_tty: bool | None = None):
        self.is_tty = is_tty

    @classmethod
    def clear_cache(cls):
        cls._capability_cache = None

    def capabilities(self) -> TerminalCapabilities:
        if self.__class__._capability_cache is not None:
            return self.__class__._capability_cache

        is_tty = sys.stdout.isatty() if self.is_tty is None else self.is_tty
        if not is_tty:
            caps = TerminalCapabilities(False, False, reason="输出不是交互式终端")
            self.__class__._capability_cache = caps
            return caps

        kitten = _find_kitten()
        if not kitten:
            caps = TerminalCapabilities(True, False, reason="未找到 kitten 命令")
            self.__class__._capability_cache = caps
            return caps

        if not _tmux_passthrough_enabled():
            caps = TerminalCapabilities(
                True,
                False,
                reason="tmux allow-passthrough 未开启",
            )
            self.__class__._capability_cache = caps
            return caps

        try:
            result = subprocess.run(
                [
                    kitten,
                    "icat",
                    "--detect-support",
                    "--detection-timeout=2",
                    "--stdin=no",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None

        if result is not None and result.returncode == 0:
            caps = TerminalCapabilities(True, True, backend_name="kitty")
        else:
            caps = TerminalCapabilities(True, False, reason="终端不支持 Kitty 图片协议")
        self.__class__._capability_cache = caps
        return caps

    def display(self, path: Path) -> bool:
        if not path.is_file():
            return False
        kitten = _find_kitten()
        if not kitten:
            return False
        try:
            result = subprocess.run(
                [
                    kitten,
                    "icat",
                    "--stdin=no",
                    "--align=left",
                    "--fit=width",
                    "--scale-up=no",
                    "--passthrough=detect",
                    str(path),
                ],
                check=False,
            )
        except OSError:
            return False
        return result.returncode == 0
