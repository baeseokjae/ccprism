---
name: deepseek
display_name: DeepSeek
enabled: true
auth_type: api_key

connection:
  api_base: https://api.deepseek.com

models:
  - id: deepseek-chat
    context_window: 128000
    input_cost_per_million: 0.27
    output_cost_per_million: 1.10
    capabilities: [text, code, fast, cost-efficient]

  - id: deepseek-reasoner
    context_window: 128000
    input_cost_per_million: 0.55
    output_cost_per_million: 2.19
    capabilities: [text, code, reasoning]

rate_limits:
  rpm: 300
  tpm: 1000000

health_check:
  enabled: true
  interval: 300
---

# DeepSeek Provider

## Authentication
Uses API Key authentication. Set `DEEPSEEK_API_KEY` environment variable.

## Models
- **deepseek-chat**: Very cost-effective general model
- **deepseek-reasoner**: Reasoning-specialized model, good alternative to o3
