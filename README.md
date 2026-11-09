# ccprism

> **[한국어 문서 (Korean)](README.ko.md)**

**Claude Code + Prism** — An AI Gateway that dynamically routes Anthropic Messages API requests from Claude Code to multiple AI providers based on Markdown rule files.

```
Claude Code  →  ccprism Gateway  →  Anthropic / OpenAI Codex / Gemini / DeepSeek / xAI / Groq / Ollama
```

## Features

- **Markdown Rule-Based Routing** — Define routing rules in YAML frontmatter; Markdown body doubles as documentation
- **10 Matchers** — `thinking`, `token_count`, `tool`, `model`, `keyword`, `always`, `content_type`, `custom`, `time_range`, `ab_test`
- **Hot-reload** — Rule file changes are applied instantly without restarting the server
- **Automatic Fallback** — Automatically switches to fallback chain when primary provider fails
- **Cost Tracking** — SQLite-based daily/monthly cost monitoring with budget alerts
- **Admin API** — REST API for managing rules, stats, costs, and providers
- **OS Keychain** — Three-tier credential fallback: Environment Variable → OS Keychain → Encrypted Vault
- **Slack Alerts** — CRITICAL log entries are automatically forwarded to Slack webhook
- **Security Checks** — Sensitive file permission validation and API key masked logging at startup
- **Codex OAuth** — Automatic reuse and refresh of `~/.codex/auth.json` tokens
- **Multi-Provider Auth** — API Key, Codex OAuth, Google ADC/Service Account
- **LiteLLM-based** — Unified interface for 40+ AI providers

---

## Quick Start

### Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### Installation

```bash
git clone https://github.com/anthropics/ccprism
cd ccprism
uv sync
```

### Start Server

```bash
# Generate a gateway-only key (keep it private; never commit it)
export CCPRISM_AUTH__GATEWAY_MASTER_KEY="$(openssl rand -hex 32)"

# Default (127.0.0.1:8080, authentication required)
uv run ccprism start

# Custom port
uv run ccprism start --port 9090

# Development mode (auto-restart on file changes)
uv run ccprism start --reload
```

### Connect Claude Code

```bash
export ANTHROPIC_BASE_URL=http://localhost:8080
export ANTHROPIC_AUTH_TOKEN="$CCPRISM_AUTH__GATEWAY_MASTER_KEY"
# Or add to ~/.claude/settings.json:
# { "env": { "ANTHROPIC_BASE_URL": "http://localhost:8080",
#              "ANTHROPIC_AUTH_TOKEN": "<your gateway token>" } }
```

All Claude Code requests are now routed through ccprism. Set the same gateway token
in the client shell; provider API keys remain separate and are not gateway credentials.

---

## Docker

```bash
# Set CCPRISM_AUTH__GATEWAY_MASTER_KEY as above, then build and run
docker compose up

# Pass API keys via environment variables
ANTHROPIC_API_KEY=sk-ant-... docker compose up
```

Compose publishes only `127.0.0.1:8080` and requires a gateway master key. The
container listens on all interfaces internally so port forwarding works. For
manual `docker run`, use `-p 127.0.0.1:8080:8080`, not `-p 8080:8080`.
Port, volumes, and environment variables can be adjusted in `docker-compose.yaml`.

---

## Routing Rules

Rules are defined as `.md` files in the `rules/` directory. **Lower priority numbers are evaluated first.** The first matching rule is applied.

### Rule File Format

```markdown
---
name: my-rule           # lowercase alphanumeric, hyphens, underscores
enabled: true
priority: 10            # 0 (highest) ~ 999 (lowest)
description: "Description"

match:
  type: thinking        # see matcher types below

route:
  primary:
    provider: anthropic
    model: claude-opus-4-6
  fallback:
    - provider: deepseek
      model: deepseek-reasoner

tags:
  - reasoning
---

# Rule Title

Markdown body is used as documentation for this rule.
```

### Matcher Types

