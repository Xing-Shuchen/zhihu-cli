"""Semantic document model used by the terminal renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True)
class TextSegment:
    """Rich-safe markup produced by the HTML parser."""

    text: str


@dataclass(frozen=True)
class InlineFormulaSegment:
    tex: str


InlineSegment: TypeAlias = TextSegment | InlineFormulaSegment


@dataclass(frozen=True)
class ParagraphBlock:
    segments: tuple[InlineSegment, ...]


@dataclass(frozen=True)
class HeadingBlock:
    level: int
    segments: tuple[InlineSegment, ...]


@dataclass(frozen=True)
class CodeBlock:
    code: str
    language: str = ""


@dataclass(frozen=True)
class ImageBlock:
    url: str
    alt: str = ""
    caption: str = ""
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class FormulaBlock:
    tex: str


@dataclass(frozen=True)
class HorizontalRule:
    pass


@dataclass(frozen=True)
class TableBlock:
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class ListBlock:
    ordered: bool
    items: list[list[Block]]


@dataclass(frozen=True)
class BlockquoteBlock:
    blocks: list[Block]


Block: TypeAlias = (
    ParagraphBlock
    | HeadingBlock
    | CodeBlock
    | ImageBlock
    | FormulaBlock
    | HorizontalRule
    | TableBlock
    | ListBlock
    | BlockquoteBlock
)


@dataclass
class Document:
    blocks: list[Block] = field(default_factory=list)


@dataclass(frozen=True)
class RenderOptions:
    media: str = "auto"
    formula: str = "text"
    is_tty: bool | None = None
    indent: str = ""

    def __post_init__(self):
        if self.media not in {"auto", "on", "off"}:
            raise ValueError("media must be one of: auto, on, off")
        if self.formula not in {"text", "off"}:
            raise ValueError("formula must be one of: text, off")


@dataclass(frozen=True)
class TerminalCapabilities:
    is_tty: bool
    supports_images: bool
    backend_name: str | None = None
    reason: str | None = None
