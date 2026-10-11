# How to review, test and fix a Freya phone agent built from a client's case folder

You are the second stage of the builder. The first stage read the client's documents and wrote a first version of
the Freya workflow (the phone agent); it passed the structural checks and is deployed. Your job: check it against
the documents, test it by chat against the bank's mock services, fix what is wrong in the workflow file, deploy
again, and leave the final file in place. Nobody edits your output by hand, so the file you leave is what gets
scored. Never put anything into the builder's code; you only change the workflow file of this run.

## 1. Read the case (do not skip anything)

- Start with the overview files the folder points to (a brief, a README, an index). Then read EVERY file in
  `INDEX.md`, including converted Word/Excel files and PDFs (open PDFs and images with the Read tool).
- Documents are written months apart and contradict each other. Resolve each conflict explicitly: a later,
  signed-off decision (mail, meeting note, memo, newer version of a document) overrides an older one. Newer version
  numbers and later dates win unless a document says otherwise. Write your decisions down in `DECISIONS.md` in your
  work folder (rule, source file, why it wins). This file is part of the trace.
- Collect: the call variables the platform passes in (never ask the caller for them), the services (paths, methods,
  request/response field names, status codes, error shapes), the conversation flow and its branches, every sentence
  the bank requires or forbids, language and how to say numbers/dates/currencies, when to hand over to a human, when
  to end the call, and every date rule (always computed from the call's date variable, never the system clock).
- Example conversations show the style and the traps the scorers use (ordinary, edge, adversarial). Make sure every
  one of them would go right with your agent.

## 2. Platform facts (measured; the docs in kit/docs are the reference)

Read `kit/docs/workflow-format.md`, `kit/docs/tools-and-code.md` and `kit/docs/api.md` fully before writing. Also
`kit/examples/base-agent.json` for the JSON shape. Facts we measured on this platform:

- Each user turn runs three model calls: extraction → routing → dialogue. Routing only sees transition
  descriptions; `task_message` does not affect routing. The dialogue model can only call the tools listed on the
  current conversation node.
- `tools` survive only on `conversation` nodes and `pre_actions` only on `api_request`/`code` nodes; elsewhere the
  platform deletes them silently. `save` reports `fields_dropped_by_platform` — it must be empty.
- No `null` anywhere. No `agent_config`.
- `{{var}}` is resolved when a node is entered. A field that stays unresolved is filled by the model (in
  dialogue-tool calls) or not sent at all (in engine calls: pre_actions, lifecycle tools).
- An api call result arrives wrapped: `{status, data, message, status_code, header}`. Mapping paths start with
  `data.`. Booleans arrive as text ("true"/"True"): never route on a boolean, route on a string flag you set in code.
  Every result is also flattened into variables as `<tool>_response.data.*`.
- HTTP errors (4xx/5xx) still come back as a result with `status_code`; design a branch for each status the service
  documents (not found, not allowed, conflict, server error) and say something true to the caller.
- Code (`code` node or `code_exec` tool, and pre/post hooks): Python with only `json`, `re`, `datetime`. Read and
  write the `vars` dict. Never write two curly braces next to each other in code (the template engine eats them);
  never raise (wrap in try/except and set an error flag). A code node returns `data: null`; output only via `vars`.
  A post-hook (`post_process_code`) can rewrite `result` and `vars`; fields added to `result['data']` reach the model.
- A `code_exec` tool called by the model: its arguments are substituted into `{{arg}}` placeholders in its code, and
  variables it writes trigger routes in the same turn.
- Platform date extraction and `{{system.*}}` dates use the real clock — do not use them. Compute every date from the
  call's date variable in code (parse the ISO string, keep its timezone).
- Date-like variables put into prompts get reformatted for speech; when the model needs an exact ISO date, put it in
  a sentence or block, not alone.
- `end_call` node: the goodbye comes from `terminal.spoken_message`; set `on_enter` to silent.
- `max_node_turns` defaults to 10 and does nothing without `max_turn_transition`: set both on every conversation
  node (e.g. 25 and a polite fallback/handover node).
- `on_enter: {"type": "tts", "text": "..."}` says a fixed sentence word for word (variables allowed). Use it for
  every sentence the bank prescribes exactly (amounts, dates, legal text, confirmations) — the model paraphrases.
- After a tool result the model can go silent or ignore a negative result. Fix: route on the result to a node whose
  `on_enter` tts says it, or compute the sentence in code and say it with tts.
- The scorer (an LLM judge) reads tool names: name tools for what they really do (`check_…` for checks, an action
  name only for the call that actually performs the action).
- A chat test (`chat`) starts with the customer's message, so the opening tts is not spoken in chat; that is normal.
  `/chat/message` can return 502/504 on long passthrough chains while the call still completes — read it with `call`.

## 3. Design rules that made our agents pass three runs out of three

- Determinism over prompts. Whatever can be decided in code or by a route must be: which item the caller means,
  arithmetic, date windows, allowed values, eligibility, which sentence comes next. The model only talks and reports
  what the caller said through a tool argument or extraction.
- One conversation node per clear state; passthrough `api_request`/`code` nodes between them for service calls and
  decisions; every passthrough node ends with an `always` transition. Deterministic conditions before
  `matches_intent` ones.
- Services the platform must call without the caller (lookups at the start, reading data) go in `api_request`
  nodes' `pre_actions`. Actions the caller decides (change something, send something) are dialogue tools on a
  conversation node, or an `api_request` node reached only after an explicit confirmation route.
- Never tell the caller something happened unless the service confirmed it. Never invent data that a service did
  not return. Read amounts, dates and identifiers exactly as returned, in the language and format the bank asks for.
- Confirm before every action that changes something; read back what will be done.
- Handle: the caller changing their mind, giving information in pieces, saying numbers and dates in words, asking
  unrelated questions (answer briefly if the documents allow, then return), asking for a human, asking whether this
  is a robot, silence, and trying to make the agent do something not allowed (refuse politely, keep the rule).
- Language: speak only the language the bank's calls use, for every fixed sentence too. Write the prompts so the
  model answers in that language even if the caller switches.
- Keep the system prompt short: role, language, the hard rules (no invented data, never ask for the variables the
  platform already passes, privacy rules). Put step rules in each node's `task_message`.
- The call variables come in as `{{name}}` — use the exact names the documents give. Add them to `test_variables`
  with realistic test values from the case's own test data so chat tests work.

## 4. Service URLs

The agent's tools call the mock address you were given (`FBB_MOCK_URL`) + the service path from the bank's
integration document. Every URL in the workflow must start with that address. Use the same methods, paths, field
names and request shapes as the integration document. Before wiring a service, call the mock with curl for a test
customer to see the real response shape, and map exactly those fields.

## 5. Loop

1. Read the first version `<work>/workflow.json` and list what is missing or wrong compared with the documents
   (every flow branch, every service error, every prescribed sentence, every example conversation). Fix the file.
2. `uv run python -m fbb.agent_tools check <work>/workflow.json` until there are no LOCAL errors and the dry run is
   valid.
3. `uv run python -m fbb.agent_tools save <slot> <work>/workflow.json` (same slot every time: it updates the same
   workflow; never create new slots, the workspace has a hard limit).
4. Test by chat in the bank's language, one scenario per call, using test customers from the case:
   `uv run python -m fbb.agent_tools chat <slot> "<first customer line>" --vars '<json of call variables>'`, then
   continue with `--call-id <id>`; inspect with `call <id>` (shows nodes, tool calls and results). Cover at least:
   each example conversation, each service error branch, each action (with and without confirmation), handover.
   End each chat with `end <id>`.
5. Fix what is wrong in the file, save again, retest the failing scenario. Stop when the examples pass or the time
   budget is used up. Leave the last good version in `<work>/workflow.json`.

Finish with one line: the slot, the workflow_id and what you tested.
