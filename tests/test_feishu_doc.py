# -*- coding: utf-8 -*-
"""Tests for Feishu cloud document Markdown conversion."""

from src.feishu_doc import FeishuDocManager


def _manager():
    return FeishuDocManager.__new__(FeishuDocManager)


def _text_content(block):
    for attr_name in ("text", "heading1", "heading2", "heading3", "bullet", "ordered", "quote"):
        text_obj = getattr(block, attr_name, None)
        if text_obj and getattr(text_obj, "elements", None):
            return text_obj.elements[0].text_run.content
    return ""


def test_markdown_to_sdk_blocks_covers_headings_lists_quotes_dividers_and_table():
    blocks = _manager()._markdown_to_sdk_blocks(
        "\n".join(
            [
                "# 标题",
                "普通 **段落**",
                "- 要点一",
                "1. 步骤一",
                "> 风险提示",
                "---",
                "| 名称 | 结论 |",
                "| --- | --- |",
                "| 贵州茅台 | 买入 |",
            ]
        )
    )

    block_types = [block.block_type for block in blocks]

    assert block_types[:6] == [3, 2, 12, 13, 15, 22]
    assert 19 in block_types
    assert _text_content(blocks[0]) == "标题"
    assert _text_content(blocks[1]) == "普通 段落"
    assert _text_content(blocks[2]) == "要点一"
    assert _text_content(blocks[3]) == "步骤一"
    assert _text_content(blocks[4]) == "风险提示"

    table_block = next(block for block in blocks if block.block_type == 19)
    assert table_block.table.property.row_size == 2
    assert table_block.table.property.column_size == 2
    assert "贵州茅台 | 买入" in _text_content(blocks[-1])


def test_markdown_table_requires_separator_line():
    blocks = _manager()._markdown_to_sdk_blocks("| A | B |\nnot a separator")

    assert [block.block_type for block in blocks] == [2, 2]
