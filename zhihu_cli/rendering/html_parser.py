"""Parse Zhihu HTML into an ordered semantic document."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag
from rich.markup import escape as rich_escape

from .model import (
    Block,
    BlockquoteBlock,
    CodeBlock,
    Document,
    FormulaBlock,
    HeadingBlock,
    HorizontalRule,
    ImageBlock,
    InlineFormulaSegment,
    InlineSegment,
    ListBlock,
    ParagraphBlock,
    TableBlock,
    TextSegment,
)

_BLOCK_TAGS = {
    "blockquote",
    "div",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "ol",
    "p",
    "pre",
    "table",
    "ul",
}
_STYLE_TAGS = {
    "b": ("bold",),
    "strong": ("bold",),
    "i": ("italic",),
    "em": ("italic",),
    "code": ("code",),
    "del": ("strike",),
    "s": ("strike",),
}
_IMAGE_ATTRS = ("data-original", "data-actualsrc", "data-default-watermark-src")
_SMALL_IMAGE_MAX_PX = 48


def _positive_int(value: object) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    if not match:
        return None
    number = int(match.group())
    return number if number > 0 else None


def _image_url(tag: Tag) -> str:
    for attr in _IMAGE_ATTRS:
        value = str(tag.get(attr, "")).strip()
        if value and not value.startswith("data:"):
            return f"https:{value}" if value.startswith("//") else value

    srcset = str(tag.get("srcset", "")).strip()
    if srcset:
        candidates = [part.strip().split()[0] for part in srcset.split(",") if part.strip()]
        if candidates:
            value = candidates[-1]
            return f"https:{value}" if value.startswith("//") else value
    value = str(tag.get("src", "")).strip()
    if not value or value.startswith("data:"):
        return ""
    return f"https:{value}" if value.startswith("//") else value


def _formula_tex(tag: Tag) -> str | None:
    classes = {str(item) for item in tag.get("class", [])}
    if "ztext-math" in classes or tag.get("eeimg") == "1":
        tex = str(tag.get("data-tex", "") or tag.get("alt", "")).strip()
        if tex:
            return tex

    if tag.name == "img":
        url = _image_url(tag)
        parsed = urlparse(url)
        if "/equation" in parsed.path:
            values = parse_qs(parsed.query).get("tex", [])
            if values:
                return unquote(values[0])
            alt = str(tag.get("alt", "")).strip()
            return alt or None
    return None


class HtmlParser:
    """BeautifulSoup-based parser that preserves text/image ordering."""

    def parse(self, html: str) -> Document:
        if not html:
            return Document()
        soup = BeautifulSoup(html, "html.parser")
        return Document(self._parse_nodes(soup.children))

    def _parse_nodes(self, nodes: Iterable[object]) -> list[Block]:
        blocks: list[Block] = []
        loose_segments: list[InlineSegment] = []

        def flush_loose():
            if loose_segments and self._segments_have_content(loose_segments):
                blocks.append(ParagraphBlock(tuple(loose_segments)))
            loose_segments.clear()

        for node in nodes:
            if isinstance(node, NavigableString):
                if str(node).strip():
                    loose_segments.append(TextSegment(rich_escape(str(node))))
                continue
            if not isinstance(node, Tag):
                continue

            tag = node.name.lower()
            if tag not in _BLOCK_TAGS and tag != "img":
                if node.find("img"):
                    flush_loose()
                    blocks.extend(self._parse_flow_container(node))
                else:
                    loose_segments.extend(self._inline_segments(node))
                continue

            flush_loose()
            blocks.extend(self._parse_block(node))

        flush_loose()
        return blocks

    def _parse_block(self, tag: Tag) -> list[Block]:
        name = tag.name.lower()
        if name in {"p", "div"}:
            return self._parse_flow_container(tag)
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            segments = tuple(self._inline_segments(tag))
            return (
                [HeadingBlock(int(name[1]), segments)]
                if self._segments_have_content(segments)
                else []
            )
        if name == "pre":
            code_tag = tag.find("code")
            source = code_tag or tag
            language = ""
            for cls in source.get("class", []):
                if str(cls).startswith("language-"):
                    language = str(cls)[len("language-") :]
                    break
            return [CodeBlock(source.get_text(), language)]
        if name == "blockquote":
            return [BlockquoteBlock(self._parse_nodes(tag.children))]
        if name in {"ul", "ol"}:
            items: list[list[Block]] = []
            for li in tag.find_all("li", recursive=False):
                parsed = self._parse_nodes(li.children)
                if not parsed:
                    segments = self._inline_segments(li)
                    parsed = [ParagraphBlock(tuple(segments))] if segments else []
                items.append(parsed)
            return [ListBlock(name == "ol", items)]
        if name == "table":
            return [self._parse_table(tag)]
        if name == "figure":
            caption_tag = tag.find("figcaption")
            caption = caption_tag.get_text(" ", strip=True) if caption_tag else ""
            blocks = []
            for image in tag.find_all("img", recursive=True):
                block = self._image_block(image, caption=caption)
                if block:
                    blocks.append(block)
            return blocks
        if name == "hr":
            return [HorizontalRule()]
        if name == "img":
            formula = _formula_tex(tag)
            if formula:
                return [FormulaBlock(formula)]
            block = self._image_block(tag)
            return [block] if block else []
        return self._parse_nodes(tag.children)

    def _parse_flow_container(self, tag: Tag) -> list[Block]:
        blocks: list[Block] = []
        segments: list[InlineSegment] = []

        def flush():
            if segments and self._segments_have_content(segments):
                blocks.append(ParagraphBlock(tuple(segments)))
            segments.clear()

        children = list(tag.children)
        formula_only = [
            _formula_tex(child)
            for child in children
            if isinstance(child, Tag) and child.name in {"img", "span"}
        ]
        meaningful_text = "".join(
            str(child).strip() for child in children if isinstance(child, NavigableString)
        )
        if formula_only and all(formula_only) and not meaningful_text:
            return [FormulaBlock(tex) for tex in formula_only if tex]

        for child in children:
            if isinstance(child, NavigableString):
                segments.append(TextSegment(rich_escape(str(child))))
                continue
            if not isinstance(child, Tag):
                continue

            name = child.name.lower()
            if name == "img":
                formula = _formula_tex(child)
                if formula:
                    segments.append(InlineFormulaSegment(formula))
                    continue
                if self._is_small_image(child):
                    fallback = self._inline_image_fallback(child)
                    if fallback:
                        segments.append(TextSegment(fallback))
                    continue
                flush()
                image = self._image_block(child)
                if image:
                    blocks.append(image)
                continue
            if name == "span" and _formula_tex(child):
                segments.append(InlineFormulaSegment(_formula_tex(child) or ""))
                continue
            if name == "noscript":
                flush()
                blocks.extend(self._parse_nodes(child.children))
                continue
            if child.find("img"):
                flush()
                blocks.extend(self._parse_flow_container(child))
                continue
            if name in _BLOCK_TAGS:
                flush()
                blocks.extend(self._parse_block(child))
                continue
            segments.extend(self._inline_segments(child))

        flush()
        return blocks

    def _inline_segments(self, node: object, styles: tuple[str, ...] = ()) -> list[InlineSegment]:
        if isinstance(node, NavigableString):
            text = rich_escape(str(node))
            for style in reversed(styles):
                text = f"[{style}]{text}[/{style}]"
            return [TextSegment(text)] if text else []
        if not isinstance(node, Tag):
            return []

        formula = _formula_tex(node)
        if formula:
            return [InlineFormulaSegment(formula)]

        name = node.name.lower()
        if name == "br":
            return [TextSegment("\n")]
        if name == "img":
            fallback = self._inline_image_fallback(node)
            return [TextSegment(fallback)] if fallback else []

        next_styles = styles + _STYLE_TAGS.get(name, ())
        segments: list[InlineSegment] = []
        for child in node.children:
            segments.extend(self._inline_segments(child, next_styles))

        if name == "a":
            href = str(node.get("href", "")).strip()
            if href:
                segments.append(TextSegment(rich_escape(f" ({href})")))
        return segments

    @staticmethod
    def _segments_have_content(segments: Iterable[InlineSegment]) -> bool:
        return any(
            isinstance(segment, InlineFormulaSegment)
            or (isinstance(segment, TextSegment) and segment.text.strip())
            for segment in segments
        )

    @staticmethod
    def _is_small_image(tag: Tag) -> bool:
        width = _positive_int(tag.get("width"))
        height = _positive_int(tag.get("height"))
        return bool(
            width and height and width <= _SMALL_IMAGE_MAX_PX and height <= _SMALL_IMAGE_MAX_PX
        )

    def _image_block(self, tag: Tag, *, caption: str = "") -> ImageBlock | None:
        url = _image_url(tag)
        if not url:
            return None
        return ImageBlock(
            url=url,
            alt=str(tag.get("alt", "")).strip(),
            caption=caption,
            width=_positive_int(tag.get("width")),
            height=_positive_int(tag.get("height")),
        )

    @staticmethod
    def _inline_image_fallback(tag: Tag) -> str:
        url = _image_url(tag)
        if not url:
            return ""
        alt = str(tag.get("alt", "")).strip() or "图片"
        return rich_escape(f"[图片：{alt}] {url}")

    @staticmethod
    def _parse_table(tag: Tag) -> TableBlock:
        rows: list[tuple[str, ...]] = []
        headers: tuple[str, ...] = ()
        for index, tr in enumerate(tag.find_all("tr")):
            cells = tuple(cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"]))
            if not cells:
                continue
            if index == 0 and tr.find("th"):
                headers = cells
            else:
                rows.append(cells)
        return TableBlock(headers, tuple(rows))
