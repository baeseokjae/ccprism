# ccprism

> **[English Documentation](README.md)**

**Claude Code + Prism** — Claude Code의 Anthropic Messages API 요청을 Markdown 규칙 파일에 따라 여러 AI 프로바이더로 동적 라우팅하는 AI Gateway.

```
Claude Code  →  ccprism Gateway  →  Anthropic / OpenAI Codex / Gemini / DeepSeek / xAI / Groq / Ollama
```

## 주요 기능

- **Markdown 규칙 기반 라우팅** — YAML frontmatter로 라우팅 규칙을 정의하고, Markdown 본문이 문서 역할을 겸함
- **10가지 매처** — `thinking`, `token_count`, `tool`, `model`, `keyword`, `always`, `content_type`, `custom`, `time_range`, `ab_test`
- **Hot-reload** — 규칙 파일 변경 시 서버 재시작 없이 즉시 반영
- **자동 Fallback** — Primary 실패 시 Fallback 체인으로 자동 전환
- **Cost Tracking** — SQLite 기반 일별/월별 비용 모니터링 + 예산 알림
- **Admin API** — 규칙/통계/비용/프로바이더 관리 REST API
- **OS Keychain** — 3단 Credential 폴백: 환경변수 → OS Keychain → 암호화 Vault
- **Slack Alerts** — CRITICAL 로그를 Slack webhook으로 자동 전송
- **Security Checks** — 시작 시 민감 파일 퍼미션 검증 및 API Key 마스킹 로그
- **Codex OAuth** — `~/.codex/auth.json` 토큰 자동 재사용 및 갱신
- **멀티 프로바이더 인증** — API Key, Codex OAuth, Google ADC/Service Account
- **LiteLLM 기반** — 40+ AI 프로바이더 공통 인터페이스

---

## 빠른 시작

### 요구사항

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### 설치

```bash
git clone https://github.com/anthropics/ccprism
cd ccprism
uv sync
```

### 서버 시작

```bash
# 기본 시작 (0.0.0.0:8080)
uv run ccprism start

# 포트 지정
uv run ccprism start --port 9090

# 개발 모드 (파일 변경 시 자동 재시작)
uv run ccprism start --reload
```

### Claude Code 연결

```bash
export ANTHROPIC_BASE_URL=http://localhost:8080
# 또는 ~/.claude/settings.json에 추가:
# { "env": { "ANTHROPIC_BASE_URL": "http://localhost:8080" } }
```

이제 Claude Code의 모든 요청이 ccprism을 통해 라우팅됩니다.

---

## Docker로 실행

```bash
# 빌드 및 실행
docker compose up

# 환경변수로 API Key 전달
ANTHROPIC_API_KEY=sk-ant-... docker compose up
```

`docker-compose.yaml`에서 포트, 볼륨, 환경변수를 조정할 수 있습니다.

---

## 라우팅 규칙

규칙은 `rules/` 디렉토리의 `.md` 파일로 정의합니다. **priority 숫자가 낮을수록 먼저 평가**되며, 첫 번째로 매칭된 규칙이 적용됩니다.

### 규칙 파일 형식

```markdown
---
name: my-rule           # 소문자 영숫자, 하이픈, 언더스코어
enabled: true
priority: 10            # 0(높은 우선순위) ~ 999(낮은 우선순위)
description: "설명"

match:
  type: thinking        # 매처 종류 (아래 참고)

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

# 규칙 제목

Markdown 본문은 이 규칙에 대한 문서로 사용됩니다.
```

### 매처 종류

| 매처 | 조건 | 예시 |
|---|---|---|
| `always` | 항상 매칭 (catch-all) | `type: always` |
| `thinking` | `thinking.enabled == true` 요청 | `type: thinking` |
| `token_count` | 메시지 토큰 수 초과 | `type: token_count` + `threshold: 80000` |
| `tool` | 특정 도구 사용 요청 | `type: tool` + `tools: [web_search]` |
| `model` | 요청 모델명 regex 매칭 | `type: model` + `pattern: "^claude-haiku"` |
| `keyword` | 메시지 내 키워드 포함 | `type: keyword` + `keywords: [implement, debug]` |
| `content_type` | 이미지 등 content block 타입 매칭 | `type: content_type` + `content_types: [image]` |
| `custom` | 외부 Python 스크립트 동적 로딩 (`def match(request) -> bool`) | `type: custom` + `script_path: "/path/to/matcher.py"` |
| `time_range` | 시간대별 라우팅 (야간 절약 등) | `type: time_range` + `start_hour: 22` + `end_hour: 6` + `timezone: Asia/Seoul` |
| `ab_test` | 해시 기반 결정론적 A/B 테스트 | `type: ab_test` + `percentage: 20` + `experiment_name: "my-exp"` |

