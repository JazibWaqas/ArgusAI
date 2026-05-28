# ArgusAI Project Rules

These rules define how ArgusAI must behave.

They prevent the system from turning into a basic AI detector.

---

# Rule 1 — No Black Box Detection

ArgusAI must never output a simple probability score.

The system must always show the evidence behind its conclusions.

---

# Rule 2 — Signals Are Evidence

Individual detectors provide observations.

Signals do not produce final verdicts.

Verdicts are determined by interpreting multiple signals together.

---

# Rule 3 — Inconclusive Is Valid

If signals conflict or evidence is weak, the system must return:

INCONCLUSIVE

The system must not fabricate certainty.

---

# Rule 4 — Modular Detectors

Signal detectors must remain independent modules.

New signals should be easy to add without redesigning the system.

---

# Rule 5 — Evidence Before Explanation

The reasoning system may only interpret evidence produced by detectors.

It must not invent signals.

---

# Rule 6 — Transparency

The user interface must expose:

- which signals were analyzed
- what each signal observed
- reliability of each signal

Users should understand how the system reached its conclusion.

---

# Rule 7 — Parallel Analysis

Signal detectors should run concurrently whenever possible.

This allows the system to scale as additional signals are added.

---

# Rule 8 — Future Compatibility

The architecture must support expansion to video analysis.

The image pipeline should be designed so it can later operate on video frames.

---

# Core Principle

ArgusAI behaves like a **digital forensic investigator**, not a classifier.

The system answers:

What evidence exists?  
What does that evidence imply?  
Where is the uncertainty?