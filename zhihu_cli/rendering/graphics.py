"""Render semantic document blocks with Rich and Kitty graphics."""

from __future__ import annotations

from collections.abc import Iterable

from rich import box
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.padding import Padding
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .kitty import KittyImageBackend
from .media_fetcher import MediaFetcher, is_trusted_image_url
from .model import (
    Block,
    BlockquoteBlock,
    CodeBlock,
    FormulaBlock,
    HeadingBlock,
    HorizontalRule,
    ImageBlock,
    InlineFormulaSegment,
    ListBlock,
    ParagraphBlock,
    RenderOptions,
    TableBlock,
    TextSegment,
)


class GraphicsRenderer:
    """Render an ordered sequence of document blocks."""

    def __init__(
        self,
        *,
        console: Console | None = None,
        media_fetcher: MediaFetcher | None = None,
        image_backend: KittyImageBackend | None = None,
    ):
        self.console = console or Console()
        self.media_fetcher = media_fetcher
        self.image_backend = image_backend
        self._warned_backend = False

    def render(self, blocks: Iterable[Block], options: RenderOptions):
        for block in blocks:
            self._render_block(block, options)

    def _render_block(self, block: Block, options: RenderOptions):
        if isinstance(block, ParagraphBlock):
            self._print(self._segments_text(block.segments, options), options)
        elif isinstance(block, HeadingBlock):
            text = self._segments_text(block.segments, options)
            text.stylize("bold")
            self._print(text, options)
        elif isinstance(block, CodeBlock):
            renderable = Syntax(
                block.code,
                block.language or "text",
                theme="monokai",
                line_numbers=False,
                word_wrap=True,
            )
            self._print(renderable, options)
        elif isinstance(block, BlockquoteBlock):
            quote = Text()
            self._append_plain_blocks(quote, block.blocks, options)
            self._print(Panel(quote, border_style="dim", padding=(1, 2)), options)
        elif isinstance(block, ListBlock):
            self._render_list(block, options)
        elif isinstance(block, TableBlock):
            self._print(self._rich_table(block), options)
        elif isinstance(block, HorizontalRule):
            self._print(Text("─" * 50, style="dim"), options)
        elif isinstance(block, FormulaBlock):
            if options.formula == "text":
                self._print(Text(block.tex), options)
        elif isinstance(block, ImageBlock):
            self._render_image(block, options)

    def _render_image(self, block: ImageBlock, options: RenderOptions):
        if not is_trusted_image_url(block.url):
            self._print(
                Text(f"第三方图片，出于安全考虑未加载：{block.url}", style="yellow"),
                options,
            )
            return

        if options.media == "off":
            self._print(self._image_fallback(block), options)
            return

        backend = self.image_backend or KittyImageBackend(is_tty=options.is_tty)
        self.image_backend = backend
        capabilities = backend.capabilities()
        if not capabilities.supports_images:
            if capabilities.is_tty and not self._warned_backend:
                reason = capabilities.reason or "终端不支持图片"
                self.console.print(f"[warning]![/warning] {rich_escape(reason)}，已使用文本回退")
                self._warned_backend = True
            self._print(self._image_fallback(block), options)
            return

        fetcher = self.media_fetcher or MediaFetcher()
        self.media_fetcher = fetcher
        path = fetcher.fetch_image(block.url)
        if path is None:
            reason = fetcher.last_error or "图片加载失败"
            self._print(Text(f"{reason}：{block.url}", style="yellow"), options)
            return

        if not backend.display(path):
            if not self._warned_backend:
                self.console.print("[warning]![/warning] Kitty 图片显示失败，已使用文本回退")
                self._warned_backend = True
            self._print(self._image_fallback(block), options)
            return

        if block.caption:
            self._print(Text(block.caption, style="dim italic"), options)

    @staticmethod
    def _image_fallback(block: ImageBlock) -> Text:
        label = block.alt or block.caption or "图片"
        return Text(f"[图片：{label}] {block.url}")

    def _segments_text(self, segments, options: RenderOptions) -> Text:
        result = Text()
        for segment in segments:
            if isinstance(segment, TextSegment):
                result.append(Text.from_markup(segment.text))
            elif isinstance(segment, InlineFormulaSegment) and options.formula == "text":
                result.append(f"${segment.tex}$", style="italic")
        return result

    def _render_list(self, block: ListBlock, options: RenderOptions):
        for index, item in enumerate(block.items, 1):
            prefix = f"{index}. " if block.ordered else "• "
            line = Text(prefix)
            self._append_plain_blocks(line, item, options)
            self._print(line, options)

    def _append_plain_blocks(self, target: Text, blocks: Iterable[Block], options: RenderOptions):
        first = True
        for block in blocks:
            if not first:
                target.append("\n")
            first = False
            if isinstance(block, (ParagraphBlock, HeadingBlock)):
                target.append(self._segments_text(block.segments, options))
            elif isinstance(block, FormulaBlock):
                target.append(block.tex)
            elif isinstance(block, ImageBlock):
                target.append(self._image_fallback(block))
            elif isinstance(block, ListBlock):
                for index, item in enumerate(block.items, 1):
                    prefix = f"{index}. " if block.ordered else "• "
                    target.append(prefix)
                    self._append_plain_blocks(target, item, options)
            else:
                target.append(str(block))

    @staticmethod
    def _rich_table(block: TableBlock) -> Table:
        table = Table(
            show_header=bool(block.headers),
            header_style="bold cyan",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        column_count = max(
            [len(block.headers), *(len(row) for row in block.rows)],
            default=0,
        )
        for index in range(column_count):
            heading = block.headers[index] if index < len(block.headers) else ""
            table.add_column(Text(heading))
        for row in block.rows:
            padded = (*row, *("" for _ in range(column_count - len(row))))
            table.add_row(*(Text(cell) for cell in padded))
        return table

    def _print(self, renderable, options: RenderOptions):
        if options.indent:
            renderable = Padding(renderable, (0, 0, 0, len(options.indent)))
        self.console.print(renderable, highlight=False)