### 기본 제공 규칙

| 파일 | 우선순위 | 설명 |
|---|---|---|
| `10-thinking.md` | 10 | Extended thinking → Claude Opus |
| `10-long-context.md` | 10 | 80K+ 토큰 → Gemini 2.5 Flash |
| `15-codex-coding.md` | 15 | 코딩 키워드 → OpenAI Codex |
| `20-web-search.md` | 20 | web_search 도구 → GPT-4.1 |
| `20-background.md` | 20 | Haiku 모델 → DeepSeek |
| `30-image.md` | 30 | 이미지 content blocks → Claude Sonnet |
| `50-cost-saving.md` | 50 | 간단한 질문 → DeepSeek |
| `60-night-saving.md` | 60 | 야간 22:00–06:00 KST → DeepSeek |
| `00-default.md` | 999 | 기본 → Claude Sonnet |

### 라우팅 테스트 (Dry-run)

```bash
# 실제 요청 없이 어떤 규칙/프로바이더로 라우팅되는지 확인
uv run ccprism test-route "코드를 리팩토링해줘"
uv run ccprism test-route "긴 문서를 요약해줘" --model claude-sonnet-4-6
uv run ccprism test-route "검색해줘" --tools web_search
uv run ccprism test-route "깊이 생각해줘" --thinking
```

---

## 설정

### `config/gateway.yaml`

```yaml
server:
  host: "0.0.0.0"
  port: 8080

logging:
  level: "INFO"
  format: "json"
  file: ""

rules_dir: "rules"
litellm_config_path: "config/litellm_config.yaml"

budget:
  monthly_usd: 0.0           # 0 = 예산 제한 없음
  cost_db_path: "~/.ccprism/costs.db"
  retention_days: 90

monitoring:
  slack_webhook_url: ""
  alert_level: "CRITICAL"
```

환경변수로 오버라이드 가능 (`CCPRISM_` 접두사):

```bash
CCPRISM_SERVER__PORT=9090 uv run ccprism start
CCPRISM_LOGGING__LEVEL=DEBUG uv run ccprism start
```

### `config/litellm_config.yaml`

LiteLLM 모델 목록과 라우터 설정:

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

## 프로바이더 인증

### Credential Fallback 체인

ccprism은 다음 순서로 Credential을 조회합니다:

```
환경변수  →  OS Keychain  →  암호화 Vault
```

### API Key (환경변수)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export DEEPSEEK_API_KEY=sk-...
export XAI_API_KEY=xai-...
export GROQ_API_KEY=gsk_...
export GEMINI_API_KEY=AIza...
```

### `ccprism auth add`로 키 저장

`--store` 옵션으로 저장 위치를 선택합니다:

```bash
# OS Keychain에 저장 (macOS Keychain / Linux SecretService / Windows Credential Locker)
uv run ccprism auth add anthropic --key sk-ant-... --store keychain

# 암호화 로컬 Vault에 저장 (~/.ccprism/credentials.enc)
uv run ccprism auth add anthropic --key sk-ant-... --store vault

# 환경변수 export 명령 출력 (기본값)
uv run ccprism auth add anthropic --key sk-ant-... --store env
```

### OpenAI Codex OAuth

Codex CLI로 로그인하면 `~/.codex/auth.json`이 자동 생성됩니다. ccprism은 이 파일을 자동으로 읽어 토큰을 재사용하고, 만료 시 자동으로 갱신합니다.

```bash
# Codex CLI 로그인 (별도 설치 필요)
codex login

# ccprism에서 Codex 인증 상태 확인
uv run ccprism auth status
```

### Google Vertex AI

Application Default Credentials(ADC)를 사용합니다:

```bash
gcloud auth application-default login
```

서비스 계정을 사용하려면 `GOOGLE_APPLICATION_CREDENTIALS` 환경변수를 설정하세요.

---

## Admin API

게이트웨이는 `/admin` 경로에 런타임 관리용 REST API를 제공합니다.

| 엔드포인트 | 설명 |
|---|---|
| `GET /admin/rules` | 로드된 규칙 목록 |
| `GET /admin/rules/{name}` | 단일 규칙 상세 정보 |
| `POST /admin/rules/reload` | 규칙 강제 재로드 |
| `GET /admin/stats` | 요청 통계 (전체/성공/실패/규칙별/프로바이더별) |
| `GET /admin/providers` | 프로바이더 상태 및 Credential 상태 |
| `GET /admin/costs/summary` | 이번 달 총 비용 + 예산 현황 |
| `GET /admin/costs/daily` | 일별 비용 (기본: 최근 7일) |
| `GET /admin/costs/by-provider` | 프로바이더별 비용 (기본: 최근 30일) |
| `GET /admin/costs/by-rule` | 규칙별 비용 (기본: 최근 30일) |

```bash
# 사용 예시
curl http://localhost:8080/admin/rules
curl http://localhost:8080/admin/stats
curl http://localhost:8080/admin/costs/summary
curl "http://localhost:8080/admin/costs/daily?days=14"
```

---

## CLI 명령어

```
ccprism start                   서버 시작
  --host HOST                   바인딩 호스트 (기본: 0.0.0.0)
  --port PORT                   포트 (기본: 8080)
  --reload                      개발 모드 자동 재시작
  --config CONFIG               gateway.yaml 경로

