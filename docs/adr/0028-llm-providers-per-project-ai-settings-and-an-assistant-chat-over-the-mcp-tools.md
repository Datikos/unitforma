# ADR-0028: Language models (Claude, OpenAI) behind one text provider, AI settings per project, and an assistant chat in the admin app that works through the Unitforma MCP tools

- **Status:** proposed (2026-10-27). Widens two earlier scope lines: ADR-0015 put "the Unitforma backend calling a model itself" out of scope, and ADR-0025 put "an agent over MCP" out of scope and rejected its Option B (a model drives the setup pipeline). ADR-0025 Option A stands: the deterministic solver stays the pipeline; a language model gets only the residue the solver hands to the person, and a chat that works through the same tools a person's assistant already has (ADR-0015). Picks up ADR-0025 Revisit ("an MCP tool that reports the checklist and runs the solver", facade sides from title text, layout facts on the proposed layout), ADR-0023 Revisit (a per-project prompt override, its Option D) and backlog #31 (MCP tools beyond projects and buildings).
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner). Three picks are his before "start": who pays for the model calls (Decision 9 takes platform keys with caps as the default), which OpenAI model tier is the default (Decision 2 lists prices, not capability), and whether the chat may run write tools at all in phase 1 (Decision 6 takes "yes, each write approved in the chat").
- **Plan reference:** §8.6 (abuse protection), §11.2 (Setup and Settings screens), §12.2 (API boundaries), §12.3 (jobs), §13.2 (automation classification), §21 (sources), ADR-0015 (MCP server, tokens, `request_id = mcp:<prefix>`), ADR-0017 Decision 4 (image provider interface), ADR-0021 (retention sweep), ADR-0023 (workspace settings), ADR-0025 Decisions 3 to 5, 8 and 9 (solver, passes, settings with `none` defaults)

## Context

The owner's request of 2026-10-27: integrate language models (Claude, OpenAI) to "simplify autonomy of the
setup", to get "a more granular configuration for each project", and to explore a chat that uses MCP to solve
tasks such as "give me a merged view of the A 21, A22 apartments dollhouse image". What `main` has on
2026-10-27:

- **One model provider, images only.** `renders/provider.py` defines `ImageProvider.edit(image, mime, prompt)`
  and `describe(image, mime, prompt) -> str`; `renders/gemini.py` is the one implementation, over `httpx`
  against one fixed https host, key from the file secret `ai_image_api_key`, settings `UF_AI_IMAGE_*`
  (ADR-0017 Decision 4). `describe` is used by one caller, the solver's classify pass, which sends a 1024 px
  JPEG of a drawing page and parses one word (ADR-0025 Decision 5). There is no text-only call to any model
  anywhere, and no tool-calling adapter.