| Matcher | Condition | Example |
|---|---|---|
| `always` | Always matches (catch-all) | `type: always` |
| `thinking` | Request with `thinking.enabled == true` | `type: thinking` |
| `token_count` | Message token count exceeds threshold | `type: token_count` + `threshold: 80000` |
| `tool` | Request uses a specific tool | `type: tool` + `tools: [web_search]` |
| `model` | Request model name matches regex | `type: model` + `pattern: "^claude-haiku"` |
| `keyword` | Message contains any of the keywords | `type: keyword` + `keywords: [implement, debug]` |
| `content_type` | Message contains specific content block type (e.g., image) | `type: content_type` + `content_types: [image]` |
| `custom` | External Python script with `def match(request) -> bool` | `type: custom` + `script_path: "/path/to/matcher.py"` |
| `time_range` | Request arrives within a specified hour range | `type: time_range` + `start_hour: 22` + `end_hour: 6` + `timezone: Asia/Seoul` |
| `ab_test` | Hash-based deterministic A/B test bucket | `type: ab_test` + `percentage: 20` + `experiment_name: "my-exp"` |

### Built-in Rules

| File | Priority | Description |
|---|---|---|
| `10-thinking.md` | 10 | Extended thinking → Claude Opus |
| `10-long-context.md` | 10 | 80K+ tokens → Gemini 2.5 Flash |
| `15-codex-coding.md` | 15 | Coding keywords → OpenAI Codex |
| `20-web-search.md` | 20 | `web_search` tool → GPT-4.1 |
| `20-background.md` | 20 | Haiku model → DeepSeek |
| `30-image.md` | 30 | Image content blocks → Claude Sonnet |
| `50-cost-saving.md` | 50 | Simple questions → DeepSeek |
| `60-night-saving.md` | 60 | Nighttime 22:00–06:00 KST → DeepSeek |
| `00-default.md` | 999 | Default → Claude Sonnet |

### Routing Dry-run

```bash
# Preview which rule/provider will be selected without making a real request
uv run ccprism test-route "Refactor this code"
uv run ccprism test-route "Summarize this document" --model claude-sonnet-4-6
uv run ccprism test-route "Search for this" --tools web_search
uv run ccprism test-route "Think deeply" --thinking
```

---

## Configuration

### `config/gateway.yaml`

```yaml
server:
  host: "127.0.0.1"
  port: 8080

logging:
  level: "INFO"
  format: "json"
  file: ""

rules_dir: "rules"
litellm_config_path: "config/litellm_config.yaml"

budget:
  monthly_usd: 0.0           # 0 = no budget limit
  cost_db_path: "~/.ccprism/costs.db"
  retention_days: 90

monitoring:
  slack_webhook_url: ""
  alert_level: "CRITICAL"
```

Override with environment variables using the `CCPRISM_` prefix:

```bash
CCPRISM_SERVER__PORT=9090 uv run ccprism start
CCPRISM_LOGGING__LEVEL=DEBUG uv run ccprism start
```

### `config/litellm_config.yaml`

LiteLLM model list and router settings:

```yaml
model_list:
  - model_name: anthropic/claude-sonnet-4-6
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: openai/gpt-4.1
    litellm_params:
      model: openai/gpt-4.1
      api_key: os.environ/OPENAI_API_KEY

router_settings:
  num_retries: 2
  cooldown_time: 30
```

---

## Provider Authentication

### Credential Fallback Chain

ccprism resolves credentials in the following order:

```
Environment Variable  →  OS Keychain  →  Encrypted Vault
```

### API Keys (Environment Variables)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export DEEPSEEK_API_KEY=sk-...
export XAI_API_KEY=xai-...
export GROQ_API_KEY=gsk_...
export GEMINI_API_KEY=AIza...
```

### Storing Keys with `ccprism auth add`

Use `--store` to choose where credentials are persisted:

```bash
# Store in OS Keychain (macOS Keychain / Linux SecretService / Windows Credential Locker)
uv run ccprism auth add anthropic --key sk-ant-... --store keychain

