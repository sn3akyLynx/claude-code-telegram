# Configuration Guide

This document provides comprehensive information about configuring the Claude Code Telegram Bot.

## Overview

The bot uses a configuration system built with Pydantic Settings v2 that provides:

- **Type Safety**: All configuration values are validated and type-checked
- **Environment Support**: Automatic environment-specific overrides
- **Feature Flags**: Dynamic enabling/disabling of functionality
- **Validation**: Cross-field validation and runtime checks

## Configuration Sources

Configuration is loaded in this order (later sources override earlier ones):

1. **Default values** defined in the Settings class
2. **Environment variables**
3. **`.env` file** (if present)
4. **Environment-specific overrides** (development/testing/production)

## Environment Variables

### Required Settings

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_BOT_USERNAME=your_bot_name

# Security
APPROVED_DIRECTORY=/path/to/your/projects
ALLOWED_USERS=123456789,987654321  # At least one Telegram user ID is required
```

`ALLOWED_USERS` is mandatory and fail-closed. Startup aborts when it is unset,
empty, or contains only separators. This applies to development, testing, and
production; `DEVELOPMENT_MODE=true` never enables allow-all access. Token-based
authentication can be enabled in addition to the allowlist, but cannot replace it.

### Optional Settings

#### User Access Control

```bash
# Enable token-based authentication (requires AUTH_TOKEN_SECRET)
ENABLE_TOKEN_AUTH=false
AUTH_TOKEN_SECRET=your-secret-key-here
```

#### Security Relaxation (Trusted Environments Only)

```bash
# Disable dangerous pattern validation in SecurityValidator (default: false)
# WARNING: This allows characters such as pipes and redirections in validated paths.
DISABLE_SECURITY_PATTERNS=false

# Disable ToolMonitor allowlist/disallowlist checks (default: false)
# WARNING: This only skips tool-name allow/disallow checks; path and Bash safety checks still apply.
DISABLE_TOOL_VALIDATION=false
```

#### Working-Directory Containment

```bash
# Contain agentic /repo and cd: selection to APPROVED_DIRECTORY (default: false)
RESTRICT_WORKING_DIRECTORY=false
```

When `RESTRICT_WORKING_DIRECTORY=true`, agentic `/repo <name>` commands and `cd:`
callbacks accept only existing directories whose resolved paths are within
`APPROVED_DIRECTORY`. Absolute paths, any `..` path component, parent-directory
escapes, and symbolic-link escapes are rejected. Resolution also covers existing
symlinks followed by non-existent path components, and path comparisons are
component-aware so similarly prefixed sibling directories are not treated as
children.

The default `false` deliberately preserves the existing ability to select
external directories through these agentic commands. This setting does not change
classic-mode path validation, tool validation, or sandbox exclusions.

#### Claude Configuration

```bash
# Authentication
ANTHROPIC_API_KEY=sk-ant-api03-...    # Optional: API key for SDK (uses CLI auth if omitted)

# Maximum conversation turns before requiring new session
CLAUDE_MAX_TURNS=10

# Timeout for Claude operations in seconds
CLAUDE_TIMEOUT_SECONDS=300

# Maximum cost per user in USD
CLAUDE_MAX_COST_PER_USER=10.0

# Allowed Claude tools (comma-separated list; see docs/tools.md for descriptions)
CLAUDE_ALLOWED_TOOLS=Read,Write,Edit,Bash,Glob,Grep,LS,Task,TaskOutput,MultiEdit,NotebookRead,NotebookEdit,WebFetch,TodoRead,TodoWrite,WebSearch
```

#### Rate Limiting

```bash
# Number of requests allowed per window
RATE_LIMIT_REQUESTS=10

# Rate limit window in seconds
RATE_LIMIT_WINDOW=60

# Burst capacity for rate limiting
RATE_LIMIT_BURST=20
```

#### Storage & Database

```bash
# Database URL (SQLite by default)
DATABASE_URL=sqlite:///data/bot.db

# Session management
SESSION_TIMEOUT_HOURS=24           # Session timeout in hours
MAX_SESSIONS_PER_USER=5            # Max concurrent sessions per user

# Data retention
DATA_RETENTION_DAYS=90            # Days to keep old data
AUDIT_LOG_RETENTION_DAYS=365     # Days to keep audit logs
```

#### Mode Selection

```bash
# Agentic mode (default: true)
# true = conversational mode with 3 commands (/start, /new, /status)
# false = classic terminal mode with 13 commands and inline keyboards
AGENTIC_MODE=true
```

#### Feature Flags

```bash
# Enable Model Context Protocol
ENABLE_MCP=false
MCP_CONFIG_PATH=/path/to/mcp/config.json

