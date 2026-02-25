---
name: xai
display_name: xAI (Grok)
enabled: true
auth_type: api_key

connection:
  api_base: https://api.x.ai/v1

models:
  - id: grok-3
    context_window: 131072
    input_cost_per_million: 3.00
    output_cost_per_million: 15.00
    capabilities: [text, code, reasoning]

rate_limits:
  rpm: 60
  tpm: 400000

health_check:
  enabled: true
  interval: 300
---

# xAI (Grok) Provider

## Authentication
Uses API Key authentication. Set `XAI_API_KEY` environment variable.

## Models
- **grok-3**: Advanced reasoning model from xAI
