"""Seed a believable recent-accuracy drift for one detector, so the operator
console's "Run investigator agent" genuinely detects drift and recalibrates on
camera. The drift is real (computed by detect_accuracy_drift from these records),
it is only the timing that is staged for the demo.

What it does:
  - Writes historical analysis records where the chosen detector was RIGHT
    (high historical confirmed accuracy).
  - Writes more-recent records where it was WRONG (low recent accuracy).
  - detect_accuracy_drift() then sees recent << historical and flags drift, which
    the agent acts on by down-weighting the detector.

All seeded docs are tagged `_demo_seed: True` and keyed `demoseed_*` so they can
be removed cleanly.

Usage:
  python -m backend.scripts.seed_demo_drift              # seed spectral_artifacts
  python -m backend.scripts.seed_demo_drift --detector spectral_artifacts
  python -m backend.scripts.seed_demo_drift --clear      # remove all seeded docs
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from backend.app.core.firebase import get_db
from backend.app.core.analysis_store import detect_accuracy_drift


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def clear_seed(db) -> int:
    removed = 0
    for doc in db.collection("analyses").where("_demo_seed", "==", True).stream():
        doc.reference.delete()
        removed += 1
    return removed


def reset_override(db, detector: str) -> None:
    """Clear any prior agent weight override so the recalibration on camera is a
    visible change, and retakes re-arm cleanly."""
    try:
        from firebase_admin import firestore

        db.collection("detector_stats").document(detector).set(
            {"agent_weight_override": firestore.DELETE_FIELD, "agent_override_reason": firestore.DELETE_FIELD},
            merge=True,
        )
    except Exception as exc:
        print(f"(could not reset override for {detector}: {exc})")


def seed(db, detector: str, historical_right: int = 9, recent_wrong: int = 6) -> None:
    """Truth is ai_generated in every seeded case. The detector 'agrees' (right)
    in the historical block and 'disagrees' (wrong) in the recent block."""
    reset_override(db, detector)
    now = datetime.now(timezone.utc)

    def write(idx: int, minutes_ago: int, support: str) -> None:
        sha = f"demoseed_{detector}_{idx}"
        db.collection("analyses").document(sha).set(
            {
                "_demo_seed": True,
                "timestamp": _iso(now - timedelta(minutes=minutes_ago)),
                "sha256": sha,
                "media_type": "image",
                "verdict": "ai_generated",
                "certainty": 0.9,
                "user_feedback": "correct",  # human confirmed verdict was right -> truth = ai_generated
                "feedback_timestamp": _iso(now - timedelta(minutes=minutes_ago)),
                "detectors": {detector: {"support": support, "status": "ok", "visible": True}},
            }
        )

    # Recent block (newest): detector says authentic while truth is ai_generated -> wrong.
    for i in range(recent_wrong):
        write(idx=i, minutes_ago=i + 1, support="authentic")
    # Historical block (older): detector says ai_generated -> right.
    for i in range(historical_right):
        write(idx=100 + i, minutes_ago=120 + i * 5, support="ai_generated")

    print(f"Seeded {recent_wrong} recent-wrong and {historical_right} historical-right records for '{detector}'.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default="spectral_artifacts")
    ap.add_argument("--clear", action="store_true")
    args = ap.parse_args()

    db = get_db()
    if db is None:
        raise SystemExit("Firebase is not configured. Set FIREBASE_PROJECT_ID and credentials, then retry.")

    if args.clear:
        n = clear_seed(db)
        reset_override(db, args.detector)
        print(f"Removed {n} seeded record(s) and reset the {args.detector} weight override. Environment restored to pre-seed state.")
        return

    clear_seed(db)  # idempotent: clear any prior seed first
    seed(db, args.detector)

    drift = detect_accuracy_drift()
    rows = {d["detector_id"]: d for d in drift.get("detectors", [])}
    row = rows.get(args.detector)
    if row:
        print(
            f"drift check -> recent={row['recent_accuracy']} historical={row['historical_accuracy']} "
            f"delta={row['delta']} drifted={row['drifted']}"
        )
        if row["drifted"]:
            print("Drift is live. Pressing 'Run investigator agent' will now recalibrate this detector.")
        else:
            print("Drift not flagged yet. Increase recent_wrong or lower the drift threshold.")
    else:
        print("Detector not present in drift output. Check the detector id.")


if __name__ == "__main__":
    main()
