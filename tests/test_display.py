"""Tests for zhihu_cli.display module."""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.table import Table

from zhihu_cli.display import (
    ZHIHU_THEME,
    format_count,
    format_stats_line,
    format_timestamp,
    html_to_rich,
    make_kv_table,
    make_table,
    strip_html,
    truncate,
)


# ── strip_html ─────────────────────────────────────────────────────────────────


class TestStripHtml:
    def test_removes_tags(self):
        assert strip_html("<p>hello</p>") == "hello"

    def test_removes_nested_tags(self):
        assert strip_html("<div><b>bold</b> text</div>") == "bold text"

    def test_unescapes_entities(self):
        assert strip_html("a &amp; b") == "a & b"

    def test_empty_string(self):
        assert strip_html("") == ""

    def test_none_returns_empty(self):
        assert strip_html(None) == ""

    def test_plain_text_unchanged(self):
        assert strip_html("no tags here") == "no tags here"

    def test_mixed_html_entities(self):
        assert strip_html("<a href='#'>click &gt; here</a>") == "click > here"

    def test_strips_whitespace(self):
        assert strip_html("  <p> padded </p>  ") == "padded"

    def test_self_closing_tags(self):
        assert strip_html("line1<br/>line2") == "line1line2"


# ── format_count ───────────────────────────────────────────────────────────────


class TestFormatCount:
    def test_small_number(self):
        assert format_count(42) == "42"

    def test_zero(self):
        assert format_count(0) == "0"

    def test_wan(self):
        assert format_count(12345) == "1.2万"

    def test_exact_wan(self):
        assert format_count(10000) == "1.0万"

    def test_large_wan(self):
        assert format_count(99999) == "10.0万"

    def test_yi(self):
        assert format_count(100_000_000) == "1.0亿"

    def test_large_yi(self):
        assert format_count(350_000_000) == "3.5亿"

    def test_string_number(self):
        assert format_count("5000") == "5000"

    def test_string_wan(self):
        assert format_count("50000") == "5.0万"

    def test_invalid_string(self):
        assert format_count("abc") == "abc"

    def test_below_boundary(self):
        assert format_count(9999) == "9999"


# ── truncate ───────────────────────────────────────────────────────────────────


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert truncate("12345", 5) == "12345"

    def test_truncates_with_ellipsis(self):
        result = truncate("hello world", 6)
        assert result == "hello…"

    def test_empty_string(self):
        assert truncate("") == ""

    def test_none_returns_empty(self):
        assert truncate(None) == ""

    def test_newlines_replaced(self):
        assert truncate("line1\nline2", 50) == "line1 line2"

    def test_newlines_before_truncation(self):
        result = truncate("line1\nline2\nline3", 8)
        assert "\n" not in result
        assert result.endswith("…")

    def test_default_max_len(self):
        long_text = "a" * 60
        result = truncate(long_text)
        assert len(result) == 50
        assert result.endswith("…")


# ── format_stats_line ──────────────────────────────────────────────────────────


class TestFormatStatsLine:
    def test_single_stat(self):
        result = format_stats_line({"Answers": 42})
        assert "42" in result
        assert "Answers" in result

    def test_multiple_stats(self):
        result = format_stats_line({"Answers": 42, "Followers": 100})
        assert "42" in result
        assert "100" in result
        assert "Answers" in result
        assert "Followers" in result

    def test_large_numbers_formatted(self):
        result = format_stats_line({"Views": 50000})
        assert "5.0万" in result

    def test_empty_dict(self):
        result = format_stats_line({})
        assert result == ""

    def test_contains_separator(self):
        result = format_stats_line({"A": 1, "B": 2})
        assert "▸" in result


# ── make_table ─────────────────────────────────────────────────────────────────


class TestMakeTable:
    def test_returns_table(self):
        t = make_table("Test Title")
        assert isinstance(t, Table)

    def test_table_not_expanded(self):
        t = make_table("Title")
        assert t.expand is False

    def test_show_lines_default_false(self):
        t = make_table("Title")
        assert t.show_lines is False

    def test_show_lines_enabled(self):
        t = make_table("Title", show_lines=True)
        assert t.show_lines is True


class TestMakeKvTable:
    def test_returns_table(self):
        t = make_kv_table("Profile")
        assert isinstance(t, Table)

    def test_has_two_columns(self):
        t = make_kv_table("Profile")
        assert len(t.columns) == 2

    def test_no_header(self):
        t = make_kv_table("Profile")
        assert t.show_header is False

    def test_can_add_rows(self):
        t = make_kv_table("Profile")
        t.add_row("Name", "Alice")
        t.add_row("Age", "30")
        assert t.row_count == 2


# ── Theme ──────────────────────────────────────────────────────────────────────


class TestTheme:
    def test_theme_has_required_styles(self):
        for style_name in ["info", "success", "warning", "error", "title"]:
            assert style_name in ZHIHU_THEME.styles


