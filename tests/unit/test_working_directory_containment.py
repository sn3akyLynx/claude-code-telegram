"""Regression tests for opt-in agentic working-directory containment."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Update

from src.bot.orchestrator import MessageOrchestrator
from src.config import create_test_config


def make_orchestrator(
    approved_directory: Path, restrict_working_directory: bool
) -> MessageOrchestrator:
    settings = create_test_config(
        approved_directory=str(approved_directory),
        agentic_mode=True,
        restrict_working_directory=restrict_working_directory,
    )
    return MessageOrchestrator(settings, {})


def make_context(current_directory: Path) -> MagicMock:
    context = MagicMock()
    context.user_data = {
        "current_directory": current_directory,
        "claude_session_id": "original-session",
    }
    context.bot_data = {"claude_integration": None, "audit_logger": None}
    return context


def make_repo_update(target_name: str) -> MagicMock:
    update = MagicMock()
    update.message.text = f"/repo {target_name}"
    update.message.reply_text = AsyncMock()
    update.effective_user.id = 123
    return update


def make_callback_update(target_name: str) -> Update:
    return Update.de_json(
        {
            "update_id": 1,
            "callback_query": {
                "id": "callback-id",
                "from": {"id": 123, "is_bot": False, "first_name": "Test"},
                "chat_instance": "chat-instance",
                "data": f"cd:{target_name}",
            },
        }
    )


@pytest.fixture(autouse=True)
def mock_callback_telegram_io(monkeypatch):
    """Use real PTB callback objects without network access."""
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())
    monkeypatch.setattr(CallbackQuery, "edit_message_text", AsyncMock())


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    approved = tmp_path / "approved"
    outside = tmp_path / "outside"
    approved.mkdir()
    outside.mkdir()
    (approved / "original").mkdir()
    return approved, outside


async def test_repo_rejects_absolute_path_when_containment_enabled(workspace):
    approved, outside = workspace
    orchestrator = make_orchestrator(approved, restrict_working_directory=True)
    context = make_context(approved / "original")
    update = make_repo_update(str(outside))

    await orchestrator.agentic_repo(update, context)

    assert context.user_data["current_directory"] == approved / "original"
    assert context.user_data["claude_session_id"] == "original-session"
    assert "Directory not found" in update.message.reply_text.call_args.args[0]


async def test_callback_rejects_absolute_path_when_containment_enabled(workspace):
    approved, outside = workspace
    orchestrator = make_orchestrator(approved, restrict_working_directory=True)
    context = make_context(approved / "original")
    update = make_callback_update(str(outside))

    await orchestrator._agentic_callback(update, context)

    assert context.user_data["current_directory"] == approved / "original"
    assert context.user_data["claude_session_id"] == "original-session"
    edit = CallbackQuery.edit_message_text
    assert "Directory not found" in edit.call_args.args[0]


@pytest.mark.parametrize("handler", ["repo", "callback"])
@pytest.mark.parametrize(
    "target_name", ["..", "nested/../../outside", "nested/../original"]
)
async def test_parent_traversal_is_rejected_when_containment_enabled(
    workspace, handler, target_name
):
    approved, _ = workspace
    (approved / "nested").mkdir()
    orchestrator = make_orchestrator(approved, restrict_working_directory=True)
    context = make_context(approved / "original")

    if handler == "repo":
        update = make_repo_update(target_name)
        await orchestrator.agentic_repo(update, context)
        message = update.message.reply_text.call_args.args[0]
    else:
        update = make_callback_update(target_name)
        await orchestrator._agentic_callback(update, context)
        message = CallbackQuery.edit_message_text.call_args.args[0]

    assert context.user_data["current_directory"] == approved / "original"
    assert context.user_data["claude_session_id"] == "original-session"
    assert "Directory not found" in message


@pytest.mark.parametrize("handler", ["repo", "callback"])
@pytest.mark.parametrize("target_name", ["escape", "escape/child"])
async def test_symlink_escape_is_rejected_when_containment_enabled(
    workspace, handler, target_name
):
    approved, outside = workspace
    (outside / "child").mkdir()
    (approved / "escape").symlink_to(outside, target_is_directory=True)
    orchestrator = make_orchestrator(approved, restrict_working_directory=True)
    context = make_context(approved / "original")

    if handler == "repo":
        update = make_repo_update(target_name)
        await orchestrator.agentic_repo(update, context)
        message = update.message.reply_text.call_args.args[0]
    else:
        update = make_callback_update(target_name)
        await orchestrator._agentic_callback(update, context)
        message = CallbackQuery.edit_message_text.call_args.args[0]

    assert context.user_data["current_directory"] == approved / "original"
    assert context.user_data["claude_session_id"] == "original-session"
    assert "Directory not found" in message


async def invoke_target(orchestrator, context, handler: str, target_name: str) -> str:
    """Invoke a real entry point and return its user-facing response."""
    if handler == "repo":
        update = make_repo_update(target_name)
        await orchestrator.agentic_repo(update, context)
        return update.message.reply_text.call_args.args[0]

    update = make_callback_update(target_name)
    await orchestrator._agentic_callback(update, context)
    return CallbackQuery.edit_message_text.call_args.args[0]


@pytest.mark.parametrize("handler", ["repo", "callback"])
@pytest.mark.parametrize("restrict", [False, True])
async def test_valid_child_directory_works_in_both_modes(workspace, handler, restrict):
    approved, _ = workspace
    child = approved / "parent" / "child"
    child.mkdir(parents=True)
    orchestrator = make_orchestrator(approved, restrict_working_directory=restrict)
    context = make_context(approved / "original")

    message = await invoke_target(orchestrator, context, handler, "parent/child")

    assert context.user_data["current_directory"] == child
    assert context.user_data["claude_session_id"] is None
    assert "Switched to" in message


@pytest.mark.parametrize("handler", ["repo", "callback"])
@pytest.mark.parametrize(
    "target_kind", ["absolute", "parent", "prefix_lookalike", "symlink"]
)
async def test_external_directories_remain_available_when_containment_disabled(
    workspace, handler, target_kind
):
    approved, outside = workspace
    lookalike = approved.parent / "approved-lookalike"
    lookalike.mkdir()
    (approved / "escape").symlink_to(outside, target_is_directory=True)
    targets = {
        "absolute": (str(outside), outside),
        "parent": ("..", approved.parent),
        "prefix_lookalike": ("../approved-lookalike", lookalike),
        "symlink": ("escape", outside),
    }
    target_name, expected = targets[target_kind]
    orchestrator = make_orchestrator(approved, restrict_working_directory=False)
    context = make_context(approved / "original")

    message = await invoke_target(orchestrator, context, handler, target_name)

    assert context.user_data["current_directory"].resolve() == expected.resolve()
    assert context.user_data["claude_session_id"] is None
    assert "Switched to" in message


@pytest.mark.parametrize("handler", ["repo", "callback"])
async def test_absolute_child_path_is_rejected_when_containment_enabled(
    workspace, handler
):
    approved, _ = workspace
    orchestrator = make_orchestrator(approved, restrict_working_directory=True)
    context = make_context(approved / "original")

    message = await invoke_target(
        orchestrator, context, handler, str(approved / "original")
    )

    assert context.user_data["current_directory"] == approved / "original"
    assert context.user_data["claude_session_id"] == "original-session"
    assert "Directory not found" in message


@pytest.mark.parametrize("handler", ["repo", "callback"])
@pytest.mark.parametrize(
    "target_name",
    [
        "lookalike-link",
        "lookalike-link/missing/child",
        "missing/child",
        "bad\0path",
    ],
)
async def test_resolved_containment_covers_lookalikes_and_missing_components(
    workspace, handler, target_name
):
    approved, _ = workspace
    lookalike = approved.parent / "approved-lookalike"
    lookalike.mkdir()
    (approved / "lookalike-link").symlink_to(lookalike, target_is_directory=True)
    orchestrator = make_orchestrator(approved, restrict_working_directory=True)
    context = make_context(approved / "original")

    message = await invoke_target(orchestrator, context, handler, target_name)

    assert context.user_data["current_directory"] == approved / "original"
    assert context.user_data["claude_session_id"] == "original-session"
    assert "Directory not found" in message
