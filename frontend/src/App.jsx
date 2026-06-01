import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence, useInView } from "framer-motion";
import {
  ShieldCheck, AlertOctagon, HelpCircle, Search, Camera, Eye,
  ScanSearch, Activity, Target, Database, ChevronDown, ChevronRight,
  Fingerprint, Sparkles, Send, X, Image as ImageIcon, Copy, Check,
  Zap, Globe, Layers, Cpu, FileDown, Lock, RefreshCw, BarChart3
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const ADMIN_PASSWORD = import.meta.env.VITE_ADMIN_PASSWORD || "argusai2026";
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
const METRIC_KEYS_STRIP_FOR_PDF = ["ela_image_base64", "grounding_metadata"];

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
  default:   { color: "#00e6ff", glow: "rgba(0,230,255,0.25)",   label: "Signal"   },
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
  audio_track: {
    video: "Extracts the video's embedded audio track, when present, and checks whether speech or production patterns suggest cloning or synthesis.",
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

function AnimatedSignalCard({ signal, index, mediaType = "image" }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });
  const [showDetails, setShowDetails] = useState(false);
  const theme = getSignalTheme(signal.category);
  const wide = isOsintSignal(signal);

  const hasInfluence = typeof signal.verdict_influence_percent === "number";
  const barPct = hasInfluence ? signal.verdict_influence_percent : Math.round((signal.reliability || 0) * 100);

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
      <img src={`data:image/png;base64,${signal.metrics.ela_image_base64}`} alt="ELA compression heatmap — brighter areas had more compression stress" />
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
      className={`signal-card${wide ? " signal-card-osint" : ""}`}
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
                <p className="signal-detail-text signal-detail-text-compact">{signal.what_found}</p>
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

function AudioReportCard({ reportData }) {
  if (!reportData) return null;

  const certaintyPercent = Math.round((reportData.certainty || 0) * 100);
  const isAI = (reportData.verdict || "").toLowerCase().includes("ai_generated");
  const isAuth = (reportData.verdict || "").toLowerCase().includes("authentic");
  const verdictLabel = isAI ? "AI-Generated Voice" : isAuth ? "Authentic Voice" : "Inconclusive";
  const verdictClass = isAI ? "verdict-ai" : isAuth ? "verdict-authentic" : "verdict-inconclusive";

  const source = reportData.inference_source || "unknown";
  const sourceLabel = source === "local_wav2vec2" ? "🖥 Local wav2vec2" : source === "hf_space" ? "☁ HuggingFace Space" : source;
  const sourceColor = source === "local_wav2vec2" ? "#10b981" : "#06b6d4";

  const sig = reportData.signal;
  const confidenceLabel = reportData.confidence_label || "Guarded";
  const observations = sig?.observations || [];
  const probFake = sig?.metrics?.prob_fake ?? null;
  const probReal = sig?.metrics?.prob_real ?? null;

  return (
    <motion.div
      className="forensic-report-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 24 }}
    >
      {/* Verdict banner */}
      <motion.div
        className={`verdict-banner ${verdictClass}`}
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
      >
        <Zap size={28} />
        <div className="verdict-text-wrap">
          <span className="verdict-label">Audio Verdict</span>
          <span className="verdict-value">{verdictLabel}</span>
          {reportData.explanation && (
            <p className="verdict-summary">{reportData.explanation}</p>
          )}
        </div>
        <div className="verdict-meta">
          <div className="verdict-confidence">
            <span className="verdict-confidence-label">Certainty</span>
            <span className="verdict-confidence-value">{certaintyPercent}%</span>
            <span className="verdict-confidence-tag">{confidenceLabel}</span>
          </div>
          {/* Inference source badge */}
          <span
            className="arize-badge"
            style={{ color: sourceColor, borderColor: `${sourceColor}40`, background: `${sourceColor}12`, marginTop: 8 }}
          >
            {sourceLabel}
          </span>
        </div>
      </motion.div>

      {/* Waveform probability bar */}
      <motion.div
        className="report-helper"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.4 }}
      >
        Audio authenticity analysis via dedicated voice models and Gemini semantic listening when model confidence is weak.
      </motion.div>

      {/* Signal card */}
      {sig && (
        <motion.div
          className="signals-section"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.35 }}
        >
          <h3 className="signals-section-title">
            <Activity size={14} /> Audio Evidence
          </h3>

          <div className="signal-card" style={{ "--signal-color": "#06b6d4", "--signal-glow": "rgba(6,182,212,0.25)" }}>
            <div className="signal-card-header">
              <div className="signal-icon-wrap" style={{ color: "#06b6d4", background: "rgba(6,182,212,0.12)" }}>
                <Zap size={14} />
              </div>
              <div className="signal-title-group">
                <span className="signal-name">{sig.name || "Audio Authenticity"}</span>
                <span className="signal-category-badge" style={{ color: "#06b6d4", background: "rgba(6,182,212,0.12)" }}>
                  Audio
                </span>
              </div>
              <span className={`status-badge ${sig.status === "ok" ? "status-pass" : sig.status === "error" ? "status-error" : "status-info"}`}>
                {sig.status === "ok" ? "Completed" : sig.status === "error" ? "Error" : sig.status}
              </span>
            </div>

            <p className="signal-summary">{sig.summary}</p>

            {/* Probability bars */}
            {probFake !== null && probReal !== null && (
              <div className="signal-stats" style={{ marginTop: 12 }}>
                <div className="stat-item">
                  <span className="stat-label">AI-generated probability</span>
                  <div className="reliability-bar-wrap">
                    <span className="stat-value" style={{ color: isAI ? "#f87171" : "inherit" }}>
                      {Math.round(probFake * 100)}%
                    </span>
                    <div className="reliability-bar">
                      <motion.div
                        className="reliability-fill"
                        style={{ background: isAI ? "#f87171" : "#06b6d4" }}
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.round(probFake * 100)}%` }}
                        transition={{ duration: 0.9, ease: "easeOut" }}
                      />
                    </div>
                  </div>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Real human probability</span>
                  <div className="reliability-bar-wrap">
                    <span className="stat-value" style={{ color: isAuth ? "#34d399" : "inherit" }}>
                      {Math.round(probReal * 100)}%
                    </span>
                    <div className="reliability-bar">
                      <motion.div
                        className="reliability-fill"
                        style={{ background: isAuth ? "#34d399" : "#06b6d4" }}
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.round(probReal * 100)}%` }}
                        transition={{ duration: 0.9, delay: 0.1, ease: "easeOut" }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Observations */}
            {observations.length > 0 && (
              <ul className="signal-observations" style={{ marginTop: 12 }}>
                {observations.map((obs, i) => (
                  <li key={i} className="signal-obs-item">{obs}</li>
                ))}
              </ul>
            )}

            {/* What checked / why it matters */}
            {sig.what_checked && (
              <div className="signal-detail-row signal-detail-row--purpose" style={{ marginTop: 12 }}>
                <span className="signal-detail-label">What this check does</span>
                <p className="signal-detail-text">{sig.what_checked}</p>
              </div>
            )}
            {sig.caveat && (
              <div className="signal-detail-row" style={{ marginTop: 8 }}>
                <span className="signal-detail-label">Caveat</span>
                <p className="signal-detail-text">{sig.caveat}</p>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}

function ForensicReportCard({ reportData, showJson, onToggleJson, onDownloadPdf, pdfDownloading }) {
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

      <motion.div
        className="report-helper"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, duration: 0.4 }}
      >
        {modelHealth || "All detector health gates operational"}. The verdict is based on media-specific evidence agreement, not a naked classifier output.
      </motion.div>

      <motion.div
        className="narrative"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, duration: 0.5 }}
      >
        {explanationParagraphs.map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
      </motion.div>

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
          {visibleSignals.length > 0
            ? visibleSignals.map((signal, i) => (
                <AnimatedSignalCard key={signal.id} signal={signal} index={i} mediaType={mediaType} />
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

function AdminPanel({ open, onClose, arizeHealth, onHealthUpdate }) {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState(() => localStorage.getItem("argusai_admin") === "1");
  const [shake, setShake] = useState(false);
  const [traces, setTraces] = useState([]);
  const [health, setHealth] = useState(arizeHealth);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setHealth(arizeHealth);
  }, [arizeHealth]);

  const loadAdminData = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    setError("");
    try {
      const [healthRes, tracesRes] = await Promise.all([
        fetch(`${API_BASE}/arize/health`),
        fetch(`${API_BASE}/arize/traces?limit=10`),
      ]);
      const healthJson = healthRes.ok ? await healthRes.json() : null;
      const tracesJson = tracesRes.ok ? await tracesRes.json() : { traces: [] };
      if (healthJson) {
        setHealth(healthJson);
        onHealthUpdate?.(healthJson);
      }
      setTraces(Array.isArray(tracesJson.traces) ? tracesJson.traces : []);
    } catch {
      setError("Could not load Arize operator data.");
    } finally {
      setLoading(false);
    }
  }, [authed, onHealthUpdate]);

  useEffect(() => {
    if (open && authed) loadAdminData();
  }, [open, authed, loadAdminData]);

  if (!open) return null;

  const governor = health?.detector_governor || {};
  const detectorRows = Object.entries(governor.detectors || {});
  const calibration = governor.calibration_divergence;
  const latestTrace = traces[0];
  const latestDetectors = latestTrace?.detectors ? Object.entries(latestTrace.detectors) : [];
  const maxLatency = Math.max(0.01, ...latestDetectors.map(([, row]) => Number(row?.latency) || 0));

  const submitPassword = (e) => {
    e.preventDefault();
    if (password === ADMIN_PASSWORD) {
      localStorage.setItem("argusai_admin", "1");
      setAuthed(true);
      setPassword("");
      return;
    }
    setShake(true);
    setPassword("");
    setTimeout(() => setShake(false), 450);
  };

  return (
    <AnimatePresence>
      <motion.div className="admin-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
        <motion.div
          className="admin-modal"
          initial={{ opacity: 0, y: 18, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.98 }}
          transition={{ duration: 0.18 }}
        >
          <div className="admin-head">
            <div>
              <span className="admin-kicker">Operator View</span>
              <h2>Arize Reliability Console</h2>
            </div>
            <button className="admin-icon-btn" onClick={onClose} title="Close">
              <X size={18} />
            </button>
          </div>

          {!authed ? (
            <form className={`admin-login ${shake ? "admin-shake" : ""}`} onSubmit={submitPassword}>
              <Lock size={28} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoFocus
              />
              <button type="submit">Unlock</button>
            </form>
          ) : (
            <div className="admin-dashboard">
              <div className="admin-toolbar">
                <div className={`admin-health-pill ${health?.status === "calibration_alert" ? "warn" : health?.status === "anomaly" ? "error" : "ok"}`}>
                  <Activity size={14} />
                  {health?.label || "Arize health unavailable"}
                </div>
                <button className="admin-refresh" onClick={loadAdminData} disabled={loading}>
                  <RefreshCw size={14} /> {loading ? "Refreshing" : "Refresh"}
                </button>
              </div>

              {error && <div className="admin-alert error">{error}</div>}
              {calibration?.active && (
                <div className="admin-alert warn">
                  <AlertOctagon size={16} />
                  Spectral detector influence is reduced to {formatPercent(governor.spectral_attenuation_factor)} after repeated calibration divergence.
                </div>
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
                          <td>{Number(trace.latency_seconds || 0).toFixed(2)}s</td>
                          <td className="mono">{shortHash(trace.sha256)}</td>
                        </tr>
                      )) : (
                        <tr><td colSpan={6}>No x-ray traces written yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="admin-grid">
                <div className="admin-section">
                  <h3>Detector Health</h3>
                  <div className="admin-health-grid">
                    {detectorRows.length ? detectorRows.map(([id, row]) => (
                      <div key={id} className={`admin-detector ${row.active ? "active" : ""}`}>
                        <span className="mono">{id}</span>
                        <strong>{row.active ? "Adjusted" : "Recovered"}</strong>
                        <small>{row.reason || "nominal"}</small>
                      </div>
                    )) : (
                      <div className="admin-empty">All detector health gates are nominal.</div>
                    )}
                  </div>
                </div>

                <div className="admin-section">
                  <h3><BarChart3 size={14} /> Latest Latency</h3>
                  <div className="admin-bars">
                    {latestDetectors.length ? latestDetectors.slice(0, 8).map(([id, row]) => {
                      const latency = Number(row?.latency) || 0;
                      return (
                        <div className="admin-bar-row" key={id}>
                          <span className="mono">{id}</span>
                          <div className="admin-bar-track">
                            <div className="admin-bar-fill" style={{ width: `${Math.max(4, (latency / maxLatency) * 100)}%` }} />
                          </div>
                          <strong>{latency.toFixed(2)}s</strong>
                        </div>
                      );
                    }) : (
                      <div className="admin-empty">Run an investigation to populate latency bars.</div>
                    )}
                  </div>
                </div>
              </section>

              <section className="admin-section">
                <h3>Calibration Events</h3>
                <div className="admin-events">
                  {(governor.recent_events || []).length ? governor.recent_events.slice().reverse().map((event, idx) => (
                    <div className={`admin-event ${event.reason === "calibration_divergence" ? "warn" : ""}`} key={`${event.recorded_at || idx}-${idx}`}>
                      <span className="mono">{event.reason || "detector_event"}</span>
                      <p>{event.detector_id || "detector"} · {formatTime(event.recorded_at)}{event.active_until ? ` · active until ${formatTime(event.active_until)}` : ""}</p>
                    </div>
                  )) : (
                    <div className="admin-empty">No calibration or circuit-breaker events recorded.</div>
                  )}
                </div>
              </section>
            </div>
          )}
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
      <section className="lp-evidence">
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
      <section className="lp-how">
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
          <div className="lp-pipeline-card" style={{"--card-accent":"#00e5ff"}}>
            <div className="lp-step-num" style={{color:"#00e5ff",borderColor:"rgba(0,229,255,0.3)",background:"rgba(0,229,255,0.07)"}}>04</div>
            <h4>Verdict engine</h4>
            <p>The visible signals are weighed together and a final verdict is issued with a plain-language explanation of exactly what was found and why.</p>
          </div>
        </div>
      </section>

      {/* ── WHY DIFFERENT ── */}
      <section className="lp-diff">
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
          <div className="lp-diff-icon" style={{background:"rgba(0,229,255,0.08)",borderColor:"rgba(0,229,255,0.2)",color:"#00e5ff"}}><Zap size={18}/></div>
          <div>
            <h4>Results in under 30 seconds</h4>
            <p>Image, video, and audio each use the checks that fit. You get a forensic report with a clear evidence trail instead of a generic score.</p>
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
  const [pdfLoadingForId, setPdfLoadingForId] = useState(null);
  const [arizeHealth, setArizeHealth] = useState(null);
  const [fileType, setFileType]         = useState("");
  const [selectedMediaType, setSelectedMediaType] = useState("");
  const [adminOpen, setAdminOpen] = useState(false);

  const fileInputRef = useRef(null);
  const feedEndRef   = useRef(null);

  // Cycle scan text while analyzing
  useEffect(() => {
    if (!isAnalyzing) return;
    const id = setInterval(() => setScanStep((s) => s + 1), 2200);
    return () => clearInterval(id);
  }, [isAnalyzing]);

  const createFreshSession = useCallback(async () => {
    const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
    if (!res.ok) throw new Error("session_create_failed");
    const data = await res.json();
    setSessionId(data.session_id);
    return data.session_id;
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
        if (!cancelled) setSessionError("Could not reach the API. Check backend and VITE_API_BASE.");
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
    setIsSending(true); setFollowUp("");
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", kind: "text", text }]);
    try {
      const res  = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      const reply = res.ok ? data.reply : (data.error || "Could not answer.");
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", kind: "text", text: reply }]);
    } catch {
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", kind: "text", text: "Network error." }]);
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

  const hasReport  = messages.some((m) => m.role === "assistant" && (m.kind === "report" || m.kind === "audio_report"));
  const currentScanSteps = selectedMediaType === "audio" ? AUDIO_SCAN_STEPS : selectedMediaType === "video" ? VIDEO_SCAN_STEPS : SCAN_STEPS;
  const arizeWarn = arizeHealth?.status === "anomaly" || arizeHealth?.status === "calibration_alert";
  const activeMediaCopy = getMediaCopy(selectedMediaType || "default");

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
        <div className="header-nav">
          <button
            type="button"
            className={`arize-badge arize-badge-button ${arizeWarn ? "arize-badge-warn" : ""}`}
            onClick={() => setAdminOpen(true)}
            title="Open Arize reliability console"
          >
            <Activity size={13} />
            {arizeHealth?.label || "Phoenix monitor ready"}
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
                  <div className="assistant-bubble"><p>{m.text}</p></div>
                )}
                {m.role === "assistant" && m.kind === "audio_report" && m.report && (
                  <AudioReportCard reportData={m.report} />
                )}
                {m.role === "assistant" && m.kind === "report" && m.report && (
                  <ForensicReportCard
                    reportData={m.report}
                    showJson={!!showJsonById[m.id]}
                    onToggleJson={() => toggleJson(m.id)}
                    onDownloadPdf={() => handleDownloadPdf(m.id, m.report)}
                    pdfDownloading={pdfLoadingForId === m.id}
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
                  placeholder="Ask a follow-up question about this report…"
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

            <div className="signal-legend">
              <p className="legend-title">Signal detectors</p>
              <div className="legend-grid">
                {Object.entries(SIGNAL_THEME).filter(([k]) => k !== "default").map(([key, t]) => (
                  <div key={key} className="legend-item">
                    <span className="legend-dot" style={{ background: t.color, boxShadow: `0 0 6px ${t.color}` }} />
                    <span>{t.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        )}

      </main>
      <button className="admin-lock" onClick={() => setAdminOpen(true)} title="Operator view">
        <Lock size={15} />
      </button>
      <AdminPanel
        open={adminOpen}
        onClose={() => setAdminOpen(false)}
        arizeHealth={arizeHealth}
        onHealthUpdate={setArizeHealth}
      />
    </div>
  );
}