# Enable Git integration (classic mode)
ENABLE_GIT_INTEGRATION=true

# Enable file upload handling
ENABLE_FILE_UPLOADS=true

# Enable quick action buttons (classic mode)
ENABLE_QUICK_ACTIONS=true
```

#### Agentic Platform

```bash
# Webhook API Server
ENABLE_API_SERVER=false               # Enable FastAPI webhook server
API_SERVER_PORT=8080                  # Server port (default: 8080)

# Webhook Authentication
GITHUB_WEBHOOK_SECRET=your-secret    # GitHub HMAC-SHA256 secret
WEBHOOK_API_SECRET=your-secret       # Bearer token for generic providers

# Job Scheduler
ENABLE_SCHEDULER=false                # Enable cron job scheduler

# Notifications
NOTIFICATION_CHAT_IDS=123456,789012  # Default Telegram chat IDs for proactive notifications
```

#### Project Thread Mode

```bash
# Strict project routing via Telegram project topics
ENABLE_PROJECT_THREADS=false

# Mode: private (default) or group
PROJECT_THREADS_MODE=private

# YAML registry file with project slugs/names/paths
PROJECTS_CONFIG_PATH=config/projects.yaml

# Required only for PROJECT_THREADS_MODE=group
PROJECT_THREADS_CHAT_ID=-1001234567890
```

`PROJECTS_CONFIG_PATH` schema:

```yaml
projects:
  - slug: my-app
    name: My App
    path: my-app
    enabled: true
```

When `ENABLE_PROJECT_THREADS=true`:
- `PROJECT_THREADS_MODE=private`:
  - `/start` and `/sync_threads` are allowed outside topics in private chat.
  - all other updates must be inside mapped project topics.
- `PROJECT_THREADS_MODE=group`:
  - behavior remains forum-topic based using `PROJECT_THREADS_CHAT_ID`.

#### Monitoring & Logging

```bash
# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# Enable anonymous telemetry
ENABLE_TELEMETRY=false

# Sentry DSN for error tracking
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project
```

#### Development

```bash
# Enable debug mode
DEBUG=false

# Enable development features
DEVELOPMENT_MODE=false

# Environment override (development, testing, production)
ENVIRONMENT=development
```

#### Telegram Delivery (Polling vs Webhook)

Leave `WEBHOOK_URL` unset or empty to use Telegram polling. Polling is the default
and does not require any of the webhook settings below.

To enable Telegram webhook delivery instead, generate an independent random
secret and configure the public HTTPS URL and local receiver:

```bash
# Generate with: openssl rand -hex 32
# Replace this placeholder with the command's output; do not use a static example.
WEBHOOK_SECRET_TOKEN=<64-lowercase-hex-characters-from-the-command-above>
WEBHOOK_URL=https://bot.example.com/webhook
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8443

