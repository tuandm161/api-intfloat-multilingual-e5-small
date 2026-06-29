# Phase 03 - Safety And Postprocessing

## Purpose

Local Qwen output must be filtered before saving candidates. The goal is not to prove medical correctness, but to prevent obvious unsafe rewrites before E5 validation and human review.

## Protected Terms

Extract protected terms from the source stem before generation output is accepted.

Treat these as protected:

- Acronyms and all-caps terms: `ABC`, `ABCDE`, `ICU`, `GCS`, `INR`, `NANDA`, `NIC`, `WHS`, `CDC`.
- Mixed-case clinical tokens: `SpO2`, `HbA1c`, `Log-roll`.
- Units and measurements: `mmHg`, `ml/kg/h`, `%`, `mmol/L`.
- Numeric thresholds: `> 90`, `< 10`, `0.5`, `30 - 45`.
- English terms inside parentheses or quotes, such as `(Primary Survey)` or `"Evidence-Based Practice"`.

Recommended helper behavior:

- Use regex-based extraction, not a fixed dictionary only.
- Normalize comparison case-insensitively for alphabetic terms.
- Preserve exact display form in warnings/debug details when possible.

## Candidate Filtering

For each generated stem:

- Normalize for display using existing `TextNormalizer.normalize_for_display()`.
- Normalize for comparison using existing `TextNormalizer.normalize_for_comparison()`.
- Drop empty strings.
- Drop candidates whose normalized text equals the source stem.
- Drop duplicate candidates within the same generation result.
- Drop candidates missing protected source terms.
- Drop candidates that include answer-option text too directly if existing rule helpers can detect it.

The service layer already deduplicates against source and candidates; keep that behavior, but local generator should also filter early so retry can recover.

## Retry Policy

Use at most one retry when:

- Model output cannot be parsed as JSON.
- All candidates are filtered out.
- Too many candidates are missing protected terms.

Retry prompt additions:

```text
The previous output was invalid or removed required terms.
You must keep these exact terms unchanged: ...
Return valid JSON only.
```

Do not retry indefinitely.

## Failure Behavior

If no candidate remains after retry:

- Raise `AppError(ErrorCode.GENERATION_FAILED, status_code=503)`.
- Include a concise details payload with the reason.
- Let `ParaphraseService.create_job()` persist job status `FAILED`, as it already does.

## Relationship With E5 Validation

Postprocessing is a pre-filter only.

Keep the existing validation flow:

- E5 computes semantic similarity to source.
- Lexical difference is calculated.
- Rule checks detect answer hints, true/false drift, too-short, too-long.
- Human reviewer approves before saving a child question.
