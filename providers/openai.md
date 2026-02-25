---
name: openai
display_name: OpenAI
enabled: true
auth_type: api_key

connection:
  api_base: https://api.openai.com/v1

models:
  - id: gpt-4.1
    context_window: 1000000
    input_cost_per_million: 2.00
    output_cost_per_million: 8.00
    capabilities: [text, code, vision, fast]

  - id: o3
    context_window: 200000
    input_cost_per_million: 10.00
    output_cost_per_million: 40.00
    capabilities: [text, code, reasoning]

rate_limits:
  rpm: 500
  tpm: 800000

health_check:
  enabled: true
  interval: 300
---

# OpenAI Provider (API Key)

## Authentication
Uses API Key authentication. Set `OPENAI_API_KEY` environment variable.

## Models
- **gpt-4.1**: Fast, capable general-purpose model with 1M context
- **o3**: Advanced reasoning model
