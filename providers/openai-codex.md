---
name: openai-codex
display_name: OpenAI Codex (OAuth)
enabled: true
auth_type: codex_oauth
auth_json_path: ~/.codex/auth.json

connection:
  api_base: https://api.openai.com/v1
  api_format: responses

models:
  - id: gpt-5.2-codex
    context_window: 400000
    input_cost_per_million: 1.75
    output_cost_per_million: 14.00
    max_output_tokens: 128000
    capabilities: [code, advanced, production]
    api_type: responses

  - id: gpt-5.1-codex
    context_window: 400000
    input_cost_per_million: 1.25
    output_cost_per_million: 10.00
    max_output_tokens: 128000
    capabilities: [code, stable]
    api_type: responses

  - id: gpt-5-codex
    context_window: 400000
    input_cost_per_million: 1.25
    output_cost_per_million: 10.00
    max_output_tokens: 128000
    capabilities: [code, baseline]
    api_type: responses

rate_limits:
  rpm: 60
  tpm: 500000

health_check:
  enabled: true
  interval: 60
---

# OpenAI Codex Provider (Codex CLI OAuth)

## Authentication
Uses Codex CLI OAuth tokens from `~/.codex/auth.json`.
Run `codex --full-auto` to authenticate. Requires ChatGPT Plus/Pro subscription.

## Models
- **gpt-5.2-codex**: Latest production Codex model ($1.75/1M input)
- **gpt-5.1-codex**: Stable, cost-effective ($1.25/1M input)
- **gpt-5-codex**: Baseline Codex model

All Codex models use the Responses API (`/v1/responses`).
