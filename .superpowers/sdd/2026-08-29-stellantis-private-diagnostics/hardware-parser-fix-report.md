# Parked acceptance parser fix report

## Scope and privacy

- Reproduced only with synthetic ELM/CAN frames.
- Sent no vehicle requests and performed no hardware or network access.
- Stored no vehicle payloads, identifiers, codes, or diagnostic results.

## Root cause

`ELM327Transport.exchange()` grouped every frame solely by responder and passed the entire
group to `reassemble_isotp()`. The reassembler intentionally accepts exactly one ISO-TP
message, so a valid prompt containing a complete response-pending message followed by a
complete final message was rejected as trailing frames. After transport partitioning, the
scanner also needed to avoid selecting the leading pending response as the result.

## RED evidence

The initial focused run selected six synthetic tests and produced five expected failures:

- multiple complete messages from one responder were rejected as trailing frames;
- matching-service response-pending was selected instead of the final response;
- malformed/trailing sequence assertions confirmed strict rejection remained active.

Command:

```text
.venv/bin/pytest -q --no-cov tests/protocols/test_elm327.py -k 'partitions_multiple or trailing_or_interleaved' tests/stellantis/test_scanner.py -k 'partitions_multiple or trailing_or_interleaved or response_pending or mismatched_service'
```

## Minimal fix

- Partition each responder's frames only at complete ISO-TP message boundaries, then pass
  every partition through the existing strict reassembler.
- Skip one or more exact `responsePending` payloads only when the next payload is a valid
  final response for the requested service.
- Preserve a lone pending response as a bounded negative result, with no retry.
- Preserve mismatched-service and all other negative responses.

## GREEN and verification evidence

- Focused synthetic gate: `6 passed`.
- Full suite: `538 passed`, `100.00%` coverage.
- Ruff: clean.
- Mypy strict mode: clean across 28 source files.
- `git diff --check`: clean.

