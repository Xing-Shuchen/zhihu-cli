"""High-level HTML document renderer."""

from __future__ import annotations

from rich.console import Console

from .graphics import GraphicsRenderer
from .html_parser import HtmlParser
from .model import RenderOptions


class DocumentRenderer:
    def __init__(
        self,
        *,
        console: Console | None = None,
        parser: HtmlParser | None = None,
        graphics: GraphicsRenderer | None = None,
    ):
        self.console = console or Console()
        self.parser = parser or HtmlParser()
        self.graphics = graphics or GraphicsRenderer(console=self.console)

    def render(
        self,
        html: str,
        *,
        media: str | bool = "auto",
        formula: str | bool = "text",
        indent: str = "",
        is_tty: bool | None = None,
    ):
        if isinstance(media, bool):
            media = "auto" if media else "off"
        if isinstance(formula, bool):
            formula = "text" if formula else "off"
        document = self.parser.parse(html)
        options = RenderOptions(
            media=media,
            formula=formula,
            is_tty=is_tty,
            indent=indent,
        )
        self.graphics.render(document.blocks, options)
