"""Terminal display utilities for zhihu-cli.

Provides a consistent visual theme for all CLI output.
Uses Rich library for professional terminal rendering.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import unescape

from bs4 import BeautifulSoup, NavigableString, Tag
from rich import box as rich_box
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.markup import render as rich_render
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ── Theme ──────────────────────────────────────────────────────────────────────

ZHIHU_THEME = Theme({
    "info": "dim cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "title": "bold cyan",
    "subtitle": "dim white",
    "accent": "bold blue",
    "muted": "dim",
    "stat.key": "cyan",
    "stat.value": "white",
    "badge": "bold magenta",
})

console = Console(theme=ZHIHU_THEME)

# ── Timezone ────────────────────────────────────────────────────────────────────

_BEIJING_TZ = timezone(timedelta(hours=8))

# ── Brand ──────────────────────────────────────────────────────────────────────

BRAND = "[bold blue]zhihu[/bold blue][bold white]-cli[/bold white]"
SEPARATOR = "[dim]─" * 50 + "[/dim]"


def print_banner():
    """Print a branded banner."""
    ver = _get_version()
    console.print(
        Panel(
            f"{BRAND}  [dim]v{ver}[/dim]\n"
            "[dim]知乎命令行工具 — Search, Read, Interact[/dim]",
            border_style="blue",
            padding=(0, 2),
        ),
        highlight=False,
    )


def _get_version() -> str:
    from . import __version__
    return __version__


# ── Message helpers ────────────────────────────────────────────────────────────

def print_success(msg: str):
    """Print a success message."""
    console.print(f"  [success]✓[/success] {msg}")


def print_error(msg: str):
    """Print an error message."""
    console.print(f"  [error]✗[/error] {msg}")


def print_warning(msg: str):
    """Print a warning message."""
    console.print(f"  [warning]![/warning] {msg}")


def print_info(msg: str):
    """Print an informational message."""
    console.print(f"  [info]›[/info] {msg}")


def print_hint(msg: str):
    """Print a hint/tip message."""
    console.print(f"  [muted]hint: {msg}[/muted]")


# ── Text utilities ─────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return unescape(clean).strip()


def format_count(count: int | str) -> str:
    """Format large numbers for display (e.g. 12345 → 1.2万)."""
    if isinstance(count, str):
        try:
            count = int(count)
        except ValueError:
            return str(count)
    if count >= 100_000_000:
        return f"{count / 100_000_000:.1f}亿"
    if count >= 10_000:
        return f"{count / 10_000:.1f}万"
    return str(count)


def format_timestamp(ts: int | str | None) -> str:
    """Convert Unix timestamp to Beijing time string (YYYY-MM-DD HH:MM)."""
    if ts is None:
        return "—"
    if isinstance(ts, str):
        try:
            ts = int(ts)
        except (ValueError, TypeError):
            return str(ts)
    if ts <= 0:
        return "—"
    dt = datetime.fromtimestamp(ts, tz=_BEIJING_TZ)
    return dt.strftime("%Y-%m-%d %H:%M")


def truncate(text: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


# ── Table factories ────────────────────────────────────────────────────────────

def make_table(title: str, *, show_lines: bool = False, pad_edge: bool = False) -> Table:
    """Create a branded Table with standard styling."""
    return Table(
        title=f"[title]{title}[/title]",
        title_style="",
        border_style="blue",
        header_style="bold cyan",
        show_lines=show_lines,
        pad_edge=pad_edge,
        expand=False,
    )


def make_kv_table(title: str) -> Table:
    """Create a key-value profile table."""
    table = Table(
        title=f"[title]{title}[/title]",
        title_style="",
        border_style="blue",
        show_header=False,
        pad_edge=False,
        expand=False,
    )
    table.add_column("Key", style="stat.key", width=12, justify="right")
    table.add_column("Value", style="stat.value")
    return table


# ── Stats display ──────────────────────────────────────────────────────────────

def format_stats_line(pairs: dict[str, str | int]) -> str:
    """Create an inline stats display like '▸ 1.2万 Answers  ▸ 500 Followers'."""
    parts = []
    for label, value in pairs.items():
        parts.append(f"[dim]▸[/dim] [white]{format_count(value)}[/white] [dim]{label}[/dim]")
    return "  ".join(parts)


# ── Answer card display ─────────────────────────────────────────────────────────

def print_answer_card(idx: int, ans: dict, *, excerpt_len: int = 80):
    """Render one answer as a card block for list views."""
    answer_id = ans.get("id", "—")
    author = ans.get("author", {})
    author_name = author.get("name", "Anonymous")
    author_token = author.get("url_token", "—")

    question = ans.get("question", {})
    question_id = question.get("id", "—")
    question_title = strip_html(question.get("title", ""))

    upvotes = format_count(ans.get("voteup_count", 0))
    comments = format_count(ans.get("comment_count", 0))
    created = format_timestamp(ans.get("created_time"))

    # Line 1: index + answer ID + author
    console.print(
        f"  [dim]#{idx}[/dim]  [title]Answer #{answer_id}[/title]"
        f"  [dim]by[/dim] [accent]{author_name}[/accent]"
        f"  [dim]@{author_token}[/dim]"
    )

    # Line 2: question reference + timestamp
    meta_parts = []
    if question_id != "—" or question_title:
        q_ref = ""
        if question_id != "—":
            q_ref = f"Q#{question_id}"
        if question_title:
            sep = ": " if q_ref else ""
            q_ref += f"{sep}{truncate(question_title, 50)}"
        meta_parts.append(q_ref)
    if created != "—":
        meta_parts.append(f"created: {created}")
    if meta_parts:
        console.print(f"      [dim]{'  ·  '.join(meta_parts)}[/dim]")

    # Line 3: excerpt
    excerpt = strip_html(ans.get("excerpt", ans.get("content", "")))
    if excerpt:
        console.print(f"      {truncate(excerpt, excerpt_len)}")

    # Line 4: stats
    console.print(f"      [dim]▲ {upvotes} upvotes  ·  💬 {comments} comments[/dim]")
    console.print(f"  [dim]{'─' * 50}[/dim]")


# ── HTML to Rich converter ─────────────────────────────────────────────────────

def _build_table(table_tag: Tag) -> Table:
    """Convert an HTML <table> to a Rich Table."""
    rows = table_tag.find_all('tr')
    if not rows:
        return Table()

    # First row with <th> or first row determines headers
    first_cells = rows[0].find_all(['th', 'td'])
    headers = [cell.get_text(strip=True) for cell in first_cells]

    table = Table(show_header=bool(headers), header_style="bold cyan",
                  box=rich_box.ROUNDED, padding=(0, 1))
    for h in headers:
        table.add_column(h or "")

    for row in rows[1:]:
        cells = [cell.get_text(strip=True) for cell in row.find_all(['th', 'td'])]
        if cells:
            table.add_row(*cells)
    return table


def _build_list(list_tag: Tag) -> Text:
    """Convert an HTML <ul>/<ol> to a Rich Text with indented bullets."""
    result = Text()
    is_ol = list_tag.name.lower() == 'ol'
    index = 1
    for li in list_tag.find_all('li', recursive=False):
        prefix = f"  {index}. " if is_ol else "  • "
        result.append(prefix)
        # Check for nested lists
        text_parts = []
        for child in li.children:
            if isinstance(child, NavigableString):
                text_parts.append(str(child).strip())
            elif isinstance(child, Tag) and child.name in ('ul', 'ol'):
                # Nested list — will be handled separately
                continue
            elif isinstance(child, Tag):
                text_parts.append(child.get_text(strip=True))
        result.append(' '.join(text_parts).strip())
        # Check for nested list
        for child in li.children:
            if isinstance(child, Tag) and child.name in ('ul', 'ol'):
                result.append('\n')
                nested = _build_list(child)
                # Indent nested list further
                for line in nested.plain.split('\n'):
                    result.append(f"    {line}\n")
        result.append('\n')
        index += 1
    return result


def _process_inline(node, parts: list):
    """Recursively process inline HTML nodes, appending Rich markup strings to parts.

    Handles: bold, italic, code, links, images, text, line breaks.
    Escapes user content to prevent Rich markup injection.
    """
    if isinstance(node, NavigableString):
        text = str(node)
        if text:
            parts.append(rich_escape(text))
    elif isinstance(node, Tag):
        tag = node.name.lower()

        if tag in ('b', 'strong'):
            parts.append('[bold]')
            for child in node.children:
                _process_inline(child, parts)
            parts.append('[/bold]')
        elif tag in ('i', 'em'):
            parts.append('[italic]')
            for child in node.children:
                _process_inline(child, parts)
            parts.append('[/italic]')
        elif tag == 'code':
            parts.append('[code]')
            for child in node.children:
                _process_inline(child, parts)
            parts.append('[/code]')
        elif tag == 'a':
            href = node.get('href', '')
            inner_parts = []
            for child in node.children:
                _process_inline(child, inner_parts)
            link_text = ''.join(inner_parts)
            if href:
                parts.append(f'{link_text} ({href})')
            else:
                parts.append(link_text)
        elif tag == 'img':
            alt = node.get('alt', '图片')
            src = node.get('src', '')
            parts.append(rich_escape(f' {alt} ({src}) '))
        elif tag == 'br':
            parts.append('\n')
        elif tag == 'span':
            for child in node.children:
                _process_inline(child, parts)
        else:
            # Unknown inline tag, recurse
            for child in node.children:
                _process_inline(child, parts)


def html_to_rich(html_content: str) -> list:
    """Convert HTML to a list of Rich renderables.

    Renders:
    - Paragraphs, divisions, line breaks → newlines
    - Bold, italic → Rich markup
    - Code blocks → Rich Syntax with Pygments highlighting
    - Inline code → Rich code style
    - Links → text (url)
    - Images → alt text (url)
    - Blockquotes → Rich Panel
    - Tables → Rich Table
    - Lists → indented bullets / numbers

    Returns a list of ``Text``, ``Syntax``, ``Table``, ``Panel`` objects.
    """
    if not html_content:
        return [Text("")]

    soup = BeautifulSoup(html_content, 'html.parser')
    renderables = []

    # Buffer for inline markup parts
    markup_parts = []

    def flush():
        if markup_parts:
            text = rich_render(''.join(markup_parts))
            if text.plain:
                renderables.append(text)
            markup_parts.clear()

    for child in soup.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text.strip():
                markup_parts.append(rich_escape(text))
        elif isinstance(child, Tag):
            tag = child.name.lower()

            if tag in ('p', 'div'):
                flush()
                if tag == 'p':
                    markup_parts.append('\n')
                _process_inline(child, markup_parts)
                markup_parts.append('\n')

            elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                flush()
                markup_parts.append('[bold]')
                _process_inline(child, markup_parts)
                markup_parts.append('[/bold]\n')

            elif tag == 'blockquote':
                flush()
                quote_text = Text(child.get_text(strip=True))
                renderables.append(Panel(quote_text, border_style="dim", padding=(1, 2)))

            elif tag in ('ul', 'ol'):
                flush()
                renderables.append(_build_list(child))

            elif tag == 'table':
                flush()
                renderables.append(_build_table(child))

            elif tag == 'pre':
                flush()
                code_node = child.find('code') or child
                code_text = code_node.get_text()
                lang = None
                for cls in code_node.get('class', []):
                    if cls.startswith('language-'):
                        lang = cls.replace('language-', '')
                        break
                renderables.append(
                    Syntax(code_text, lang or 'text', theme="monokai",
                           line_numbers=False, word_wrap=True)
                )

            elif tag == 'hr':
                flush()
                renderables.append(Text('─' * 50))

            elif tag in ('b', 'strong', 'i', 'em', 'code', 'a', 'span'):
                _process_inline(child, markup_parts)

            elif tag == 'br':
                markup_parts.append('\n')

            elif tag == 'img':
                alt = child.get('alt', '图片')
                src = child.get('src', '')
                markup_parts.append(rich_escape(f' {alt} ({src}) '))

            else:
                # Unknown tag, recurse into children
                for sub_child in child.children:
                    if isinstance(sub_child, NavigableString):
                        if str(sub_child).strip():
                            markup_parts.append(rich_escape(str(sub_child)))
                    elif isinstance(sub_child, Tag):
                        subtag = sub_child.name.lower()
                        if subtag in ('p', 'div', 'blockquote', 'ul', 'ol', 'table', 'pre'):
                            flush()
                            renderables.extend(html_to_rich(str(sub_child)))
                        else:
                            _process_inline(sub_child, markup_parts)

    flush()
    return renderables


def print_html_content(
    html_content: str,
    *,
    indent: str = "",
    media: str = "off",
    renderer=None,
):
    """Print HTML content with full Rich formatting.

    Args:
        html_content: Raw HTML string from Zhihu API.
        indent: Optional indentation prefix (e.g. ``'  '``).
    """
    if media != "off":
        from .rendering import DocumentRenderer

        (renderer or DocumentRenderer(console=console)).render(
            html_content, media=media, indent=indent, is_tty=console.is_terminal
        )
        return

    renderables = html_to_rich(html_content)
    for item in renderables:
        if isinstance(item, Text) and indent:
            console.print(item, highlight=False)
        else:
            console.print(item, highlight=False)
