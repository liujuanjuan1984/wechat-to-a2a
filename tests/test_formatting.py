from __future__ import annotations

from wechat_to_a2a.formatting import format_wechat_text, split_wechat_text


def test_format_wechat_text_returns_empty_string_for_none() -> None:
    assert format_wechat_text(None) == ""


def test_split_wechat_text_keeps_structured_table_together() -> None:
    content = "| Setting | Value |\n| --- | --- |\n| Timeout | 30s |"

    assert split_wechat_text(content) == [content]


def test_split_wechat_text_can_split_short_chatty_multiline_messages() -> None:
    assert split_wechat_text(
        "第一行\n第二行\n第三行",
        split_multiline_messages=True,
    ) == ["第一行", "第二行", "第三行"]


def test_split_wechat_text_keeps_code_fences_balanced_when_splitting() -> None:
    lines = "\n".join(f"line_{index:02d} = {index}" for index in range(10))

    chunks = split_wechat_text(f"```python\n{lines}\n```", max_chars=70)

    assert len(chunks) > 1
    assert all(len(chunk) <= 70 for chunk in chunks)
    assert all(chunk.count("```") == 2 for chunk in chunks)
