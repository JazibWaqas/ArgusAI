import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence, useInView } from "framer-motion";
import {
  ShieldCheck, AlertOctagon, HelpCircle, Search, Camera, Eye,
  ScanSearch, Activity, Target, Database, ChevronDown, ChevronRight,
  Fingerprint, Sparkles, Send, X, Image as ImageIcon, Copy, Check,
  Zap, Globe, Layers, Cpu, FileDown, RefreshCw, LogIn, Gauge
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const ADMIN_PASSWORD = import.meta.env.VITE_ADMIN_PASSWORD || "argusai2026";
const PHOENIX_FALLBACK_BASE = "https://argusai-phoenix-ddmxiumrdq-uc.a.run.app";

function renderInlineMarkdown(text) {
  const parts = String(text || "").split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    const bold = part.match(/^\*\*([^*]+)\*\*$/);
    return bold ? <strong key={idx}>{bold[1]}</strong> : <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

function AssistantMessageText({ text }) {
  const normalized = String(text || "")
    .replace(/\r\n/g, "\n")
    .replace(/\s*###\s*/g, "\n### ")
    .replace(/\s+\*\s+(?=\*\*|\w)/g, "\n- ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const lines = normalized.split("\n").map((line) => line.trim()).filter(Boolean);
  const nodes = [];
  let listItems = [];

  const flushList = () => {
    if (!listItems.length) return;
    const items = listItems;
    listItems = [];
    nodes.push(
      <ul className="assistant-list" key={`list-${nodes.length}`}>
        {items.map((item, idx) => <li key={idx}>{renderInlineMarkdown(item)}</li>)}
      </ul>
    );
  };

  lines.forEach((line) => {
    if (/^###\s+/.test(line)) {
      flushList();
      nodes.push(<h4 className="assistant-section-title" key={`h-${nodes.length}`}>{renderInlineMarkdown(line.replace(/^###\s+/, ""))}</h4>);
      return;
    }
    if (/^[-*]\s+/.test(line)) {
      listItems.push(line.replace(/^[-*]\s+/, ""));
      return;
    }
    flushList();
    nodes.push(<p key={`p-${nodes.length}`}>{renderInlineMarkdown(line)}</p>);
  });
  flushList();

  return <div className="assistant-markdown">{nodes}</div>;
}

// Resolved at runtime from /arize/health so deep-links point at whichever
// Phoenix actually received the traces (local Docker or Cloud Run) and use the
// project's internal ID, which is what Phoenix URLs require.
let phoenixLinkInfo = { base: "", projectId: "", projectName: "argusai-forensics" };
function setPhoenixLinkInfo(info) {
  if (info && typeof info === "object") {
    phoenixLinkInfo = {
      base: info.base || "",
      projectId: info.project_id || "",
      projectName: info.project_name || "argusai-forensics",
    };
  }
}
const SUPPORTED_MEDIA = {
  image: ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"],
  video: ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska", "video/x-mkvideo"],
  audio: ["audio/wav", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/flac", "audio/m4a", "audio/mp4", "audio/x-m4a"],
};

function detectMediaType(file) {
  const mime = (file?.type || "").toLowerCase();
  const name = (file?.name || "").toLowerCase();
  if (SUPPORTED_MEDIA.image.includes(mime) || /\.(jpe?g|png|webp|gif|bmp)$/.test(name)) return "image";
  if (SUPPORTED_MEDIA.video.includes(mime) || /\.(mp4|webm|mov|mkv)$/.test(name)) return "video";
  if (SUPPORTED_MEDIA.audio.includes(mime) || /\.(wav|mp3|mpeg|ogg|flac|m4a)$/.test(name)) return "audio";
  return null;
}

function mediaBadgeLabel(mediaType) {
  if (mediaType === "video") return "Video";
  if (mediaType === "audio") return "Audio";
  if (mediaType === "image") return "Image";
  return "";
}

function getMediaCopy(mediaType = "default") {
  if (mediaType === "image") {
    return {
      badge: "Image Investigation",
      titleAccent: "what you see?",
      uploadTitle: "Image selected",
      contextPlaceholder: "Optional context, e.g. 'Pope Francis wearing a puffer jacket, March 2023'",
      processing: "Analyzing pixels, metadata, and web sources...",
      reportNoun: "image",
      evidenceSubject: "this image",
      heroSub:
        "ArgusAI investigates still images with pixel forensics, camera metadata, semantic vision, and live web provenance. Each signal explains what it found, so the verdict reads like an evidence trail, not a naked score.",
      heroSub2:
        "Upload an image and get a forensic verdict: authentic, AI-generated, or inconclusive. The report shows which checks agreed, which were weak, and why.",
    };
  }
  if (mediaType === "video") {
    return {
      badge: "Video Investigation",
      titleAccent: "what you watch?",
      uploadTitle: "Video selected",
      contextPlaceholder: "Optional context, e.g. 'Is this campaign video real?'",
      processing: "Extracting frames, checking motion, and reviewing provenance...",
      reportNoun: "footage",
      evidenceSubject: "this footage",
      heroSub:
        "ArgusAI investigates video by extracting frames, checking cross-frame consistency, reviewing embedded audio when present, and searching public context.",
      heroSub2:
        "Upload a clip and get a forensic verdict with video-specific signals: temporal coherence, semantic review, frame evidence, OSINT, and audio-track analysis when available.",
    };
  }
  if (mediaType === "audio") {
    return {
      badge: "Audio Investigation",
      titleAccent: "what you hear?",
      uploadTitle: "Audio selected",
      contextPlaceholder: "Optional context, e.g. 'Did this public figure really say this?'",
      processing: "Analyzing voice patterns and checking public context...",
      reportNoun: "recording",
      evidenceSubject: "this recording",
      heroSub:
        "ArgusAI investigates audio with voice authenticity checks, Gemini semantic listening, and public-context verification when the claim is specific.",
      heroSub2:
        "Upload a recording and get an audio authenticity report that explains whether the voice and production patterns look human, cloned, synthetic, or unresolved.",
    };
  }
  return {
    badge: "Forensic Media Investigation",
    titleAccent: "what you see or hear?",
    uploadTitle: "Media selected",
    contextPlaceholder: "Optional context, e.g. 'What is this claimed to show?'",
    processing: "Running forensic investigation...",
    reportNoun: "media",
    evidenceSubject: "this file",
    heroSub:
      "ArgusAI investigates images, video, and audio with media-specific forensic checks, Gemini reasoning, OSINT provenance, and Arize-backed reliability monitoring.",
    heroSub2:
      "Upload a file and get an evidence trail: what each signal checked, what it found, why it matters, and how the verdict was reached.",
  };
}

/** ELA/OSINT stash large blobs in metrics; PDF endpoint does not need them and huge JSON breaks POST. */
const METRIC_KEYS_STRIP_FOR_PDF = ["ela_image_base64", "grounding_metadata", "search_queries"];

function stripReportForPdfRequest(report) {
  if (!report?.evidence?.signals?.length) return report;
  return {
    ...report,
    evidence: {
      ...report.evidence,
      signals: report.evidence.signals.map((sig) => {
        if (!sig?.metrics || typeof sig.metrics !== "object") return sig;
        const nextMetrics = { ...sig.metrics };
        for (const k of METRIC_KEYS_STRIP_FOR_PDF) delete nextMetrics[k];
        return { ...sig, metrics: nextMetrics };
      }),
    },
  };
}

const SCAN_STEPS = [
  "Extracting spectral frequencies...",
  "Parsing EXIF metadata...",
  "Analyzing thermal noise patterns...",
  "Evaluating lighting physics...",
  "Running semantic vision analysis...",
  "Computing error level analysis...",
  "Performing live OSINT search...",
  "Aggregating evidence signals...",
  "Generating forensic report...",
];

const VIDEO_SCAN_STEPS = [
  "Extracting sharp video frames...",
  "Analyzing temporal consistency...",
  "Checking spectral artifacts in frames...",
  "Running semantic video review...",
  "Investigating public provenance...",
  "Aggregating evidence signals...",
  "Generating forensic report...",
];

const AUDIO_SCAN_STEPS = [
  "Extracting spectral frequencies (Wav2Vec2)...",
  "Analyzing voice authenticity...",
  "Checking public context...",
  "Generating audio report...",
];

const FOLLOWUP_AGENT_STEPS = [
  "Reviewing current evidence",
  "Checking detector reliability",
  "Reading Phoenix and Firestore context",
  "Preparing investigator response",
];

const CAROUSEL_IMAGES = [
  "/carousel/1.jpg",
  "/carousel/2.jpg",
  "/carousel/3.jpg",
  "/carousel/4.jpg",
  "/carousel/5.jpg",
  "/carousel/6.jpg",
  "/carousel/7.jpg"
];

const SIGNAL_THEME = {
  spectral:  { color: "#a855f7", glow: "rgba(168,85,247,0.25)",  label: "Spectral" },
  metadata:  { color: "#3b82f6", glow: "rgba(59,130,246,0.25)",  label: "Metadata" },
  semantic:  { color: "#ec4899", glow: "rgba(236,72,153,0.25)",  label: "Semantic" },
  forensic:  { color: "#f59e0b", glow: "rgba(245,158,11,0.25)",  label: "Forensic" },
  noise:     { color: "#10b981", glow: "rgba(16,185,129,0.25)",  label: "Noise"    },
  lighting:  { color: "#f97316", glow: "rgba(249,115,22,0.25)",  label: "Lighting" },
  audio:     { color: "#06b6d4", glow: "rgba(6,182,212,0.25)",   label: "Audio"    },
  default:   { color: "#22d3ee", glow: "rgba(34,211,238,0.25)",  label: "Signal"   },
};

function getSignalTheme(category) {
  const c = (category || "").toLowerCase();
  for (const [key, theme] of Object.entries(SIGNAL_THEME)) {
    if (c.includes(key)) return theme;
  }
  return SIGNAL_THEME.default;
}

const SignalIcon = ({ category, size = 14 }) => {
  const c = (category || "").toLowerCase();
  if (c.includes("spectral")) return <Cpu size={size} />;
  if (c.includes("metadata")) return <Camera size={size} />;
  if (c.includes("semantic")) return <Eye size={size} />;
  if (c.includes("forensic")) return <ScanSearch size={size} />;
  if (c.includes("noise"))    return <Activity size={size} />;
  if (c.includes("lighting")) return <Sparkles size={size} />;
  if (c.includes("audio"))    return <Zap size={size} />;
  return <Database size={size} />;
};

const VerdictIcon = ({ verdict, size = 24 }) => {
  const v = verdict.toLowerCase();
  if (v.includes("authentic")) return <ShieldCheck size={size} />;
  if (v.includes("ai"))        return <AlertOctagon size={size} />;
  return <HelpCircle size={size} />;
};

const getVerdictClass = (verdict) => {
  const v = verdict.toLowerCase();
  if (v.includes("authentic")) return "verdict-authentic";
  if (v.includes("ai"))        return "verdict-ai";
  return "verdict-inconclusive";
};

const formatVerdict = (verdict) => {
  if (verdict == null || verdict === "") return "";
  const titled = String(verdict)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return titled.replace(/\bAi\b/g, "AI");
};

const formatSupportLabel = (support, mediaType = "image") => {
  const value = (support || "unknown").toLowerCase();
  if (value === "authentic") {
    if (mediaType === "video") return "Suggests real footage";
    if (mediaType === "audio") return "Suggests authentic human voice";
    return "Suggests authentic photograph";
  }
  if (value === "ai_generated") {
    if (mediaType === "video") return "Suggests AI-generated video";
    if (mediaType === "audio") return "Suggests AI-generated / cloned speech";
    return "Suggests AI-generated image";
  }
  if (value === "inconclusive") return "Mixed or unclear";
  return "No clear direction";
};

const getSupportClass = (support) => {
  const value = (support || "unknown").toLowerCase();
  if (value === "authentic") return "support-authentic";
  if (value === "ai_generated") return "support-ai_generated";
  if (value === "inconclusive") return "support-inconclusive";
  return "support-neutral";
};

const getStatusBadgeClass = (status) => {
  const value = (status || "").toLowerCase();
  if (value === "ok") return "status-pass";
  if (value === "warning") return "status-warn";
  if (value === "error") return "status-error";
  return "status-info";
};

function isOsintSignal(signal) {
  const id = (signal.id || "").toLowerCase();
  const name = (signal.name || "").toLowerCase();
  return id === "osint_verification" || name.includes("osint") || name.includes("web fact-checking");
}

function formatSourceDate(value) {
  if (!value) return "date unknown";
  return String(value);
}

function phoenixTraceUrl(traceId) {
  if (!traceId) return "";
  const base = (phoenixLinkInfo.base || PHOENIX_FALLBACK_BASE).replace(/\/$/, "");
  // Phoenix deep-links require the project's internal ID, not its name.
  const project = phoenixLinkInfo.projectId || phoenixLinkInfo.projectName;
  return `${base}/projects/${project}/traces/${traceId}`;
}

function formatTime(value) {
  if (!value) return "unknown";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleString();
}

function formatPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "n/a";
  return `${Math.round(num * 100)}%`;
}

function shortHash(value) {
  if (!value) return "unknown";
  return String(value).slice(0, 10);
}

function formatLatency(value) {
  const s = Number(value);
  if (!Number.isFinite(s) || s <= 0) return "—";
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

function formatLatencySeconds(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "n/a";
  return num >= 0.1 ? `${num.toFixed(1)}s` : "fast";
}

function stepUsesPhoenixMcp(step) {
  const tool = String(step?.tool || "").toLowerCase();
  const tags = Array.isArray(step?.tags) ? step.tags : [];
  return tool.includes("phoenix") || tags.some((tag) => String(tag).toLowerCase().includes("mcp"));
}

const DETECTOR_LABELS = {
  spectral_artifacts: "Spectral Artifacts",
  metadata_analysis: "Metadata & Provenance",
  noise_pattern_analysis: "Sensor Noise",
  lighting_consistency: "Lighting Physics",
  semantic_inconsistencies: "Semantic & Physical",
  error_level_analysis: "Error Level Analysis",
  osint_verification: "OSINT / Web Provenance",
  temporal_coherence: "Temporal Coherence",
  audio_track: "Embedded Audio",
  audio_deepfake: "Voice Authenticity",
  audio_semantic: "Audio Semantic",
  audio_acoustics: "Audio Acoustics",
  temporal_noise_coherence: "Temporal Noise Coherence",
  audio_track_acoustics: "Audio Track Acoustics",
};

function detectorLabel(id) {
  return DETECTOR_LABELS[id] || String(id || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const CONFIRMED_TRUST_MIN = 8; // confirmations before a detector earns a real trust tier

// Trust tier from human-confirmed accuracy. Until a detector has enough confirmed
// outcomes it stays "Calibrating" — we don't pretend to know its accuracy yet.
function detectorTrust(confirmedAccuracy, confirmedTotal) {
  if (!confirmedTotal || confirmedTotal < CONFIRMED_TRUST_MIN) {
    return { tier: "calibrating", label: "Calibrating", color: "#64748b" };
  }
  if (confirmedAccuracy >= 0.8) return { tier: "trusted", label: "Trusted", color: "#34d399" };
  if (confirmedAccuracy >= 0.6) return { tier: "watch", label: "Watch", color: "#fbbf24" };
  return { tier: "low", label: "Low signal", color: "#f87171" };
}

// Build a ranked leaderboard from the Firestore detector stats. Confirmed accuracy
// (vs human ground truth) is the headline; verdict-match rate is shown as context.
function buildLeaderboard(detectorStats = {}) {
  return Object.entries(detectorStats)
    .map(([id, row]) => {
      const confirmedTotal = Number(row?.confirmed_total || 0);
      const confirmedAccuracy = Number(row?.confirmed_accuracy || 0);
      const ready = confirmedTotal >= CONFIRMED_TRUST_MIN;
      return {
        id,
        label: detectorLabel(id),
        totalRuns: Number(row?.total_runs || 0),
        matchRate: Number(row?.accuracy_rate || 0),
        confirmedTotal,
        confirmedAccuracy,
        weightMultiplier: Number(row?.weight_multiplier || 1),
        avgLatency: Number(row?.avg_latency_seconds || 0),
        ready,
        // Bar reflects confirmed accuracy once earned, otherwise verdict-match as a placeholder.
        barValue: ready ? confirmedAccuracy : Number(row?.accuracy_rate || 0),
        trust: detectorTrust(confirmedAccuracy, confirmedTotal),
      };
    })
    .filter((d) => d.totalRuns > 0)
    .sort((a, b) => {
      if (a.ready !== b.ready) return b.ready - a.ready;
      if (b.barValue !== a.barValue) return b.barValue - a.barValue;
      return b.totalRuns - a.totalRuns;
    });
}

const formatStatusLabel = (status) => {
  const value = (status || "").toLowerCase();
  if (value === "ok") return "Completed";
  if (value === "warning") return "Limited";
  if (value === "error") return "Error";
  if (value === "unavailable") return "Unavailable";
  return value || "Unknown";
};

const formatConfidenceLabel = (label) => {
  const value = (label || "").toLowerCase();
  if (!value) return "Unrated";
  return value.charAt(0).toUpperCase() + value.slice(1);
};

const SIGNAL_DESCRIPTIONS = {
  spectral_artifacts: {
    image: "Runs the image through frequency-analysis models looking for mathematical patterns in pixel data that appear in AI-generated images but not in real camera photos.",
    video: "Runs extracted video frames through frequency-analysis models looking for hidden generation patterns in the frame pixels.",
  },
  metadata_analysis: {
    image: "Reads invisible file metadata such as camera, software, creation date, and GPS fields. Missing or inconsistent metadata can be a clue, though never conclusive on its own.",
    video: "Reads video container and frame metadata where available. Missing or stripped metadata limits provenance, but does not prove manipulation.",
  },
  noise_pattern_analysis: {
    image: "Every real camera sensor adds a tiny, consistent layer of electrical noise to a photo. This check looks for that sensor fingerprint.",
  },
  lighting_consistency: {
    image: "Checks whether brightness, contrast, highlights, and shadows behave like a physically captured photograph rather than a generated image.",
  },
  error_level_analysis: {
    image: "Re-saves the image and compares compression residuals. Edited or composited regions often show different compression stress.",
    video: "Runs compression-residual analysis on extracted frames. It can reveal frame-level editing or compositing clues, but not every video artifact is AI.",
  },
  semantic_inconsistencies: {
    image: "Uses Gemini vision to look for visible physical mistakes: broken hands, warped geometry, garbled text, impossible shadows, or objects that could not exist in that configuration.",
    video: "Uses Gemini video review to look for generated-video clues: morphing, flicker, unstable details, impossible motion, shifting geometry, or prompt-like production patterns.",
    audio: "Uses Gemini listening to check cadence, breathing, pronunciation, synthetic voice texture, and generated-audio production patterns.",
  },
  temporal_coherence: {
    video: "Checks whether objects, faces, text, lighting, and motion remain stable across time. AI video often fails between frames even when individual frames look plausible.",
  },
  temporal_noise_coherence: {
    video: "Measures the sensor-noise floor in flat regions of each frame and checks whether it stays consistent across the clip. Real cameras leave steady noise everywhere; AI video is often too smooth or flickers.",
  },
  audio_acoustics: {
    audio: "Measures the physical micro-variation of the voice: pitch jitter, amplitude shimmer, harmonic-to-noise ratio, and tonality. Real vocal folds never repeat a cycle perfectly; synthetic voices tend to be smoother.",
  },
  audio_track: {
    video: "Extracts the video's embedded audio track, when present, and checks whether speech or production patterns suggest cloning or synthesis.",
  },
  audio_track_acoustics: {
    video: "Measures the embedded audio's physical micro-variation (pitch jitter, amplitude shimmer, harmonic-to-noise ratio). Real voices vary cycle to cycle; synthetic ones are smoother.",
  },
  audio_deepfake: {
    audio: "Checks the recording with audio authenticity models and Gemini listening for cloned voice, text-to-speech, missing breathing, metallic artifacts, or synthetic production.",
  },
  osint_verification: {
    image: "Searches the public web to see whether the depicted event or subject appears in credible reporting, fact-checker databases, or known fake coverage.",
    video: "Searches the public web to determine whether the footage or claimed event is documented, disputed, or flagged as manipulated.",
    audio: "Searches public context around the claimed speaker, statement, or event when the recording has enough context to investigate.",
  },
};

function getSignalDescription(signal, mediaType = "image") {
  const id = (signal.id || "").toLowerCase();
  const direct = SIGNAL_DESCRIPTIONS[id];
  if (typeof direct === "string") return direct;
  if (direct && typeof direct === "object") return direct[mediaType] || direct.default || direct.image || direct.video || direct.audio || null;
  // fuzzy match by name fragment
  for (const [key, desc] of Object.entries(SIGNAL_DESCRIPTIONS)) {
    if (id.includes(key.split("_")[0])) {
      if (typeof desc === "string") return desc;
      return desc[mediaType] || desc.default || desc.image || desc.video || desc.audio || null;
    }
  }
  return null;
}

const WIDE_SIGNAL_IDS = new Set(["audio_track", "audio_track_acoustics"]);

function isWideSignalCard(signal) {
  return isOsintSignal(signal) || WIDE_SIGNAL_IDS.has(signal.id);
}

// Order signals so half-width cards pack first and full-width cards (OSINT, audio) sit at
// the end, then flag a lone trailing half-width card so it spans the row. Keeps the grid
// from leaving an orphaned empty half-row regardless of which signals are present.
function orderedSignalsForGrid(signals) {
  const normal = signals.filter((s) => !isWideSignalCard(s));
  const wide = signals.filter((s) => isWideSignalCard(s));
  const forceWideId = normal.length % 2 === 1 ? normal[normal.length - 1]?.id : null;
  return { ordered: [...normal, ...wide], forceWideId };
}

function AnimatedSignalCard({ signal, index, mediaType = "image", detectorStats = {}, phoenixTraceId = "", forceWide = false }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });
  const [showDetails, setShowDetails] = useState(false);
  const theme = getSignalTheme(signal.category);
  const wide = isOsintSignal(signal);
  // Standalone audio cards (and a lone trailing card) span full width so the grid never
  // leaves an orphaned empty half-row.
  const fullWidth = wide || forceWide || WIDE_SIGNAL_IDS.has(signal.id);

  const hasInfluence = typeof signal.verdict_influence_percent === "number";
  const barPct = hasInfluence ? signal.verdict_influence_percent : Math.round((signal.reliability || 0) * 100);
  const realStats = detectorStats?.[signal.id];
  const showRealStats = realStats && Number(realStats.total_runs || 0) >= 5;

  const statsBlock = (
    <div className={`signal-stats ${wide ? "signal-stats-osint" : ""}`}>
      <div className="stat-item">
        <span className="stat-label">{hasInfluence ? "Influence on verdict" : "Confidence"}</span>
        <div className="reliability-bar-wrap">
          <span className="stat-value">{barPct}%</span>
          <div className={`reliability-bar ${wide ? "reliability-bar-wide" : ""}`}>
            <motion.div
              className="reliability-fill"
              style={{ background: theme.color }}
              initial={{ width: 0 }}
              animate={isInView ? { width: `${barPct}%` } : {}}
              transition={{ duration: 0.8, delay: index * 0.07 + 0.3, ease: "easeOut" }}
            />
          </div>
        </div>
      </div>
      <div className="stat-item">
        <span className="stat-label">Result</span>
        <span className={`stat-value ${getSupportClass(signal.supports)}`}>
          {formatSupportLabel(signal.supports, mediaType)}
        </span>
      </div>
      {showRealStats && (
        <div className="signal-real-stats">
          Based on {realStats.total_runs} analyses · {formatPercent(realStats.accuracy_rate)} accuracy
        </div>
      )}
    </div>
  );

  const signalDescription = getSignalDescription(signal, mediaType);
  const osintMetrics = signal.metrics || {};
  const factSources = Array.isArray(osintMetrics.fact_check_sources) ? osintMetrics.fact_check_sources : [];
  const earliest = osintMetrics.earliest_web_appearance || null;
  const timeline = osintMetrics.timeline_contradiction || null;

  // ELA heatmap is always visible above the toggle (not hidden behind expand)
  const elaImage = mediaType === "image" && signal.metrics?.ela_image_base64 ? (
    <div className="signal-image-container">
      <img src={`data:image/png;base64,${signal.metrics.ela_image_base64}`} alt="ELA compression heatmap, brighter areas had more compression stress" />
    </div>
  ) : null;

  const detailsSection = (
    <AnimatePresence>
      {showDetails && (
        <motion.div
          className="signal-details-expanded"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.22 }}
        >
          {signalDescription && (
            <div className="signal-detail-row signal-detail-row--purpose">
              <span className="signal-detail-label">What this check does</span>
              <p className="signal-detail-text">{signalDescription}</p>
            </div>
          )}
          {signal.why_it_matters && (
            <div className="signal-detail-row">
              <span className="signal-detail-label">Why it matters</span>
              <p className="signal-detail-text">{signal.why_it_matters}</p>
            </div>
          )}
          {signal.caveat && (
            <div className="signal-detail-row">
              <span className="signal-detail-label">Caveat</span>
              <p className="signal-detail-text">{signal.caveat}</p>
            </div>
          )}
          {signal.observations?.length > 0 && (
            <div className="signal-detail-row">
              <span className="signal-detail-label">Technical details</span>
              <ul className="observations-list">
                {signal.observations.map((obs, idx) => (
                  <li key={idx}>{obs}</li>
                ))}
              </ul>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );

  const toggleBtn = (
    <button className="signal-toggle-btn" onClick={() => setShowDetails((v) => !v)}>
      {showDetails ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      {showDetails ? "Less" : "Details"}
    </button>
  );

  return (
    <motion.div
      ref={ref}
      className={`signal-card${wide ? " signal-card-osint" : ""}${(fullWidth && !wide) ? " signal-card-wide" : ""}`}
      style={{ "--signal-color": theme.color, "--signal-glow": theme.glow }}
      initial={{ opacity: 0, y: 30 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ type: "spring", stiffness: 280, damping: 22, delay: index * 0.07 }}
      whileHover={{ y: wide ? -2 : -5, boxShadow: `0 16px 40px ${theme.glow}` }}
    >
      <div className="signal-header">
        <div className="signal-title-wrap">
          <span className="signal-category" style={{ color: theme.color }}>
            <SignalIcon category={signal.category} /> {signal.category}
          </span>
          <h4>{signal.name}</h4>
        </div>
        <span className={`signal-status-badge ${getStatusBadgeClass(signal.status)}`}>{formatStatusLabel(signal.status)}</span>
      </div>

      {wide ? (
        <>
          <div className="signal-osint-layout">
            {signal.what_found && (
              <div className="signal-osint-finding">
                <span className="signal-detail-label">What the web found</span>
                <p className="signal-detail-text">{signal.what_found}</p>
              </div>
            )}
            <div className="signal-osint-primary">
              {statsBlock}
              <div className="signal-summary signal-summary-osint">{signal.summary}</div>
            </div>
          </div>
          {(osintMetrics.research_hops || earliest || factSources.length > 0 || timeline?.present) && (
            <div className="osint-research-panel">
              {osintMetrics.research_hops && (
                <div className="osint-research-item">
                  <span className="signal-detail-label">Research hops</span>
                  <strong>{osintMetrics.research_hops}</strong>
                </div>
              )}
              {earliest && (
                <div className="osint-research-item osint-research-wide">
                  <span className="signal-detail-label">Earliest web appearance</span>
                  {earliest.url ? (
                    <a href={earliest.url} target="_blank" rel="noreferrer">
                      {earliest.source_name || earliest.title || "Source"} · {formatSourceDate(earliest.date)}
                    </a>
                  ) : (
                    <strong>{earliest.source_name || "Unknown source"} · {formatSourceDate(earliest.date)}</strong>
                  )}
                </div>
              )}
              {factSources.length > 0 && (
                <div className="osint-research-item osint-research-wide">
                  <span className="signal-detail-label">Fact-checkers</span>
                  <div className="source-badges">
                    {factSources.slice(0, 5).map((source, idx) => (
                      source?.url ? (
                        <a key={idx} className="source-badge" href={source.url} target="_blank" rel="noreferrer">
                          {source.outlet || "Source"}
                        </a>
                      ) : (
                        <span key={idx} className="source-badge">{source?.outlet || "Source"}</span>
                      )
                    ))}
                  </div>
                </div>
              )}
              {timeline?.present && (
                <div className="osint-timeline-warning">
                  <AlertOctagon size={14} />
                  <span>{timeline.explanation}</span>
                </div>
              )}
            </div>
          )}
          {detailsSection}
          {toggleBtn}
        </>
      ) : (
        <>
          {statsBlock}
          <div className="signal-summary">{signal.summary}</div>
          {signal.what_found && (
            <p className="signal-what-found">{signal.what_found}</p>
          )}
          {elaImage}
          {detailsSection}
          {toggleBtn}
        </>
      )}
    </motion.div>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <motion.button
      className="copy-btn"
      onClick={handleCopy}
      whileTap={{ scale: 0.9 }}
      title="Copy JSON"
    >
      <AnimatePresence mode="wait">
        {copied
          ? <motion.span key="check" initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}><Check size={14} /></motion.span>
          : <motion.span key="copy"  initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}><Copy size={14} /></motion.span>
        }
      </AnimatePresence>
      {copied ? "Copied!" : "Copy"}
    </motion.button>
  );
}

function ScanningOverlay({ steps, currentStep }) {
  return (
    <div className="scan-overlay">
      <div className="scan-laser" />
      <div className="scan-corners">
        <span className="corner tl" />
        <span className="corner tr" />
        <span className="corner bl" />
        <span className="corner br" />
      </div>
      <div className="scan-status">
        <span className="scan-dot" />
        <AnimatePresence mode="wait">
          <motion.span
            key={currentStep}
            className="scan-text"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35 }}
          >
            {steps[currentStep % steps.length]}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
}

function FeedbackWidget({ sessionId, feedbackState, onFeedback }) {
  if (!sessionId) return null;
  const submitted = feedbackState?.submitted;
  return (
    <div className="feedback-row">
      <span>Was this verdict accurate?</span>
      {submitted ? (
        <strong>Thanks. This helps calibrate future analyses.</strong>
      ) : (
        <div className="feedback-actions">
          <button type="button" onClick={() => onFeedback(true)}>
            <Check size={13} /> Yes
          </button>
          <button type="button" onClick={() => onFeedback(false)}>
            <X size={13} /> No
          </button>
        </div>
      )}
    </div>
  );
}

function AudioReportCard({ reportData, sessionId, feedbackState, onFeedback, detectorStats = {} }) {
  if (!reportData) return null;

  const certaintyPercent = Math.round((reportData.certainty || 0) * 100);
  const isAI = (reportData.verdict || "").toLowerCase().includes("ai_generated");
  const isAuth = (reportData.verdict || "").toLowerCase().includes("authentic");
  const verdictLabel = isAI ? "AI-Generated Voice" : isAuth ? "Authentic Voice" : "Inconclusive";
  const verdictClass = isAI ? "verdict-ai" : isAuth ? "verdict-authentic" : "verdict-inconclusive";
  const confidenceLabel = reportData.confidence_label || "Guarded";

  const signals = (Array.isArray(reportData.signals) && reportData.signals.length)
    ? reportData.signals
    : (reportData.signal ? [reportData.signal] : []);
  const { ordered: orderedSignals, forceWideId } = orderedSignalsForGrid(signals);
  const voiceSig = signals.find((s) => s?.metrics?.prob_fake != null) || signals.find((s) => s?.id === "audio_deepfake");
  const probFake = voiceSig?.metrics?.prob_fake ?? null;
  const probReal = voiceSig?.metrics?.prob_real ?? null;

  return (
    <div className="report-inner">
      <motion.div
        className={`verdict-stamp ${verdictClass}`}
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
      >
        <Zap size={28} />
        <div className="verdict-text-wrap">
          <span className="verdict-label">Audio Verdict</span>
          <span className="verdict-value">{verdictLabel}</span>
          {reportData.explanation && <p className="verdict-summary">{reportData.explanation}</p>}
        </div>
        <div className="verdict-meta">
          <div className="verdict-confidence">
            <span className="verdict-confidence-label">How sure we are</span>
            <span className="verdict-confidence-value">{certaintyPercent}%</span>
            <span className="verdict-confidence-tag">{confidenceLabel}</span>
          </div>
          <span className="report-ts">{new Date(reportData.generated_at).toLocaleString()}</span>
        </div>
      </motion.div>

      <FeedbackWidget sessionId={sessionId} feedbackState={feedbackState} onFeedback={onFeedback} />

      <motion.div
        className="report-helper"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.4 }}
      >
        This recording was checked by a dedicated voice-authenticity model, a Gemini semantic listen, and public-context research when a claim was provided.
      </motion.div>

      {probFake !== null && probReal !== null && (
        <motion.div
          className="audio-prob-panel"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
        >
          <span className="audio-prob-title">Voice model probability</span>
          <div className="stat-item">
            <span className="stat-label">AI-generated / cloned</span>
            <div className="reliability-bar-wrap">
              <span className="stat-value" style={{ color: isAI ? "#f87171" : "inherit" }}>{Math.round(probFake * 100)}%</span>
              <div className="reliability-bar">
                <motion.div className="reliability-fill" style={{ background: isAI ? "#f87171" : "#22d3ee" }} initial={{ width: 0 }} animate={{ width: `${Math.round(probFake * 100)}%` }} transition={{ duration: 0.9, ease: "easeOut" }} />
              </div>
            </div>
          </div>
          <div className="stat-item">
            <span className="stat-label">Authentic human voice</span>
            <div className="reliability-bar-wrap">
              <span className="stat-value" style={{ color: isAuth ? "#34d399" : "inherit" }}>{Math.round(probReal * 100)}%</span>
              <div className="reliability-bar">
                <motion.div className="reliability-fill" style={{ background: isAuth ? "#34d399" : "#22d3ee" }} initial={{ width: 0 }} animate={{ width: `${Math.round(probReal * 100)}%` }} transition={{ duration: 0.9, delay: 0.1, ease: "easeOut" }} />
              </div>
            </div>
          </div>
        </motion.div>
      )}

      <motion.div
        className="signals-section"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        <h3 className="signals-section-title">
          <Layers size={14} /> Evidence signals
        </h3>
        <p className="signals-section-copy">
          Each card explains what that check looked for, what it found in this recording, and why it matters.
        </p>
        <div className="signals-grid">
          {orderedSignals.length > 0
            ? orderedSignals.map((signal, i) => (
                <AnimatedSignalCard key={signal.id || i} signal={signal} index={i} mediaType="audio" detectorStats={detectorStats} forceWide={signal.id === forceWideId} />
              ))
            : <p style={{ color: "var(--text-muted)" }}>No audio signals were produced.</p>}
        </div>
      </motion.div>
    </div>
  );
}

function ForensicReportCard({ reportData, showJson, onToggleJson, onDownloadPdf, pdfDownloading, sessionId, feedbackState, onFeedback, detectorStats = {} }) {
  const jsonStr = useMemo(() => {
    if (!reportData || !showJson) return "";
    try {
      return JSON.stringify(reportData, null, 2);
    } catch {
      return "";
    }
  }, [showJson, reportData]);

  if (!reportData) return null;
  const certaintyPercent = Math.round((reportData.certainty || 0) * 100);
  const explanationParagraphs = String(reportData.explanation || "")
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  const showLeaning = reportData.verdict === "inconclusive" && reportData.leaning;
  const modelHealth = reportData.pipeline_health?.model_health_label;
  const mediaType = reportData.media_type || reportData.evidence?.media_type || "image";
  const visibleSignals = (reportData.evidence?.signals || []).filter((signal) => signal?.visible !== false);
  const { ordered: orderedSignals, forceWideId } = orderedSignalsForGrid(visibleSignals);
  const mediaCopy = getMediaCopy(mediaType);
  const mediaNoun = mediaCopy.reportNoun;

  return (
    <div className="report-inner">
      <motion.div
        className={`verdict-stamp ${getVerdictClass(reportData.verdict)}`}
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
      >
        <VerdictIcon verdict={reportData.verdict} size={28} />
        <div className="verdict-text-wrap">
          <span className="verdict-label">Verdict</span>
          <span className="verdict-value">{formatVerdict(reportData.verdict)}</span>
          {reportData.short_summary && <p className="verdict-summary">{reportData.short_summary}</p>}
        </div>
        <div className="verdict-meta">
          <div className="verdict-confidence">
            <span className="verdict-confidence-label">How sure we are</span>
            <span className="verdict-confidence-value">{certaintyPercent}%</span>
            <span className="verdict-confidence-tag">{formatConfidenceLabel(reportData.confidence_label)}</span>
          </div>
          {showLeaning && (
            <div className="verdict-leaning">
              <span className="verdict-confidence-label">Current lean</span>
              <span className="verdict-leaning-value">{formatVerdict(reportData.leaning)}</span>
            </div>
          )}
          <span className="report-ts">{new Date(reportData.generated_at).toLocaleString()}</span>
        </div>
      </motion.div>

      <FeedbackWidget sessionId={sessionId} feedbackState={feedbackState} onFeedback={onFeedback} />

      <motion.div
        className="report-helper"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, duration: 0.4 }}
      >
        This verdict reflects how strongly the independent forensic signals agree, not a single classifier score.{modelHealth ? ` ${modelHealth}.` : ""}
      </motion.div>

      {explanationParagraphs.length > 0 && (
        <motion.div
          className="narrative"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.5 }}
        >
          <h3 className="narrative-title">Detailed assessment</h3>
          {explanationParagraphs.map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </motion.div>
      )}

      <motion.div
        className="signals-section"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.45 }}
      >
        <h3 className="signals-section-title">
          <Layers size={14} /> Evidence signals
        </h3>
        <p className="signals-section-copy">
          Each card explains what that check looked for, what it found in this {mediaNoun}, why it matters, and what might also explain it.
        </p>
        <div className="signals-grid">
          {orderedSignals.length > 0
            ? orderedSignals.map((signal, i) => (
                <AnimatedSignalCard
                  key={signal.id}
                  signal={signal}
                  index={i}
                  mediaType={mediaType}
                  detectorStats={detectorStats}
                  phoenixTraceId={reportData.phoenix_trace_id}
                  forceWide={signal.id === forceWideId}
                />
              ))
            : <p style={{ color: "var(--text-muted)" }}>No signals extracted.</p>
          }
        </div>
      </motion.div>

      <motion.div
        className="json-section"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
      >
        <div className="json-toggle-row">
          {onDownloadPdf && (
            <button
              type="button"
              className="json-toggle"
              onClick={onDownloadPdf}
              disabled={!!pdfDownloading}
              title="Download formal PDF report"
            >
              <FileDown size={16} />
              {pdfDownloading ? "Preparing PDF…" : "Download PDF report"}
            </button>
          )}
          <button className="json-toggle" onClick={() => onToggleJson()}>
            {showJson ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            Raw JSON export
          </button>
          {showJson && <CopyButton text={jsonStr} />}
        </div>
        <AnimatePresence>
          {showJson && (
            <motion.pre
              className="json-view"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
            >
              {jsonStr}
            </motion.pre>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

function AdminConsole({ onExit, onLogout, arizeHealth, onHealthUpdate, statsData, onStatsUpdate }) {
  const [traces, setTraces] = useState([]);
  const [health, setHealth] = useState(arizeHealth);
  const [agentActions, setAgentActions] = useState([]);
  const [roi, setRoi] = useState(null);
  const [drift, setDrift] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentResult, setAgentResult] = useState(null);
  const [expandedAgentActionId, setExpandedAgentActionId] = useState(null);
  const [agentPhase, setAgentPhase] = useState("idle"); // idle | booting | running | done
  const [revealedSteps, setRevealedSteps] = useState(0);
  const [pulsedDetectors, setPulsedDetectors] = useState({});
  const [calib, setCalib] = useState(null);
  const [reviewQueue, setReviewQueue] = useState([]);
  const prevRoiWeights = useRef({});

  useEffect(() => {
    setHealth(arizeHealth);
  }, [arizeHealth]);

  // Live weight update: when the agent changes a detector's weight, flash that
  // row so the causal loop (observability -> action -> changed influence) is visible.
  useEffect(() => {
    const rows = roi?.detectors || [];
    if (!rows.length) return;
    const prev = prevRoiWeights.current;
    const changed = {};
    rows.forEach((r) => {
      const w = Number(r.weight_multiplier);
      const before = prev[r.detector_id];
      if (before != null && Math.abs(before - w) > 0.001) {
        changed[r.detector_id] = w < before ? "down" : "up";
      }
    });
    const next = {};
    rows.forEach((r) => { next[r.detector_id] = Number(r.weight_multiplier); });
    prevRoiWeights.current = next;
    if (Object.keys(changed).length) {
      setPulsedDetectors(changed);
      const t = setTimeout(() => setPulsedDetectors({}), 3500);
      return () => clearTimeout(t);
    }
  }, [roi]);

  const loadAdminData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [healthRes, tracesRes, statsRes, agentRes, driftRes, roiRes, calibRes, queueRes] = await Promise.all([
        fetch(`${API_BASE}/arize/health`),
        fetch(`${API_BASE}/arize/traces?limit=10`),
        fetch(`${API_BASE}/stats`),
        fetch(`${API_BASE}/agent/activity?limit=15`),
        fetch(`${API_BASE}/agent/tools/accuracy-drift`),
        fetch(`${API_BASE}/agent/detector-roi`),
        fetch(`${API_BASE}/agent/calibration`),
        fetch(`${API_BASE}/agent/review-queue?limit=10`),
      ]);
      const healthJson = healthRes.ok ? await healthRes.json() : null;
      const tracesJson = tracesRes.ok ? await tracesRes.json() : { traces: [] };
      const statsJson = statsRes.ok ? await statsRes.json() : null;
      const agentJson = agentRes.ok ? await agentRes.json() : { actions: [] };
      const driftJson = driftRes.ok ? await driftRes.json() : { detectors: [] };
      const roiJson = roiRes.ok ? await roiRes.json() : null;
      const calibJson = calibRes.ok ? await calibRes.json() : null;
      const queueJson = queueRes.ok ? await queueRes.json() : null;
      if (calibJson && Array.isArray(calibJson.bands)) setCalib(calibJson);
      if (queueJson && Array.isArray(queueJson.items)) setReviewQueue(queueJson.items);
      if (roiJson && Array.isArray(roiJson.detectors)) setRoi(roiJson);
      const driftMap = {};
      (Array.isArray(driftJson.detectors) ? driftJson.detectors : []).forEach((row) => { driftMap[row.detector_id] = row; });
      setDrift(driftMap);
      if (healthJson) {
        if (healthJson.phoenix_link) setPhoenixLinkInfo(healthJson.phoenix_link);
        setHealth(healthJson);
        onHealthUpdate?.(healthJson);
      }
      if (statsJson) onStatsUpdate?.(statsJson);
      setTraces(Array.isArray(tracesJson.traces) ? tracesJson.traces : []);
      setAgentActions(Array.isArray(agentJson.actions) ? agentJson.actions : []);
    } catch {
      setError("Could not load Arize operator data.");
    } finally {
      setLoading(false);
    }
  }, [onHealthUpdate, onStatsUpdate]);

  useEffect(() => {
    loadAdminData();
    const id = setInterval(loadAdminData, 15000);
    return () => clearInterval(id);
  }, [loadAdminData]);

  const runInvestigatorAgent = useCallback(async () => {
    setAgentRunning(true);
    setAgentResult(null);
    setRevealedSteps(0);
    setAgentPhase("booting");
    try {
      // Kick off the real call, but hold the boot sequence on screen so the
      // runtime (Agent Builder + Phoenix MCP + Gemini) is named before steps run.
      const fetchPromise = fetch(`${API_BASE}/agent/investigate`, { method: "POST" })
        .then((res) => (res.ok ? res.json() : null));
      await new Promise((r) => setTimeout(r, 1600));
      const data = await fetchPromise;
      if (!data) {
        setAgentResult({ error: "Agent run failed." });
        setAgentPhase("done");
        return;
      }
      setAgentResult(data);
      if (Array.isArray(data.roi)) {
        setRoi({ detectors: data.roi, system: data.system, phoenix_available: roi?.phoenix_available });
      }
      // Stream the tool steps in one at a time so the run reads as live reasoning.
      setAgentPhase("running");
      const steps = Array.isArray(data.steps) ? data.steps : [];
      for (let i = 1; i <= steps.length; i += 1) {
        setRevealedSteps(i);
        // eslint-disable-next-line no-await-in-loop
        await new Promise((r) => setTimeout(r, 480));
      }
      setAgentPhase("done");
      loadAdminData();
    } catch {
      setAgentResult({ error: "Could not reach the agent endpoint." });
      setAgentPhase("done");
    } finally {
      setAgentRunning(false);
    }
  }, [loadAdminData, roi]);

  const reactivateDetector = useCallback(async (detectorId) => {
    try {
      await fetch(`${API_BASE}/agent/tools/reactivate-detector`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ detector_id: detectorId }),
      });
      loadAdminData();
    } catch {
      /* best effort */
    }
  }, [loadAdminData]);

  const benchDetectorManually = useCallback(async (detectorId) => {
    try {
      await fetch(`${API_BASE}/agent/tools/bench-detector`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ detector_id: detectorId, reason: "manual operator bench" }),
      });
      loadAdminData();
    } catch {
      /* best effort */
    }
  }, [loadAdminData]);

  const BOOT_LINES = [
    "Google Agent Builder · session started",
    "Arize Phoenix MCP · connected",
    "Gemini · ready",
  ];
  const stepPlatform = (s) =>
    (s?.tags || []).some((t) => /mcp/i.test(t)) || /phoenix/i.test(s?.tool || "")
      ? "Arize MCP"
      : "Agent Builder";

  const governor = health?.detector_governor || {};
  const detectorRows = Object.entries(governor.detectors || {});
  const calibration = governor.calibration_divergence;
  // The operator feed shows what the reliability agent does to govern the system.
  // Per-case consumer artifacts (fact-check notes drafted from the public chat)
  // belong to that case, not this system-governance feed.
  const GOVERNANCE_ACTIONS = new Set(["review", "recalibrate", "flag_review", "bench", "reactivate"]);
  const governanceActions = agentActions.filter((a) => GOVERNANCE_ACTIONS.has(a.type));
  const roiRows = roi?.detectors || [];
  const roiSystem = roi?.system || {};
  const globalStats = statsData?.global || {};
  const mediaStats = globalStats.by_media_type || {};
  const verdictStats = globalStats.by_verdict || {};
  const feedback = statsData?.feedback || {};
  const realWorldAccuracy = feedback.total_feedback ? feedback.accuracy_rate : null;
  const aiCount = verdictStats.likely_ai_generated || verdictStats.ai_generated || 0;
  const authCount = verdictStats.likely_authentic || verdictStats.authentic || 0;
  const incCount = verdictStats.inconclusive || 0;
  const detectorUniverse = new Set();
  traces.forEach((t) => Object.keys(t.detectors || {}).forEach((d) => detectorUniverse.add(d)));
  const detectorCount = detectorUniverse.size || 13;
  const phoenixProjectUrl = phoenixLinkInfo.base
    ? `${phoenixLinkInfo.base.replace(/\/$/, "")}/projects/${phoenixLinkInfo.projectId || phoenixLinkInfo.projectName}`
    : "";

  return (
    <div className="console-page">
      <header className="console-header">
        <div className="console-title">
          <span className="console-kicker">Operator console</span>
          <h1>Reliability & Agent Operations</h1>
          <p className="console-sub">Arize Phoenix traces and human-confirmed outcomes drive how the Gemini agent reweights each detector.</p>
        </div>
        <div className="console-actions">
          <div className={`admin-health-pill ${health?.status === "calibration_alert" ? "warn" : health?.status === "anomaly" ? "error" : "ok"}`}>
            <Activity size={14} />
            Arize Phoenix · Live
          </div>
          <button className="admin-refresh" onClick={loadAdminData} disabled={loading}>
            <RefreshCw size={14} /> {loading ? "Refreshing" : "Refresh"}
          </button>
          <button className="console-btn" onClick={onExit}>Back to app</button>
          <button className="console-btn ghost" onClick={onLogout} title="Log out">Log out</button>
        </div>
      </header>
      <div className="console-body">
              <p className="admin-framing-copy">
                Every investigation is stored in Firestore and recorded as a Phoenix trace, so any verdict can be reopened and inspected later.
              </p>

              <section className="console-arize">
                <div className="console-arize-head">
                  <h3>Why Arize Phoenix is in the loop</h3>
                  {phoenixProjectUrl && (
                    <a className="phoenix-link" href={phoenixProjectUrl} target="_blank" rel="noreferrer">
                      Open Phoenix dashboard <ChevronRight size={12} />
                    </a>
                  )}
                </div>
                <div className="console-arize-cards">
                  <div className="console-arize-card">
                    <strong>{globalStats.total_analyses || 0}</strong>
                    <span>verdicts traced</span>
                    <p>Each analysis is recorded as a Phoenix trace with its detector spans, so the reasoning behind any verdict stays auditable.</p>
                  </div>
                  <div className="console-arize-card">
                    <strong>{detectorCount}</strong>
                    <span>forensic detectors</span>
                    <p>Phoenix captures each detector's latency and result on every run, so we see where time goes and which checks start to misbehave.</p>
                  </div>
                  <div className="console-arize-card">
                    <strong>{governanceActions.length}</strong>
                    <span>autonomous agent actions</span>
                    <p>The agent reads this telemetry and acts on it, recalibrating detector weights instead of leaving them fixed.</p>
                  </div>
                </div>
              </section>

              <div className="agent-status-strip">
                <span className="agent-status-item">
                  <Target size={14} /> Investigator agent
                </span>
                <span className="agent-pillar"><Cpu size={12} /> Google Agent Builder</span>
                <span className={`agent-pillar ${health?.phoenix_link?.project_id ? "live" : "off"}`}>
                  <Activity size={12} /> Phoenix MCP{health?.phoenix_link?.project_id ? "" : " · offline"}
                </span>
                <span className="agent-pillar"><Sparkles size={12} /> Gemini</span>
                <span className="agent-pillar"><Database size={12} /> Firestore</span>
                <span className="agent-status-meta">Recalibrates, flags, and drafts from its own observability</span>
              </div>

              {error && <div className="admin-alert error">{error}</div>}
              {calibration?.active && (
                <div className="admin-alert warn">
                  <AlertOctagon size={16} />
                  Spectral detector influence is reduced to {formatPercent(governor.spectral_attenuation_factor)} after repeated calibration divergence.
                </div>
              )}

              <section className="admin-stats-row">
                <div className="admin-stat-pill admin-stat-hero">
                  <strong>{realWorldAccuracy != null ? formatPercent(realWorldAccuracy) : "—"}</strong>
                  <span>
                    real-world accuracy
                    {feedback.total_feedback
                      ? ` · ${feedback.confirmed_correct}/${feedback.total_feedback} human-confirmed`
                      : " · awaiting confirmations"}
                  </span>
                </div>
                <div className="admin-stat-pill">
                  <strong>{globalStats.total_analyses || 0}</strong>
                  <span>total analyses</span>
                </div>
                <div className="admin-stat-pill">
                  <strong>{mediaStats.image || 0} · {mediaStats.video || 0} · {mediaStats.audio || 0}</strong>
                  <span>images · videos · audio</span>
                </div>
                <div className="admin-stat-pill">
                  <strong>{aiCount} · {authCount} · {incCount}</strong>
                  <span>AI · authentic · inconclusive</span>
                </div>
              </section>

              {calib?.bands?.length > 0 && (
                <section className="admin-section calib-card">
                  <h3><Target size={14} /> Confidence Calibration</h3>
                  <p className="admin-section-sub">
                    Whether our confidence is honest: how often each reported-certainty band was confirmed correct by a human reviewer.
                  </p>
                  {calib.hero && (
                    <p className="calib-hero">
                      When ArgusAI reports <strong>{calib.hero.label}</strong> confidence, it is confirmed correct <strong>{formatPercent(calib.hero.accuracy)}</strong> of the time across {calib.hero.count} reviewed {calib.hero.count === 1 ? "case" : "cases"}.
                    </p>
                  )}
                  {calib.bands.map((b) => {
                    const color = b.well_calibrated ? "#34d399" : "#fbbf24";
                    return (
                      <div className="calib-band" key={b.label}>
                        <span className="calib-band-label">{b.label}</span>
                        <span className="calib-band-track">
                          <span className="calib-band-fill" style={{ width: `${Math.max(3, Math.round((b.accuracy || 0) * 100))}%`, background: color }} />
                        </span>
                        <span className="calib-band-val" style={{ color }}>{formatPercent(b.accuracy)}</span>
                      </div>
                    );
                  })}
                </section>
              )}

              <section className="admin-section">
                <div className="admin-section-head">
                  <h3><Activity size={14} /> Investigator Agent</h3>
                  <button className="agent-run-btn" onClick={runInvestigatorAgent} disabled={agentRunning}>
                    {agentRunning ? <><div className="spin-ring" /> Running…</> : <><Target size={14} /> Run investigator agent</>}
                  </button>
                </div>
                <p className="admin-section-sub">
                  ArgusAI self-calibrates slowly from each detector's lifetime accuracy on its own. The agent is the fast layer: it fuses human-confirmed accuracy from Firestore with live Phoenix telemetry, catches recent drift the slow loop misses, and recalibrates under human oversight. It governs the system, it does not just report on it.
                </p>

                {(agentPhase === "booting" || agentResult) && (
                  <div className="agent-run-result">
                    {agentPhase === "booting" ? (
                      <div className="agent-boot">
                        {BOOT_LINES.map((line, i) => (
                          <div className="agent-boot-line" style={{ animationDelay: `${i * 0.45}s` }} key={line}>
                            <Check size={13} /> {line}
                          </div>
                        ))}
                      </div>
                    ) : agentResult?.error ? (
                      <div className="admin-alert error">{agentResult.error}</div>
                    ) : (
                      <>
                        <ol className="agent-steps">
                          {(agentResult?.steps || []).slice(0, revealedSteps).map((s, i) => (
                            <li key={i} className={(s.tool === "recalibrate_detector_weight" || s.tool === "bench_detector") ? "agent-step-action" : ""}>
                              <span className={`step-platform ${stepPlatform(s) === "Arize MCP" ? "mcp" : ""}`}>{stepPlatform(s)}</span>
                              <span className="mono">{s.tool}</span> {s.summary}
                            </li>
                          ))}
                        </ol>
                        {agentPhase === "done" && agentResult?.narration && (
                          <p className="agent-narration">{agentResult.narration}</p>
                        )}
                      </>
                    )}
                  </div>
                )}

                <div className="admin-events">
                  {governanceActions.length ? governanceActions.map((a) => {
                    const cls = a.type === "bench" ? "warn" : a.type === "recalibrate" ? "calib" : a.type === "flag_review" ? "warn" : "";
                    const label = a.type === "bench" ? "Benched" : a.type === "reactivate" ? "Reactivated" : a.type === "recalibrate" ? "Recalibrated" : a.type === "flag_review" ? "Flagged" : "Reviewed";
                    const actionId = a.id || `${a.timestamp}-${a.summary}`;
                    const expanded = expandedAgentActionId === actionId;
                    const report = a.detail?.report || null;
                    const steps = report?.steps || [];
                    const telemetry = report?.phoenix_telemetry || null;
                    const lowValue = report?.low_value_detectors || a.detail?.low_value_detectors || [];
                    const detectors = report?.detectors_evaluated || [];
                    const recalibrations = report?.recalibrations || [];
                    return (
                      <div className={`admin-event ${cls} agent-report-row ${expanded ? "expanded" : ""}`} key={actionId}>
                        <button className="agent-report-toggle" onClick={() => setExpandedAgentActionId(expanded ? null : actionId)}>
                          <span className="mono">{label}</span>
                          <span>{a.summary} · {formatTime(a.timestamp)}</span>
                          <ChevronDown className="agent-report-chevron" size={15} />
                        </button>
                        {expanded && (
                          <div className="agent-report-detail">
                            {!report ? (
                              <div className="agent-report-block">
                                <h4>Legacy action</h4>
                                <p>This row was logged before full agent run reports were stored. Run the investigator agent again to create an auditable report.</p>
                              </div>
                            ) : (
                              <>
                                {report.narration && <p className="agent-report-narration">{report.narration}</p>}

                                {steps.length > 0 && (
                                  <div className="agent-report-block">
                                    <h4>Tool trail</h4>
                                    <ol className="agent-steps agent-report-steps">
                                      {steps.map((step, idx) => (
                                        <li key={`${step.tool || "step"}-${idx}`}>
                                          <span className="mono">{step.tool}</span>
                                          {stepUsesPhoenixMcp(step) && <span className="mcp-chip">via Arize Phoenix MCP</span>}
                                          {step.summary}
                                        </li>
                                      ))}
                                    </ol>
                                  </div>
                                )}

                                {telemetry && (
                                  <div className="agent-report-metrics">
                                    <div>
                                      <strong>{telemetry.available ? "Live" : "Unavailable"}</strong>
                                      <span>Phoenix telemetry</span>
                                    </div>
                                    <div>
                                      <strong>{Number(telemetry.model_calls || 0).toLocaleString()}</strong>
                                      <span>model calls</span>
                                    </div>
                                    <div>
                                      <strong>{Number(telemetry.total_tokens || 0).toLocaleString()}</strong>
                                      <span>tokens</span>
                                    </div>
                                    <div>
                                      <strong>{formatPercent(telemetry.fallback_rate || 0)}</strong>
                                      <span>fallback rate</span>
                                    </div>
                                  </div>
                                )}

                                <div className="agent-report-block">
                                  <h4>Decision</h4>
                                  {lowValue.length > 0 ? (
                                    <p>Flagged low-value detectors: {lowValue.map((row) => row.name || detectorLabel(row.id)).join(", ")}.</p>
                                  ) : (
                                    <p>No detector crossed the low-value threshold in this review.</p>
                                  )}
                                  {recalibrations.length > 0 ? (
                                    <p>Recalibrated: {recalibrations.map((row) => detectorLabel(row.detector_id)).join(", ")}.</p>
                                  ) : (
                                    <p>Weights held stable because confirmed drift stayed within tolerance.</p>
                                  )}
                                </div>

                                {detectors.length > 0 && (
                                  <div className="agent-report-block">
                                    <h4>Detectors evaluated</h4>
                                    <div className="agent-report-table-wrap">
                                      <table className="agent-report-table">
                                        <thead>
                                          <tr>
                                            <th>Detector</th>
                                            <th>Tier</th>
                                            <th>Accuracy</th>
                                            <th>Latency</th>
                                            <th>Weight</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {detectors.map((row) => (
                                            <tr key={row.id || row.name}>
                                              <td>{row.name || detectorLabel(row.id)}</td>
                                              <td>{formatVerdict(row.tier || "unknown")}</td>
                                              <td>{formatPercent(row.confirmed_accuracy || 0)}</td>
                                              <td>{formatLatencySeconds(row.avg_latency_seconds)}</td>
                                              <td>{Number(row.weight || 1).toFixed(2)}x</td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  }) : (
                    <div className="admin-empty">No agent actions yet. Run the investigator agent above, and its actions will appear here.</div>
                  )}
                </div>
              </section>

              {roiRows.length > 0 && (() => {
                const ROI_TIERS = {
                  earning: { label: "Earning its weight", color: "#34d399" },
                  watch: { label: "Watch", color: "#fbbf24" },
                  low_value: { label: "Low value for cost", color: "#f87171" },
                  calibrating: { label: "Calibrating", color: "#38bdf8" },
                };
                const maxEff = Math.max(...roiRows.map((r) => r.efficiency || 0), 0.001);
                return (
                  <section className="admin-section">
                    <h3><Gauge size={14} /> Detector Influence</h3>
                    <p className="admin-section-sub">
                      Confirmed accuracy weighed against Phoenix latency and error rate. This is how the agent decides which detectors earn their weight on every future verdict.
                    </p>
                    {Object.keys(statsData?.learned_weights || {}).length > 0 && (
                      <div className="admin-alert calib">
                        <Activity size={15} />
                        Self-calibration is active. ArgusAI has re-weighted {Object.keys(statsData.learned_weights).length} detector{Object.keys(statsData.learned_weights).length > 1 ? "s" : ""} from confirmed outcomes.
                      </div>
                    )}
                    {roi?.phoenix_available === false && (
                      <p className="admin-section-sub" style={{ color: "#fbbf24" }}>
                        Phoenix telemetry is not reachable right now, so latency and error figures fall back to Firestore averages.
                      </p>
                    )}
                    <div className="admin-leaderboard admin-roi-list">
                      {roiRows.map((r) => {
                        const tier = ROI_TIERS[r.tier] || ROI_TIERS.calibrating;
                        const bar = Math.max(2, Math.round(((r.efficiency || 0) / maxEff) * 100));
                        const dr = drift[r.detector_id];
                        const driftDelta = dr ? Number(dr.delta) : null;
                        const showDrift = dr && Math.abs(driftDelta) >= 0.05;
                        const pulse = pulsedDetectors[r.detector_id];
                        return (
                          <div className={`lb-row lb-row-roi${pulse ? ` lb-row-pulse-${pulse}` : ""}`} key={r.detector_id}>
                            <div className="lb-main">
                              <div className="lb-head">
                                <span className="lb-name mono">{detectorLabel(r.detector_id)}</span>
                                <div className="lb-tags">
                                  {showDrift && (
                                    <span className="lb-drift" style={{ color: driftDelta < 0 ? "#f87171" : "#34d399" }} title="Recent confirmed accuracy vs historical">
                                      {driftDelta < 0 ? "↘" : "↗"} {Math.abs(Math.round(driftDelta * 100))}% recent
                                    </span>
                                  )}
                                  {r.weight_source === "benched" ? (
                                    <>
                                      <span className="lb-source-benched" title={r.override_reason || "Benched by the reliability agent"}>
                                        Benched by agent
                                      </span>
                                      <button className="lb-reactivate" onClick={() => reactivateDetector(r.detector_id)} title="Bring this detector back into rotation">
                                        Reactivate
                                      </button>
                                    </>
                                  ) : (
                                    <>
                                      {r.weight_source === "agent" && (
                                        <span className="lb-source-agent" title={r.override_reason || "The reliability agent set this weight"}>
                                          Agent override
                                        </span>
                                      )}
                                      <span className="lb-weight" style={{ color: tier.color, borderColor: `${tier.color}55` }}>
                                        {r.weight_multiplier?.toFixed(2)}× weight
                                      </span>
                                      <span className="lb-trust" style={{ color: tier.color, borderColor: `${tier.color}55`, background: `${tier.color}14` }}>
                                        {tier.label}
                                      </span>
                                      <button className="lb-disable" onClick={() => benchDetectorManually(r.detector_id)} title="Disable this detector until it is reactivated">
                                        Disable
                                      </button>
                                    </>
                                  )}
                                </div>
                              </div>
                              <div className="lb-bar-track">
                                <div className="lb-bar-fill" style={{ width: `${bar}%`, background: tier.color }} />
                              </div>
                              <div className="lb-meta">
                                <span>{r.insight}</span>
                                <span>{Number(r.avg_latency_seconds) >= 0.1 ? `${Number(r.avg_latency_seconds).toFixed(1)}s/run` : "sub-second"}</span>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    {(roiSystem.total_tokens > 0 || roiSystem.least_efficient_detector) && (
                      <p className="admin-section-sub" style={{ marginTop: "0.75rem" }}>
                        Phoenix recorded {roiSystem.total_tokens?.toLocaleString?.() || roiSystem.total_tokens || 0} model tokens across {roiSystem.llm_calls || 0} calls
                        {roiSystem.fallback_rate > 0 ? `, with ${Math.round(roiSystem.fallback_rate * 100)}% on the lighter fallback model` : ""}
                        {roiSystem.least_efficient_detector ? `. Weakest on value for cost: ${detectorLabel(roiSystem.least_efficient_detector)}.` : "."}
                      </p>
                    )}
                  </section>
                );
              })()}

              {reviewQueue.length > 0 && (
                <section className="admin-section">
                  <h3><AlertOctagon size={14} /> Needs Human Review</h3>
                  <p className="admin-section-sub">
                    Cases the agent flagged, plus low-confidence or inconclusive verdicts awaiting a human decision.
                  </p>
                  <div className="review-queue">
                    {reviewQueue.map((it, i) => (
                      <div className={`review-item ${it.source === "flagged" ? "flagged" : "low"}`} key={`${it.timestamp || i}-${i}`}>
                        <span className="review-media">{it.media_type || "—"}</span>
                        <span className="review-verdict">{formatVerdict(it.verdict || "unknown")}</span>
                        <span className="review-reason">{it.reason}{it.timestamp ? ` · ${formatTime(it.timestamp)}` : ""}</span>
                        {it.phoenix_trace_id ? (
                          <a className="review-btn" href={phoenixTraceUrl(it.phoenix_trace_id)} target="_blank" rel="noreferrer">Review case</a>
                        ) : (
                          <span className="review-btn">Review case</span>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="admin-section">
                <h3>Recent Investigations</h3>
                <div className="admin-table-wrap">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Media</th>
                        <th>Verdict</th>
                        <th>Certainty</th>
                        <th>Latency</th>
                        <th>Trace</th>
                      </tr>
                    </thead>
                    <tbody>
                      {traces.length ? traces.map((trace, idx) => (
                        <tr key={`${trace.sha256 || idx}-${trace.timestamp || idx}`}>
                          <td>{formatTime(trace.timestamp)}</td>
                          <td>{trace.media_type || "image"}</td>
                          <td>{formatVerdict(trace.verdict || "unknown")}</td>
                          <td>{formatPercent(trace.certainty)}</td>
                          <td>{formatLatency(trace.latency_seconds)}</td>
                          <td className="mono">
                            {trace.phoenix_trace_id ? (
                              <a className="phoenix-link" href={phoenixTraceUrl(trace.phoenix_trace_id)} target="_blank" rel="noreferrer">
                                {shortHash(trace.sha256 || trace.phoenix_trace_id)}
                              </a>
                            ) : shortHash(trace.sha256)}
                          </td>
                        </tr>
                      )) : (
                        <tr><td colSpan={6}>No x-ray traces written yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              {(detectorRows.length > 0 || (governor.recent_events || []).length > 0) && (
                <section className="admin-grid">
                  {detectorRows.length > 0 && (
                    <div className="admin-section">
                      <h3><Activity size={14} /> Detector Health Gates</h3>
                      <div className="admin-health-grid">
                        {detectorRows.map(([id, row]) => (
                          <div key={id} className={`admin-detector ${row.active ? "active" : ""}`}>
                            <span className="mono">{detectorLabel(id)}</span>
                            <strong>{row.active ? "Weight reduced" : "Recovered"}</strong>
                            <small>{row.reason || "nominal"}</small>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {(governor.recent_events || []).length > 0 && (
                    <div className="admin-section">
                      <h3><AlertOctagon size={14} /> Calibration Events</h3>
                      <div className="admin-events">
                        {governor.recent_events.slice().reverse().map((event, idx) => (
                          <div className={`admin-event ${event.reason === "calibration_divergence" ? "warn" : ""}`} key={`${event.recorded_at || idx}-${idx}`}>
                            <span className="mono">{event.reason || "detector_event"}</span>
                            <p>{detectorLabel(event.detector_id) || "detector"} · {formatTime(event.recorded_at)}{event.active_until ? ` · active until ${formatTime(event.active_until)}` : ""}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
              )}
      </div>
    </div>
  );
}

function LoginModal({ open, onClose, onAdminSuccess }) {
  const [password, setPassword] = useState("");
  const [shake, setShake] = useState(false);

  if (!open) return null;

  const submit = (e) => {
    e.preventDefault();
    if (password === ADMIN_PASSWORD) {
      localStorage.setItem("argusai_admin", "1");
      setPassword("");
      onAdminSuccess();
      return;
    }
    setShake(true);
    setPassword("");
    setTimeout(() => setShake(false), 450);
  };

  return (
    <AnimatePresence>
      <motion.div className="admin-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
        <motion.div
          className="login-modal"
          initial={{ opacity: 0, y: 18, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.98 }}
          transition={{ duration: 0.18 }}
          onClick={(e) => e.stopPropagation()}
        >
          <button className="admin-icon-btn login-close" onClick={onClose} title="Close"><X size={18} /></button>
          <div className="login-head">
            <img src="/logo.jpeg" alt="ArgusAI" className="login-logo" />
            <h2>Sign in to ArgusAI</h2>
            <p>Investigators and teams sign in for the operator console. You can also continue without an account.</p>
          </div>
          <form className={`login-form ${shake ? "admin-shake" : ""}`} onSubmit={submit}>
            <label className="login-label">Access key</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your access key"
              autoFocus
            />
            <button type="submit" className="login-submit">Sign in</button>
          </form>
          <button className="login-guest" onClick={onClose}>Continue without an account</button>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function LandingPage({ fileInputRef, previewUrl, fileType, selectedMediaType, handleDrop, handleFileChange, contextText, setContextText, fileSelected, isAnalyzing, handleAnalyze, sessionError }) {
  const mediaCopy = getMediaCopy(selectedMediaType || "default");
  return (
    <div className="landing-root">

      {/* ── HERO: 2-column split ── */}
      <section className="lp-hero">
        {/* Left: pitch */}
        <div className="lp-hero-left">
          <div className="lp-hero-badge">{mediaCopy.badge}</div>
          <h2 className="lp-hero-title">
            Can you trust<br/>
            <span className="lp-hero-accent">{mediaCopy.titleAccent}</span>
          </h2>
          <p className="lp-hero-sub">{mediaCopy.heroSub}</p>
          <p className="lp-hero-sub">{mediaCopy.heroSub2}</p>
          <ul className="lp-hero-bullets">
            <li>Runs only the signals that make sense for the uploaded media type</li>
            <li>Uses Gemini and public-source research to explain provenance and context</li>
            <li>Shows every visible signal individually so the reasoning stays transparent</li>
          </ul>
        </div>

        {/* Right: examiner panel */}
        <div className="lp-hero-right">
          <div className="lp-examiner">
            <div className="lp-examiner-label">Begin examination</div>
            <div
              className={`lp-drop-zone ${previewUrl ? "has-preview" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => !previewUrl && fileInputRef.current?.click()}
            >
              <input ref={fileInputRef} type="file"
                accept="image/*,video/*,audio/*,.mp3,.wav,.ogg,.m4a,.flac"
                className="file-input-hidden" onChange={handleFileChange} />
              {previewUrl ? (
                <div style={{ width: "100%", position: "relative" }}>
                  {selectedMediaType && (
                    <span className="arize-badge" style={{ position: "absolute", top: 10, left: 10, zIndex: 2 }}>
                      {mediaBadgeLabel(selectedMediaType)}
                    </span>
                  )}
                  {selectedMediaType === "video" ? (
                    <video src={previewUrl} controls className="lp-preview-img" />
                  ) : selectedMediaType === "audio" ? (
                    <div className="lp-audio-preview">
                      <Zap size={36} style={{ color: "#06b6d4", marginBottom: 10 }} />
                      <p style={{ color: "#06b6d4", fontWeight: 600, margin: "0 0 8px" }}>{mediaCopy.uploadTitle}</p>
                      <audio src={previewUrl} controls style={{ width: "100%" }} />
                    </div>
                  ) : (
                    <img src={previewUrl} alt="Preview" className="lp-preview-img" />
                  )}
                  </div>
              ) : (
                <div className="lp-drop-inner">
                  <div className="lp-drop-icon"><ImageIcon size={20} /></div>
                  <p className="lp-drop-title">Drop image, video, or audio</p>
                  <p className="lp-drop-sub">or click to browse (JPG, PNG, MP4, WAV, MP3...)</p>
                </div>
              )}
            </div>
            <textarea
              className="lp-context-input"
              rows={2}
              placeholder={mediaCopy.contextPlaceholder}
              value={contextText}
              onChange={(e) => setContextText(e.target.value)}
              disabled={isAnalyzing}
            />
            <motion.button
              className={`lp-analyze-btn ${isAnalyzing ? "analyzing" : ""} ${!fileSelected ? "disabled" : ""}`}
              onClick={handleAnalyze}
              disabled={!fileSelected || isAnalyzing || !!sessionError}
              whileHover={fileSelected && !isAnalyzing ? { scale: 1.015 } : {}}
              whileTap={fileSelected && !isAnalyzing ? { scale: 0.97 } : {}}
            >
              {isAnalyzing
                ? <><div className="spin-ring white" />{mediaCopy.processing}</>
                : <><Search size={15} />Run Investigation</>
              }
            </motion.button>
          </div>
        </div>
      </section>

      {/* ── EVIDENCE STRIP ── */}
      <section className="lp-evidence" id="sample-media">
        <p className="lp-section-eyebrow">Sample investigation media</p>
        <div className="lp-carousel-wrapper">
          <div className="lp-carousel-track">
            {[...CAROUSEL_IMAGES, ...CAROUSEL_IMAGES].map((src, idx) => (
              <div key={idx} className="lp-carousel-item">
                <img src={src} className="lp-carousel-img" alt="Forensic benchmark" loading="lazy" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS — 2×2 grid ── */}
      <section className="lp-how" id="how-it-works">
        <div className="lp-how-head">
          <p className="lp-section-eyebrow">How it works</p>
          <h3 className="lp-section-title">Four lenses. One verdict.</h3>
        </div>
        <div className="lp-pipeline-grid">
          <div className="lp-pipeline-card" style={{"--card-accent":"#a855f7"}}>
            <div className="lp-step-num" style={{color:"#a855f7",borderColor:"rgba(168,85,247,0.3)",background:"rgba(168,85,247,0.07)"}}>01</div>
            <h4>Spectral analysis</h4>
            <p>Looks for hidden frequency patterns in image pixels or extracted video frames when that signal is relevant.</p>
          </div>
          <div className="lp-pipeline-card" style={{"--card-accent":"#3b82f6"}}>
            <div className="lp-step-num" style={{color:"#3b82f6",borderColor:"rgba(59,130,246,0.3)",background:"rgba(59,130,246,0.07)"}}>02</div>
            <h4>Physical coherence</h4>
            <p>Checks the physical and semantic coherence of the media: scene geometry, motion, voice cadence, lighting, or other cues depending on file type.</p>
          </div>
          <div className="lp-pipeline-card" style={{"--card-accent":"#10b981"}}>
            <div className="lp-step-num" style={{color:"#10b981",borderColor:"rgba(16,185,129,0.3)",background:"rgba(16,185,129,0.07)"}}>03</div>
            <h4>Live web fact-checking</h4>
            <p>Searches live news and public databases to see whether the claimed image, footage, recording, or event has public provenance.</p>
          </div>
          <div className="lp-pipeline-card" style={{"--card-accent":"#22d3ee"}}>
            <div className="lp-step-num" style={{color:"#22d3ee",borderColor:"rgba(34,211,238,0.3)",background:"rgba(34,211,238,0.07)"}}>04</div>
            <h4>Verdict engine</h4>
            <p>The visible signals are weighed together and a final verdict is issued with a plain-language explanation of exactly what was found and why.</p>
          </div>
        </div>
      </section>

      {/* ── WHY DIFFERENT ── */}
      <section className="lp-diff" id="why-argus">
        <div className="lp-diff-card">
          <div className="lp-diff-icon" style={{background:"rgba(168,85,247,0.08)",borderColor:"rgba(168,85,247,0.2)",color:"#a855f7"}}><Layers size={18}/></div>
          <div>
            <h4>You see the evidence</h4>
            <p>Every check is shown individually. You can see exactly what each detector found and decide for yourself how much weight to give it.</p>
          </div>
        </div>
        <div className="lp-diff-card">
          <div className="lp-diff-icon" style={{background:"rgba(16,185,129,0.08)",borderColor:"rgba(16,185,129,0.2)",color:"#10b981"}}><Globe size={18}/></div>
          <div>
            <h4>Cross-referenced with the web</h4>
            <p>File analysis only goes so far. ArgusAI also checks whether the claim matches real events or statements reported by credible sources.</p>
          </div>
        </div>
        <div className="lp-diff-card">
          <div className="lp-diff-icon" style={{background:"rgba(34,211,238,0.08)",borderColor:"rgba(34,211,238,0.2)",color:"#22d3ee"}}><Activity size={18}/></div>
          <div>
            <h4>Every verdict is auditable</h4>
            <p>Each analysis is recorded as a traceable forensic record: what each detector found, when, and how the verdict was reached. Defensible enough for a newsroom or a court.</p>
          </div>
        </div>
      </section>

    </div>
  );
}

export default function App() {
  const [sessionId, setSessionId]       = useState(null);
  const [sessionError, setSessionError] = useState("");
  const [messages, setMessages]         = useState([]);
  const [status, setStatus]             = useState("");
  const [isAnalyzing, setIsAnalyzing]   = useState(false);
  const [isSending, setIsSending]       = useState(false);
  const [previewUrl, setPreviewUrl]     = useState("");
  const [fileSelected, setFileSelected] = useState(false);
  const [contextText, setContextText]   = useState("");
  const [followUp, setFollowUp]         = useState("");
  const [showJsonById, setShowJsonById] = useState({});
  const [scanStep, setScanStep]         = useState(0);
  const [followUpStep, setFollowUpStep] = useState(0);
  const [pdfLoadingForId, setPdfLoadingForId] = useState(null);
  const [arizeHealth, setArizeHealth] = useState(null);
  const [statsData, setStatsData] = useState(null);
  const [feedbackBySession, setFeedbackBySession] = useState({});
  const [fileType, setFileType]         = useState("");
  const [selectedMediaType, setSelectedMediaType] = useState("");
  const [view, setView] = useState("app"); // 'app' | 'admin'
  const [loginOpen, setLoginOpen] = useState(false);
  const isAdmin = view === "admin";

  const fileInputRef = useRef(null);
  const feedEndRef   = useRef(null);

  // Cycle scan text while analyzing
  useEffect(() => {
    if (!isAnalyzing) return;
    const id = setInterval(() => setScanStep((s) => s + 1), 2200);
    return () => clearInterval(id);
  }, [isAnalyzing]);

  useEffect(() => {
    if (!isSending) return;
    setFollowUpStep(0);
    const id = setInterval(() => setFollowUpStep((s) => s + 1), 1800);
    return () => clearInterval(id);
  }, [isSending]);

  const createFreshSession = useCallback(async () => {
    let coldStartTimer = null;
    try {
      coldStartTimer = setTimeout(() => {
        const localApi = API_BASE.includes("localhost") || API_BASE.includes("127.0.0.1");
        setStatus((current) => current || (
          localApi
            ? "Connecting to local backend..."
            : "Connecting to Google Cloud Run (waking up backend container)..."
        ));
      }, 3500);
      const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
      if (!res.ok) throw new Error("session_create_failed");
      const data = await res.json();
      setSessionId(data.session_id);
      setStatus("");
      return data.session_id;
    } finally {
      if (coldStartTimer) clearTimeout(coldStartTimer);
    }
  }, []);

  const ensureSession = useCallback(async () => {
    if (sessionId) return sessionId;
    return createFreshSession();
  }, [sessionId, createFreshSession]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await createFreshSession();
      } catch {
        if (!cancelled) {
          setSessionError("Could not reach the API. Check backend and VITE_API_BASE.");
          setStatus("");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [createFreshSession]);

  useEffect(() => {
    let cancelled = false;
    const loadArizeHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/arize/health`);
        if (!res.ok) return;
        const data = await res.json();
        if (data?.phoenix_link) setPhoenixLinkInfo(data.phoenix_link);
        if (!cancelled) setArizeHealth(data);
      } catch {
        if (!cancelled) setArizeHealth(null);
      }
    };
    loadArizeHealth();
    const id = setInterval(loadArizeHealth, 45000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      if (!res.ok) return;
      const data = await res.json();
      setStatsData(data);
    } catch {
      setStatsData(null);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const mediaType = detectMediaType(file);
    if (!mediaType) {
      setStatus("Unsupported file type. Use JPG, PNG, WebP, MP4, WebM, MOV, WAV, MP3, OGG, FLAC, or M4A.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    setStatus("");
    setFileSelected(true);
    setFileType(file.type);
    setSelectedMediaType(mediaType);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    // Audio has no visual preview — just store a blob URL for possible playback
    setPreviewUrl(URL.createObjectURL(file));
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!detectMediaType(file)) {
      setStatus("Unsupported file type. Use JPG, PNG, WebP, MP4, WebM, MOV, WAV, MP3, OGG, FLAC, or M4A.");
      return;
    }
    if (fileInputRef.current) {
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInputRef.current.files = dt.files;
      handleFileChange({ target: { files: [file] } });
    }
  };

  const clearImage = () => {
    setPreviewUrl(""); setFileSelected(false); setFileType(""); setSelectedMediaType("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAnalyze = async () => {
    const file = fileInputRef.current?.files[0];
    if (!file) return;

    const mediaType = detectMediaType(file);
    if (!mediaType) {
      setStatus("Unsupported file type. Use JPG, PNG, WebP, MP4, WebM, MOV, WAV, MP3, OGG, FLAC, or M4A.");
      return;
    }
    const isAudio = mediaType === "audio";

    setIsAnalyzing(true); setScanStep(0);
    setStatus(getMediaCopy(mediaType).processing);
    setShowJsonById({});

    const mediaSnapshot = previewUrl;

    try {
      let sid = await ensureSession();

      setMessages((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: "user", kind: "analyze", text: contextText.trim(), imageUrl: mediaSnapshot, fileType: file.type, mediaType },
      ]);

      if (isAudio) {
        // ── AUDIO PATH ───────────────────────────────────────────────────
        const postAudio = (sessionKey) => {
          const fd = new FormData();
          fd.append("file", file);
          fd.append("context", contextText.trim());
          return fetch(`${API_BASE}/sessions/${sessionKey}/analyze-audio`, { method: "POST", body: fd });
        };

        let res = await postAudio(sid);
        if (res.status === 404) {
          setSessionId(null);
          sid = await createFreshSession();
          res = await postAudio(sid);
        }
        if (!res.ok) {
          let detail = "";
          try {
            const errBody = await res.json();
            if (errBody?.error) detail = ` ${errBody.error}`;
          } catch { /* ignore */ }
          setStatus(`Audio analysis failed.${detail}`);
          return;
        }
        const audioReport = await res.json();
        setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", kind: "audio_report", report: audioReport }]);
      } else {
        // ── IMAGE / VIDEO PATH ────────────────────────────────────────────
        const postAnalyze = (sessionKey) => {
          const fd = new FormData();
          fd.append("file", file);
          fd.append("context", contextText.trim());
          return fetch(`${API_BASE}/sessions/${sessionKey}/analyze`, { method: "POST", body: fd });
        };

        let res = await postAnalyze(sid);
        if (res.status === 404) {
          setSessionId(null);
          sid = await createFreshSession();
          res = await postAnalyze(sid);
        }
        if (!res.ok) {
          let detail = "";
          try {
            const errBody = await res.json();
            if (errBody?.error) detail = ` ${errBody.error}`;
          } catch { /* ignore */ }
          setStatus(`Analysis failed.${detail}`);
          return;
        }
        const report = await res.json();
        setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", kind: "report", report }]);
      }

      setStatus("");
      setContextText("");
      loadStats();
    } catch {
      setStatus(
        API_BASE.includes("localhost")
          ? "Unable to reach the backend. For production, set VITE_API_BASE on Render and redeploy the static site."
          : "Unable to reach the backend. If the API was asleep, wait and try again."
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleFollowUp = async () => {
    const text = followUp.trim();
    if (!text || !sessionId) return;
    const now = Date.now();
    const pendingId = `pending-${now}`;
    setIsSending(true);
    setFollowUp("");
    setMessages((prev) => [
      ...prev,
      { id: `u-${now}`, role: "user", kind: "text", text },
      { id: pendingId, role: "assistant", kind: "agent_pending" },
    ]);
    try {
      const res  = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      const reply = res.ok ? data.reply : (data.error || "Could not answer.");
      const toolCalls = Array.isArray(data.tool_calls) ? data.tool_calls : [];
      setMessages((prev) => prev.map((m) => (
        m.id === pendingId
          ? { id: `a-${Date.now()}`, role: "assistant", kind: "text", text: reply, toolCalls }
          : m
      )));
    } catch {
      setMessages((prev) => prev.map((m) => (
        m.id === pendingId
          ? { id: `a-${Date.now()}`, role: "assistant", kind: "text", text: "Network error." }
          : m
      )));
    } finally {
      setIsSending(false);
    }
  };

  const toggleJson = (id) => setShowJsonById((prev) => ({ ...prev, [id]: !prev[id] }));

  const handleDownloadPdf = async (messageId, report) => {
    setPdfLoadingForId(messageId);
    try {
      const payload = stripReportForPdfRequest(report);
      const res = await fetch(`${API_BASE}/reports/official.pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let msg = "Could not download PDF. Try again.";
        try {
          const err = await res.json();
          if (err?.error) msg = `${err.error}${err.detail ? ` (${err.detail})` : ""}`;
        } catch {
          /* ignore */
        }
        setStatus(msg);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const hint = report?.evidence?.image?.sha256?.slice(0, 8) || "report";
      a.download = `argusai-report-${hint}.pdf`;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setStatus("Could not download PDF. Check the API connection.");
    } finally {
      setPdfLoadingForId(null);
    }
  };

  const handleFeedback = async (correct) => {
    if (!sessionId) return;
    setFeedbackBySession((prev) => ({ ...prev, [sessionId]: { submitted: true, value: correct } }));
    try {
      const res = await fetch(`${API_BASE}/sessions/${sessionId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict_correct: correct }),
      });
      if (res.ok) loadStats();
    } catch {
      /* Feedback is best-effort; the UI thank-you state can remain. */
    }
  };

  const hasReport  = messages.some((m) => m.role === "assistant" && (m.kind === "report" || m.kind === "audio_report"));
  const currentScanSteps = selectedMediaType === "audio" ? AUDIO_SCAN_STEPS : selectedMediaType === "video" ? VIDEO_SCAN_STEPS : SCAN_STEPS;
  const activeMediaCopy = getMediaCopy(selectedMediaType || "default");

  if (isAdmin) {
    return (
      <AdminConsole
        onExit={() => setView("app")}
        onLogout={() => { localStorage.removeItem("argusai_admin"); setView("app"); }}
        arizeHealth={arizeHealth}
        onHealthUpdate={setArizeHealth}
        statsData={statsData}
        onStatsUpdate={setStatsData}
      />
    );
  }

  return (
    <div className="app-root">
      {/* ── HEADER ── */}
      <header className="app-header">
        <div className="logo-wrap">
          <img src="/logo.jpeg" alt="ArgusAI" className="logo-img" />
          <div className="logo-text">
            <span className="logo-name">ArgusAI</span>
            <span className="logo-sub">Forensic media investigation</span>
          </div>
        </div>
        {messages.length === 0 && !status && (
          <nav className="header-center-nav">
            <a href="#how-it-works">How it works</a>
            <a href="#why-argus">Why ArgusAI</a>
            <a href="#sample-media">Sample media</a>
          </nav>
        )}
        <div className="header-nav">
          <button type="button" className="header-login-btn" onClick={() => setLoginOpen(true)}>
            <LogIn size={15} /> Sign in
          </button>
        </div>
      </header>

      {sessionError && <div className="banner-error">{sessionError}</div>}

      {/* ── MAIN LAYOUT ── */}
      <main className={`main-layout ${messages.length === 0 && !status ? "is-landing" : "is-session"}`}>

        {/* LANDING MODE — full page with inline examiner */}
        {messages.length === 0 && !status && (
          <LandingPage
            fileInputRef={fileInputRef}
            previewUrl={previewUrl}
            fileType={fileType}
            selectedMediaType={selectedMediaType}
            handleDrop={handleDrop}
            handleFileChange={handleFileChange}
            contextText={contextText}
            setContextText={setContextText}
            fileSelected={fileSelected}
            isAnalyzing={isAnalyzing}
            handleAnalyze={handleAnalyze}
            sessionError={sessionError}
          />
        )}

        {/* SESSION MODE — split feed + panel */}
        {(messages.length > 0 || status) && (
          <section className="feed-col">
            <AnimatePresence initial={false}>
            {messages.map((m) => (
              <motion.div
                key={m.id}
                className={`msg-row msg-${m.role}`}
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ type: "spring", stiffness: 380, damping: 28 }}
              >
                {m.role === "user" && m.kind === "analyze" && (
                  <div className="user-bubble">
                    {m.imageUrl && (
                      m.fileType?.startsWith("video/") ? (
                        <video src={m.imageUrl} className="msg-thumb" muted />
                      ) : m.fileType?.startsWith("audio/") ? (
                        <div className="msg-audio-thumb">
                          <Zap size={18} style={{color:"#06b6d4"}} />
                          <span>Audio file submitted</span>
                          <audio src={m.imageUrl} controls className="msg-audio-player" />
                        </div>
                      ) : (
                        <img src={m.imageUrl} alt="" className="msg-thumb" />
                      )
                    )}
                    {m.text && <p className="msg-context">{m.text}</p>}
                  </div>
                )}
                {m.role === "user" && m.kind === "text" && (
                  <div className="user-bubble text-only"><p>{m.text}</p></div>
                )}
                {m.role === "assistant" && m.kind === "text" && (
                  <div className="assistant-bubble">
                    {Array.isArray(m.toolCalls) && m.toolCalls.length > 0 && (
                      <div className="tool-call-strip">
                        {m.toolCalls.map((tool, idx) => (
                          <span key={`${tool.name || "tool"}-${idx}`} className={`tool-call-chip ${tool.ok === false ? "tool-call-failed" : ""}`}>
                            <Target size={12} />
                            {tool.label || (tool.name || "used tool").replaceAll("_", " ")}
                          </span>
                        ))}
                      </div>
                    )}
                    <AssistantMessageText text={m.text} />
                  </div>
                )}
                {m.role === "assistant" && m.kind === "agent_pending" && (
                  <div className="assistant-bubble agent-pending-bubble">
                    <div className="agent-pending-head">
                      <div className="spin-ring" />
                      <span>Investigator agent is working</span>
                    </div>
                    <div className="tool-call-strip pending-tool-strip">
                      {FOLLOWUP_AGENT_STEPS.map((step, idx) => {
                        const active = idx === followUpStep % FOLLOWUP_AGENT_STEPS.length;
                        const complete = idx < followUpStep % FOLLOWUP_AGENT_STEPS.length;
                        return (
                          <span key={step} className={`tool-call-chip pending-tool-chip ${active ? "active" : ""} ${complete ? "complete" : ""}`}>
                            <Target size={12} />
                            {step}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
                {m.role === "assistant" && m.kind === "audio_report" && m.report && (
                  <AudioReportCard
                    reportData={m.report}
                    sessionId={sessionId}
                    feedbackState={feedbackBySession[sessionId]}
                    onFeedback={handleFeedback}
                    detectorStats={statsData?.detectors || {}}
                  />
                )}
                {m.role === "assistant" && m.kind === "report" && m.report && (
                  <ForensicReportCard
                    reportData={m.report}
                    showJson={!!showJsonById[m.id]}
                    onToggleJson={() => toggleJson(m.id)}
                    onDownloadPdf={() => handleDownloadPdf(m.id, m.report)}
                    pdfDownloading={pdfLoadingForId === m.id}
                    sessionId={sessionId}
                    feedbackState={feedbackBySession[sessionId]}
                    onFeedback={handleFeedback}
                    detectorStats={statsData?.detectors || {}}
                  />
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {status && (
            <motion.div className="feed-status" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="spin-ring" />{status}
            </motion.div>
          )}
          <div ref={feedEndRef} />

          <AnimatePresence>
            {hasReport && (
              <motion.div
                className="followup-bar"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
              >
                <Send size={16} className="followup-icon" />
                <input
                  className="followup-input"
                  placeholder={isSending ? "Investigator agent is working..." : "Ask a follow-up question about this report..."}
                  value={followUp}
                  onChange={(e) => setFollowUp(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleFollowUp(); }
                  }}
                  disabled={isSending || !!sessionError}
                />
                <motion.button
                  className="followup-send"
                  onClick={handleFollowUp}
                  disabled={isSending || !followUp.trim() || !!sessionError}
                  whileTap={{ scale: 0.92 }}
                >
                  {isSending ? <div className="spin-ring" /> : <Send size={16} />}
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>
          </section>
        )}

        {/* Session-mode right aside */}
        {(messages.length > 0 || status) && (
          <aside className="control-panel glass-panel">
            <div className="panel-head-label">New {activeMediaCopy.reportNoun} investigation</div>

            <div
              className={`drop-zone ${previewUrl ? "has-preview" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => !previewUrl && fileInputRef.current?.click()}
            >
              <input ref={fileInputRef} type="file"
                accept="image/*,video/*,audio/*,.mp3,.wav,.ogg,.m4a,.flac"
                className="file-input-hidden" onChange={handleFileChange} />
              {previewUrl ? (
                <div className="preview-wrap">
                  {selectedMediaType && (
                    <span className="arize-badge" style={{ position: "absolute", top: 10, left: 10, zIndex: 2 }}>
                      {mediaBadgeLabel(selectedMediaType)}
                    </span>
                  )}
                  {selectedMediaType === "video" ? (
                    <video src={previewUrl} className="preview-img" muted />
                  ) : selectedMediaType === "audio" ? (
                    <div className="audio-preview-wrap">
                      <Zap size={32} style={{color:"#06b6d4",marginBottom:8}} />
                      <p className="drop-title" style={{color:"#06b6d4",marginBottom:4}}>{activeMediaCopy.uploadTitle}</p>
                      <audio src={previewUrl} controls style={{width:"100%",marginTop:4}} />
                    </div>
                  ) : (
                    <img src={previewUrl} alt="Preview" className="preview-img" />
                  )}
                  {isAnalyzing && <ScanningOverlay steps={currentScanSteps} currentStep={scanStep} />}
                  {!isAnalyzing && (
                    <div className="preview-actions">
                      <button className="preview-btn" onClick={(e) => { e.stopPropagation(); clearImage(); }}>
                        <X size={14} /> Remove
                      </button>
                      <button className="preview-btn" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>
                        Change
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="drop-empty">
                  <div className="drop-icon-ring">
                    <div className="drop-cloud-icon" />
                  </div>
                  <p className="drop-title">Drop image, video, or audio</p>
                  <p className="drop-sub">or click to browse</p>
                </div>
              )}
            </div>

            <label className="field-label">Context <span className="optional">(optional)</span></label>
            <textarea
              className="context-input"
              rows={3}
              placeholder={activeMediaCopy.contextPlaceholder}
              value={contextText}
              onChange={(e) => setContextText(e.target.value)}
              disabled={isAnalyzing}
            />

            <motion.button
              className={`analyze-btn ${isAnalyzing ? "analyzing" : ""}`}
              onClick={handleAnalyze}
              disabled={!fileSelected || isAnalyzing || !!sessionError}
              whileHover={fileSelected && !isAnalyzing ? { scale: 1.02 } : {}}
              whileTap={fileSelected && !isAnalyzing ? { scale: 0.97 } : {}}
            >
              {isAnalyzing
                ? <><div className="spin-ring white" />{activeMediaCopy.processing}</>
                : <><Search size={18} />Run Investigation</>
              }
            </motion.button>
          </aside>
        )}

      </main>
      <LoginModal
        open={loginOpen}
        onClose={() => setLoginOpen(false)}
        onAdminSuccess={() => { setLoginOpen(false); setView("admin"); }}
      />
    </div>
  );
}
