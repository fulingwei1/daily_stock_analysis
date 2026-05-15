# -*- coding: utf-8 -*-
"""Internal report delivery contract for notification renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import quote, urljoin


REPORT_DELIVERY_CARRIERS: Tuple[str, ...] = (
    "summary_text",
    "summary_card",
    "full_markdown",
    "full_html",
    "image_snapshot",
    "report_url",
    "external_doc_url",
)

_SENSITIVE_METADATA_KEY_PARTS = (
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "bot_secret",
    "cookie",
    "password",
    "private_key",
    "secret",
    "sendkey",
    "session",
    "token",
    "webhook",
)


@dataclass(frozen=True)
class ChannelDeliveryCapability:
    """Static delivery-shape metadata for a notification channel."""

    channel: str
    display_name: str
    markdown_support: str
    size_limit: str
    supports_image: bool
    supports_file: bool
    supports_native_card: bool
    recommended_carriers: Tuple[str, ...]
    full_report_suitability: str
    fallback: str
    note: str = ""


def _cap(
    channel: str,
    display_name: str,
    markdown_support: str,
    size_limit: str,
    supports: Tuple[bool, bool, bool],
    carriers: Tuple[str, ...],
    full_report_suitability: str,
    fallback: str,
    note: str = "",
) -> ChannelDeliveryCapability:
    return ChannelDeliveryCapability(
        channel,
        display_name,
        markdown_support,
        size_limit,
        supports[0],
        supports[1],
        supports[2],
        carriers,
        full_report_suitability,
        fallback,
        note,
    )


CHANNEL_DELIVERY_CAPABILITIES: Tuple[ChannelDeliveryCapability, ...] = (
    _cap("wechat", "企业微信", "markdown/text 子集，单条大小限制明显", "WECHAT_MAX_BYTES，text 模式还受 2048 字节约束",
         (True, False, False), ("summary_text", "report_url", "image_snapshot"), "不推荐承载完整研报", "文本/Markdown 分片",
         "图片仅在 MARKDOWN_TO_IMAGE_CHANNELS=wechat 时启用，适合摘要快照。"),
    _cap("feishu", "飞书", "lark_md 子集，表格等复杂 Markdown 会降级", "FEISHU_MAX_BYTES，超长会分片",
         (False, True, True), ("summary_card", "external_doc_url", "report_url"), "不推荐承载完整研报正文", "lark_md 卡片/文本分片",
         "FEISHU_WEBHOOK_URL 负责群消息，FEISHU_APP_ID/SECRET/FOLDER_TOKEN 负责云文档。"),
    _cap("telegram", "Telegram", "Markdown/HTML 能力取决于发送实现与客户端", "平台存在单条消息大小限制",
         (True, True, False), ("summary_text", "report_url", "image_snapshot"), "较长报告建议走链接或文件，不默认转长图", "文本消息",
         "图片发送保持 MARKDOWN_TO_IMAGE_CHANNELS=telegram opt-in。"),
    _cap("email", "邮件", "可承载完整 HTML/Markdown", "通常高于 IM，仍受邮箱服务限制",
         (True, True, False), ("full_html", "full_markdown", "report_url"), "适合完整报告阅读", "Markdown 文本邮件",
         "邮件是完整报告的高质量载体之一。"),
    _cap("slack", "Slack", "mrkdwn 子集；Webhook/Bot 能力不同", "平台存在消息长度限制",
         (True, True, True), ("summary_text", "report_url", "image_snapshot"), "摘要和链接优先，完整报告建议走外部入口", "Webhook 文本消息",
         "Bot 模式可上传图片；Webhook 模式回退文本。"),
    _cap("discord", "Discord", "Markdown 子集", "受 Discord 消息长度限制",
         (False, False, False), ("summary_text", "report_url"), "不推荐承载完整研报", "文本消息"),
    _cap("pushplus", "PushPlus", "基础文本/Markdown 展示", "受服务端消息限制",
         (False, False, False), ("summary_text", "report_url"), "不推荐承载完整研报", "文本消息"),
    _cap("serverchan3", "Server酱3", "基础文本/Markdown 展示", "受服务端消息限制",
         (False, False, False), ("summary_text", "report_url"), "不推荐承载完整研报", "文本消息"),
    _cap("ntfy", "ntfy", "通知文本为主", "适合短提醒",
         (False, False, False), ("summary_text", "report_url"), "不推荐承载完整研报", "文本消息"),
    _cap("gotify", "Gotify", "Markdown 文本展示", "适合短提醒",
         (False, False, False), ("summary_text", "report_url"), "不推荐承载完整研报", "文本消息"),
    _cap("custom", "自定义 Webhook", "取决于目标服务与 CUSTOM_WEBHOOK_BODY_TEMPLATE", "取决于目标服务",
         (True, False, False), ("summary_text", "report_url"), "由目标服务决定，默认建议摘要和链接", "默认 JSON 文本 payload",
         "模板建议显式传 summary + link，避免把完整 Markdown 强塞给未知服务。"),
)

_CAPABILITY_BY_CHANNEL: Dict[str, ChannelDeliveryCapability] = {
    item.channel: item for item in CHANNEL_DELIVERY_CAPABILITIES
}


def get_channel_delivery_capability(channel: str) -> Optional[ChannelDeliveryCapability]:
    """Return delivery capability metadata for a channel name."""

    return _CAPABILITY_BY_CHANNEL.get((channel or "").strip().lower())


def is_sensitive_metadata_key(key: str) -> bool:
    """Return whether a metadata key is likely to carry credentials."""

    normalized = (key or "").strip().lower()
    return any(part in normalized for part in _SENSITIVE_METADATA_KEY_PARTS)


def sanitize_delivery_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return metadata safe for package serialization and logging."""

    if not metadata:
        return {}

    def _sanitize(value: Any) -> Any:
        if isinstance(value, Mapping):
            sanitized: Dict[str, Any] = {}
            for raw_key, raw_value in value.items():
                key = str(raw_key)
                sanitized[key] = "[redacted]" if is_sensitive_metadata_key(key) else _sanitize(raw_value)
            return sanitized
        if isinstance(value, (list, tuple)):
            return [_sanitize(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    return _sanitize(metadata)


def build_report_markdown_url(public_base_url: Optional[str], record_id: Any) -> Optional[str]:
    """Build a full-report Markdown endpoint URL only when an explicit base URL exists."""

    base = (public_base_url or "").strip()
    normalized_record_id = str(record_id or "").strip()
    if not base or not normalized_record_id:
        return None

    if not base.startswith(("http://", "https://")):
        return None

    path = f"/api/v1/history/{quote(normalized_record_id, safe='')}/markdown"
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


@dataclass(frozen=True)
class ReportDeliveryPackage:
    """Channel-neutral report payload for future notification renderers."""

    title: str
    summary_text: str = ""
    summary_card: Optional[Mapping[str, Any]] = None
    summary_markdown: str = ""
    summary_items: Tuple[str, ...] = field(default_factory=tuple)
    full_markdown: str = ""
    full_html: str = ""
    report_url: Optional[str] = None
    external_doc_url: Optional[str] = None
    image_snapshot_bytes: Optional[bytes] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", str(self.title or "").strip())
        object.__setattr__(self, "summary_text", str(self.summary_text or "").strip())
        object.__setattr__(self, "summary_card", sanitize_delivery_metadata(self.summary_card))
        object.__setattr__(self, "summary_markdown", str(self.summary_markdown or "").strip())
        object.__setattr__(
            self,
            "summary_items",
            tuple(str(item).strip() for item in (self.summary_items or ()) if str(item).strip()),
        )
        object.__setattr__(self, "full_markdown", str(self.full_markdown or ""))
        object.__setattr__(self, "full_html", str(self.full_html or ""))
        object.__setattr__(self, "report_url", (self.report_url or "").strip() or None)
        object.__setattr__(self, "external_doc_url", (self.external_doc_url or "").strip() or None)
        object.__setattr__(self, "metadata", sanitize_delivery_metadata(self.metadata))

    @property
    def has_full_report_entry(self) -> bool:
        """Whether this package has a stable full-report entry outside IM text."""

        return bool(self.report_url or self.external_doc_url or self.full_html or self.full_markdown)

    def build_summary_message(self, *, include_links: bool = True) -> str:
        """Build a text fallback from the package without exposing metadata."""

        lines = []
        if self.title:
            lines.append(f"# {self.title}")
        if self.summary_markdown:
            lines.append(self.summary_markdown)
        elif self.summary_text:
            lines.append(self.summary_text)
        if self.summary_items:
            lines.extend(f"- {item}" for item in self.summary_items)

        if include_links:
            if self.report_url:
                lines.append(f"查看完整报告：{self.report_url}")
            if self.external_doc_url:
                lines.append(f"外部文档：{self.external_doc_url}")

        return "\n\n".join(part for part in lines if part)

    def as_public_dict(self, *, include_full_content: bool = False) -> Dict[str, Any]:
        """Serialize the package for diagnostics without raw image bytes."""

        data: Dict[str, Any] = {
            "title": self.title,
            "summary_text": self.summary_text,
            "summary_card": dict(self.summary_card or {}),
            "summary_markdown": self.summary_markdown,
            "summary_items": list(self.summary_items),
            "report_url": self.report_url,
            "external_doc_url": self.external_doc_url,
            "image_snapshot_size": len(self.image_snapshot_bytes or b""),
            "metadata": dict(self.metadata),
        }
        if include_full_content:
            data["full_markdown"] = self.full_markdown
            data["full_html"] = self.full_html
        else:
            data["full_markdown_size"] = len(self.full_markdown.encode("utf-8"))
            data["full_html_size"] = len(self.full_html.encode("utf-8"))
        return data


__all__ = [
    "CHANNEL_DELIVERY_CAPABILITIES",
    "REPORT_DELIVERY_CARRIERS",
    "ChannelDeliveryCapability",
    "ReportDeliveryPackage",
    "build_report_markdown_url",
    "get_channel_delivery_capability",
    "is_sensitive_metadata_key",
    "sanitize_delivery_metadata",
]
