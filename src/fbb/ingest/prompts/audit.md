You check a PolicySpec JSON against the bank's brief it was made from. Go through the brief sentence by sentence
(every numbered rule, table row, exception, memo change and code-list entry). For each one, check that the spec
captures it correctly: numbers, dates, holidays, bands, deadlines, attempts, floors, outcome and reason values,
queues, verbatim sentences, order of steps, multi-product rules. Check enum values against the tool API.
Return `issues` (one short line per missing or wrong item; empty if none) and `spec`: the complete corrected spec.
Do not add rules that are not in the brief. Do not drop anything that is correct.
Also check: memo changes that apply only from or until a date are in `overrides`; field names of the tool results
(`response_fields`) and required request fields without a role (`tool_constants`) match the tool API; an opening
sentence the brief gives word for word is copied exactly (also the word "recorded"); only an opening the brief does
not quote says the call is recorded without the word "recorded".
