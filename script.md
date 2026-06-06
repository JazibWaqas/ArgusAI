# ArgusAI — Demo Voiceover (final, tuned for AI voice)

Copy the block below into your AI voice tool. Stage cues are at the bottom.
Written for synthetic delivery: short sentences, one idea each, periods over dashes,
no idioms, no mid-sentence asides. Pause markers (—pause—) are where to insert a real
beat if your TTS supports it. Do NOT read the —pause— text aloud.

---

AI-generated media is reaching the point where ordinary people can no longer tell what is real. And the problem is not only that synthetic content keeps getting better. It is that the tools we use to detect it can become outdated just as fast.

That is why we built ArgusAI. It is a forensic media investigation platform, not a classifier. Instead of a single black-box score, it works like a forensic auditor. It dissects content in ways that expose the fundamental limits of AI.

And it does not just hand you a number. It shows you what every detector found. It investigates from several angles at once. Our own fine-tuned model. Provenance checks for the fingerprints AI tools leave behind. Mathematical analysis of pixels and frequencies, which catches construction that is too perfect to be real. Gemini, reasoning about physical inconsistencies. And a research agent that searches the web to see if the content has already been debunked.

It is also careful. If it genuinely cannot tell, it says inconclusive instead of guessing. And you can question any verdict directly, to see exactly how it reached its conclusion.

The same approach runs across audio and video. And this is the core idea. We do not chase surface looks. We target the deeper artifacts. The frequency patterns, the sensor noise, the compression traces that come from how generators build content, not how it appears. No single check can be fooled, because a fake has to defeat several independent signals at once. And the system re-weights those signals as models evolve. So it adapts instead of going stale.

—pause—

But detecting media is only half the problem. As generators improve, a signal that is reliable today can quietly degrade tomorrow. So every verdict, and every human judgment of it, becomes evidence. Not about the media. About the system itself.

The forensic pipeline investigates the media. A second agent, built on Google's Agent Builder, investigates the pipeline. It reads live telemetry from Arize Phoenix. Latency. Error rates. Cost. It combines that with human-confirmed outcomes in Firestore.

—pause—

Running it now. It finds a detector that is both unreliable and expensive. So it removes that detector from the verdict completely. And it writes that change to Firestore. This is the key. It is a decision the accuracy-only system could never make. Because the cost signal exists only in Arize Phoenix.

And this is not just a dashboard. That weight is the exact value the verdict engine reads. The next investigation already trusts that detector less. And every step the agent took is a permanent Arize Phoenix trace. Fully auditable.

So ArgusAI does not just analyze media. It investigates it. It explains its reasoning. And it governs its own reliability over time. It uses Arize Phoenix not as a log, but as the evidence its agent acts on. Built with Gemini, Google Agent Builder, and Arize Phoenix.

---

## Stage cues (screen during each paragraph)

1. **Will Smith clip** (full 15s).
2. **Landing page** → navigate into the Pope report as the line ends.
3. **Pope report** — verdict card + scroll the evidence signals as the angles are listed (model, provenance, math/spectral, Gemini, OSINT cards). Let each card appear as the voice names it.
4. **Stay on signals** — pause on Metadata "No clear direction" (the inconclusive point).
5. **Open the follow-up chat** — show a pre-asked question + answer. ("question any verdict directly")
6. **Click through audio + video results** — showing breadth.
7. **Back to Pope, click feedback** ("helps calibrate future analyses") on "becomes evidence."
8. **Open Operator Console** (leaderboard / detector list) on "investigates the pipeline."
9. **Run the Reliability Agent** — pre-cached. MONEY SHOT. The action lands on "removes that detector from the verdict." Make sure the `query_phoenix_telemetry` step ("via Arize Phoenix MCP") is visible.
10. **Point at the changed weight → open Phoenix dashboard** (~5s) on "permanent Arize Phoenix trace," then **Agent Builder shot + GitHub/URL** on the final line.

## Notes
- **The two —pause— markers are the drama.** Insert a real ~1s beat there. Flat delivery kills the money shot. Use a TTS with pacing control (ElevenLabs / Play.ht) if you can.
- **Para 9 fork:** this version says BENCH ("removes that detector completely"). If your seeded run RECALIBRATES instead, swap to: "It finds a detector whose recent accuracy has drifted below its peers. So it reduces that detector's influence on the verdict. And it writes the new weight to Firestore." — then keep the "cost signal exists only in Phoenix" line only if it benched; for a pure recalibrate, change that line to "a decision driven by telemetry only Arize Phoenix captures."
- **Confirm with a trial run which one fires**, then delete the unused fork so the voice matches the screen exactly.
- Pre-ask the follow-up chat (para/cue 5) — no live LLM call on camera.
- Buffers if long: the careful/inconclusive line, one angle in para 3. Never cut the agent run or the loop-close.
