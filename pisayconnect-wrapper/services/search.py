import re
from html import unescape

from bs4 import BeautifulSoup
from markupsafe import Markup, escape

MARK_OPEN = '<mark class="search-match">'
MARK_CLOSE = "</mark>"


def html_to_plain(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return unescape(soup.get_text(" ", strip=True))


def build_search_text(post):
    parts = [
        post.get("teacher") or "",
        post.get("author") or "",
        post.get("title") or "",
        post.get("date") or "",
        html_to_plain(post.get("message") or ""),
    ]

    for img in post.get("images") or []:
        parts.extend([img.get("alt") or "", img.get("src") or ""])

    for att in post.get("attachments") or []:
        parts.extend([
            att.get("name") or "",
            att.get("filename") or "",
            att.get("type") or "",
        ])

    return " ".join(p for p in parts if p).lower()


def parse_query(raw_query):
    query = (raw_query or "").strip()
    if not query:
        return ("empty", None)

    if query.lower().startswith("re:"):
        try:
            return ("regex", re.compile(query[3:].strip(), re.IGNORECASE | re.DOTALL))
        except re.error:
            pass

    slash_match = re.match(r"^/(.+)/([imsx]*)$", query)
    if slash_match:
        pattern_str, flags_str = slash_match.groups()
        flags = re.DOTALL
        if "i" in flags_str:
            flags |= re.IGNORECASE
        if "m" in flags_str:
            flags |= re.MULTILINE
        try:
            return ("regex", re.compile(pattern_str, flags))
        except re.error:
            pass

    return ("fuzzy", query)


def subsequence_score(needle, haystack):
    """fzf-style subsequence match. Returns 0 if no match, else a positive score."""
    if not needle:
        return 0

    n_idx = 0
    score = 0
    consecutive = 0
    prev_match = -2

    for h_idx, char in enumerate(haystack):
        if n_idx < len(needle) and char == needle[n_idx]:
            if h_idx == prev_match + 1:
                consecutive += 1
            else:
                consecutive = 1

            score += 10 + consecutive * 5

            if h_idx == 0 or not haystack[h_idx - 1].isalnum():
                score += 8

            prev_match = h_idx
            n_idx += 1

            if n_idx == len(needle):
                score += 20
                break

    if n_idx != len(needle):
        return 0

    return score


def fuzzy_score(query, text):
    text_lower = text.lower()
    query_lower = query.lower()

    if query_lower in text_lower:
        return 1000 + len(query_lower) * 10

    tokens = [t for t in re.split(r"\s+", query_lower) if t]
    if not tokens:
        return 0

    total = 0
    for token in tokens:
        token_score = subsequence_score(token, text_lower)
        if token_score == 0:
            return 0
        total += token_score

    return total / len(tokens)


def score_post(post, mode, parsed):
    text = post.get("search_text") or build_search_text(post)

    if mode == "regex":
        if parsed.search(text):
            return 500 + len(parsed.pattern)
        return 0

    return fuzzy_score(parsed, text)


def rank_posts(posts, raw_query, min_score=1):
    mode, parsed = parse_query(raw_query)

    if mode == "empty":
        return []

    scored = []
    for post in posts:
        score = score_post(post, mode, parsed)
        if score >= min_score:
            scored.append((score, post))

    scored.sort(key=lambda item: (-item[0], item[1].get("date") or ""), reverse=False)
    return [post for _, post in scored]


def _subsequence_indices(needle, haystack_lower):
    indices = []
    n_idx = 0

    for h_idx, char in enumerate(haystack_lower):
        if n_idx < len(needle) and char == needle[n_idx]:
            indices.append(h_idx)
            n_idx += 1
            if n_idx == len(needle):
                break

    return indices if n_idx == len(needle) else []


def _indices_to_ranges(indices):
    if not indices:
        return []

    ranges = []
    start = indices[0]
    prev = indices[0]

    for idx in indices[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        ranges.append((start, prev + 1))
        start = idx
        prev = idx

    ranges.append((start, prev + 1))
    return ranges


def _wrap_ranges(text, ranges):
    if not ranges:
        return escape(text)

    parts = []
    cursor = 0

    for start, end in ranges:
        if cursor < start:
            parts.append(escape(text[cursor:start]))
        parts.append(MARK_OPEN)
        parts.append(escape(text[start:end]))
        parts.append(MARK_CLOSE)
        cursor = end

    if cursor < len(text):
        parts.append(escape(text[cursor:]))

    return Markup("".join(str(part) for part in parts))


def highlight_plain_text(text, mode, parsed):
    text = str(text or "")
    if not text:
        return text

    if mode == "regex":
        def repl(match):
            return f"{MARK_OPEN}{escape(match.group(0))}{MARK_CLOSE}"

        return Markup(parsed.sub(repl, text))

    query = parsed
    text_lower = text.lower()
    query_lower = query.lower()
    ranges = []

    if query_lower in text_lower:
        idx = text_lower.index(query_lower)
        ranges = [(idx, idx + len(query))]
    else:
        tokens = [t for t in re.split(r"\s+", query) if t]
        for token in tokens:
            token_indices = _subsequence_indices(token.lower(), text_lower)
            ranges.extend(_indices_to_ranges(token_indices))

    if not ranges:
        return escape(text)

    ranges.sort()
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    return _wrap_ranges(text, merged)


def highlight_html(html, mode, parsed):
    if not html:
        return html

    soup = BeautifulSoup(html, "html.parser")

    for node in list(soup.find_all(string=True)):
        if node.parent and node.parent.name in {"script", "style"}:
            continue

        original = str(node)
        highlighted = highlight_plain_text(original, mode, parsed)
        if highlighted != escape(original):
            node.replace_with(BeautifulSoup(str(highlighted), "html.parser"))

    return Markup(str(soup))


def prepare_search_results(posts, raw_query):
    mode, parsed = parse_query(raw_query)
    if mode == "empty":
        return posts

    prepared = []

    for post in posts:
        item = dict(post)
        item["teacher"] = highlight_plain_text(post.get("teacher") or "", mode, parsed)
        item["date"] = highlight_plain_text(post.get("date") or "", mode, parsed)

        if post.get("message"):
            item["message"] = highlight_html(post.get("message") or "", mode, parsed)

        if post.get("images"):
            item["images"] = []
            for img in post.get("images") or []:
                image = dict(img)
                image["alt"] = highlight_plain_text(img.get("alt") or "", mode, parsed)
                item["images"].append(image)

        if post.get("attachments"):
            item["attachments"] = []
            for att in post.get("attachments") or []:
                attachment = dict(att)
                attachment["name"] = highlight_plain_text(att.get("name") or "", mode, parsed)
                attachment["filename"] = highlight_plain_text(att.get("filename") or "", mode, parsed)
                item["attachments"].append(attachment)

        prepared.append(item)

    return prepared