ccprism auth status             모든 프로바이더 인증 상태 확인
ccprism auth add PROVIDER       프로바이더 API Key 설정
  --key KEY                     API Key 값
  --store keychain|vault|env    저장 위치 (기본: env)

ccprism rules list              로드된 규칙 목록 표시
ccprism rules validate          규칙 파일 유효성 검사
ccprism rules reload            규칙 강제 재로드

ccprism costs summary           월별 비용 요약 + 예산 현황
ccprism costs daily             일별 비용 테이블
  --days N                      표시할 일수 (기본: 7)

ccprism status                  실행 중인 게이트웨이 상태 확인
ccprism test-route PROMPT       라우팅 dry-run 테스트
  --model MODEL                 요청 모델명
  --thinking                    thinking 활성화
  --tools TOOL ...              사용 도구 지정
```

---

## 아키텍처

```
┌────────────────────────────────────────────────────────────────────┐
│                          ccprism Gateway                           │
│                                                                    │
│  POST /v1/messages                                                 │
│       │                                                            │
│       ▼                                                            │
│  MDRuleBasedRouting ──→ RuleEngine.evaluate()                      │
│  (규칙 평가 + 모델 선택)       (매처 순회, first-match)            │
│       │                                                            │
│       ├──→ StatsCollector  (요청 통계)                             │
│       │                                                            │
│       ▼                                                            │
│  LiteLLM Router                                                    │
│       │                                                            │
│       ▼                                                            │
│  GatewayHooks.async_pre_call_hook()                                │
│  (Credential 주입)                                                 │
│       │                                                            │
│       ▼                                                            │
│  CredentialManager ──→ Adapter (Codex / Google / APIKey)          │
│       │                       ↑                                    │
│       │              환경변수 → Keychain → Vault                   │
│       │                                                            │
│  GatewayHooks.async_post_call_hook()                               │
│       │                                                            │
│       ├──→ CostTracker ──→ CostDB (SQLite)                        │
│       └──→ BudgetAlert  (80% 경고 / 100% CRITICAL)               │
│                                                                    │
│  시작 시                                                           │
│       └──→ SecurityChecks (파일 퍼미션 + API Key 마스킹)          │
│                                                                    │
│  로깅                                                              │
│       └──→ AlertHandler ──→ Slack webhook (CRITICAL 레벨)        │
└────────────────────────────────────────────────────────────────────┘
```

**역할 분리 원칙:**
- `MDRuleBasedRouting`: 규칙 평가 + 프로바이더 선택만
- `GatewayHooks`: Credential 주입, 비용 기록
- `CredentialManager`: 프로바이더별 Adapter 관리 + Fallback 체인
- `StatsCollector`: 인메모리 Thread-safe 요청 카운터
- `CostTracker` + `CostDB`: LiteLLM 응답에서 비용 추출 + SQLite 저장
- `BudgetAlert`: 월별 지출 모니터링 (80% 경고 / 100% CRITICAL)
- `AlertHandler`: CRITICAL 로그를 Slack webhook으로 전송
- `SecurityChecks`: 시작 시 파일 퍼미션 및 Credential 노출 검사

### 인증 2계층

| 계층 | 역할 |
|---|---|
| Layer 1: Client → Gateway | JWT / Master Key / 로컬 모드(우회) |
| Layer 2: Gateway → Provider | API Key / Codex OAuth / Google ADC |

---

## 개발

```bash
# 테스트 실행
uv run pytest

# 특정 테스트 파일
uv run pytest tests/test_rule_engine.py -v

# 린트 검사
uv run ruff check src/ tests/

# 타입 체크
uv run mypy src/
```

### 커스텀 규칙 추가

1. `rules/` 디렉토리에 새 `.md` 파일 생성
2. YAML frontmatter에 규칙 정의
3. 파일 저장 — 서버가 자동으로 재로드 (Hot-reload)

```bash
# 규칙 유효성 확인
uv run ccprism rules validate

# 라우팅 테스트
uv run ccprism test-route "테스트 프롬프트"
```

---

## 라이선스

MIT License — [LICENSE](LICENSE) 참고
