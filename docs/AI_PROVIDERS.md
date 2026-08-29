# AI Provider Strategy

Last reviewed: 2026-08-29

Local diagnostics do not need an AI provider or network connection. Anthropic Claude
is the only implemented external provider. Sending diagnostic data requires **explicit per-request authorization**;
there is no standing consent.

## Authorization flow

- Every CLI AI invocation requires `--share-with-ai`.
- Without the flag, the CLI displays the categories that would be shared and exits before adapter or AI access.
  It does not prompt or retain authorization.
- API use requires `external_sharing_authorized: true`; otherwise it returns `403`
  without calling the provider.
- Local scan, DTC, snapshot, and Stellantis commands never invoke AI.
- Authorization is not stored. Provider requests and responses are not cached.
- The API's `cached` field is retained for response compatibility and is always false.

Example with invented synthetic vehicle context:

```bash
python scripts/diagnose.py --vehicle "Synthetic Example Vehicle" \
  --mileage 10000 --protocol 6 --share-with-ai
```

Before using the flag, assume vehicle context, DTCs, and sensor snapshot fields listed
by the disclosure will leave the local machine. Do not share a VIN or identifying value
unless it is genuinely necessary and intended.

## Provider rules

- `DiagnosticEngine` owns client setup, prompt submission, response validation, and
  disclaimer injection.
- Read credentials only from environment variables; never commit them.
- Every result includes the informational-only safety disclaimer.
- Provider tests use synthetic data and mocked clients. CI never uses live credentials.
- A future provider must preserve the same consent, no-cache, privacy, error, and
  disclaimer guarantees.

Possible future work includes an explicit provider interface, an OpenAI Responses API
backend, and a fully local backend. Provider selection must be deliberate, never
auto-detected from whichever credential happens to exist.
