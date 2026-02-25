---
name: gemini
display_name: Google Gemini
enabled: true
auth_type: oauth
oauth_flow: service_account

connection:
  vertex_project: ""
  vertex_location: us-central1

models:
  - id: gemini-2.5-pro
    context_window: 2000000
    input_cost_per_million: 1.25
    output_cost_per_million: 10.00
    capabilities: [text, code, vision, long-context]

  - id: gemini-2.5-flash
    context_window: 1000000
    input_cost_per_million: 0.15
    output_cost_per_million: 0.60
    capabilities: [text, code, fast]

rate_limits:
  rpm: 1000
  tpm: 4000000

health_check:
  enabled: true
  interval: 300
---

# Google Gemini Provider

## Authentication
Uses Google Cloud Application Default Credentials (ADC).
Run `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS`.

## Models
- **gemini-2.5-pro**: 2M token context window, ideal for large codebase analysis
- **gemini-2.5-flash**: Fast responses, suitable for simple tasks
