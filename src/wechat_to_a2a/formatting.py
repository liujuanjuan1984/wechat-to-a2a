from __future__ import annotations

MAX_WECHAT_TEXT_CHARS = 2000


def split_wechat_text(
    content: str | None,
    *,
    max_chars: int = MAX_WECHAT_TEXT_CHARS,
    split_multiline_messages: bool = False,
) -> list[str]:
    text = (content or "").strip()
    if not text:
        return []
    if len(text) <= max_chars and (
        not split_multiline_messages or not _is_short_chatty_multiline(text)
    ):
        return [text]
    if split_multiline_messages and _is_short_chatty_multiline(text):
        return [line.strip() for line in text.splitlines() if line.strip()]
    return _split_into_chunks(text, max_chars=max_chars)


def _split_into_chunks(text: str, *, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for block in _markdown_blocks(text):
        block = block.strip()
        if not block:
            continue
        if len(block) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_block(block, max_chars=max_chars))
            continue

        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block

    if current:
        chunks.append(current)
    return chunks


def _markdown_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    in_code = False

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            current.append(line)
            continue
        if not in_code and not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)

    if current:
        blocks.append("\n".join(current))
    return blocks


def _split_long_block(block: str, *, max_chars: int) -> list[str]:
    if block.startswith("```"):
        return _split_long_code_block(block, max_chars=max_chars)

    chunks: list[str] = []
    current = ""
    for line in block.splitlines() or [block]:
        if len(line) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_plain_text(line, max_chars=max_chars))
            continue
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = line
    if current:
        chunks.append(current)
    return chunks


def _split_long_code_block(block: str, *, max_chars: int) -> list[str]:
    lines = block.splitlines()
    opening = lines[0] if lines else "```"
    closing = lines[-1] if len(lines) > 1 and lines[-1].strip() == "```" else "```"
    body = lines[1:-1] if closing == "```" else lines[1:]
    overhead = len(opening) + len(closing) + 2
    body_limit = max(1, max_chars - overhead)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in body:
        line_len = len(line) + (1 if current else 0)
        if current and current_len + line_len > body_limit:
            chunks.append("\n".join([opening, *current, closing]))
            current = []
            current_len = 0
        if len(line) > body_limit:
            chunks.extend(
                "\n".join([opening, part, closing])
                for part in _split_plain_text(line, max_chars=body_limit)
            )
            continue
        current.append(line)
        current_len += line_len
    if current or not chunks:
        chunks.append("\n".join([opening, *current, closing]))
    return chunks


def _split_plain_text(text: str, *, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _is_short_chatty_multiline(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return (
        1 < len(lines) <= 6
        and all(len(line) <= 48 for line in lines)
        and not any(_looks_structured(line) for line in lines)
    )


def _looks_structured(line: str) -> bool:
    stripped = line.lstrip()
    return (
        stripped.startswith(("#", "-", "*", ">", "|", "```"))
        or stripped[:2].isdigit()
        or stripped.startswith(tuple(f"{number}." for number in range(1, 10)))
    )
