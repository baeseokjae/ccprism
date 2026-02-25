---
name: anthropic
display_name: Anthropic Claude
enabled: true
auth_type: api_key

connection:
  api_base: https://api.anthropic.com

models:
  - id: claude-opus-4-6
    context_window: 200000
    input_cost_per_million: 15.00
    output_cost_per_million: 75.00
    capabilities: [text, code, vision, reasoning]

  - id: claude-sonnet-4-6
    context_window: 200000
    input_cost_per_million: 3.00
    output_cost_per_million: 15.00
    capabilities: [text, code, vision, fast]

rate_limits:
  rpm: 100
  tpm: 400000

health_check:
  enabled: true
  interval: 300
---

# Anthropic Claude Provider

## Authentication
Uses API Key authentication. Set `ANTHROPIC_API_KEY` environment variable.

## Models
- **claude-opus-4-6**: Most capable model, best for reasoning and complex tasks
- **claude-sonnet-4-6**: Balanced performance and cost, default model