- **The solver is deterministic and leaves a residue.** `autopilot/service.py` runs the eleven passes of ADR-0025
  Decision 5 and records every decision in `setup_runs.summary.decisions[]` with `step, kind, entity, detail,
  confidence, needs_you, link`. On permit 1127975 (ADR-0025 D3, 2026-10-27) the residue it handed over was:
  the kinds of the documents whose pages the vision pass may not see (text-heavy sheets, ADR-0025 D2), labels
  printed twice on one sheet ("7" at 0.65), the ten proposed plan types with codes `L1`..`L7` and no names,
  the split-level blocks (ADR-0025 D3 keeps them a proposal). The facades pass wrote nothing there ("facades 0,
  needs the placed building"); by rule it writes at 0.6 with "verify which of the two parallel sides" once the
  building is placed, and reading the sheet title would let it decide the side even then. Each of these is a reading of printed words (sheet titles such as
  "ფასადი ღერძებში 1-9", room labels, legends), not of geometry. `passes/facades.py` says in its docstring
  that axis labels in the titles are "a later refinement".
- **Settings live on three levels already, each with one home.** Deployment: `core/settings.py` (`UF_AI_IMAGE_*`,
  `UF_AI_CLASSIFY`, `UF_GEOCODER`, each defaulting to off). Workspace: `tenants.settings` JSONB with one key,
  `render_prompt`, edited on the Settings page behind `tenant.settings` (ADR-0023). Project: `projects.setup_auto`
  JSONB `{enabled, approve_sheets, requested_by, since}`, edited on the setup checklist behind project write
  (ADR-0025 Decision 2). A project cannot turn the vision classifier on or off, pick a model, or override the
  render prompt (ADR-0023 Option D, "revisit if a second style is ever wanted").
- **Tools exist, for external assistants only.** `mcp/server.py` registers 13 tools (`whoami`, projects,
  buildings, floors, floor proposal, site features) on the SDK's `MCPServer`, each a thin wrapper over a service
  function returning the `api/schemas.py` shapes; `mcp/auth.py` verifies a bearer `api_tokens` row, puts a
  `TokenPrincipal` in a `ContextVar`, and `tenant_ctx(write=...)` builds the same `TenantContext` as the admin
  API, refusing a `read` token before a write tool. Audit rows carry `request_id = "mcp:" + token_prefix` through
  `audit.service.set_audit_origin`. There are no tools for units, documents, renders, layouts or the setup
  checklist (backlog #31). Nothing in the admin app talks to a model.
- **The example task is one existing write.** "A merged view of A 21 and A22" is a joined render:
  `renders/service.request_render(unit, note, actor, partner=...)` requires the partner on the same floor and
  building (422 otherwise) with an outline on the same sheet (409 otherwise); the worker cuts an opening into the
  shared wall and appends `JOINED_PROMPT`; the image belongs to the first unit as private `unit_media(kind =
  plan_render)` until a reviewer approves it (ADR-0017 E4). The API takes it as `POST /units/{id}/renders` with
  `RenderRequest.with_unit_id`. A chat therefore needs: find two units by code in a project (the owner typed
  "A 21" and "A22": lookup must ignore spaces and case), request the render, report its status, and show the
  image for the human review, which stays human. Units on different floors get the 422 text as the answer.
- **The MCP endpoint is sized for a person's client.** Caddy's `mcp_by_ip` zone allows 120 requests per minute
  per IP and `transport_security` allows the admin host and its origin only (ADR-0015 Decision 1). A vendor's
  shared egress calling it on behalf of many users would hit the per-IP zone first.
- **Jobs, not requests, do the slow work.** `renders.generate` and `setup.autopilot` run on the `docs` queue;
  the setup page polls every 5 s while a run is queued or running (ADR-0025 Decision 7). The admin API holds no
  request across an outbound call (plan §12.3).
- Migrations are at `0019_setup_autopilot`; the retention sweep (ADR-0021) owns per-kind grace periods in
  `core/settings.py` (`retention_*`).

Third-party facts (read 2026-10-27 unless stated; URLs in plan §21):

| Fact | Value | Source |
|---|---|---|
| Claude Opus 5.5 | API id `claude-opus-5-5`; $4 input, $20 output, $0.20 cache read per 1M tokens; 1M context, 128K output; retirement not sooner than 2027-09-22; Batch API 50 % off | platform.claude.com pricing page and models overview, read 2026-10-27 |
| Claude Sonnet 5.5 | API id `claude-sonnet-5-5`; $2 / $10 / $0.10 per 1M tokens; retirement not sooner than 2027-09-28 | same pages |
| Claude Haiku 5.5 | API id `claude-haiku-5-5`; $0.10 / $0.50 / $0.01 per 1M tokens for prompts up to 100 000 tokens; $0.50 / $2.50 above; the overview names it "for high-volume, latency-sensitive tasks such as classification, extraction"; retirement not sooner than 2027-10-07 | same pages |
| Tool use overhead | 286 tokens of system prompt per request with tools on Opus 5.5, plus the tool schemas, `tool_use` and `tool_result` blocks | same page |
| Anthropic training on API data | "By default, we will not use your inputs or outputs from our commercial products" (page dated 2026-08-18); the default retention period is not stated on that page: **unverified** | privacy.claude.com article 7996868 |
| `anthropic` Python SDK | 2.3.0 reported by PyPI (version **unverified**: the release list was truncated), Apache-2.0, Python ≥ 3.10, depends on `httpx2 >= 2, < 3`, `pydantic < 3`, `anyio < 5` | pypi.org/pypi/anthropic/json |
| Anthropic MCP connector | beta header `mcp-client-2025-11-20`; `mcp_servers[{type: url, url, name, authorization_token}]` plus `tools[{type: mcp_toolset, mcp_server_name}]`; "The server must be publicly exposed through HTTP (supports both Streamable HTTP and SSE transports)"; `zdr: not-eligible` | platform.claude.com MCP connector page |
| Claude model behaviour | Opus 5.5 and Sonnet 5.5 refuse forced `tool_choice` (`any`, `tool`) with 400; thinking blocks are bound to the model and the conversation, so the stored history must be appended to, never edited; `stop_reason = refusal` is a normal 200 to handle | SDK skill documentation bundled with the assistant, not a page read today: **per SDK docs, unverified here** |
| OpenAI text models | per 1M tokens, standard tier: `gpt-5.5` $5 / $30 (cached $0.50); `gpt-5.4` $2.50 / $15; `gpt-5.4-mini` $0.75 / $4.50; `gpt-5.4-nano` $0.20 / $1.25; `gpt-6-sol` $2 / $10; `gpt-6.1-terra` $1 / $5; `gpt-6-luna` $0.10 / $0.50 (no page date). Which tier matches Opus 5.5 or Haiku 5.5 in capability is **unverified** | developers.openai.com pricing page |
| `openai` Python SDK | 3.39.0, Apache-2.0, Python ≥ 3.10, depends on `httpx2 >= 2.12, < 3`, `pydantic < 3` | pypi.org/pypi/openai/json |
| OpenAI remote MCP tool | Responses API `tools[{type: "mcp", server_url, server_label, authorization, require_approval, allowed_tools}]`; the API calls the server itself (`mcp_list_tools`, `mcp_call`); private servers through "Secure MCP Tunnel" | developers.openai.com tools-remote-mcp guide |
| OpenAI data use | API data not used for training unless opted in; abuse-monitoring logs up to 30 days | plan §21 (read 2026-10-26) |
| `httpx2` beside `httpx` | the `mcp` package already brought `httpx2` 2.16.0 next to `httpx` 0.28.1 and `uv lock` resolved it (ADR-0015 #4, 2026-10-26); a second and third dependent on `httpx2` is **unverified until `uv lock`** | ADR-0015 |

Estimated cost of one chat turn (not measured; action item E1 measures the first real turn): a fixed prefix
of system text and 25 tool schemas of about 6 000 tokens, cached after the first call ($0.0012 per read on Opus
5.5), plus about 2 000 tokens of history and tool results per step and about 300 output tokens per step. A turn
with four tool calls (find units, request render, two status reads) is about 5 steps, 10 000 uncached input
tokens and 1 500 output tokens: about $0.07 on Opus 5.5, $0.035 on Sonnet 5.5. A solver residue question (one
sheet's title words, one answer) is about 1 500 input and 20 output tokens: $0.0002 on Haiku 5.5. The render
itself stays $0.0336 (ADR-0017).

## Decision

1. **One text provider interface, two implementations, both official SDKs, none hard-coded.** New package
   `backend/src/unitforma/ai/` with `provider.py`: `TextProvider.complete(system, messages, tools, *,
   max_tokens, max_tool_calls) -> Turn`, where `tools` are JSON-Schema tool definitions with a `read | write`
   tag and a Python callable, and `Turn` carries the final text, the raw assistant content blocks as the vendor
   returned them, the tool calls made, `usage` (input, cached input, output tokens) and `stop` (`end | tool |
   max_tokens | refusal | budget`). `ai/anthropic_provider.py` uses the `anthropic` SDK (`messages.create`
   with `tool_choice: auto`, no forced tool use, adaptive thinking left at the SDK default, streaming for
   `max_tokens` above 16 000); `ai/openai_provider.py` uses the `openai` SDK's Responses API with function
   tools. Each adapter owns its tool loop because the wire shapes differ; the interface is at the level of
   "run one assistant turn with these tools and this executor". The image provider of ADR-0017 is unchanged;
   `ai/` imports `renders/provider.py` only to reuse `ProviderError`. `core` never imports `ai` (import-linter).
2. **Settings, deployment level, all off by default.** `UF_AI_TEXT_PROVIDER` (`none | anthropic | openai`,
   default `none`: the chat and the residue passes are hidden), `UF_AI_TEXT_MODEL` (the assistant's model;
   default `claude-opus-5-5` for Anthropic, for OpenAI the owner's pick from the price table, no default taken),
   `UF_AI_TEXT_MODEL_SMALL` (the solver's residue model; default `claude-haiku-5-5` for Anthropic, OpenAI the
   owner's pick), `UF_AI_TEXT_ENDPOINT` (the vendor's https base URL, one fixed host per provider, TLS verified),
   `UF_AI_TEXT_API_KEY_FILE` (`/run/secrets/ai_text_api_key`, one key for the configured provider, created empty
   by `init-secrets.sh`), `UF_AI_TEXT_TIMEOUT_S` (default 120), `UF_AI_DAILY_BUDGET_USD` (default 5.00 per
   tenant per UTC day across every text call), `UF_AI_CHAT_ENABLED` (default `true` when a provider is set).
   Prices per 1M tokens for the configured models live in `ai/prices.py` as constants with the date they were
   read, used for the estimate column only, never for billing.
3. **A usage ledger, one row per model call.** Table `ai_usage` (migration `0020`): `id, tenant_id,
   project_id (nullable), user_id (nullable), task (chat | residue:<pass> | classify), provider, model,
   input_tokens, cached_input_tokens, output_tokens, est_cost_usd numeric(10,6), request_id, created_at`, RLS
   from `migrations/rls.py`, index `(tenant_id, created_at desc)`. The daily budget check is one indexed `sum`
   before every call; past the budget the call is refused with 429 `ai-budget` (chat) or recorded as "budget
   reached" in the run summary (solver). The classify pass of ADR-0025 writes a row too, so one table answers
   "what did AI cost this tenant this month". The Settings page shows the month to date per task.
4. **AI settings per project, layered, each key with one home.** `tenants.settings.ai` (tenant admin, Settings
   page, merged by `PATCH /tenants/{id}` as `render_prompt` is) holds the workspace defaults: `{assistant:
   bool, residue: bool, classify: bool, daily_budget_usd (≤ the deployment budget)}`. `projects.ai_settings`
   JSONB (migration `0020`, project write, edited on the setup checklist next to the two ADR-0025 switches)
   holds overrides for the same four keys plus `render_prompt` (1 to 4000 characters, ADR-0023 Option D: when
   set it replaces the workspace prompt for this project's renders; the joined sentence, the wall colour and the
   note are still appended by the code) and `instructions` (up to 2000 characters of project facts the
   assistant and the residue passes read, for example "building A is the tower, B the townhouses; codes are
   A-<floor><unit>"). Resolution is deployment allows → workspace default → project override, computed by one
   function `ai/settings.resolve(tenant, project) -> AiSettings`; `GET /projects/{id}/setup` returns the
   resolved values with their source (`deployment | workspace | project`) so the card can show where a value
   comes from. The thresholds of ADR-0025 Decision 5 are not per project: they stay constants in
   `autopilot/rules.py`, changed only with a fixture.
5. **The solver's residue passes read words, never geometry.** Three new passes at the end of the ADR-0025
   order, each behind `residue` and the daily budget, each with `kind = "llm"`, the model name and a confidence
   in the decision record, each under ADR-0025 Decision 4 (never change what a person set, skip what an earlier
   run decided):

   | Pass | Input sent (text only) | Asks for | Writes through | Confidence |
   |---|---|---|---|---|
   | facade sides | per elevation sheet: the title words and axis labels from `extract.json` `words`, the building's footprint side lengths and the axis labels read on the plan sheets | which side (`north \| south \| east \| west` in the site frame's orientation) and the axis range | `projects.update_building(facades)` only where ADR-0025 left `flip` unverified at 0.6; the record names the title it read | 0.8 when the title names axes that match the plan's labels, else no write |
   | document kinds | per `kind_source = pending` document whose first page passes `classify.page_is_drawing` (at least 50 vectors) but that the vision pass did not reach (budget, cap, or `UF_AI_CLASSIFY` off): the file name and the title-block words only (the words in the lowest 15 % of the page and the largest font, at most 600 characters). A page without line work stays on the host whatever its kind, as in ADR-0025 Decision 5: a permit decision, a contract or a letter is `pending` until classified and the `permit` kind cannot protect it before then | one of `rules.CLASSIFY_KINDS` or `unknown` | `documents.update_document(kind, kind_source = "ai")` | 0.8; `unknown` writes nothing |
   | layout names | per proposed layout: the room labels inside the member outlines (words of the sheet within the polygon), printed areas, the count of members | a name of at most 40 characters ("2-bedroom with loggia") and a room list | `sales.layouts.update(name, match.rooms)` on `status = proposed` layouts only; a confirmed layout is the person's | 0.7; shown on the Layouts page as "suggested" |

   The outlines, calibration, floors, placement and approval passes do not call a model: a wrong outline cannot be
   re-keyed (AGENTS.md rule 3) and no text answer is more exact than the printed scale. The "labels printed
   twice" list stays with the person.
6. **An assistant chat in the admin app, per project, acting as the signed-in person, through the one tool
   registry.** Tools are plain async functions in `mcp/tools/*.py` (projects, buildings, units, documents,
   renders, layouts, setup), each with a schema from its Pydantic models, a docstring the model reads, and a
   tag `read | write`. `mcp/server.py` registers the same list on the SDK's `MCPServer` for external clients
   (ADR-0015, unchanged behaviour); `ai/chat.py` converts the same list into provider tool definitions. The tool
   registry is the one home; a tool added for the chat is a tool for Claude Code the same day. New tools, all
   over existing service functions: `find_units(project_id, codes[] | query)` (normalises spaces and case, returns
   `UnitOut` with floor, building, layout, lifecycle), `list_units(project_id, floor_id?, status?)`,
   `get_unit(unit_id)`, `list_documents(project_id)` (metadata and kinds, never page text), `request_render(unit_id,
   with_unit_id?, note?)` (write), `get_render(render_id)`, `list_renders(unit_id)`, `list_layouts(project_id)`,
   `confirm_layout(layout_id)` (write), `get_setup_checklist(project_id)`, `run_setup(project_id)` (write),
   `set_setup_auto(project_id, enabled, approve_sheets)` (write). No `approve_render` tool: the review of a
   generated image is a person's click (ADR-0017 Decision 3), and the chat shows the image with the existing
   Approve and Reject buttons instead. No delete tools (ADR-0012).
7. **A chat turn is a job; writes pause for the person.** Tables (migration `0020`, RLS): `chat_conversations`
   (`id, tenant_id, project_id, user_id, provider, model, title, created_at, last_at`) and `chat_messages` (`id,
   tenant_id, conversation_id, seq, role (user | assistant | tool | system), content JSONB, format (1), pending_action
   JSONB (nullable), usage JSONB, created_at`), append-only; `content` stores the vendor's raw blocks so thinking
   and tool blocks go back unchanged. A conversation is bound to the provider and model it started with; a
   settings change applies to the next conversation. `POST /projects/{id}/chat/{conversation_id}/messages`
   writes the user message, refuses a second running turn (409), and defers task `ai.chat_turn` on the `default`
   queue (`retry = 0`); the worker opens `tenant_session(tenant_id, user_id, scope = "tenant")`, builds the
   `TenantContext` from the user's membership (the role matrix applies; a `sales` member's chat cannot call a
   project write tool), sets the audit origin `chat:<conversation_id>` (`audit_log.request_id` is `Text`, so the 41 characters fit), and runs one provider turn with budgets:
   at most 12 tool calls, 16 000 output tokens, 180 s wall clock, and the daily USD budget. Read tools run at
   once. A write tool does not run: the turn ends with `pending_action = {tool, arguments, summary}` and the
   page shows "The assistant wants to request a render of A-21 joined with A-22" with Allow and Deny; Allow
   runs that one call under the same context and continues the turn, Deny feeds the model a refusal
   `tool_result`. The page polls `GET .../messages?after=<seq>` every 2 s while a turn is running. Streaming
   is Revisit. The actor of every write is `(user_id, "assistant")`, so audit rows, code history and approvals say
   who decided, as `autopilot` rows do.
8. **What leaves the host is listed, and personal data is not on it.** The model receives: the system text, the
   project `instructions`, the user's typed messages, tool results of the tools in Decision 6 (names, codes,
   statuses, areas, prices, addresses, document names and kinds, checklist text), and in the residue passes the
   words named in Decision 5. It never receives: page text of `permit`-kind documents, buyer data (Phase 5),
   staff emails other than the signed-in user's own `whoami`, secrets, document files or images outside the
   existing classify path. `get_render` returns a signed URL for the admin app to show, not image bytes to the
   model. The chat panel carries the sentence "Answers are generated by <provider> <model>; it acts with your
   permissions and asks before changing anything", which also covers EU AI Act Article 50 (plan §21). Logs carry
   the conversation id, the model and the token counts, never the text.
9. **Defaults taken for the owner's three picks** (each one setting or one line to change): (1) the platform
   pays: one key per installation in the file secret, per-tenant and per-project daily budgets, the ledger shows
   the spend; per-tenant keys stored encrypted in the database are Option C of "who pays" and not built; (2) no
   OpenAI default model: `UF_AI_TEXT_PROVIDER=openai` without `UF_AI_TEXT_MODEL` fails at startup with the price
   table's names in the message; (3) write tools are allowed in the chat with the per-call approval of
   Decision 7; a workspace can turn the assistant off for everyone (`tenants.settings.ai.assistant = false`).

## Options considered

### Provider abstraction

**A. Own thin interface, two official SDKs (chosen).** Pros: both vendors the owner named, one place to switch,
each SDK keeps up with its vendor's API, no other party sees the data. Cons: two tool-loop adapters to keep
correct, two dependency lines, both on `httpx2`.

**B. Anthropic only.** Pros: one adapter, the MCP connector and the SDK's tool runner come for free. Cons: the
owner named two vendors; one price list; a vendor outage takes the feature down with no setting to flip.

**C. A gateway (LiteLLM proxy container, or OpenRouter).** Pros: one OpenAI-shaped API for every vendor. Cons:
one more container to operate and patch, or a third party that sees every prompt and tool result; tool-call
shapes still differ underneath and leak through as edge cases. Rejected.

**D. Extend the Gemini `describe` only.** Pros: nothing new to depend on. Cons: no tool calling was written for
it, the owner asked for Claude and OpenAI, and the image provider's daily cap and cost line were sized for
images. Gemini stays the image provider.

### Where the chat's model loop runs

**A. In the worker, over the shared tool registry, as the signed-in person (chosen).** Pros: Kratos identity,
role matrix, RLS and audit rows as the admin API; no token to create; writes approved in the UI; the tool list
has one home; the model never holds a credential of ours. Cons: a job per turn and polling, no streaming in
phase 1; we own the loop and its budgets.

**B. The vendor's MCP connector pointed at `https://app.<domain>/mcp`.** Pros: no loop to write; approval
exists on the OpenAI side (`require_approval`). Cons: the person must first create an API token (ADR-0015) and
hand it to the vendor as `authorization_token`, so our credential travels to a third party and the audit says
`mcp:<prefix>`, not the person's session; Anthropic's connector is beta and "zdr: not-eligible"; both vendors
call from shared egress, which the `mcp_by_ip` zone of 120 per minute and the Origin allow-list were not sized
for; the server must stay publicly exposed, which it is. Kept as a later option for users who already live in
Claude or ChatGPT.

**C. External assistants only, as today (ADR-0015).** Pros: zero work; Claude Code already does "create project
X with buildings A and B". Cons: no chat in the admin app, no image shown next to Approve, no tools for units
and renders until #31 is built anyway, and nothing for the setup residue.

**D. Anthropic Managed Agents.** Pros: hosted loop and sandbox, scheduled runs. Cons: one vendor, the data
and the tools live in the vendor's sandbox, a second identity model next to Kratos. Rejected for this product.

### What the model does in the setup

**A. Residue only, text in, one structured answer out, recorded like every other decision (chosen).** Pros:
testable with stub answers on the fixtures, bounded cost per run, the deterministic passes keep their fixtures
and thresholds. Cons: handles only what prints words; a wordless sheet stays with the person.

**B. A model agent drives the whole solver over the tools.** Rejected in ADR-0025 Option B and unchanged:
not deterministic, not testable on fixtures, minutes and tokens per project, drawings leave the host.

**C. Do nothing more.** Pros: no cost, nothing leaves the host. Cons: on the pilot permit the person still
reads every facade title, names ten plan types and classifies the text-heavy sheets by hand.

### Who pays

**A. Platform key per installation, per-tenant and per-project budgets, the ledger shows the spend (default
taken).** Pros: one secret, one bill, caps protect the owner. Cons: the owner carries the cost until pricing
passes it on.

**B. Tenant's own key stored encrypted in `tenants.settings`.** Pros: the tenant pays the vendor directly.
Cons: a credential kind stored in the database, key encryption and rotation to build, support when a tenant's
key is out of credit. Not built; Revisit.

## Trade-off analysis

| Axis | Chat A worker loop | Chat B vendor connector | Chat C external only | Chat D Managed Agents |
|---|---|---|---|---|
| Identity in audit rows | the person, `chat:<id>` | the token, `mcp:<prefix>` | the token | the vendor's agent |
| Our credential sent to the vendor | none | the API token | none | none (vendor holds the loop) |
| Write approval | in the UI, per call | vendor-side, per call (OpenAI); Anthropic: tool allow-list | the assistant's own prompt | vendor permission policy |
| Image shown with Approve/Reject | yes | no | no | no |
| Works with both vendors | yes | yes (two shapes) | yes | Anthropic only |
| Caddy and Origin changes | none | per-IP zone and allow-list for vendor egress | none | none |
| New code | adapters, job, panel, tools | tools only | none | agent config, tools |
| Size | L | M | — | L |

| Axis | Provider A interface + 2 SDKs | B Anthropic only | C gateway | D Gemini describe |
|---|---|---|---|---|
| Vendors | 2, switch by setting | 1 | many | 1 |
| Parties that see the data | the chosen vendor | Anthropic | vendor + gateway operator | Google |
| New containers | none | none | 1 (LiteLLM) or 0 (OpenRouter) | none |
| Tool calling | written twice | once | once, leaky | not written |
| Dependencies | `anthropic`, `openai` | `anthropic` | none in the image | none |

## Consequences

**Easier.** On the pilot permit the facade sides, the plan type names and the text-heavy sheets' kinds arrive
as recorded decisions for a few cents per run instead of ten screens. A sales person types "merged dollhouse of
A 21 and A22" and gets the image to approve in the same panel, with the same 422 texts a wrong pair gets on the
unit page. A tool written once serves the chat, Claude Code and claude.ai. Every model call has a row with its
cost, so the owner sees what AI costs per tenant and per project, and a runaway loop stops at 12 calls, 180 s or
the daily budget. A project can have its own render style and its own facts for the assistant without a
workspace-wide change.

**Harder.** Reviewers hold four rules: a tool is added to the registry, never to the chat or the MCP server
alone; a tool result never carries permit page text, buyer data or file bytes; a write tool is tagged `write`
and therefore pauses; `chat_messages` is append-only and `content` is stored as the vendor returned it (a
stored JSON shape under format marker 1; the previous release ignores the tables). Two SDKs on `httpx2` next
to `httpx` and `mcp`: `uv lock` is the proof, as in ADR-0015 #4, and the three are pinned together. A refusal
(`stop_reason = refusal`) or a vendor 5xx ends the turn with a message, never a retry of a write. A conversation
pinned to a model that the vendor retires fails on its next turn with a clear message and a "start a new
conversation" button; the retirement dates in plan §21 are watched at each release. Data leaves the host for
the first time in text form: the list in Decision 8 is written on the Settings page and in plan §13.2, and the
vendor's training and retention terms are quoted in §21 with their dates.

**Operations.** Two optional outbound hosts more, each a setting that defaults to off, one new file secret
(`ai_text_api_key`), one new queue task on `default`, three new tables with RLS and one JSONB column on `projects`, a sweep rule
(`retention_chat_days`, default 180) in the ADR-0021 sweep. Cost: estimated in Context, measured in E1 and
shown on the Settings page.

**Revisit.** Streaming turns (SSE from the API, or the worker publishing partial text); the vendor MCP
connector (chat Option B) for people who live in Claude or ChatGPT, with a per-vendor rate-limit zone; a
tenant's own key (who pays, Option B); residue passes for the "labels printed twice" list and for level markers
read as text; the Batch API for the residue passes if their volume ever matters (50 % off, minutes of latency);
`UF_AI_TEXT_MODEL` per task once the first measured turns show what Sonnet 5.5 or the OpenAI mid tier
gets wrong.

**Out of scope here:** a model deciding geometry (outlines, scale, floors, placement, blocks); a buyer-facing
chat on the portal; approving renders or publishing from the chat; deleting anything from the chat; voice;
fine-tuning; embeddings or search over documents; a second image provider (ADR-0017 Option C stays there).

## Action items

### Phase A: provider, settings, ledger (S to M)

- [ ] A1 `pyproject.toml`: `anthropic>=2,<3` (or the verified 1.x line), `openai>=3,<4`; `uv lock`; record
      the resolved `httpx2`, `httpx` and `mcp` versions here as ADR-0015 #4 did. Import-linter: `unitforma.ai`
      added to `core`'s forbidden list.
- [ ] A2 Migration `0020_ai_settings_chat_usage.py` (expand): `projects.ai_settings` JSONB default `{}`;
      `ai_usage`, `chat_conversations`, `chat_messages` with `enable_tenant_rls`, indexes
      `ai_usage (tenant_id, created_at desc)`, `chat_messages (conversation_id, seq)` unique. Models in
      `tenants/models.py`.
- [ ] A3 `core/settings.py`: the `UF_AI_TEXT_*`, `UF_AI_DAILY_BUDGET_USD`, `UF_AI_CHAT_ENABLED`,
      `retention_chat_days` settings; startup check of Decision 9 (2). `deploy/compose/secrets/README.md` and
      `init-secrets.sh`: `ai_text_api_key` created empty; `compose.yaml` mounts it on api and workers;
      `.env.example` lines with comments.
- [ ] A4 `ai/provider.py` (interface, `Turn`, tool definition with tag and callable), `ai/anthropic_provider.py`,
      `ai/openai_provider.py`, `ai/prices.py`, `ai/usage.py` (`record`, `spent_today`, `check_budget`),
      `ai/settings.py` (`resolve`). Unit tests with stub HTTP clients: a tool loop of two calls, a write tool
      pauses, `max_tool_calls` stops the loop, a refusal ends the turn with text, a 5xx becomes `ProviderError`
      without a retry of a write, the ledger row has the estimate, the budget refusal.
- [ ] A5 `api/admin.py`: `tenants.settings.ai` merged like `render_prompt`; `api/admin_setup.py`: `PUT
      /projects/{id}/ai-settings` (project write; `render_prompt` and `instructions` length checks; audit row
      `entity_type = project, action = ai_settings`); `GET /projects/{id}/setup` returns resolved AI settings
      with sources; `GET /tenants/{id}/ai-usage?month=` (tenant admin). Schemas; `openapi.json`;
      `npm run api:generate`.
- [ ] A6 `renders/service.base_prompt` reads `projects.ai_settings.render_prompt` before the workspace prompt;
      tests in `test_unit_renders.py` (project override wins, cleared falls back, 422 above 4000 characters).

### Phase B: residue passes (M)

- [ ] B1 `autopilot/passes/facade_sides.py`, `doc_kinds_text.py`, `layout_names.py` with a `TextProvider`
      stub in tests; prompts as module constants with the fixed answer format (one JSON object validated by
      Pydantic; a non-parsing answer writes nothing and records "unparsed answer"); every call writes an
      `ai_usage` row with `task = residue:<pass>`; `rules.py` gains the three confidences as constants.
- [ ] B2 `autopilot/service.py`: the three passes after `layouts`, skipped when `resolve(...).residue` is
      false or the budget is reached (one decision "budget reached, N documents left"); ADR-0025 Decision 4
      honoured (skip entities decided before, skip what a person set).
- [ ] B3 Tests in `test_autopilot.py`: a stub names the facade side from "ფასადი ღერძებში 1-9" and the plan's
      axis labels; a `permit` document's text is never in a request body; a `pending` page without line work (a letter, a contract) is never in a request body; a proposed layout gets a name and a
      confirmed one does not; the daily budget stops the third pass and records it; the decisions carry
      `kind = llm` and the model.
- [ ] B4 `sales/layouts.update` accepts `match.rooms`; Layouts page shows the suggested name with a
      "suggested by <model>" marker; `documents.update_document` with `kind_source = ai` from text (already
      allowed by `0019`).

### Phase C: tool registry and new tools (M)

- [ ] C1 Move the 13 tool bodies of `mcp/server.py` into `mcp/tools/{projects,buildings}.py` as plain functions
      with `tag` and schema; `mcp/server.py` registers from the list; `mcp/auth.py`: `tenant_ctx` takes a
      principal from the contextvar **or** an explicit `(tenant_id, user_id, origin)` so the worker can build it
      from a Kratos user without a token (read `TokenPrincipal` and `StaffPrincipal` first; the token path must
      stay byte-for-byte as tested in `test_mcp_server.py`). Verify how the SDK exposes registered tools for an
      in-process call before relying on it; if it does not, the registry list is the source and the SDK is one
      consumer.
- [ ] C2 New tools of Decision 6 in `mcp/tools/{units,documents,renders,layouts,setup}.py` over
      `inventory`, `documents`, `renders.service`, `sales.layouts`, `publishing.setup`, `autopilot.queue`;
      `find_units` normalises codes (`"A 21"` → `"A21"`, case-insensitive, also matches `A-21`); tool docstrings
      state units and the 422/409 texts the model will see.
- [ ] C3 Tests `test_mcp_server.py`: the tool count and names through `tools/list`; `find_units` with spaced
      codes; `request_render` with a partner on another floor returns the 422 text as a tool error; `read`
      token refused on `run_setup`; `list_documents` output has no page text. Plan §12.2 unchanged (same
      door), ADR-0015 status line notes the tool families added here.

### Phase D: chat (L)

- [ ] D1 `ai/chat.py`: system text (who the assistant is, units are `numeric` and null means unknown, it asks
      before writing, it answers in the user's language), the registry → provider tools conversion, the
      turn runner with the budgets of Decision 7, `pending_action` handling, append-only message writes with
      `format = 1`, audit origin `chat:<conversation_id>`, actor `(user_id, "assistant")`. Task `ai.chat_turn`
      in `jobs/tasks.py` (`default` queue, `retry = 0`).
- [ ] D2 `api/admin_chat.py`: `GET/POST /projects/{id}/chat` (conversations), `GET
      /projects/{id}/chat/{cid}/messages?after=`, `POST .../messages` (202; 409 while a turn runs; 429
      `ai-budget`), `POST .../actions/{message_id}` with `{allow: bool}`. Problem types in `core/errors.py`.
- [ ] D3 Tests `test_ai_chat.py` with the stub provider through the ASGI app and the task function: a turn that
      calls `find_units` then proposes `request_render` ends with `pending_action`; Allow runs it as the user
      and the audit row reads `chat:<cid>` with role `assistant`; Deny continues with a refusal result; a
      `sales` member's turn cannot run `run_setup` (the tool error text is the answer); the 13th tool call stops
      the turn; a second POST during a turn is 409; the ledger has one row per model call; a conversation of
      another tenant is 404 (RLS).
- [ ] D4 Admin app: `pages/project-chat.page.ts` (route `t/:tenantId/projects/:projectId/chat`, side-menu entry
      "Assistant" shown only when the resolved settings allow it), message list, composer, polling at 2 s while
      running, the pending-action card with Allow and Deny, a render card that shows the image with the existing
      Approve and Reject calls, the disclosure sentence of Decision 8, token and estimated cost per turn in a
      small line; guide entry. `api-client`: the new endpoints.
- [ ] D5 Setup page: the "AI" card (assistant, residue, classify switches with their source chip, daily budget,
      the project render prompt with "use workspace prompt", the instructions textarea); Settings page: the
      workspace AI card and the month-to-date usage table per task. Guide entries.
- [ ] D6 ADR-0021 sweep: `chat_messages` and `chat_conversations` older than `retention_chat_days`, count-only
      switch honoured; test in `test_retention.py`.

### Phase E: first measurements and docs (S)

- [ ] E1 First live turn on the dev stack with the owner's key: "merged dollhouse of A 21 and A22" on
      `permit-1127975`; record the tool calls, tokens, estimate and wall time here; compare the estimate with
      the vendor's usage figures; adjust `ai/prices.py` if the page changed.
- [ ] E2 First live residue run on `permit-1127975`: the facade sides it names against the owner's hand-set
      ones, the layout names, the kinds of the text-heavy sheets; tune prompts only with a fixture.
- [ ] E3 Plan: §11.2 (Setup AI card, Settings AI card, Assistant page), §12.3 (`ai.chat_turn`), §13.2 (the
      three residue passes in the "auto" column), §17 (new secret), §21 (the facts of this ADR's table with
      URLs and dates). README status sentence. `frontend/README.md`. `.env.example`. `docs/BACKLOG.md`
      rows added for every open item here; rows deleted as items are ticked.