# Store in encrypted local Vault (~/.ccprism/credentials.enc)
uv run ccprism auth add anthropic --key sk-ant-... --store vault

# Print export command for environment variable (default)
uv run ccprism auth add anthropic --key sk-ant-... --store env
```

### OpenAI Codex OAuth

Log in with Codex CLI to auto-generate `~/.codex/auth.json`. ccprism reads this file automatically, reusing and refreshing tokens as needed.

```bash
# Codex CLI login (requires separate installation)
codex login

# Check Codex auth status in ccprism
uv run ccprism auth status
```

### Google Vertex AI

Uses Application Default Credentials (ADC):

```bash
gcloud auth application-default login
```

Set `GOOGLE_APPLICATION_CREDENTIALS` to use a service account.

---

## Admin API

The gateway exposes a REST API at `/admin` for runtime management.

| Endpoint | Description |
|---|---|
| `GET /admin/rules` | List all loaded routing rules |
| `GET /admin/rules/{name}` | Get detailed information for a single rule |
| `POST /admin/rules/reload` | Force reload all rules from disk |
| `GET /admin/stats` | Request statistics (total, success, failure, rule matches, provider calls) |
| `GET /admin/providers` | Provider status and credential health |
| `GET /admin/costs/summary` | Current month total cost and budget status |
| `GET /admin/costs/daily` | Daily cost breakdown (default: last 7 days) |
| `GET /admin/costs/by-provider` | Cost summary grouped by provider (default: last 30 days) |
| `GET /admin/costs/by-rule` | Cost summary grouped by rule (default: last 30 days) |

```bash
# Examples
curl -H "x-api-key: $CCPRISM_AUTH__GATEWAY_MASTER_KEY" http://localhost:8080/admin/rules
curl -H "x-api-key: $CCPRISM_AUTH__GATEWAY_MASTER_KEY" http://localhost:8080/admin/stats
curl -H "x-api-key: $CCPRISM_AUTH__GATEWAY_MASTER_KEY" http://localhost:8080/admin/costs/summary
curl -H "x-api-key: $CCPRISM_AUTH__GATEWAY_MASTER_KEY" "http://localhost:8080/admin/costs/daily?days=14"
```

---

## CLI Commands

```
ccprism start                   Start the gateway server
  --host HOST                   Bind host (default: 127.0.0.1)
  --port PORT                   Port (default: 8080)
  --reload                      Development mode auto-restart
  --config CONFIG               Path to gateway.yaml

ccprism auth status             Show credential status for all providers
ccprism auth add PROVIDER       Add API key for a provider
  --key KEY                     API key value
  --store keychain|vault|env    Storage backend (default: env)

ccprism rules list              Display loaded rules
ccprism rules validate          Validate all rule files
ccprism rules reload            Force reload rules from disk

ccprism costs summary           Current month cost summary with budget status
ccprism costs daily             Daily cost table
  --days N                      Number of days to show (default: 7)

