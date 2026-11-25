"""Security tests for Telegram webhook delivery."""

import asyncio
import secrets
import socket
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import ValidationError
from telegram import Update, User
from telegram.ext import Application, ExtBot, TypeHandler

from src.bot.core import ClaudeCodeBot
from src.config.settings import Settings

TEST_SECRET = secrets.token_hex(32)


def make_settings(tmp_path, **overrides):
    """Build settings with only the required application fields."""
    values = {
        "telegram_bot_token": "test_token",
        "telegram_bot_username": "test_bot",
        "approved_directory": str(tmp_path),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("secret", [None, ""])
def test_webhook_mode_requires_configured_secret_token(tmp_path, secret):
    """Telegram webhook startup fails closed without a delivery secret."""
    with pytest.raises(ValidationError, match="WEBHOOK_SECRET_TOKEN"):
        make_settings(
            tmp_path,
            webhook_url="https://bot.example.test/telegram",
            webhook_secret_token=secret,
        )


@pytest.mark.parametrize("secret", ["changeme", "password", "webhook-secret", "a" * 32])
def test_webhook_mode_rejects_static_or_default_secret_tokens(tmp_path, secret):
    """Placeholder, short, and trivial secrets cannot protect webhook delivery."""
    with pytest.raises(ValidationError, match="WEBHOOK_SECRET_TOKEN.*random"):
        make_settings(
            tmp_path,
            webhook_url="https://bot.example.test/telegram",
            webhook_secret_token=secret,
        )


def test_webhook_listener_defaults_to_loopback(tmp_path):
    """Webhook delivery is local-only unless the operator explicitly exposes it."""
    settings = make_settings(
        tmp_path,
        webhook_url="https://bot.example.test/telegram",
        webhook_secret_token=TEST_SECRET,
    )

    assert settings.webhook_listen == "127.0.0.1"


@pytest.mark.parametrize("secret", [TEST_SECRET + "!", "A1" * 129])
def test_webhook_secret_matches_telegram_token_contract(tmp_path, secret):
    """Secrets use Telegram's allowed alphabet and 256-character maximum."""
    with pytest.raises(ValidationError, match="WEBHOOK_SECRET_TOKEN.*1-256"):
        make_settings(
            tmp_path,
            webhook_url="https://bot.example.test/telegram",
            webhook_secret_token=secret,
        )


def test_non_loopback_listener_requires_explicit_opt_in(tmp_path):
    """An exposed listener requires a separate, deliberate operator decision."""
    with pytest.raises(ValidationError, match="WEBHOOK_ALLOW_NON_LOOPBACK"):
        make_settings(
            tmp_path,
            webhook_url="https://bot.example.test/telegram",
            webhook_secret_token=TEST_SECRET,
            webhook_listen="0.0.0.0",
        )


def test_non_loopback_listener_can_be_explicitly_enabled(tmp_path):
    """The documented two-setting opt-in permits an intentional exposed bind."""
    settings = make_settings(
        tmp_path,
        webhook_url="https://bot.example.test/telegram",
        webhook_secret_token=TEST_SECRET,
        webhook_listen="0.0.0.0",
        webhook_allow_non_loopback=True,
    )

    assert settings.webhook_listen == "0.0.0.0"
    assert settings.webhook_allow_non_loopback is True


async def test_bot_passes_secret_and_loopback_listener_to_ptb(tmp_path):
    """The production bot forwards the secured settings to PTB's receiver."""
    settings = make_settings(
        tmp_path,
        webhook_url="https://bot.example.test/telegram",
        webhook_secret_token=TEST_SECRET,
    )
    bot = ClaudeCodeBot(settings, {})
    bot.initialize = AsyncMock()
    bot.app = MagicMock()
    bot.app.run_webhook = AsyncMock()

    await bot.start()

    bot.app.run_webhook.assert_awaited_once_with(
        listen="127.0.0.1",
        port=settings.webhook_port,
        url_path=settings.webhook_path,
        webhook_url=settings.webhook_url,
        secret_token=TEST_SECRET,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


def test_ptb_webhook_dependencies_are_installed():
    """A locked application install includes PTB's webhook receiver."""
    from telegram.ext import _updater

    assert _updater.WEBHOOKS_AVAILABLE is True


async def test_polling_mode_does_not_require_webhook_secret_or_listener(tmp_path):
    """Existing polling startup remains independent of webhook configuration."""
    settings = make_settings(tmp_path)
    bot = ClaudeCodeBot(settings, {})
    bot.initialize = AsyncMock()
    bot.app = MagicMock()
    bot.app.initialize = AsyncMock()
    bot.app.start = AsyncMock()
    bot.app.run_webhook = AsyncMock()

    async def finish_polling_start(**kwargs):
        bot.is_running = False

    bot.app.updater.start_polling = AsyncMock(side_effect=finish_polling_start)

    await bot.start()

    bot.app.updater.start_polling.assert_awaited_once_with(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
    bot.app.run_webhook.assert_not_awaited()


async def test_loopback_http_secret_rejections_and_normal_update_processing(
    tmp_path, monkeypatch
):
    """Real PTB HTTP delivery rejects bad secrets and dispatches a valid update."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    settings = make_settings(
        tmp_path,
        webhook_url="https://bot.example.test/telegram",
        webhook_secret_token=TEST_SECRET,
        webhook_port=port,
    )
    monkeypatch.setattr(
        ExtBot,
        "get_me",
        AsyncMock(return_value=User(123456, "Test", True, username="test_bot")),
    )
    monkeypatch.setattr(ExtBot, "delete_webhook", AsyncMock(return_value=True))
    set_webhook = AsyncMock(return_value=True)
    monkeypatch.setattr(ExtBot, "set_webhook", set_webhook)

    app = Application.builder().token("123456:TEST").build()
    # The mocked get_me bypasses Bot's normal cache population.
    app.bot._bot_user = User(123456, "Test", True, username="test_bot")
    processed = []
    processed_event = asyncio.Event()

    async def record_update(update, context):
        processed.append(update)
        processed_event.set()

    app.add_handler(TypeHandler(Update, record_update))
    await app.initialize()
    try:
        await app.start()
        await app.updater.start_webhook(
            listen=settings.webhook_listen,
            port=settings.webhook_port,
            url_path=settings.webhook_path,
            webhook_url=settings.webhook_url,
            secret_token=settings.webhook_secret_token_str,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        payload = {
            "update_id": 42,
            "message": {
                "message_id": 7,
                "date": 0,
                "chat": {"id": 123456789, "type": "private"},
                "from": {
                    "id": 123456789,
                    "is_bot": False,
                    "first_name": "Test User",
                },
                "text": "hello through the authenticated webhook",
            },
        }
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5
        ) as client:
            missing = await client.post(settings.webhook_path, json=payload)
            incorrect = await client.post(
                settings.webhook_path,
                json=payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": "incorrect"},
            )
            assert missing.status_code == 403
            assert incorrect.status_code == 403
            assert processed == []
            assert app.update_queue.empty()

            accepted = await client.post(
                settings.webhook_path,
                json=payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": TEST_SECRET},
            )

        assert accepted.status_code == 200
        await asyncio.wait_for(processed_event.wait(), timeout=2)
        assert len(processed) == 1
        assert processed[0].update_id == 42
        assert processed[0].effective_user.id == 123456789
        assert (
            processed[0].effective_message.text
            == "hello through the authenticated webhook"
        )
        assert set_webhook.await_args.kwargs["secret_token"] == TEST_SECRET
    finally:
        if app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
