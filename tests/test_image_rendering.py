"""Contract tests for safe Kitty image rendering."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from rich.console import Console

from zhihu_cli.commands.content import answer, pick
from zhihu_cli.rendering.graphics import GraphicsRenderer
from zhihu_cli.rendering.html_parser import HtmlParser
from zhihu_cli.rendering.kitty import KittyImageBackend
from zhihu_cli.rendering.media_fetcher import is_trusted_image_url
from zhihu_cli.rendering.model import (
    ImageBlock,
    ParagraphBlock,
    RenderOptions,
    TerminalCapabilities,
)


def test_parser_preserves_text_image_text_order():
    document = HtmlParser().parse(
        '<p>before<img src="https://pic.zhimg.com/photo.jpg" alt="photo">after</p>'
    )

    assert len(document.blocks) == 3
    assert isinstance(document.blocks[0], ParagraphBlock)
    assert isinstance(document.blocks[1], ImageBlock)
    assert isinstance(document.blocks[2], ParagraphBlock)
    assert "before" in document.blocks[0].segments[0].text
    assert "after" in document.blocks[2].segments[0].text


def test_parser_promotes_image_wrapped_in_a_link():
    document = HtmlParser().parse(
        '<p><a href="https://www.zhihu.com/photo">'
        '<img src="https://pic.zhimg.com/wrapped.jpg" alt="wrapped"></a></p>'
    )

    assert document.blocks == [
        ImageBlock(url="https://pic.zhimg.com/wrapped.jpg", alt="wrapped")
    ]


def test_parser_uses_data_actualsrc_before_src():
    document = HtmlParser().parse(
        '<img src="https://pic.zhimg.com/thumb.jpg" '
        'data-actualsrc="https://pic.zhimg.com/original.jpg">'
    )

    assert document.blocks == [ImageBlock(url="https://pic.zhimg.com/original.jpg")]


def test_parser_uses_last_srcset_candidate():
    document = HtmlParser().parse(
        '<img src="https://pic.zhimg.com/fallback.jpg" srcset="https://pic.zhimg.com/small.jpg 1x, '
        'https://pic.zhimg.com/large.jpg 2x">'
    )

    assert document.blocks == [ImageBlock(url="https://pic.zhimg.com/large.jpg")]


def test_trusted_url_matching_rejects_spoofed_domains():
    assert is_trusted_image_url("https://pic.zhimg.com/image.jpg")
    assert is_trusted_image_url("https://www.zhihu.com/image.jpg")
    assert not is_trusted_image_url("https://evil-zhimg.com/image.jpg")
    assert not is_trusted_image_url("https://zhimg.com.attacker.test/image.jpg")
    assert not is_trusted_image_url("http://pic.zhimg.com/image.jpg")


def test_third_party_image_is_not_fetched():
    output = io.StringIO()
    console = Console(file=output, width=80, color_system=None)
    fetcher = MagicMock()
    backend = MagicMock()
    renderer = GraphicsRenderer(
        console=console,
        media_fetcher=fetcher,
        image_backend=backend,
    )

    renderer.render(
        [ImageBlock(url="https://images.example.com/tracker.gif")],
        RenderOptions(media="auto", is_tty=True),
    )

    fetcher.fetch_image.assert_not_called()
    backend.capabilities.assert_not_called()
    assert "第三方图片，出于安全考虑未加载" in output.getvalue()


def test_media_off_does_not_probe_kitty():
    output = io.StringIO()
    backend = MagicMock()
    renderer = GraphicsRenderer(
        console=Console(file=output, width=80, color_system=None),
        image_backend=backend,
    )

    renderer.render(
        [ImageBlock(url="https://pic.zhimg.com/photo.jpg", alt="Photo")],
        RenderOptions(media="off", is_tty=True),
    )

    backend.capabilities.assert_not_called()
    assert "Photo" in output.getvalue()


def test_kitty_display_scales_width_without_height_limit(tmp_path: Path):
    image_path = tmp_path / "photo.gif"
    image_path.write_bytes(b"GIF89a")
    completed = MagicMock(returncode=0)

    with (
        patch("zhihu_cli.rendering.kitty._find_kitten", return_value="/usr/bin/kitten"),
        patch("zhihu_cli.rendering.kitty.subprocess.run", return_value=completed) as run,
    ):
        assert KittyImageBackend(is_tty=True).display(image_path)

    command = run.call_args.args[0]
    assert "--fit=width" in command
    assert "--scale-up=no" in command
    assert not any(argument.startswith("--place") for argument in command)
    assert "--loop=0" not in command


def test_backend_failure_warning_is_emitted_once():
    output = io.StringIO()
    backend = MagicMock()
    backend.capabilities.return_value = TerminalCapabilities(
        is_tty=True,
        supports_images=False,
        reason="tmux allow-passthrough 未开启",
    )
    renderer = GraphicsRenderer(
        console=Console(file=output, width=80, color_system=None),
        image_backend=backend,
    )

    renderer.render(
        [
            ImageBlock(url="https://pic.zhimg.com/one.jpg"),
            ImageBlock(url="https://pic.zhimg.com/two.jpg"),
        ],
        RenderOptions(media="auto", is_tty=True),
    )

    assert output.getvalue().count("tmux allow-passthrough 未开启") == 1


def test_answer_and_pick_expose_media_option():
    runner = CliRunner()

    assert "--media [auto|on|off]" in runner.invoke(answer, ["--help"]).output
    assert "--media [auto|on|off]" in runner.invoke(pick, ["--help"]).output
