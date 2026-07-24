"""Tests for the zhihu_cli.rendering package.

Tests cover:
- HtmlParser: semantic block extraction, image handling, formulas
- KittyImageBackend: capability probing, display calls
- MediaFetcher: caching, validation, error handling
- GraphicsRenderer: document traversal, fallbacks
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from zhihu_cli.rendering.html_parser import HtmlParser
from zhihu_cli.rendering.kitty import KittyImageBackend
from zhihu_cli.rendering.media_fetcher import MediaFetcher, _url_extension
from zhihu_cli.rendering.model import (
    BlockquoteBlock,
    CodeBlock,
    Document,
    FormulaBlock,
    HeadingBlock,
    HorizontalRule,
    ImageBlock,
    InlineFormulaSegment,
    ListBlock,
    ParagraphBlock,
    RenderOptions,
    TerminalCapabilities,
    TextSegment,
)
from zhihu_cli.rendering.renderer import DocumentRenderer

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def parser():
    return HtmlParser()


@pytest.fixture
def console():
    return Console(width=80)


@pytest.fixture
def render_options():
    return RenderOptions(
        media="off",
        formula="off",
        is_tty=True,
    )


# ── HtmlParser Tests ───────────────────────────────────────────────────────────


class TestHtmlParserBasic:
    def test_empty_string(self, parser):
        doc = parser.parse("")
        assert isinstance(doc, Document)
        assert len(doc.blocks) == 0

    def test_plain_paragraph(self, parser):
        doc = parser.parse("<p>Hello world</p>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ParagraphBlock)
        assert len(block.segments) == 1
        assert isinstance(block.segments[0], TextSegment)
        assert "Hello world" in block.segments[0].text

    def test_multiple_paragraphs(self, parser):
        doc = parser.parse("<p>First</p><p>Second</p>")
        assert len(doc.blocks) == 2
        assert all(isinstance(block, ParagraphBlock) for block in doc.blocks)
        assert "First" in doc.blocks[0].segments[0].text
        assert "Second" in doc.blocks[1].segments[0].text

    def test_heading(self, parser):
        doc = parser.parse("<h2>Title</h2>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, HeadingBlock)
        assert block.level == 2

    def test_br(self, parser):
        doc = parser.parse("<p>Line1<br>Line2</p>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ParagraphBlock)
        text = "".join(s.text for s in block.segments if isinstance(s, TextSegment))
        assert "Line1" in text
        assert "Line2" in text

    def test_hr(self, parser):
        doc = parser.parse("<hr>")
        assert len(doc.blocks) == 1
        assert isinstance(doc.blocks[0], HorizontalRule)


class TestHtmlParserBoldItalic:
    def test_bold(self, parser):
        doc = parser.parse("<p>This is <b>bold</b> text</p>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ParagraphBlock)
        text = "".join(s.text for s in block.segments if isinstance(s, TextSegment))
        assert "[bold]" in text
        assert "bold" in text
        assert "[/bold]" in text

    def test_italic(self, parser):
        doc = parser.parse("<p><i>italic</i></p>")
        text = "".join(s.text for s in doc.blocks[0].segments if isinstance(s, TextSegment))
        assert "[italic]" in text
        assert "italic" in text

    def test_strong(self, parser):
        doc = parser.parse("<p><strong>strong</strong></p>")
        text = "".join(s.text for s in doc.blocks[0].segments if isinstance(s, TextSegment))
        assert "[bold]" in text
        assert "strong" in text


class TestHtmlParserLists:
    def test_ul(self, parser):
        doc = parser.parse("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ListBlock)
        assert block.ordered is False
        assert len(block.items) == 2

    def test_ol(self, parser):
        doc = parser.parse("<ol><li>First</li><li>Second</li></ol>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ListBlock)
        assert block.ordered is True
        assert len(block.items) == 2


class TestHtmlParserCode:
    def test_code_block(self, parser):
        doc = parser.parse('<pre><code class="language-python">print("hello")</code></pre>')
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, CodeBlock)
        assert block.language == "python"
        assert "print" in block.code

    def test_code_block_no_lang(self, parser):
        doc = parser.parse("<pre><code>plain text</code></pre>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, CodeBlock)
        assert block.language == ""


class TestHtmlParserBlockquote:
    def test_blockquote(self, parser):
        doc = parser.parse("<blockquote><p>Quote text</p></blockquote>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, BlockquoteBlock)
        assert len(block.blocks) > 0


class TestHtmlParserImages:
    def test_top_level_image(self, parser):
        doc = parser.parse('<img src="https://pic.zhihu.com/123.jpg" alt="Photo">')
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ImageBlock)
        assert block.url == "https://pic.zhihu.com/123.jpg"
        assert block.alt == "Photo"

    def test_image_in_paragraph(self, parser):
        """Image in a paragraph that is the only content should be promoted."""
        doc = parser.parse('<p><img src="https://pic.zhihu.com/123.jpg" alt="Arch"></p>')
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ImageBlock), f"Expected ImageBlock, got {type(block)}"

    def test_image_with_data_attributes(self, parser):
        """data-original should take priority over src."""
        doc = parser.parse(
            '<img src="https://pic.zhihu.com/thumb.jpg" '
            'data-original="https://pic.zhihu.com/full.jpg">'
        )
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ImageBlock)
        assert block.url == "https://pic.zhihu.com/full.jpg"

    def test_protocol_relative_url(self, parser):
        doc = parser.parse('<img src="//pic.zhihu.com/123.jpg">')
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ImageBlock)
        assert block.url.startswith("https:")

    def test_figure_with_caption(self, parser):
        doc = parser.parse(
            "<figure>"
            '<img src="https://pic.zhihu.com/123.jpg" alt="Diagram">'
            "<figcaption>Figure 1</figcaption>"
            "</figure>"
        )
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ImageBlock)
        assert block.caption == "Figure 1"

    def test_small_icon_not_promoted(self, parser):
        """Small images (emoji/icon) should remain inline text."""
        doc = parser.parse('<p><img src="https://example.com/icon.png" width="24" height="24"></p>')
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        # Should be a ParagraphBlock with text fallback, not an ImageBlock
        assert isinstance(block, ParagraphBlock), f"Expected ParagraphBlock, got {type(block)}"

    def test_missing_image_url(self, parser):
        doc = parser.parse('<img alt="No src">')
        assert len(doc.blocks) == 0

    def test_noscript_fallback(self, parser):
        """Test that images inside <noscript> are still extracted."""
        html = "<p>Text <noscript><img src='https://pic.zhihu.com/123.jpg'></noscript></p>"
        doc = parser.parse(html)
        # Should have at least a paragraph block
        assert len(doc.blocks) > 0


class TestHtmlParserFormulas:
    def test_inline_formula(self, parser):
        doc = parser.parse(
            '<p>Formula: <span class="ztext-math" data-tex="E=mc^2">E=mc^2</span></p>'
        )
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ParagraphBlock)
        has_formula = any(isinstance(s, InlineFormulaSegment) for s in block.segments)
        assert has_formula

    def test_display_formula_span_wrapping_generic_image(self, parser):
        doc = parser.parse(
            '<p><span class="ztext-math" data-tex="\\sum_i x_i">'
            '<img src="https://pic.zhimg.com/equation.svg" alt="图片">'
            "</span></p>"
        )
        assert doc.blocks == [FormulaBlock(tex="\\sum_i x_i")]

    def test_inline_formula_tex_attr(self, parser):
        """data-tex should be used for formula content."""
        doc = parser.parse(
            '<p>Value: <span class="ztext-math" '
            'data-tex="\\frac{1}{2}">1/2</span></p>'
        )
        block = doc.blocks[0]
        formula = next(s for s in block.segments if isinstance(s, InlineFormulaSegment))
        assert formula.tex == "\\frac{1}{2}"

    def test_bracket_injection(self, parser):
        """User content with [brackets] should not crash."""
        doc = parser.parse("<p>Use [code] tags for formatting</p>")
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ParagraphBlock)

    def test_formula_img_with_eeimg(self, parser):
        """<img> with eeimg=1 should produce FormulaBlock."""
        doc = parser.parse(
            '<p><img src="https://www.zhihu.com/equation?tex=E%3Dmc%5E2" '
            'alt="E=mc^2" eeimg="1"></p>'
        )
        assert len(doc.blocks) == 1
        assert isinstance(doc.blocks[0], FormulaBlock)
        assert "E=mc^2" in doc.blocks[0].tex

    def test_formula_img_equation_url(self, parser):
        """<img> with src matching /equation endpoint should produce FormulaBlock."""
        doc = parser.parse(
            '<p><img src="https://www.zhihu.com/equation?tex=%5Cnabla" alt="\\nabla"></p>'
        )
        assert len(doc.blocks) == 1
        assert isinstance(doc.blocks[0], FormulaBlock)
        assert "nabla" in doc.blocks[0].tex

    def test_formula_img_inline_with_text(self, parser):
        """<img> formula inside a paragraph with text should be InlineFormulaSegment."""
        doc = parser.parse(
            '<p>Text before <img src="https://www.zhihu.com/equation?tex=f%28x%29" '
            'alt="f(x)" eeimg="1"> text after</p>'
        )
        assert len(doc.blocks) == 1
        block = doc.blocks[0]
        assert isinstance(block, ParagraphBlock)
        has_inline = any(isinstance(s, InlineFormulaSegment) for s in block.segments)
        assert has_inline

    def test_formula_div_with_equation(self, parser):
        """<div> containing an equation img should produce FormulaBlock."""
        doc = parser.parse(
            '<div><img src="https://www.zhihu.com/equation?tex=%5Cmin_x" '
            'alt="\\min_x" eeimg="1"></div>'
        )
        assert len(doc.blocks) == 1
        assert isinstance(doc.blocks[0], FormulaBlock)

    def test_regular_img_not_formula(self, parser):
        """Regular image without equation signs should stay ImageBlock."""
        doc = parser.parse('<img src="https://pic4.zhimg.com/80/v2-test.jpg" alt="Photo">')
        assert len(doc.blocks) == 1
        assert isinstance(doc.blocks[0], ImageBlock)

    def test_formula_div_multiple_equations(self, parser):
        """<div> with multiple equation imgs and no text should produce FormulaBlocks."""
        doc = parser.parse(
            "<div>"
            '<img src="https://www.zhihu.com/equation?tex=a" alt="a" eeimg="1">'
            '<img src="https://www.zhihu.com/equation?tex=b" alt="b" eeimg="1">'
            "</div>"
        )
        assert len(doc.blocks) == 2
        assert all(isinstance(b, FormulaBlock) for b in doc.blocks)

    def test_formula_fallback_to_tex(self, parser):
        """FormulaBlock should fall back to TeX text, not [Image]."""
        from rich.console import Console

        from zhihu_cli.rendering.graphics import GraphicsRenderer

        buf = io.StringIO()
        console = Console(
            file=buf, width=80, force_terminal=True, color_system=None, highlight=False
        )
        renderer = GraphicsRenderer(console=console)
        from zhihu_cli.rendering.model import RenderOptions

        opts = RenderOptions(media="off", formula="text", is_tty=True)
        renderer.render([FormulaBlock(tex="E=mc^2")], opts)
        output = buf.getvalue()
        assert "E=mc^2" in output
        assert "[Image]" not in output


# ── KittyImageBackend Tests ────────────────────────────────────────────────────


class TestKittyImageBackend:
    def setup_method(self):
        KittyImageBackend.clear_cache()

    def test_no_tty_capabilities(self):
        with patch("sys.stdout.isatty", return_value=False):
            backend = KittyImageBackend()
            caps = backend.capabilities()
            assert caps.is_tty is False
            assert caps.supports_images is False

    def test_missing_kitten(self):
        with patch("sys.stdout.isatty", return_value=True):
            with patch("zhihu_cli.rendering.kitty._find_kitten", return_value=None):
                backend = KittyImageBackend()
                caps = backend.capabilities()
                assert caps.supports_images is False

    @patch.dict("os.environ", {}, clear=True)
    @patch("sys.stdout")
    @patch("zhihu_cli.rendering.kitty._find_kitten", return_value="/usr/bin/kitten")
    @patch("subprocess.run")
    def test_successful_detection(self, mock_run, mock_find, mock_stdout):
        mock_stdout.isatty.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="support=1")
        backend = KittyImageBackend()
        caps = backend.capabilities()
        assert caps.supports_images is True
        assert caps.backend_name == "kitty"

    @patch("sys.stdout.isatty", return_value=True)
    @patch("zhihu_cli.rendering.kitty._find_kitten", return_value="/usr/bin/kitten")
    @patch("subprocess.run")
    def test_detection_failure(self, mock_run, mock_find, mock_tty):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        backend = KittyImageBackend()
        caps = backend.capabilities()
        assert caps.supports_images is False

    def test_display_missing_file(self):
        backend = KittyImageBackend()
        result = backend.display(Path("/nonexistent/image.png"))
        assert result is False

    @patch("zhihu_cli.rendering.kitty._find_kitten", return_value=None)
    def test_display_no_kitten(self, mock_find):
        backend = KittyImageBackend()
        temp = Path("/tmp/test_exists.png")
        try:
            temp.touch()
            result = backend.display(temp)
            assert result is False
        finally:
            temp.unlink(missing_ok=True)

    def test_capabilities_cached(self):
        with patch("sys.stdout.isatty", return_value=False):
            backend = KittyImageBackend()
            caps1 = backend.capabilities()
            caps2 = backend.capabilities()
            assert caps1 is caps2  # Same cached object


# ── MediaFetcher Tests ─────────────────────────────────────────────────────────


class TestMediaFetcher:
    def test_url_extension(self):
        assert _url_extension("https://example.com/image.jpg") == ".jpg"
        assert _url_extension("https://example.com/image.png?w=800") == ".png"
        assert _url_extension("https://example.com/image") == ".jpg"

    def test_cache_key_consistency(self):
        key1 = MediaFetcher._cache_key("https://example.com/img.jpg")
        key2 = MediaFetcher._cache_key("https://example.com/img.jpg")
        assert key1 == key2

    def test_formula_cache_key(self):
        key1 = MediaFetcher._formula_cache_key("E=mc^2", "light")
        key2 = MediaFetcher._formula_cache_key("E=mc^2", "light")
        assert key1 == key2

    def test_formula_cache_key_theme_different(self):
        key1 = MediaFetcher._formula_cache_key("E=mc^2", "light")
        key2 = MediaFetcher._formula_cache_key("E=mc^2", "dark")
        assert key1 != key2  # Different themes = different cache keys

    def test_empty_url(self):
        fetcher = MediaFetcher(client=None)
        result = fetcher.fetch_image("")
        assert result is None

    def test_non_http_url(self):
        fetcher = MediaFetcher(client=None)
        result = fetcher.fetch_image("ftp://example.com/image.jpg")
        assert result is None

    @patch("zhihu_cli.rendering.media_fetcher.MediaFetcher._validate_image", return_value=True)
    @patch("zhihu_cli.rendering.media_fetcher.MediaFetcher._download")
    def test_cache_hit(self, mock_download, mock_validate):
        from zhihu_cli.rendering.media_fetcher import MEDIA_CACHE_DIR

        fetcher = MediaFetcher(client=None)
        key = fetcher._cache_key("https://pic.zhimg.com/img.jpg")
        cache_path = MEDIA_CACHE_DIR / f"{key}.jpg"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.touch()
        try:
            result = fetcher.fetch_image("https://pic.zhimg.com/img.jpg")
            assert result is not None
            # Should not call _download
            mock_download.assert_not_called()
        finally:
            cache_path.unlink(missing_ok=True)


# ── GraphicsRenderer Tests ─────────────────────────────────────────────────────


class TestGraphicsRenderer:
    def test_paragraph_text(self, console, render_options):
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [ParagraphBlock((TextSegment("Hello world"),))]
        # Should not raise
        renderer.render(blocks, render_options)

    def test_heading_text(self, console, render_options):
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [HeadingBlock(level=1, segments=(TextSegment("Title"),))]
        renderer.render(blocks, render_options)

    def test_code_block(self, console, render_options):
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [CodeBlock(code='print("hello")', language="python")]
        renderer.render(blocks, render_options)

    def test_blockquote(self, console, render_options):
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [BlockquoteBlock(blocks=[ParagraphBlock((TextSegment("Quote"),))])]
        renderer.render(blocks, render_options)

    def test_horizontal_rule(self, console, render_options):
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [HorizontalRule()]
        renderer.render(blocks, render_options)

    def test_list_block(self, console, render_options):
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [
            ListBlock(
                ordered=False,
                items=[
                    [ParagraphBlock((TextSegment("Item 1"),))],
                    [ParagraphBlock((TextSegment("Item 2"),))],
                ],
            )
        ]
        renderer.render(blocks, render_options)

    def test_image_fallback(self, console, render_options):
        """Without Kitty, images should fall back to text."""
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [ImageBlock(url="https://example.com/img.jpg", alt="Photo")]
        renderer.render(blocks, render_options)

    def test_formula_fallback(self, console, render_options):
        """Without Kitty, formulas should fall back to TeX text."""
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [FormulaBlock(tex="E=mc^2")]
        renderer.render(blocks, render_options)

    def test_inline_formula_text(self, console, render_options):
        """Inline formulas should render as $...$ text."""
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [
            ParagraphBlock(
                (
                    TextSegment("Energy: "),
                    InlineFormulaSegment(tex="E=mc^2"),
                )
            )
        ]
        renderer.render(blocks, render_options)

    def test_mixed_document(self, console, render_options):
        """Multiple block types in sequence should render without error."""
        from zhihu_cli.rendering.graphics import GraphicsRenderer

        renderer = GraphicsRenderer(console=console)
        blocks = [
            HeadingBlock(level=1, segments=(TextSegment("Title"),)),
            ParagraphBlock((TextSegment("Some text"),)),
            CodeBlock(code="code here", language=""),
            HorizontalRule(),
            BlockquoteBlock(blocks=[ParagraphBlock((TextSegment("Quote"),))]),
        ]
        renderer.render(blocks, render_options)


# ── DocumentRenderer Integration Tests ─────────────────────────────────────────


class TestDocumentRenderer:
    def test_render_html_empty(self, console):
        renderer = DocumentRenderer(console=console)
        renderer.render("", media=False, formula=False)

    def test_render_html_text(self, console):
        renderer = DocumentRenderer(console=console)
        renderer.render("<p>Hello world</p>", media=False, formula=False)

    def test_render_html_with_formula(self, console):
        renderer = DocumentRenderer(console=console)
        renderer.render(
            '<p>E=mc^2: <span class="ztext-math" data-tex="E=mc^2">E=mc^2</span></p>',
            media=False,
            formula=False,
        )

    def test_render_html_with_image(self, console):
        renderer = DocumentRenderer(console=console)
        renderer.render(
            '<p><img src="https://pic.zhihu.com/123.jpg" alt="Photo"></p>',
            media=False,
            formula=False,
        )

    def test_render_complex_html(self, console):
        """Render a complex HTML document with multiple elements."""
        html = """
        <h2>Introduction</h2>
        <p>This is a <b>test</b> of the rendering system.</p>
        <pre><code class="language-python">print("hello")</code></pre>
        <blockquote>Important note</blockquote>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
        <p>Another paragraph with a formula:
           <span class="ztext-math" data-tex="\\alpha + \\beta">a+b</span>
        </p>
        <hr>
        <img src="https://pic.zhihu.com/456.jpg" alt="Final image">
        """
        renderer = DocumentRenderer(console=console)
        renderer.render(html, media=False, formula=False)


# ── TerminalCapabilities ───────────────────────────────────────────────────────


class TestTerminalCapabilities:
    def test_defaults(self):
        caps = TerminalCapabilities(is_tty=True, supports_images=False)
        assert caps.is_tty is True
        assert caps.supports_images is False
        assert caps.backend_name is None

    def test_full_capabilities(self):
        caps = TerminalCapabilities(is_tty=True, supports_images=True, backend_name="kitty")
        assert caps.backend_name == "kitty"