# Safe default: only a same-host reverse proxy can reach the receiver.
WEBHOOK_LISTEN=127.0.0.1
WEBHOOK_ALLOW_NON_LOOPBACK=false
```

`WEBHOOK_SECRET_TOKEN` is mandatory in webhook mode. Startup fails closed if it
is missing, blank, a common placeholder, shorter than 32 characters, or made of
only one repeated character. Telegram permits 1-256 characters from `A-Z`,
`a-z`, `0-9`, `_`, and `-`; this application additionally requires at least 32
characters. The token is registered with Telegram and authenticated by the
receiver through the `X-Telegram-Bot-Api-Secret-Token` request header.

The built-in receiver speaks HTTP on `WEBHOOK_LISTEN:WEBHOOK_PORT`. Terminate
TLS at a reverse proxy on the same host and proxy only the configured path to
the loopback listener. For example, with the settings above, an HTTPS Nginx
server can use:

```nginx
location /webhook {
    proxy_pass http://127.0.0.1:8443;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
}
```

Do not expose port 8443 through the host firewall, and do not strip the
Telegram secret header in the proxy. `WEBHOOK_URL` must be the public HTTPS URL
whose path matches `WEBHOOK_PATH`.

A non-loopback receiver is not required for a same-host proxy. If a deployment
deliberately places the proxy elsewhere, the operator must explicitly set both
`WEBHOOK_LISTEN` to the desired interface and
`WEBHOOK_ALLOW_NON_LOOPBACK=true`, restrict that interface with firewall rules,
and provide a trusted private transport plus public TLS termination.

These `WEBHOOK_*` settings configure **only Telegram update delivery through
python-telegram-bot**. They are independent of the excluded FastAPI/GitHub
webhook surface: `ENABLE_API_SERVER`, `/webhooks/{provider}`,
`GITHUB_WEBHOOK_SECRET`, and generic-provider `WEBHOOK_API_SECRET` do not enable
or authenticate Telegram delivery, and Telegram delivery does not enable that
separate server.

## Environment-Specific Configuration

The bot automatically applies different settings based on the environment:

### Development Environment

Activated when `ENVIRONMENT=development` or when `DEBUG=true`:

- `debug = true`
- `development_mode = true`
- `log_level = "DEBUG"`
- `rate_limit_requests = 100` (more lenient)
- `claude_timeout_seconds = 600` (longer timeout)
- `enable_telemetry = false`

### Testing Environment

Activated when `ENVIRONMENT=testing`:

- `debug = true`
- `database_url = "sqlite:///:memory:"` (in-memory database)
- `approved_directory = "/tmp/test_projects"`
- `claude_timeout_seconds = 30` (faster timeout)
- `rate_limit_requests = 1000` (no effective rate limiting)

### Production Environment

Activated when `ENVIRONMENT=production`:

- `debug = false`
- `log_level = "INFO"`
- `enable_telemetry = true`
- `claude_max_cost_per_user = 5.0` (stricter cost limit)
- `rate_limit_requests = 5` (stricter rate limiting)
- `session_timeout_hours = 12` (shorter session timeout)

## Feature Flags

Feature flags allow you to enable or disable functionality dynamically:

```python
from src.config import load_config, FeatureFlags

config = load_config()
features = FeatureFlags(config)

if features.agentic_mode_enabled:
    # Use agentic mode handlers
    pass

if features.api_server_enabled:
    # Start webhook API server
    pass
```

Available feature flags:

- `agentic_mode_enabled`: Agentic conversational mode (default: true)
- `api_server_enabled`: Webhook API server
- `scheduler_enabled`: Cron job scheduler
- `mcp_enabled`: Model Context Protocol support
- `git_enabled`: Git integration commands
- `file_uploads_enabled`: File upload handling
- `quick_actions_enabled`: Quick action buttons
- `telemetry_enabled`: Anonymous usage telemetry
- `token_auth_enabled`: Token-based authentication
- `webhook_enabled`: Telegram webhook mode (vs polling)
- `development_features_enabled`: Development-only features

## Validation

The configuration system performs extensive validation:

### Path Validation

- `APPROVED_DIRECTORY` must exist and be accessible
- `MCP_CONFIG_PATH` must exist if MCP is enabled

### Cross-Field Validation

- `AUTH_TOKEN_SECRET` is required when `ENABLE_TOKEN_AUTH=true`
- `MCP_CONFIG_PATH` is required when `ENABLE_MCP=true`
- `WEBHOOK_SECRET_TOKEN` is required and must be random when `WEBHOOK_URL` is set
- `WEBHOOK_ALLOW_NON_LOOPBACK=true` is required for a non-loopback Telegram listener

### Value Validation

- `LOG_LEVEL` must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Numeric values must be positive where appropriate
- User IDs in `ALLOWED_USERS` must be valid integers

## Claude Integration Options

### Authentication Options

#### Option 1: Use Existing Claude CLI Authentication (Recommended)
```bash
# No ANTHROPIC_API_KEY needed - SDK will use CLI credentials
# Ensure Claude CLI is installed and authenticated: claude auth login
```

#### Option 2: Direct API Key
```bash
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

## Troubleshooting

### Common Issues

1. **"Approved directory does not exist"**
   - Ensure the path in `APPROVED_DIRECTORY` exists
   - Use absolute paths, not relative paths
   - Check file permissions

2. **"auth_token_secret required"**
   - Set `AUTH_TOKEN_SECRET` when using `ENABLE_TOKEN_AUTH=true`
   - Generate a secure secret: `openssl rand -hex 32`

3. **"MCP config file does not exist"**
   - Ensure `MCP_CONFIG_PATH` points to an existing file
   - Or disable MCP with `ENABLE_MCP=false`

## Security Considerations

- **Never commit secrets** to version control
- **Use environment variables** for sensitive data
- **Rotate tokens regularly** if using token-based auth
- **Restrict `APPROVED_DIRECTORY`** to only necessary paths
- **Monitor logs** for configuration errors and security events