ccprism status                  Check running gateway status
ccprism test-route PROMPT       Dry-run routing test
  --model MODEL                 Request model name
  --thinking                    Enable thinking
  --tools TOOL ...              Specify tools to include
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          ccprism Gateway                           │
│                                                                    │
│  POST /v1/messages                                                 │
│       │                                                            │
│       ▼                                                            │
│  MDRuleBasedRouting ──→ RuleEngine.evaluate()                      │
│  (rule evaluation + model selection)  (matchers, first-match)     │
│       │                                                            │
│       ├──→ StatsCollector  (request statistics)                    │
│       │                                                            │
│       ▼                                                            │
│  LiteLLM Router                                                    │
│       │                                                            │
│       ▼                                                            │
│  GatewayHooks.async_pre_call_hook()                                │
│  (credential injection)                                            │
│       │                                                            │
│       ▼                                                            │
│  CredentialManager ──→ Adapter (Codex / Google / APIKey)          │
│       │                       ↑                                    │
│       │              Env → Keychain → Vault                        │
│       │                                                            │
│  GatewayHooks.async_post_call_hook()                               │
│       │                                                            │
│       ├──→ CostTracker ──→ CostDB (SQLite)                        │
│       └──→ BudgetAlert  (80% warning / 100% critical)             │
│                                                                    │
│  Startup                                                           │
│       └──→ SecurityChecks (file permissions + API key masking)    │
│                                                                    │
│  Logging                                                           │
│       └──→ AlertHandler ──→ Slack webhook (CRITICAL level)        │
└────────────────────────────────────────────────────────────────────┘
```

**Separation of Concerns:**
- `MDRuleBasedRouting`: Rule evaluation and provider selection only
- `GatewayHooks`: Credential injection, cost recording
- `CredentialManager`: Per-provider adapter management with fallback chain
- `StatsCollector`: In-memory thread-safe request counters
- `CostTracker` + `CostDB`: LiteLLM response cost extraction and SQLite persistence
- `BudgetAlert`: Monthly spend monitoring with warning/critical thresholds
- `AlertHandler`: Forwards CRITICAL log records to Slack webhook
- `SecurityChecks`: File permission and credential exposure checks at startup

### Authentication Layers

| Layer | Role |
|---|---|
| Layer 1: Client → Gateway | JWT / Master Key / Explicit loopback-only local mode |
| Layer 2: Gateway → Provider | API Key / Codex OAuth / Google ADC |

---

## Gateway Security

- Authentication is enabled by default. Startup refuses missing or shorter-than-32-character
  master/JWT keys, conflicting local-mode settings, and unauthenticated remote binding.
  Use randomly generated keys rather than passwords. Configure secrets through environment
  variables, never a committed YAML file.
- `/v1/messages` accepts `x-api-key` or `Authorization: Bearer` credentials. The master key
  is an administrator credential. HS256 JWTs require `sub` and `exp`; a token with
  `role: user` may proxy requests but cannot manage the gateway.
- `/admin/*`, `/auth/status`, and all embedded `/oauth/*` endpoints require administrator
  access. The embedded OAuth server is development scaffolding with in-memory state, not
  a public OAuth service. Token exchange/refresh also require admin authentication, and
  issuance is unavailable unless `CCPRISM_AUTH__JWT_SECRET_KEY` is configured. Provider
  Codex OAuth credential reuse is separate and unchanged.
- `/health` is the only public application endpoint and returns minimal liveness data.
  Interactive API documentation and OpenAPI discovery are disabled.
- `CCPRISM_` nested environment values now override YAML, for example
  `CCPRISM_AUTH__GATEWAY_MASTER_KEY` and `CCPRISM_SERVER__PORT`. `start --config` loads
  the selected file; `--host` and `--port` override it, including reload workers.
  The old unprefixed `GATEWAY_MASTER_KEY` Compose variable is no longer used.
- For a deliberate local-only development opt-out, set both `CCPRISM_AUTH__ENABLED=false`
  and `CCPRISM_AUTH__LOCAL_MODE=true`. Only loopback binding, loopback peers, and loopback
  Host values are allowed. Requests with Origin or Fetch Metadata headers are rejected.
  Never use this mode behind a reverse proxy. Local processes are trusted in this mode.
- Remote access is opt-in: configure authentication before `--host 0.0.0.0`, and use TLS,
  a firewall, and restricted access. Do not expose this development gateway directly to
  the public internet. The CLI/container disable proxy-header trust by default.

## Development

```bash
# Run tests
uv run pytest

# Specific test file
uv run pytest tests/test_rule_engine.py -v

# Lint check
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

### Adding Custom Rules

1. Create a new `.md` file in the `rules/` directory
2. Define the rule in YAML frontmatter
3. Save the file — the server reloads it automatically (hot-reload)

```bash
# Validate rules
uv run ccprism rules validate

# Test routing
uv run ccprism test-route "test prompt"
```

---

## License

MIT License — see [LICENSE](LICENSE)

For Korean documentation, see [README.ko.md](README.ko.md).
