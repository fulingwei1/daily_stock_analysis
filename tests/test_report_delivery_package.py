# -*- coding: utf-8 -*-
"""Tests for report delivery package contract."""

from src.schemas.report_delivery import (
    CHANNEL_DELIVERY_CAPABILITIES,
    ReportDeliveryPackage,
    build_report_markdown_url,
    get_channel_delivery_capability,
    sanitize_delivery_metadata,
)


def test_channel_delivery_matrix_covers_required_channels():
    channels = {item.channel for item in CHANNEL_DELIVERY_CAPABILITIES}

    assert {
        "wechat",
        "feishu",
        "telegram",
        "email",
        "slack",
        "discord",
        "pushplus",
        "serverchan3",
        "ntfy",
        "gotify",
        "custom",
    }.issubset(channels)

    assert get_channel_delivery_capability("feishu").supports_native_card is True
    assert get_channel_delivery_capability("email").full_report_suitability == "适合完整报告阅读"


def test_report_delivery_package_redacts_sensitive_metadata_and_keeps_links():
    package = ReportDeliveryPackage(
        title="日报",
        summary_text="摘要",
        summary_card={"title": "日报", "webhook_token": "secret"},
        summary_items=["买入 1", "", "风险 2"],
        full_markdown="# full",
        report_url="https://dsa.example/api/v1/history/1/markdown",
        external_doc_url="https://feishu.cn/docx/doc_1",
        image_snapshot_bytes=b"1234",
        metadata={
            "query_id": "q-1",
            "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/hook/secret",
            "nested": {"email_password": "secret-password", "safe": "ok"},
        },
    )

    public = package.as_public_dict()

    assert package.summary_items == ("买入 1", "风险 2")
    assert public["metadata"]["FEISHU_WEBHOOK_URL"] == "[redacted]"
    assert public["metadata"]["nested"]["email_password"] == "[redacted]"
    assert public["metadata"]["nested"]["safe"] == "ok"
    assert public["summary_card"]["webhook_token"] == "[redacted]"
    assert public["image_snapshot_size"] == 4
    assert "full_markdown" not in public
    assert public["full_markdown_size"] == len("# full".encode("utf-8"))
    assert "https://dsa.example/api/v1/history/1/markdown" in package.build_summary_message()


def test_sanitize_delivery_metadata_handles_lists_and_non_scalar_values():
    class CustomValue:
        def __str__(self):
            return "custom"

    metadata = sanitize_delivery_metadata(
        {
            "items": [{"token": "secret"}, CustomValue()],
            "plain": "value",
        }
    )

    assert metadata == {
        "items": [{"token": "[redacted]"}, "custom"],
        "plain": "value",
    }


def test_build_report_markdown_url_requires_explicit_http_base_url():
    assert build_report_markdown_url("", 1) is None
    assert build_report_markdown_url("localhost:8000", 1) is None
    assert build_report_markdown_url("https://dsa.example/app", "") is None

    assert (
        build_report_markdown_url("https://dsa.example/app", "q 1")
        == "https://dsa.example/app/api/v1/history/q%201/markdown"
    )
