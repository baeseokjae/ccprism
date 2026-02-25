---
name: ollama
display_name: Ollama (Local)
enabled: true
auth_type: none

connection:
  api_base: http://localhost:11434

models:
  - id: "qwen2.5-coder:32b"
    context_window: 32768
    input_cost_per_million: 0
    output_cost_per_million: 0
    capabilities: [code, local]

rate_limits:
  rpm: 0
  tpm: 0

health_check:
  enabled: false
---

# Ollama Provider (Local)

## Authentication
No authentication required. Runs locally.

## Setup
Install Ollama and pull models:
```bash
ollama pull qwen2.5-coder:32b
```

## Models
- **qwen2.5-coder:32b**: Local coding model, no cost
