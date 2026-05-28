import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence, useInView } from "framer-motion";
import {
  ShieldCheck, AlertOctagon, HelpCircle, Search, Camera, Eye,
  ScanSearch, Activity, Target, Database, ChevronDown, ChevronRight,
  Fingerprint, Sparkles, Send, X, Image as ImageIcon, Copy, Check,
  Zap, Globe, Layers, Cpu, FileDown
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

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

const formatSupportLabel = (support) => {
  const value = (support || "unknown").toLowerCase();
  if (value === "authentic") return "Suggests a real photo";
  if (value === "ai_generated") return "Suggests AI generation";
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
  spectral_artifacts: "Runs the image through six different frequency-analysis models and combines their votes. It is looking for mathematical patterns in the pixel data that appear in AI-generated images but not in real camera photos.",
  metadata_analysis: "Reads the invisible information stored inside the image file itself, such as which camera or app created it, the date it was taken, and GPS coordinates. Missing or inconsistent metadata can be a clue, though it is never conclusive on its own.",
  noise_pattern_analysis: "Every real camera sensor adds a tiny, consistent layer of electrical noise to every photo it takes. This check looks for that noise fingerprint. AI generators tend to produce images that are either too smooth or have noise that does not match any real sensor.",
  lighting_consistency: "Checks whether the brightness distribution across the image matches how real-world lighting behaves. Real cameras often clip highlights and crush shadows in a physically predictable way. AI images sometimes produce light that is unnaturally balanced or inconsistent with a real light source.",
  error_level_analysis: "Re-saves the image at a lower quality and compares the result to the original. Regions that have been edited or composited usually show a different compression residual than untouched areas. The heatmap below highlights where those differences are largest.",
  semantic_inconsistencies: "Uses a vision model to look at the image the same way a human analyst would, checking for physical mistakes that AI generators commonly make: wrong number of fingers, shadows missing for certain objects, text that is garbled, or objects that could not physically exist in that configuration.",
  osint_verification: "Searches the public web in real time to see whether the event or subject in the image appears in credible news reporting, fact-checker databases, or is flagged as a known fake. This is the only check that goes beyond the image file itself.",
};

function getSignalDescription(signal) {
  const id = (signal.id || "").toLowerCase();
  if (SIGNAL_DESCRIPTIONS[id]) return SIGNAL_DESCRIPTIONS[id];
  // fuzzy match by name fragment
  for (const [key, desc] of Object.entries(SIGNAL_DESCRIPTIONS)) {
    if (id.includes(key.split("_")[0])) return desc;
  }
  return null;
}

function AnimatedSignalCard({ signal, index }) {
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
          {formatSupportLabel(signal.supports)}
        </span>
      </div>
    </div>
  );

  const signalDescription = getSignalDescription(signal);

  // ELA heatmap is always visible above the toggle (not hidden behind expand)
  const elaImage = signal.metrics?.ela_image_base64 ? (
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
        This score tells you how strongly the evidence agrees overall. It is not a guarantee, and the explanation below matters more than the number by itself.
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
          Each card explains what that check looked for, what it found in this image, why it matters, and what might also explain it.
        </p>
        <div className="signals-grid">
          {reportData.evidence?.signals?.length > 0
            ? reportData.evidence.signals.map((signal, i) => (
                <AnimatedSignalCard key={signal.id} signal={signal} index={i} />
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

function LandingPage({ fileInputRef, previewUrl, handleDrop, handleFileChange, contextText, setContextText, fileSelected, isAnalyzing, handleAnalyze, sessionError }) {
  return (
    <div className="landing-root">

      {/* ── HERO: 2-column split ── */}
      <section className="lp-hero">
        {/* Left: pitch */}
        <div className="lp-hero-left">
          <div className="lp-hero-badge">Forensic Image Verification</div>
          <h2 className="lp-hero-title">
            Can you trust<br/>
            <span className="lp-hero-accent">what you see?</span>
          </h2>
          <p className="lp-hero-sub">
            AI-generated images are becoming harder to spot by eye. ArgusAI is a forensic tool that analyzes images the same way an investigator would, looking at the technical evidence inside the image itself rather than just how it looks.
          </p>
          <p className="lp-hero-sub">
            Upload any image and get a verdict: real or AI-generated. Each check explains exactly what it found and why it matters, so you understand the result instead of just trusting a score.
          </p>
          <ul className="lp-hero-bullets">
            <li>Analyzes pixel-level noise, lighting physics, and frequency patterns that AI images get wrong</li>
            <li>Searches live news and fact-checkers to see if the image matches a real reported event</li>
            <li>Shows you every signal individually so the reasoning is fully transparent</li>
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
              <input ref={fileInputRef} type="file" accept="image/*" className="file-input-hidden" onChange={handleFileChange} />
              {previewUrl ? (
                <img src={previewUrl} alt="Preview" className="lp-preview-img" />
              ) : (
                <div className="lp-drop-inner">
                  <div className="lp-drop-icon"><ImageIcon size={20} /></div>
                  <p className="lp-drop-title">Drop an image to examine</p>
                  <p className="lp-drop-sub">or click to browse (JPG, PNG, WEBP)</p>
                </div>
              )}
            </div>
            <textarea
              className="lp-context-input"
              rows={2}
              placeholder="Optional context, e.g. 'Is this the Netanyahu video?'"
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
                ? <><div className="spin-ring white" />Running pipeline…</>
                : <><Search size={15} />Run Forensic Analysis</>
              }
            </motion.button>
          </div>
        </div>
      </section>

      {/* ── EVIDENCE STRIP ── */}
      <section className="lp-evidence">
        <p className="lp-section-eyebrow">Tested on images like these</p>
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
            <p>Looks for hidden frequency patterns in the image that appear when AI generates pixels. Real cameras produce different mathematical signatures that are hard to fake.</p>
          </div>
          <div className="lp-pipeline-card" style={{"--card-accent":"#3b82f6"}}>
            <div className="lp-step-num" style={{color:"#3b82f6",borderColor:"rgba(59,130,246,0.3)",background:"rgba(59,130,246,0.07)"}}>02</div>
            <h4>Physical coherence</h4>
            <p>Checks whether the lighting, shadows, and noise in the image obey real-world physics. AI images often get these details wrong in ways a camera never would.</p>
          </div>
          <div className="lp-pipeline-card" style={{"--card-accent":"#10b981"}}>
            <div className="lp-step-num" style={{color:"#10b981",borderColor:"rgba(16,185,129,0.3)",background:"rgba(16,185,129,0.07)"}}>03</div>
            <h4>Live web fact-checking</h4>
            <p>Searches live news and public databases to see whether the event in the image was actually reported. This catches known fakes that have already been identified online.</p>
          </div>
          <div className="lp-pipeline-card" style={{"--card-accent":"#00e5ff"}}>
            <div className="lp-step-num" style={{color:"#00e5ff",borderColor:"rgba(0,229,255,0.3)",background:"rgba(0,229,255,0.07)"}}>04</div>
            <h4>Verdict engine</h4>
            <p>All six signals are weighed together and a final verdict is issued with a plain-language explanation of exactly what was found and why.</p>
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
            <p>Pixel analysis only goes so far. ArgusAI also checks whether the image matches real events reported by credible news sources.</p>
          </div>
        </div>
        <div className="lp-diff-card">
          <div className="lp-diff-icon" style={{background:"rgba(0,229,255,0.08)",borderColor:"rgba(0,229,255,0.2)",color:"#00e5ff"}}><Zap size={18}/></div>
          <div>
            <h4>Results in under 30 seconds</h4>
            <p>All six checks run in parallel. You get a full forensic report with a clear verdict in the time it takes to read this sentence.</p>
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
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file || !file.type.startsWith("image/")) return;
    setFileSelected(true);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(file));
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file || !file.type.startsWith("image/")) return;
    if (fileInputRef.current) {
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInputRef.current.files = dt.files;
      handleFileChange({ target: { files: [file] } });
    }
  };

  const clearImage = () => {
    setPreviewUrl(""); setFileSelected(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAnalyze = async () => {
    const file = fileInputRef.current?.files[0];
    if (!file) return;
    setIsAnalyzing(true); setScanStep(0);
    setStatus("Running forensic pipeline...");
    setShowJsonById({});

    const imageSnapshot = previewUrl;

    try {
      const postAnalyze = (sessionKey) => {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("context", contextText.trim());
        return fetch(`${API_BASE}/sessions/${sessionKey}/analyze`, { method: "POST", body: fd });
      };

      let sid = await ensureSession();

      setMessages((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: "user", kind: "analyze", text: contextText.trim(), imageUrl: imageSnapshot },
      ]);

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
        } catch {
          /* ignore */
        }
        setStatus(`Analysis failed.${detail}`);
        return;
      }

      const report = await res.json();
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", kind: "report", report }]);
      setStatus("");
      // keep image in panel so user can reference it; allow new file
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

  const hasReport  = messages.some((m) => m.role === "assistant" && m.kind === "report");

  return (
    <div className="app-root">
      {/* ── HEADER ── */}
      <header className="app-header">
        <div className="logo-wrap">
          <img src="/logo.jpeg" alt="ArgusAI" className="logo-img" />
          <div className="logo-text">
            <span className="logo-name">ArgusAI</span>
            <span className="logo-sub">Forensic image verification</span>
          </div>
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
                    {m.imageUrl && <img src={m.imageUrl} alt="" className="msg-thumb" />}
                    {m.text && <p className="msg-context">{m.text}</p>}
                  </div>
                )}
                {m.role === "user" && m.kind === "text" && (
                  <div className="user-bubble text-only"><p>{m.text}</p></div>
                )}
                {m.role === "assistant" && m.kind === "text" && (
                  <div className="assistant-bubble"><p>{m.text}</p></div>
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
            <div className="panel-head-label">New examination</div>

            <div
              className={`drop-zone ${previewUrl ? "has-preview" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => !previewUrl && fileInputRef.current?.click()}
            >
              <input ref={fileInputRef} type="file" accept="image/*" className="file-input-hidden" onChange={handleFileChange} />
              {previewUrl ? (
                <div className="preview-wrap">
                  <img src={previewUrl} alt="Preview" className="preview-img" />
                  {isAnalyzing && <ScanningOverlay steps={SCAN_STEPS} currentStep={scanStep} />}
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
                  <p className="drop-title">Drop image here</p>
                  <p className="drop-sub">or click to browse</p>
                </div>
              )}
            </div>

            <label className="field-label">Context <span className="optional">(optional)</span></label>
            <textarea
              className="context-input"
              rows={3}
              placeholder="e.g. Is this the Netanyahu video? Verify if this event occurred."
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
                ? <><div className="spin-ring white" />Analyzing…</>
                : <><Search size={18} />Run Analysis</>
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
    </div>
  );
}