# ── format_timestamp ─────────────────────────────────────────────────────────────


class TestFormatTimestamp:
    def test_valid_timestamp(self):
        # 2024-01-01 00:00:00 UTC = 2024-01-01 08:00 Beijing
        assert format_timestamp(1704067200) == "2024-01-01 08:00"

    def test_none_returns_dash(self):
        assert format_timestamp(None) == "—"

    def test_zero_returns_dash(self):
        assert format_timestamp(0) == "—"

    def test_negative_returns_dash(self):
        assert format_timestamp(-1) == "—"

    def test_string_number(self):
        assert format_timestamp("1704067200") == "2024-01-01 08:00"

    def test_invalid_string(self):
        assert format_timestamp("not-a-number") == "not-a-number"


# ── html_to_rich ────────────────────────────────────────────────────────────────


class TestHtmlToRichBold:
    def test_bold(self):
        result = html_to_rich('<p>This is <b>bold</b> text</p>')
        assert len(result) >= 1
        text = result[0]
        assert "bold" in text.plain

    def test_strong(self):
        result = html_to_rich('<p>This is <strong>strong</strong> text</p>')
        assert len(result) >= 1
        assert "strong" in result[0].plain


class TestHtmlToRichItalic:
    def test_italic(self):
        result = html_to_rich('<p>This is <i>italic</i> text</p>')
        assert len(result) >= 1
        assert "italic" in result[0].plain

    def test_em(self):
        result = html_to_rich('<p>This is <em>emphasized</em> text</p>')
        assert len(result) >= 1
        assert "emphasized" in result[0].plain


class TestHtmlToRichLink:
    def test_link_with_href(self):
        result = html_to_rich('<a href="https://example.com">Example</a>')
        text = result[0]
        assert "Example" in text.plain
        assert "example.com" in text.plain

    def test_link_without_href(self):
        result = html_to_rich('<a>No href</a>')
        text = result[0]
        assert "No href" in text.plain


class TestHtmlToRichImage:
    def test_image_with_alt(self):
        result = html_to_rich('<img src="https://pic.zhihu.com/123.jpg" alt="架构图">')
        text = result[0]
        assert "架构图" in text.plain

    def test_image_without_alt(self):
        result = html_to_rich('<img src="https://pic.zhihu.com/123.jpg">')
        text = result[0]
        assert "图片" in text.plain


class TestHtmlToRichCodeBlock:
    def test_code_block(self):
        result = html_to_rich('<pre><code class="language-python">print("hello")</code></pre>')
        assert len(result) >= 1
        # Syntax object should be in the result
        from rich.syntax import Syntax
        assert any(isinstance(r, Syntax) for r in result)

    def test_code_block_auto_detect(self):
        result = html_to_rich('<pre><code>print("hello")</code></pre>')
        assert len(result) >= 1
        from rich.syntax import Syntax
        assert any(isinstance(r, Syntax) for r in result)


class TestHtmlToRichParagraph:
    def test_paragraphs_separated(self):
        result = html_to_rich('<p>First paragraph</p><p>Second paragraph</p>')
        combined = " ".join(r.plain for r in result)
        assert "First" in combined
        assert "Second" in combined


class TestHtmlToRichInjection:
    def test_bracket_text(self):
        """User content with [brackets] should not crash."""
        result = html_to_rich('<p>Use [code] tags for formatting</p>')
        assert len(result) >= 1
        assert "code" in result[0].plain

    def test_empty_content(self):
        result = html_to_rich("")
        assert len(result) == 1
        assert result[0].plain == ""

    def test_none_content(self):
        result = html_to_rich(None)
        assert len(result) == 1
        assert result[0].plain == ""


class TestHtmlToRichTable:
    def test_simple_table(self):
        html = """
        <table>
            <tr><th>Name</th><th>Age</th></tr>
            <tr><td>Alice</td><td>30</td></tr>
            <tr><td>Bob</td><td>25</td></tr>
        </table>
        """
        result = html_to_rich(html)
        assert len(result) >= 1
        from rich.table import Table
        assert any(isinstance(r, Table) for r in result)


class TestHtmlToRichList:
    def test_unordered_list(self):
        result = html_to_rich('<ul><li>Item 1</li><li>Item 2</li></ul>')
        assert len(result) >= 1
        assert "Item 1" in result[0].plain
        assert "Item 2" in result[0].plain

    def test_ordered_list(self):
        result = html_to_rich('<ol><li>First</li><li>Second</li></ol>')
        assert len(result) >= 1
        assert "First" in result[0].plain
        assert "Second" in result[0].plain


class TestHtmlToRichBlockquote:
    def test_blockquote(self):
        result = html_to_rich('<blockquote>This is a quote</blockquote>')
        assert len(result) >= 1
        from rich.panel import Panel
        assert any(isinstance(r, Panel) for r in result)
