"""Regression tests for repository CI supply-chain contracts."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_ci_checks_and_installs_from_committed_lock() -> None:
    for workflow_name in ("ci.yml", "release.yml"):
        workflow = (WORKFLOWS / workflow_name).read_text(encoding="utf-8")

        assert "poetry check --lock" in workflow
        assert "poetry install --no-interaction" in workflow
        assert "poetry lock" not in workflow


def test_unrequested_claude_automation_is_removed() -> None:
    assert not (WORKFLOWS / "claude.yml").exists()
    assert not (WORKFLOWS / "claude-code-review.yml.disabled").exists()


def test_actions_are_pinned_to_full_shas_with_version_comments() -> None:
    action_pattern = re.compile(r"^\s*uses:\s*(\S+)(?:\s+#\s*(\S+))?\s*$", re.MULTILINE)

    for workflow_path in WORKFLOWS.glob("*.yml"):
        actions = action_pattern.findall(workflow_path.read_text(encoding="utf-8"))
        assert actions, f"No Actions found in {workflow_path.name}"
        for action, version_comment in actions:
            revision = action.rsplit("@", maxsplit=1)[-1]
            assert re.fullmatch(r"[0-9a-f]{40}", revision), action
            assert re.fullmatch(r"v\d+\.\d+\.\d+", version_comment), action


def test_ci_uses_the_lockfile_compatible_poetry_version() -> None:
    lock_header = (ROOT / "poetry.lock").read_text(encoding="utf-8").splitlines()[0]
    lock_version = re.search(r"Poetry (\d+\.\d+\.\d+)", lock_header)
    assert lock_version is not None

    for workflow_name in ("ci.yml", "release.yml"):
        workflow = (WORKFLOWS / workflow_name).read_text(encoding="utf-8")
        assert f'version: "{lock_version.group(1)}"' in workflow


def test_ci_runs_for_the_security_review_branch() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert ci.count("branches: [main, security/v1.3.0-review]") == 2


def test_workflow_tokens_are_least_privilege() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")

    assert re.search(r"(?m)^permissions:\n  contents: read$", ci)
    assert re.search(r"(?m)^permissions:\n  contents: read$", release)
    assert "contents: write" not in ci
    assert release.count("contents: write") == 1
    release_job = release.split("  release:\n", maxsplit=1)[1]
    assert "    permissions:\n      contents: write" in release_job


def test_checkouts_do_not_persist_unused_credentials() -> None:
    for workflow_path in WORKFLOWS.glob("*.yml"):
        workflow = workflow_path.read_text(encoding="utf-8")
        checkout_count = workflow.count("uses: actions/checkout@")
        assert checkout_count > 0
        assert workflow.count("persist-credentials: false") == checkout_count


def test_installation_guidance_uses_immutable_releases() -> None:
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "git tag -f latest" not in release
    assert "git push -f origin latest" not in release

    for document_name in ("README.md", "docs/setup.md", "docs/development.md"):
        document = (ROOT / document_name).read_text(encoding="utf-8")
        assert "@latest" not in document
        assert "rolling `latest`" not in document


def test_repository_metadata_identifies_fork_and_credits_upstream() -> None:
    fork = "https://github.com/sn3akyLynx/claude-code-telegram"
    upstream = "https://github.com/overwirehq/claude-code-telegram"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = project["project"]["urls"]

    for label in ("Homepage", "Repository", "Documentation"):
        assert urls[label].startswith(fork)
    assert urls["Upstream"] == upstream

    source = (ROOT / "src" / "__init__.py").read_text(encoding="utf-8")
    assert f'__homepage__ = "{fork}"' in source

    for document_name in ("README.md", "docs/setup.md", "docs/development.md"):
        document = (ROOT / document_name).read_text(encoding="utf-8")
        assert fork in document
        assert "github.com/RichardAtCT/claude-code-telegram" not in document
    assert upstream in (ROOT / "README.md").read_text(encoding="utf-8")
