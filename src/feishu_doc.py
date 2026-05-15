# feishu_doc.py
# -*- coding: utf-8 -*-
import logging
import re
import lark_oapi as lark
from lark_oapi.api.docx.v1 import *
from typing import List, Optional, Tuple
from src.config import get_config

logger = logging.getLogger(__name__)


class FeishuDocManager:
    """飞书云文档管理器 (基于官方 SDK lark-oapi)"""

    def __init__(self):
        self.config = get_config()
        self.app_id = self.config.feishu_app_id
        self.app_secret = self.config.feishu_app_secret
        self.folder_token = self.config.feishu_folder_token

        # 初始化 SDK 客户端
        # SDK 会自动处理 tenant_access_token 的获取和刷新，无需人工干预
        if self.is_configured():
            self.client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .log_level(lark.LogLevel.INFO) \
                .build()
        else:
            self.client = None

    def is_configured(self) -> bool:
        """检查配置是否完整"""
        return bool(self.app_id and self.app_secret and self.folder_token)

    def create_daily_doc(self, title: str, content_md: str) -> Optional[str]:
        """
        创建日报文档
        """
        if not self.client or not self.is_configured():
            logger.warning("飞书 SDK 未初始化或配置缺失，跳过创建")
            return None

        try:
            # 1. 创建文档
            # 使用官方 SDK 的 Builder 模式构造请求
            create_request = CreateDocumentRequest.builder() \
                .request_body(CreateDocumentRequestBody.builder()
                              .folder_token(self.folder_token)
                              .title(title)
                              .build()) \
                .build()

            response = self.client.docx.v1.document.create(create_request)

            if not response.success():
                logger.error(f"创建文档失败: {response.code} - {response.msg} - {response.error}")
                return None

            doc_id = response.data.document.document_id
            # 这里的 domain 只是为了生成链接，实际访问会重定向
            doc_url = f"https://feishu.cn/docx/{doc_id}"
            logger.info(f"飞书文档创建成功: {title} (ID: {doc_id})")

            # 2. 解析 Markdown 并写入内容
            # 将 Markdown 转换为 SDK 需要的 Block 对象列表
            blocks = self._markdown_to_sdk_blocks(content_md)

            # 飞书 API 限制每次写入 Block 数量（建议 50 个左右），分批写入
            batch_size = 50
            doc_block_id = doc_id  # 文档本身也是一个 block

            for i in range(0, len(blocks), batch_size):
                batch_blocks = blocks[i:i + batch_size]

                # 构造批量添加块的请求
                batch_add_request = CreateDocumentBlockChildrenRequest.builder() \
                    .document_id(doc_id) \
                    .block_id(doc_block_id) \
                    .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                                  .children(batch_blocks)  # SDK 需要 Block 对象列表
                                  .index(-1)  # 追加到末尾
                                  .build()) \
                    .build()

                write_resp = self.client.docx.v1.document_block_children.create(batch_add_request)

                if not write_resp.success():
                    logger.error(f"写入文档内容失败(批次{i}): {write_resp.code} - {write_resp.msg}")

            logger.info(f"文档内容写入完成")
            return doc_url

        except Exception as e:
            logger.error(f"飞书文档操作异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _markdown_to_sdk_blocks(self, md_text: str) -> List[Block]:
        """
        将基础 Markdown 转换为飞书 SDK 的 Block 对象。

        覆盖标题、段落、无序/有序列表、引用、分割线和基础表格。表格会创建
        飞书 table block，同时追加一段纯文本保留单元格内容，避免当前浅层写入
        API 无法填充 cell 内容时丢失信息。
        """
        blocks = []
        lines = md_text.split('\n')
        index = 0

        while index < len(lines):
            line = lines[index].strip()
            if not line:
                index += 1
                continue

            table_rows, next_index = self._consume_markdown_table(lines, index)
            if table_rows:
                row_size = len(table_rows)
                column_size = max(len(row) for row in table_rows)
                blocks.append(
                    Block.builder()
                    .block_type(19)
                    .table(
                        Table.builder()
                        .property(
                            TableProperty.builder()
                            .row_size(row_size)
                            .column_size(column_size)
                            .build()
                        )
                        .build()
                    )
                    .build()
                )
                table_text = "\n".join(" | ".join(row) for row in table_rows)
                blocks.append(self._build_text_block(2, table_text, "text"))
                index = next_index
                continue

            # 识别标题
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading:
                level = len(heading.group(1))
                block_type = 2 + level
                blocks.append(
                    self._build_text_block(
                        block_type,
                        self._clean_inline_markdown(heading.group(2)),
                        f"heading{level}",
                    )
                )
            elif self._is_divider(line):
                # 分割线
                blocks.append(Block.builder()
                              .block_type(22)
                              .divider(Divider.builder().build())
                              .build())
            elif line.startswith(">"):
                quote_text = re.sub(r"^>\s?", "", line).strip()
                blocks.append(
                    self._build_text_block(
                        15,
                        self._clean_inline_markdown(quote_text),
                        "quote",
                    )
                )
            else:
                unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
                ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
                if unordered:
                    blocks.append(
                        self._build_text_block(
                            12,
                            self._clean_inline_markdown(unordered.group(1)),
                            "bullet",
                        )
                    )
                elif ordered:
                    blocks.append(
                        self._build_text_block(
                            13,
                            self._clean_inline_markdown(ordered.group(1)),
                            "ordered",
                        )
                    )
                else:
                    blocks.append(
                        self._build_text_block(
                            2,
                            self._clean_inline_markdown(line),
                            "text",
                        )
                    )

            index += 1

        return blocks

    def _build_text_block(self, block_type: int, content: str, attr_name: str) -> Block:
        """Build a text-like Feishu block."""
        text_run = TextRun.builder() \
            .content(content) \
            .text_element_style(TextElementStyle.builder().build()) \
            .build()

        text_element = TextElement.builder() \
            .text_run(text_run) \
            .build()

        text_obj = Text.builder() \
            .elements([text_element]) \
            .style(TextStyle.builder().build()) \
            .build()

        block_builder = Block.builder().block_type(block_type)
        getattr(block_builder, attr_name)(text_obj)
        return block_builder.build()

    def _consume_markdown_table(self, lines: List[str], start_index: int) -> Tuple[List[List[str]], int]:
        """Consume a basic Markdown pipe table from start_index."""
        if start_index + 1 >= len(lines):
            return [], start_index

        header = lines[start_index].strip()
        separator = lines[start_index + 1].strip()
        if not self._looks_like_table_row(header) or not self._is_table_separator(separator):
            return [], start_index

        rows = [self._split_table_row(header)]
        index = start_index + 2
        while index < len(lines):
            row = lines[index].strip()
            if not self._looks_like_table_row(row):
                break
            rows.append(self._split_table_row(row))
            index += 1

        return rows, index

    def _looks_like_table_row(self, line: str) -> bool:
        return "|" in line and len(self._split_table_row(line)) >= 2

    def _is_table_separator(self, line: str) -> bool:
        if not self._looks_like_table_row(line):
            return False
        cells = self._split_table_row(line)
        return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)

    def _split_table_row(self, line: str) -> List[str]:
        trimmed = line.strip().strip("|")
        return [self._clean_inline_markdown(cell.strip()) for cell in trimmed.split("|")]

    def _is_divider(self, line: str) -> bool:
        return bool(re.fullmatch(r"[-*_]\s*[-*_\s]{2,}", line))

    def _clean_inline_markdown(self, text: str) -> str:
        """Remove common inline Markdown markers for doc blocks."""
        cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"(\*\*|__)(.*?)\1", r"\2", cleaned)
        cleaned = re.sub(r"(`+)(.*?)\1", r"\2", cleaned)
        cleaned = cleaned.replace("**", "").replace("__", "")
        cleaned = cleaned.replace("*", "").replace("_", "")
        return cleaned.strip()
