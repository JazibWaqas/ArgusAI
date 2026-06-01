# ArgusAI Project Rules

Last updated: June 2, 2026.

These rules keep ArgusAI aligned with the hackathon vision.

## Rule 1 - No Black Box Detection

ArgusAI must not present itself as a simple AI detector.

The product should show evidence, signal agreement, uncertainty, reliability, and audit trail.

Preferred framing:

> Forensic investigation platform, not classifier. Evidence trail, not score.

## Rule 2 - Signals Are Evidence, Not Verdicts

Individual detectors provide observations and directional support.

Final verdicts come from the reasoning layer after considering:

- media type
- visible/applicable signals
- detector status
- reliability
- health governor attenuation
- signal confidence

## Rule 3 - Inconclusive Is Valid

If evidence is weak, unavailable, or meaningfully conflicted, the system should return `inconclusive`.

Do not fabricate certainty to make the product look stronger.

## Rule 4 - Media-Specific UX and Scoring

The backend and frontend must stay dynamic by media type.

- Images can show image forensic signals.
- Videos can show frame/temporal/video-relevant signals.
- Audio can show audio/voice/context signals.
- Hidden signals (`visible=false`) must not be displayed as evidence cards or counted in scoring.
- Do not call videos or audio recordings "photographs."

## Rule 5 - Evidence Before Explanation

Gemini may explain, summarize, and answer follow-up questions from provided evidence.

Gemini must not invent detector outputs or claim a check happened when no detector produced it.

## Rule 6 - Phoenix Is Load-Bearing

Arize Phoenix integration must remain meaningful:

- root analysis traces and detector spans are emitted
- `phoenix_trace_id` is captured in reports
- trace links appear in report UI/admin/PDF
- detector health/circuit-breaker/calibration events affect verdict influence

Removing Phoenix should weaken auditability and reliability governance, not merely remove logs.

## Rule 7 - Firestore Is Product Memory

Firestore stores persistent analysis history, detector stats, feedback, and health state.

Do not replace Firestore-backed stats with ephemeral local files except as fallback. Cloud Run filesystems reset.

## Rule 8 - Agent Builder Must Use System Context

Agent Builder endpoints should not be generic Gemini wrappers.

They must use ArgusAI analysis plus Firestore history context so the agent can discuss accumulated reliability and similar prior cases.

## Rule 9 - Transparency in the UI

The UI must expose:

- what each signal checked
- what it found
- why it matters
- caveats/limitations
- empirical reliability when enough data exists
- Phoenix audit trail when available

## Rule 10 - Keep Scope Focused

Do not add more detectors or redesign the product unless explicitly asked.

The remaining hackathon value is:

- Agent Builder console configuration
- Phoenix MCP connection
- demo readiness
- OSINT/provenance quality
- clear Arize story

## Core Principle

ArgusAI behaves like a digital forensic investigator.

It answers:

- What evidence exists?
- What does that evidence imply?
- How reliable are these signals historically?
- What did Phoenix record for this exact verdict?
- Where is the uncertainty?
