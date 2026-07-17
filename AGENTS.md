# AGENTS.md — Project Context for AI Agents

This file documents the key design decisions, user requirements, and recent modifications to zhihu-cli. AI agents should read this before making changes to avoid repeating past mistakes.

## Recent Modifications

### 1. Detailed Answer Rendering
Every answer display now includes: **Answer ID**, **Author @token**, **UID**, **Question ID + title**, **created/updated timestamps**, **upvote/comment counts**.

### 2. HTML → Rich Terminal Formatting
Zhihu API returns HTML content. `strip_html()` is used for plain text (titles, excerpts, search results). A new `html_to_rich()` function (using BeautifulSoup4) converts HTML to Rich renderables for:

| HTML | Rich Output |
|------|-------------|
| `<b>` / `<strong>` | `[bold]` bold |
| `<i>` / `<em>` | `[italic]` italic |
| `<code>` | `[code]` inline code |
| `<pre><code class="language-*">` | `Syntax` with Pygments highlighting |
| `<a href="url">text</a>` | `text (url)` |
| `<img alt="x" src="url">` | `alt (url)` |
| `<blockquote>` | `Panel` with border |
| `<table>` | `Table` with rounded box |
| `<ul>` / `<ol>` | indented `•` / `1.` list |
| `<p>` / `<br>` | paragraph breaks |

**Critical**: User content may contain `[` / `]` which would crash Rich markup parser. The converter uses a placeholder escaping method: insert Rich tags first, escape `[` `]` in user text, then restore tags.

### 3. `zhihu pick` — Cache-Based Answer Selection
A shared cache file (`~/.zhihu-cli/feed_cache.json`) stores the last polled data from either `zhihu feed` or `zhihu answers`. The `zhihu pick <number>` command reads from this cache and fetches the full answer.

**Data format**: `pick` handles both:
- Feed format: `item → target → {id, type}`
- Answers format: `item → {id}` (type defaults to "answer")

### 4. `zhihu answers` — Pagination and Table Preview
- `-l / --limit` — answers per page (default: 5)
- `-p / --page` — page number (default: 1)
- Shows a numbered table with columns: `#`, `ID`, `Excerpt`, `Author`, `Upvotes`
- Table header shows the question title (fetched from first answer's `question.title`)
- Pagination hint: shows `--page N+1` suggestion or "no more"

### 5. `zhihu feed` — Table with Index
- `-l / --limit` — items per page (default: 10)
- Shows numbered table: `#`, `ID`, `Type`, `Title / Excerpt`, `Author`
- `zhihu feeds` default changed from 6 to 10 for consistency

## Design Decisions (from user Q&A)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Timezone | **Fixed UTC+8 (Beijing time)** for all timestamp display |
| 2 | Answer content truncation | **No truncation** for `zhihu answer` command |
| 3 | List layout | **Card layout** (not table) for `answers` and `user-answers` |
| 4 | HTML parser | **BeautifulSoup4** (stdlib `html.parser` is too basic, regex is brittle) |
| 5 | Search/hot inline snippets | **Only add Answer ID** (`A#<id>`) prefix, no full metadata |
| 6 | `--json` output | **New fields added** (`id`, `question`, `author.url_token`) documented in README |
| 7 | Answer scope | HTML→Rich conversion applied to **answer content + comments** only |
| 8 | Supported tags | **Bold, italic, code blocks, links, blockquotes, tables, lists, images** |
| 9 | Injection protection | **Placeholder method** (escape `[` `]` in user text, not in Rich tags) |
| 10 | Pick workflow | **Cache-based** — `zhihu feed` / `zhihu answers` store data, `zhihu pick` reads it |
| 11 | Code highlighting | **Yes**, using Rich `Syntax` + Pygments with language detection |

## Workflow

```bash
# Feed → pick workflow
zhihu feed              # Show numbered feed list, cache saved automatically
zhihu pick 3            # View answer #3 from the cached feed

# Answers → pick workflow
zhihu answers 12345     # Show numbered answer table, cache saved automatically
zhihu pick 3            # View answer #3 from the cached answers

# Answers pagination
zhihu answers 12345 -p 2    # Page 2 of answers
zhihu answers 12345 -l 10   # 10 answers per page
```

## File Map

| File | Purpose |
|------|---------|
| `zhihu_cli/display.py` | `format_timestamp()`, `print_answer_card()`, `html_to_rich()`, `print_html_content()` |
| `zhihu_cli/client.py` | API `include` params expanded to fetch `id`, `question`, `author` |
| `zhihu_cli/commands/content.py` | `feed`, `pick`, `answers` commands with cache logic |
| `zhihu_cli/commands/user.py` | `user-answers` uses `print_answer_card()` |
| `zhihu_cli/config.py` | `FEED_CACHE_FILE` path for shared pick cache |
| `tests/test_display.py` | Tests for `format_timestamp()` and `html_to_rich()` |
