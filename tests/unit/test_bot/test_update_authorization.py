"""Regression tests for authorization across Telegram update types."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update, User
from telegram.ext import Application, ExtBot, TypeHandler

from src.bot.core import ClaudeCodeBot
from src.bot.orchestrator import MessageOrchestrator
from src.config import create_test_config
from src.security.auth import AuthenticationManager, WhitelistAuthProvider

AUTHORIZED_USER_ID = 123456789
UNAUTHORIZED_USER_ID = 987654321


@pytest.fixture
async def telegram_app(monkeypatch):
    """Create an initialized PTB application without making network calls."""
    monkeypatch.setattr(
        ExtBot,
        "get_me",
        AsyncMock(return_value=User(123456, "Test", True, username="test_bot")),
    )
    monkeypatch.setattr(ExtBot, "send_message", AsyncMock(return_value=None))
    monkeypatch.setattr(ExtBot, "answer_callback_query", AsyncMock(return_value=True))
    monkeypatch.setattr(ExtBot, "edit_message_text", AsyncMock(return_value=None))

    app = Application.builder().token("123456:TEST").build()
    await app.initialize()
    yield app
    await app.shutdown()


def make_callback_update(app: Application, user_id: int, data: str) -> Update:
    """Build a real callback update originating from a bot inline keyboard."""
    return Update.de_json(
        {
            "update_id": 1,
            "callback_query": {
                "id": "callback-id",
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": "Test User",
                },
                "chat_instance": "chat-instance",
                "data": data,
                "message": {
                    "message_id": 10,
                    "date": 0,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {
                        "id": 123456,
                        "is_bot": True,
                        "first_name": "Test",
                        "username": "test_bot",
                    },
                    "text": "Choose an action",
                },
            },
        },
        app.bot,
    )


def configure_bot(
    app: Application, tmp_path: Path, agentic_mode: bool
) -> ClaudeCodeBot:
    """Wire real middleware and mode-specific handlers into a PTB application."""
    settings = create_test_config(
        approved_directory=str(tmp_path),
        agentic_mode=agentic_mode,
        allowed_users=[AUTHORIZED_USER_ID],
    )
    rate_limiter = MagicMock()
    rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
    security_validator = MagicMock()
    security_validator.sanitize_command_input.side_effect = lambda text: text
    dependencies = {
        "auth_manager": AuthenticationManager(
            [WhitelistAuthProvider([AUTHORIZED_USER_ID])]
        ),
        "security_validator": security_validator,
        "rate_limiter": rate_limiter,
        "audit_logger": AsyncMock(),
        "claude_integration": None,
    }
    bot = ClaudeCodeBot(settings, dependencies)
    bot.app = app
    bot._register_handlers()
    bot._add_middleware()
    return bot


@pytest.mark.parametrize(
    ("agentic_mode", "callback_data"),
    [
        (False, "action:ls"),
        (False, "git:diff"),
        (False, "cd:project"),
        (True, "cd:project"),
    ],
)
async def test_unauthorized_callback_never_reaches_mode_handler(
    telegram_app,
    monkeypatch,
    tmp_path,
    agentic_mode,
    callback_data,
):
    """Unauthorized callbacks stop before routers can read data or mutate state."""
    if agentic_mode:
        sensitive_handler = AsyncMock()
        monkeypatch.setattr(MessageOrchestrator, "_agentic_callback", sensitive_handler)
    else:
        from src.bot.handlers import callback

        sensitive_handler = AsyncMock()
        monkeypatch.setattr(callback, "handle_callback_query", sensitive_handler)

    configure_bot(telegram_app, tmp_path, agentic_mode)
    update = make_callback_update(telegram_app, UNAUTHORIZED_USER_ID, callback_data)

    await telegram_app.process_update(update)

    sensitive_handler.assert_not_awaited()


@pytest.mark.parametrize(
    ("agentic_mode", "callback_data"),
    [
        (False, "action:ls"),
        (False, "git:diff"),
        (False, "cd:project"),
        (True, "cd:project"),
    ],
)
async def test_authorized_callback_runs_all_middleware_and_mode_handler(
    telegram_app,
    monkeypatch,
    tmp_path,
    agentic_mode,
    callback_data,
):
    """Allowed callbacks pass security, authentication, and rate limiting."""
    if agentic_mode:
        sensitive_handler = AsyncMock()
        monkeypatch.setattr(MessageOrchestrator, "_agentic_callback", sensitive_handler)
    else:
        from src.bot.handlers import callback

        sensitive_handler = AsyncMock()
        monkeypatch.setattr(callback, "handle_callback_query", sensitive_handler)

    bot = configure_bot(telegram_app, tmp_path, agentic_mode)
    update = make_callback_update(telegram_app, AUTHORIZED_USER_ID, callback_data)

    await telegram_app.process_update(update)

    for group in (-3, -2, -1):
        assert len(telegram_app.handlers[group]) == 1
        middleware_handler = telegram_app.handlers[group][0]
        assert isinstance(middleware_handler, TypeHandler)
        assert middleware_handler.type is Update
        assert middleware_handler.check_update(update)
    sensitive_handler.assert_awaited_once()
    bot.deps["rate_limiter"].check_rate_limit.assert_awaited_once_with(
        user_id=AUTHORIZED_USER_ID, cost=pytest.approx(0.0116), tokens=1
    )


async def test_unauthorized_non_message_update_never_reaches_custom_handler(
    telegram_app, tmp_path
):
    """The middleware boundary also covers other user-originated update types."""
    configure_bot(telegram_app, tmp_path, agentic_mode=False)
    sensitive_handler = AsyncMock()
    telegram_app.add_handler(TypeHandler(Update, sensitive_handler), group=20)
    update = Update.de_json(
        {
            "update_id": 2,
            "inline_query": {
                "id": "inline-id",
                "from": {
                    "id": UNAUTHORIZED_USER_ID,
                    "is_bot": False,
                    "first_name": "Test User",
                },
                "query": "sensitive query",
                "offset": "",
            },
        },
        telegram_app.bot,
    )

    await telegram_app.process_update(update)

    sensitive_handler.assert_not_awaited()
