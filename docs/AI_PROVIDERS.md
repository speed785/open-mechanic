# AI Provider Strategy

Last reviewed: 2026-08-24

open-mechanic currently uses Anthropic Claude through `ANTHROPIC_API_KEY`. That is the only implemented provider and should remain the default until a real provider abstraction is added.

## Current State

- `DiagnosticEngine` owns Anthropic client setup, structured output requests, response mapping, cache behavior, and disclaimer injection.
- Diagnosis shape is defined by the Pydantic model `DiagnosisAIOutput` and requested through `client.messages.parse(..., output_format=DiagnosisAIOutput)`.
- The application always injects the safety disclaimer; it is not taken from the model response.
- `ANTHROPIC_MODEL` can override the default model.
- API and CLI callers should depend on `DiagnosticEngine` behavior instead of calling an LLM SDK directly.

## Near-Term Direction

1. Keep Anthropic as the supported production provider.
2. Extract a provider protocol only when adding a second real backend.
3. Preserve the normalized `DiagnosisResult` shape across providers.
4. Require every provider path to include the safety disclaimer.
5. Keep provider tests mocked. CI must never require live API credentials.

## Candidate Future Providers

- OpenAI Responses API for cloud-hosted diagnosis.
- Local OpenAI-compatible servers for offline experiments.
- Rule-based fallback for common DTCs when no API key is configured.

Provider selection should be explicit through environment variables or config, not auto-detected from whichever key happens to be present.
