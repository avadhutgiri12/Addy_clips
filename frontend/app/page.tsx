"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  AudioLines,
  BadgeCheck,
  Bell,
  Check,
  ChevronDown,
  CircleHelp,
  Clapperboard,
  Clock3,
  Command,
  Film,
  FolderClock,
  Gauge,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  Menu,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Scissors,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  Video,
  X,
  Zap,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CATEGORIES = [
  "Action and combat",
  "Police chases and escapes",
  "Funny moments and fails",
  "Unexpected discoveries and exploration",
  "Streamer reactions and emotions",
  "Story missions and dramatic moments",
  "Chat reactions and hype spikes",
];
type Project = {
  project_id: string;
  title: string;
  duration: number;
  filename: string;
  source_type: string;
};
type Job = {
  id: string;
  project_id: string;
  status: string;
  stage: string;
  progress: number;
  error?: string;
  updated_at?: string;
  created_at?: string;
};
type Clip = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  hashtags: string[];
  start: number;
  end: number;
  score: number;
  category: string;
  created_at: string;
  vertical_path?: string;
  landscape_path?: string;
};
type Page = "Dashboard" | "Processing" | "My Clips" | "History" | "Settings";

async function request(path: string, init?: RequestInit) {
  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return res.json();
}
const fmt = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// YouTube live processing steps
const YT_LIVE_STEPS = [
  { key: "downloading", label: "Downloading stream", icon: "download", progressRange: [0, 30] },
  { key: "probing", label: "Probing video", icon: "probe", progressRange: [30, 35] },
  { key: "analyzing", label: "Measuring audio", icon: "analyze", progressRange: [35, 55] },
  { key: "generating", label: "Generating clips", icon: "generate", progressRange: [55, 95] },
  { key: "cleanup", label: "Cleaning up", icon: "cleanup", progressRange: [95, 100] },
  { key: "complete", label: "Complete", icon: "complete", progressRange: [100, 100] },
];

function getYtLiveStepInfo(stage: string, progress: number) {
  const lowerStage = stage.toLowerCase();

  // Determine current step based on stage text
  if (lowerStage.includes("downloading")) return { stepIndex: 0, stepProgress: Math.min(100, (progress / 30) * 100) };
  if (lowerStage.includes("probing")) return { stepIndex: 1, stepProgress: Math.min(100, ((progress - 30) / 5) * 100) };
  if (lowerStage.includes("measuring") || lowerStage.includes("analyzing") || lowerStage.includes("ranking")) return { stepIndex: 2, stepProgress: Math.min(100, ((progress - 35) / 20) * 100) };
  if (lowerStage.includes("generating") || lowerStage.includes("rendered")) return { stepIndex: 3, stepProgress: Math.min(100, ((progress - 55) / 40) * 100) };
  if (lowerStage.includes("cleaning") || lowerStage.includes("cleanup")) return { stepIndex: 4, stepProgress: Math.min(100, ((progress - 95) / 5) * 100) };
  if (lowerStage.includes("complete") || progress >= 100) return { stepIndex: 5, stepProgress: 100 };

  // Fallback: estimate from progress
  if (progress < 30) return { stepIndex: 0, stepProgress: (progress / 30) * 100 };
  if (progress < 35) return { stepIndex: 1, stepProgress: ((progress - 30) / 5) * 100 };
  if (progress < 55) return { stepIndex: 2, stepProgress: ((progress - 35) / 20) * 100 };
  if (progress < 95) return { stepIndex: 3, stepProgress: ((progress - 55) / 40) * 100 };
  if (progress < 100) return { stepIndex: 4, stepProgress: ((progress - 95) / 5) * 100 };
  return { stepIndex: 5, stepProgress: 100 };
}

function Mark() {
  return (
    <span className="brand-mark">
      <Scissors size={19} strokeWidth={2.5} />
      <i />
    </span>
  );
}

export default function Home() {
  const [page, setPage] = useState<Page>("Dashboard");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [source, setSource] = useState<any>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [sourceMode, setSourceMode] = useState<"vod" | "live">("vod");
  const [generateTitles, setGenerateTitles] = useState(false);
  const [generateCaptions, setGenerateCaptions] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [count, setCount] = useState(5);
  const [duration, setDuration] = useState(45);
  const [sensitivity, setSensitivity] = useState("balanced");
  const [clips, setClips] = useState<Clip[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All moments");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [keyStatus, setKeyStatus] = useState("");
  const [model, setModel] = useState("gemini-3.6-flash");
  const [models, setModels] = useState<string[]>([
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
  ]);
  const [autoModel, setAutoModel] = useState(true);
  const [youtubeMetadataEnabled, setYoutubeMetadataEnabled] = useState(false);
  const [editing, setEditing] = useState<Clip | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [format, setFormat] = useState<"vertical" | "landscape">("vertical");
  const [queryErr, setQueryErr] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [c, j] = await Promise.all([
        request("/api/clips?limit=48"),
        request("/api/analysis"),
      ]);
      setClips(c.items);
      setJobs(j);
    } catch (e) {
      setQueryErr(e instanceof Error ? e.message : "API unavailable");
    }
  }, []);
  useEffect(() => {
    const k = localStorage.getItem("addy-gemini-key");
    if (k) setApiKey(k);
    const m = localStorage.getItem("addy-gemini-model");
    if (m) setModel(m);
    request("/api/settings/models")
      .then((v) => {
        setModels(v.models);
        setYoutubeMetadataEnabled(v.youtube_metadata_enabled);
        if (!localStorage.getItem("addy-gemini-model")) setModel(v.default);
      })
      .catch(() => {});
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);
  useEffect(() => {
    const go = () => setPage("Dashboard");
    window.addEventListener("addy-new-analysis", go);
    return () => window.removeEventListener("addy-new-analysis", go);
  }, []);
  const current = jobs.find((j) =>
    ["queued", "running", "waiting_for_key"].includes(j.status)
  );
  const filtered = useMemo(
    () =>
      clips.filter(
        (c) =>
          (filter === "All moments" || c.category === filter) &&
          `${c.title} ${c.category}`
            .toLowerCase()
            .includes(search.toLowerCase())
      ),
    [clips, filter, search]
  );

  async function preview() {
    setNotice("");
    setSource(null);
    setProject(null);
    setPreviewBusy(true);
    try {
      const v = await request("/api/source/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      setSource(v);
      if (!v.metadata_available)
        setNotice(v.metadata_message || v.access_message || "");
    } catch (e) {
      setNotice(
        e instanceof Error ? e.message : "Could not validate this source."
      );
    } finally {
      setPreviewBusy(false);
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    setNotice("");
    setUploadBusy(true);
    setUploadPct(0);
    const data = new FormData();
    data.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}/api/source/local-upload`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        setUploadPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setUploadBusy(false);
      if (xhr.status < 300) {
        const v = JSON.parse(xhr.responseText);
        setProject(v);
        setSource({
          valid: true,
          media_access: true,
          metadata_available: true,
          title: v.title,
          channel: "Local file",
          duration: fmt(v.duration),
          live: false,
        });
        setNotice("Video ready for analysis.");
      } else setNotice(JSON.parse(xhr.responseText).detail || "Upload failed.");
    };
    xhr.onerror = () => {
      setUploadBusy(false);
      setNotice("Upload failed. Check that the API is running.");
    };
    xhr.send(data);
  }
  async function start() {
    const isLive = sourceMode === "live";
    const remote = !project && source?.processable && !!url.trim();
    if ((isLive && !remote) || (!isLive && !project && !remote)) {
      setNotice(
        isLive
          ? "Validate a Twitch channel URL before starting live clipping."
          : "Upload a local recording or validate a Twitch VOD URL. YouTube links are in Beta — local files work reliably."
      );
      return;
    }
    if (generateTitles && !apiKey) {
      setNotice(
        "AI titles are optional. Add a Gemini key in Settings or turn titles off."
      );
      setPage("Settings");
      return;
    }
    setBusy(true);
    try {
      const v = await request("/api/analysis/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: project?.project_id || null,
          source_url: remote ? url : null,
          mode: sourceMode,
          count,
          duration,
          sensitivity,
          categories: CATEGORIES,
          generate_titles: generateTitles,
          generate_captions: generateCaptions,
          gemini_key: generateTitles ? apiKey : null,
          model: autoModel ? models[0] : model,
        }),
      });
      setNotice(
        isLive
          ? "Live capture started. It keeps a rolling replay buffer and stops after the requested clips or when canceled."
          : "Analysis queued. Moment detection uses audio hype spikes; titles and captions are optional."
      );
      setPage("Processing");
      refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Unable to start analysis.");
    } finally {
      setBusy(false);
    }
  }
  function saveKey() {
    localStorage.setItem("addy-gemini-key", apiKey);
    localStorage.setItem("addy-gemini-model", model);
    setKeyStatus(
      "Saved in this browser. It is sent to the local API only when needed and is not stored in the database."
    );
  }
  async function testKey() {
    setKeyStatus("Checking key…");
    try {
      const r = await request("/api/settings/test-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: apiKey }),
      });
      setKeyStatus(r.message);
    } catch (e) {
      setKeyStatus(e instanceof Error ? e.message : "Key test failed.");
    }
  }
  async function cancel(jobId: string) {
    try {
      await request(`/api/analysis/${jobId}/cancel`, { method: "POST" });
      refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not cancel job");
    }
  }
  async function retry(jobId: string) {
    try {
      await request(`/api/analysis/${jobId}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gemini_key: apiKey }),
      });
      refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not retry job");
    }
  }
  function openEdit(c: Clip) {
    setEditing(c);
    setEditTitle(c.title);
    setEditDesc(c.description || "");
  }
  async function saveEdit() {
    if (!editing) return;
    try {
      await request(`/api/clips/${editing.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: editTitle, description: editDesc }),
      });
      setEditing(null);
      refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Unable to save clip");
    }
  }
  async function removeClip(c: Clip) {
    if (!confirm(`Delete “${c.title}” and its exported files?`)) return;
    try {
      await request(`/api/clips/${c.id}`, { method: "DELETE" });
      setEditing(null);
      refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Unable to delete clip");
    }
  }
  const nav: [Page, any][] = [
    ["Dashboard", LayoutDashboard],
    ["Processing", Activity],
    ["My Clips", Clapperboard],
    ["History", FolderClock],
    ["Settings", Settings2],
  ];

  return (
    <main className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div className="brand">
          <Mark />
          <span className="brand-name">
            addy<span>clips</span>
            <small>STUDIO</small>
          </span>
          <button
            className="mobile-close icon-btn"
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>
        <div className="workspace-switch">
          <span className="workspace-avatar">A</span>
          <span>
            <b>My workspace</b>
            <small>Local instance</small>
          </span>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map(([name, Icon]) => (
            <button
              key={name}
              onClick={() => {
                setPage(name);
                setMobileOpen(false);
              }}
              className={`nav-item ${page === name ? "active" : ""}`}
            >
              <Icon size={17} />
              <span>{name}</span>
              {name === "Processing" && current && <i className="nav-live" />}
              {name === "My Clips" && clips.length > 0 && (
                <small>{clips.length}</small>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="storage-card">
            <div className="storage-icon">
              <HardDrive size={15} />
            </div>
            <div>
              <b>Stored on this device</b>
              <small>Exports stay in your data folder.</small>
            </div>
            <Check size={14} className="storage-check" />
          </div>
          <div className="side-help">
            <CircleHelp size={15} />
            <span>Help & documentation</span>
            <ArrowRight size={14} />
          </div>
          <div className="user-row">
            <div className="user-avatar">AC</div>
            <div>
              <b>Addy Clips</b>
              <small>Self-hosted studio</small>
            </div>
            <MoreHorizontal size={17} />
          </div>
        </div>
      </aside>
      {mobileOpen && (
        <button
          className="scrim"
          onClick={() => setMobileOpen(false)}
          aria-label="Close navigation"
        />
      )}
      <section className="main-area">
        <header className="topbar">
          <div className="crumb">
            <button
              className="menu-trigger icon-btn"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={19} />
            </button>
            <span>Workspace</span>
            <span className="crumb-slash">/</span>
            <b>{page}</b>
          </div>
          <div className="top-actions">
            <span className="system-status">
              <i /> All systems operational
            </span>
            <button className="icon-btn" aria-label="Notifications">
              <Bell size={17} />
            </button>
            <span className="top-avatar">A</span>
          </div>
        </header>
        <div className="content">
          {queryErr && (
            <div className="toast error">
              <CircleHelp size={17} />
              {queryErr}
              <button onClick={() => setQueryErr("")}>
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="toast">
              <Sparkles size={16} />
              <span>{notice}</span>
              <button onClick={() => setNotice("")}>
                <X size={15} />
              </button>
            </div>
          )}
          {(page === "Dashboard" || page === "My Clips") && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    <span className="eyebrow-mark">
                      <Zap size={12} />
                    </span>{" "}
                    YOUR HIGHLIGHT WORKSPACE
                  </div>
                  <h1>
                    {page === "Dashboard" ? (
                      <>
                        Turn long sessions
                        <br />
                        <span>into moments worth sharing.</span>
                      </>
                    ) : (
                      "Your clips, ready to go."
                    )}
                  </h1>
                  <p>
                    {page === "Dashboard"
                      ? "Drop in a recording. Addy finds the action, builds the cut, and keeps every export close."
                      : "Every finished moment, stored locally and ready to download."}
                  </p>
                </div>
                <div className="heading-date">
                  <span className="date-dot" /> LOCAL WORKSPACE{" "}
                  <span className="date-divider" />{" "}
                  <span>NO ACCOUNT REQUIRED</span>
                </div>
              </div>
              {page === "Dashboard" && (
                <section className="source-panel">
                  <div className="panel-topline">
                    <div className="panel-index">01</div>
                    <div>
                      <div className="section-kicker">START WITH A SOURCE</div>
                      <h2>What are we clipping today?</h2>
                    </div>
                    <span className="source-badge">
                      <LockKeyhole size={13} /> Your files stay yours
                    </span>
                  </div>
                  <div className="mode-switch" aria-label="Clipping mode">
                    <button
                      className={sourceMode === "vod" ? "selected" : ""}
                      onClick={() => {
                        setSourceMode("vod");
                        setSource(null);
                      }}
                    >
                      VOD / recording
                    </button>
                    <button
                      className={sourceMode === "live" ? "selected" : ""}
                      onClick={() => {
                        setSourceMode("live");
                        setSource(null);
                        setProject(null);
                      }}
                    >
                      <Radio size={14} /> Live replay buffer
                    </button>
                  </div>

                  {sourceMode === "vod" && (
                    <>
                      {/* Primary: Local File Upload (Prominent) */}
                      <div className="source-input-row primary-upload">
                        <label
                          className={`drop-zone ${uploadBusy ? "uploading" : ""}`}
                          style={{ display: 'flex', flexDirection: 'column', gap: '0' }}
                        >
                          <input
                            type="file"
                            accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo,.mkv,.mov,.mp4"
                            onChange={(e) => upload(e.target.files?.[0])}
                          />
                          <span className="upload-icon">
                            {uploadBusy ? (
                              <LoaderCircle className="spin" size={22} />
                            ) : (
                              <Upload size={22} />
                            )}
                          </span>
                          <span>
                            <b>
                              {uploadBusy
                                ? `Uploading your video · ${uploadPct}%`
                                : "Drop a recording here, or browse files"}
                            </b>
                            <small>
                              MP4, MOV, MKV, WebM, AVI · Up to 2 GB · Maximum 180 minutes
                            </small>
                          </span>
                          <span className="browse-pill">
                            Browse files <ArrowRight size={14} />
                          </span>
                          {uploadBusy && (
                            <i
                              className="upload-progress"
                              style={{ width: `${uploadPct}%` }}
                            />
                          )}
                        </label>
                      </div>

                      {/* Divider */}
                      <div className="source-divider">
                        <span>OR PASTE A URL (TWITCH VOD)</span>
                      </div>

                      {/* Secondary: Twitch VOD URL with YouTube marked as Beta */}
                      <div className="source-input-row">
                        <div className="source-input-wrap">
                          <Video size={17} />
                          <input
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && preview()}
                            placeholder="Twitch VOD URL (twitch.tv/videos/...)"
                            aria-label="Source URL"
                          />
                          <button
                            className="paste-btn"
                            onClick={async () => {
                              try {
                                setUrl(await navigator.clipboard.readText());
                              } catch {
                                setNotice(
                                  "Clipboard access is unavailable in this browser."
                                );
                              }
                            }}
                          >
                            Paste
                          </button>
                        </div>
                        <button
                          className="btn-secondary"
                          onClick={preview}
                          disabled={previewBusy || !url.trim()}
                        >
                          {previewBusy ? (
                            <LoaderCircle className="spin" size={16} />
                          ) : (
                            <Search size={16} />
                          )}{" "}
                          Validate source
                        </button>
                      </div>

                      {/* YouTube Beta Notice */}
                      <div className="youtube-beta-notice">
                        <span className="beta-badge">
                          <span className="beta-dot" />
                          <span>BETA</span>
                        </span>
                        <span className="beta-text">
                          YouTube Live/VOD clipping is experimental — YouTube Data API provides metadata only.
                          Video byte access requires creator-authorized OAuth. Local uploads work reliably today.
                        </span>
                        <a
                          href="https://developers.google.com/youtube/terms/developer-policies"
                          target="_blank"
                          rel="noreferrer"
                          className="beta-link"
                        >
                          Learn more
                        </a>
                      </div>
                    </>
                  )}

                  {sourceMode === "live" && (
                    <div className="source-input-row">
                      <div className="source-input-wrap">
                        <Video size={17} />
                        <input
                          value={url}
                          onChange={(e) => setUrl(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && preview()}
                          placeholder="Twitch channel URL, e.g. twitch.tv/channel"
                          aria-label="Source URL"
                        />
                        <button
                          className="paste-btn"
                          onClick={async () => {
                            try {
                              setUrl(await navigator.clipboard.readText());
                            } catch {
                              setNotice(
                                "Clipboard access is unavailable in this browser."
                              );
                            }
                          }}
                        >
                          Paste
                        </button>
                      </div>
                      <button
                        className="btn-secondary"
                        onClick={preview}
                        disabled={previewBusy || !url.trim()}
                      >
                        {previewBusy ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <Search size={16} />
                        )}{" "}
                        Validate source
                      </button>
                    </div>
                  )}
                  {source && (
                    <div className="source-preview">
                      <div className="preview-art">
                        <Video size={22} />
                      </div>
                      <div className="preview-info">
                        <b>
                          {project?.title ||
                            source.title ||
                            source.channel ||
                            "Video source"}
                        </b>
                        <small>
                          {project
                            ? `${fmt(project.duration)} · local file`
                            : source.channel ||
                              source.source_type ||
                              "Source"}{" "}
                          {source.live && <em className="live-pill">LIVE</em>}
                        </small>
                        <p>
                          {source.media_access
                            ? "Video file is accessible and ready for analysis."
                            : source.access_message ||
                              "Source format recognized; access is checked by the worker."}
                        </p>
                      </div>
                      <span
                        className={`access-pill ${
                          source.media_access || source.processable
                            ? "good"
                            : "limited"
                        }`}
                      >
                        <i />
                        {source.media_access
                          ? "Ready to analyze"
                          : source.processable
                          ? "Supported source"
                          : "Metadata only"}
                      </span>
                    </div>
                  )}
                  {project && (
                    <video
                      className="source-player"
                      controls
                      preload="metadata"
                      src={`${API}/api/projects/${project.project_id}/source`}
                    />
                  )}
                  <div className="source-foot">
                    <span>
                      <ShieldCheck size={14} /> Source access is checked before
                      processing.
                    </span>
                    <span className="beta-badge-inline-small">YouTube = Beta</span>
                    <a
                      href="https://developers.google.com/youtube/terms/developer-policies"
                      target="_blank"
                      rel="noreferrer"
                    >
                      YouTube access notes <ArrowRight size={13} />
                    </a>
                  </div>
                  <div className="analysis-config">
                    <div className="config-head">
                      <div>
                        <div className="section-kicker">MAKE IT YOURS</div>
                        <h3>Analysis preferences</h3>
                      </div>
                      <button
                        className="reset-btn"
                        onClick={() => {
                          setCount(5);
                          setDuration(45);
                          setSensitivity("balanced");
                          setGenerateTitles(false);
                          setGenerateCaptions(false);
                        }}
                      >
                        <RefreshCw size={13} /> Reset
                      </button>
                    </div>
                    <div className="config-row">
                      <div className="config-control">
                        <label htmlFor="clip-count">Number of clips</label>
                        <div className="stepper">
                          <button
                            onClick={() => setCount(Math.max(1, count - 1))}
                            aria-label="Decrease clip count"
                          >
                            −
                          </button>
                          <input
                            id="clip-count"
                            value={count}
                            type="number"
                            min="1"
                            max="50"
                            onChange={(e) =>
                              setCount(
                                Math.min(50, Math.max(1, +e.target.value || 1))
                              )
                            }
                          />
                          <button
                            onClick={() => setCount(Math.min(50, count + 1))}
                            aria-label="Increase clip count"
                          >
                            +
                          </button>
                          <span>clips</span>
                        </div>
                      </div>
                      <div className="config-control duration-control">
                        <label htmlFor="duration">Target clip length</label>
                        <div className="select-wrap">
                          <select
                            id="duration"
                            value={duration}
                            onChange={(e) => setDuration(+e.target.value)}
                          >
                            {[15, 30, 45, 60, 90, 120].map((n) => (
                              <option key={n} value={n}>
                                {n} seconds
                              </option>
                            ))}
                          </select>
                          <ChevronDown size={14} />
                        </div>
                      </div>
                      <div className="config-control sensitivity-control">
                        <label>Detection sensitivity</label>
                        <div className="segmented">
                          {["relaxed", "balanced", "sensitive"].map((s) => (
                            <button
                              onClick={() => setSensitivity(s)}
                              className={sensitivity === s ? "selected" : ""}
                              key={s}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="signal-note">
                      Prime-style picking ranks audio loudness spikes. Twitch
                      live can add chat-rate spikes when chat credentials are
                      configured.
                    </div>
                    <div className="optional-output">
                      <label>
                        <input
                          type="checkbox"
                          checked={generateTitles}
                          onChange={(e) => setGenerateTitles(e.target.checked)}
                        />{" "}
                        Generate AI titles and descriptions{" "}
                        <small>
                          Gemini is used only for metadata, never moment
                          detection.
                        </small>
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={generateCaptions}
                          onChange={(e) =>
                            setGenerateCaptions(e.target.checked)
                          }
                        />{" "}
                        Generate and burn captions{" "}
                        <small>
                          Local faster-whisper transcription; first run
                          downloads its model.
                        </small>
                      </label>
                    </div>
                  </div>
                  <div className="start-row">
                    <div className="ai-note">
                      <Sparkles size={15} />
                      <span>
                        {sourceMode === "live"
                          ? "Rolling replay buffer · Twitch live"
                          : "Audio and chat hype signals"}
                        <small>AI titles and captions are optional.</small>
                      </span>
                    </div>
                    <button
                      className="btn-primary"
                      onClick={start}
                      disabled={busy}
                    >
                      {busy ? (
                        <LoaderCircle size={16} className="spin" />
                      ) : (
                        <Sparkles size={16} />
                      )}{" "}
                      {sourceMode === "live"
                        ? "Start live clipping"
                        : "Start analysis"}{" "}
                      <ArrowRight size={15} />
                    </button>
                  </div>
                </section>
              )}
              {page === "My Clips" && (
                <div className="clip-toolbar">
                  <div className="search-box">
                    <Search size={15} />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search your clips"
                    />
                  </div>
                  <select
                    className="filter-select"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option>All moments</option>
                    {CATEGORIES.map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                </div>
              )}
              {page === "Dashboard" && (
                <section className="clips-section">
                  <div className="section-title-row">
                    <div>
                      <div className="section-kicker">THE GOOD STUFF</div>
                      <h2>
                        Generated clips{" "}
                        <span className="count-badge">{clips.length}</span>
                      </h2>
                      <p>
                        The moments you’ll want to replay. Automatically saved
                        to your device.
                      </p>
                    </div>
                    <button
                      className="text-link"
                      onClick={() => setPage("My Clips")}
                    >
                      View all clips <ArrowRight size={15} />
                    </button>
                  </div>
                  {clipGrid(filtered.slice(0, 4), openEdit)}
                </section>
              )}
              {page === "My Clips" && (
                <section className="clips-section full-clips">
                  <div className="section-title-row">
                    <div>
                      <div className="section-kicker">LOCAL LIBRARY</div>
                      <h2>
                        All generated clips{" "}
                        <span className="count-badge">{filtered.length}</span>
                      </h2>
                      <p>
                        Exports stay in <code>data/clips/</code> on this
                        machine.
                      </p>
                    </div>
                  </div>
                  {clipGrid(filtered, openEdit)}
                </section>
              )}
              {page === "Dashboard" && (
                <section className="recent-section">
                  <div className="section-title-row">
                    <div>
                      <div className="section-kicker">
                        PICK UP WHERE YOU LEFT OFF
                      </div>
                      <h2>Recent projects</h2>
                    </div>
                    <button
                      className="text-link"
                      onClick={() => setPage("History")}
                    >
                      View history <ArrowRight size={15} />
                    </button>
                  </div>
                  {jobs.length ? (
                    <div className="project-list">
                      {jobs.slice(0, 3).map((j) => (
                        <button
                          className="project-row"
                          key={j.id}
                          onClick={() => setPage("Processing")}
                        >
                          <span className="project-thumb">
                            <Film size={17} />
                          </span>
                          <span className="project-name">
                            <b>{j.stage}</b>
                            <small>
                              Project {j.project_id.slice(0, 8)} ·{" "}
                              {new Date(
                                j.updated_at || Date.now()
                              ).toLocaleDateString()}
                            </small>
                          </span>
                          <span className={`job-status ${j.status}`}>
                            {j.status.replace("_", " ")}
                          </span>
                          <ArrowRight size={15} />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="recent-empty">
                      <Clock3 size={15} /> Your project history will appear here
                      after your first analysis.
                    </div>
                  )}
                </section>
              )}
            </>
          )}
          {page === "Processing" && (
            <section className="subpage">
              <div className="eyebrow">
                <span className="eyebrow-mark">
                  <Activity size={12} />
                </span>{" "}
                LIVE JOB STATE
              </div>
              <h1>Processing queue</h1>
              <p className="subpage-lead">
                Real stages reported by the background worker. This page
                reconnects to persisted status after a refresh.
              </p>
              {jobs.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">
                    <Activity size={24} />
                  </div>
                  <h3>Nothing in the queue yet</h3>
                  <p>
                    Start an analysis from the dashboard to see its work unfold
                    here.
                  </p>
                  <button
                    className="btn-secondary"
                    onClick={() => setPage("Dashboard")}
                  >
                    Start a new analysis <ArrowRight size={15} />
                  </button>
                </div>
              ) : (
                <div className="jobs-list">
                  {jobs.map((j) => {
                    // Check if this is a YouTube live job
                    const isYtLive = j.stage.toLowerCase().includes("downloading") ||
                                     j.stage.toLowerCase().includes("probing") ||
                                     j.stage.toLowerCase().includes("cleaning") ||
                                     j.stage.toLowerCase().includes("cleanup");
                    const stepInfo = getYtLiveStepInfo(j.stage, j.progress);

                    return (
                      <article className="job-card" key={j.id}>
                        <div className="job-card-top">
                          <div className={`job-icon ${j.status}`}>
                            <Activity size={18} />
                          </div>
                          <div className="job-main">
                            <div>
                              <b>{j.stage}</b>
                              <span className={`job-status ${j.status}`}>
                                {j.status.replace("_", " ")}
                              </span>
                            </div>
                            <small>
                              Project {j.project_id.slice(0, 8)} · updated{" "}
                              {j.updated_at
                                ? new Date(j.updated_at).toLocaleTimeString()
                                : "just now"}
                            </small>
                            {j.error && <p className="job-error">{j.error}</p>}
                          </div>
                          {["queued", "running"].includes(j.status) && (
                            <button
                              className="btn-quiet"
                              onClick={() => cancel(j.id)}
                            >
                              <X size={14} /> Cancel
                            </button>
                          )}
                          {["waiting_for_key", "failed"].includes(j.status) && (
                            <button
                              className="btn-secondary"
                              onClick={() => retry(j.id)}
                            >
                              <RefreshCw size={13} /> Retry with saved key
                            </button>
                          )}
                        </div>

                        {/* Step-by-step progress for YouTube live */}
                        {isYtLive && (
                          <div className="yt-live-steps">
                            {YT_LIVE_STEPS.map((step, idx) => {
                              const isComplete = idx < stepInfo.stepIndex;
                              const isCurrent = idx === stepInfo.stepIndex;
                              const isPending = idx > stepInfo.stepIndex;

                              return (
                                <div key={step.key} className={`step-item ${isComplete ? "complete" : ""} ${isCurrent ? "current" : ""} ${isPending ? "pending" : ""}`}>
                                  <div className="step-marker">
                                    {isComplete && <Check size={14} />}
                                    {isCurrent && <LoaderCircle size={14} className="spin" />}
                                    {isPending && <span className="step-number">{idx + 1}</span>}
                                  </div>
                                  <div className="step-info">
                                    <span className="step-label">{step.label}</span>
                                    {isCurrent && (
                                      <div className="step-mini-progress">
                                        <i style={{ width: `${stepInfo.stepProgress}%` }} />
                                      </div>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        <div className="progress-track">
                          <i style={{ width: `${j.progress}%` }} />
                        </div>
                        <div className="progress-label">
                          <span>
                            {j.status === "running"
                              ? "Worker progress"
                              : "Persisted progress"}
                          </span>
                          <b>{j.progress}%</b>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          )}
          {page === "History" && (
            <section className="subpage">
              <div className="eyebrow">
                <span className="eyebrow-mark">
                  <FolderClock size={12} />
                </span>{" "}
                PROJECT RECORD
              </div>
              <h1>Analysis history</h1>
              <p className="subpage-lead">
                Projects and job states are stored locally in SQLite and survive
                restarts.
              </p>
              {jobs.length ? (
                <div className="jobs-list">
                  {jobs.map((j) => (
                    <article className="job-card history-card" key={j.id}>
                      <span className="project-thumb">
                        <Film size={17} />
                      </span>
                      <div className="job-main">
                        <b>{j.stage}</b>
                        <small>
                          Project {j.project_id} ·{" "}
                          {j.created_at
                            ? new Date(j.created_at).toLocaleString()
                            : "—"}
                        </small>
                      </div>
                      <span className={`job-status ${j.status}`}>
                        {j.status}
                      </span>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <FolderClock size={24} />
                  <h3>No history yet</h3>
                  <p>Once you start a project, it will be listed here.</p>
                </div>
              )}
            </section>
          )}
          {page === "Settings" && (
            <section className="subpage settings-page">
              <div className="eyebrow">
                <span className="eyebrow-mark">
                  <Settings2 size={12} />
                </span>{" "}
                YOUR SETUP
              </div>
              <h1>Settings</h1>
              <p className="subpage-lead">
                A few local choices to make Addy Clips work for your setup.
              </p>
              <div className="settings-card">
                <div className="settings-heading">
                  <span className="settings-icon">
                    <KeyRound size={18} />
                  </span>
                  <div>
                    <h2>Gemini API key</h2>
                    <p>
                      Optional: use your own Google AI Studio key to generate
                      clip titles and descriptions.
                    </p>
                  </div>
                  <span className="local-only">
                    <LockKeyhole size={12} /> LOCAL ONLY
                  </span>
                </div>
                <div className="key-callout">
                  <ShieldCheck size={16} />
                  <span>
                    Your key is stored in this browser’s local storage. It is
                    sent to the local API for testing or optional AI titles,
                    held in API memory, and never saved to SQLite or sent to the
                    video worker. Browser storage is convenient, but it is not a
                    secure vault.
                  </span>
                </div>
                <label className="field-label" htmlFor="gemini-key">
                  API key
                </label>
                <div className="key-input">
                  <input
                    id="gemini-key"
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Paste your Gemini API key"
                    autoComplete="off"
                  />
                  <button onClick={() => setShowKey(!showKey)}>
                    {showKey ? "Hide" : "Show"}
                  </button>
                </div>
                <div className="model-row">
                  <div>
                    <label className="field-label">Model selection</label>
                    <p>Gemini is used only when AI titles are enabled.</p>
                  </div>
                  <div className="model-control">
                    <label className="auto-toggle">
                      <input
                        type="checkbox"
                        checked={autoModel}
                        onChange={(e) => setAutoModel(e.target.checked)}
                      />
                      <span className="toggle-ui" /> Automatic
                    </label>
                    <div
                      className={`select-wrap model-select ${
                        autoModel ? "disabled" : ""
                      }`}
                    >
                      <select
                        disabled={autoModel}
                        value={model}
                        onChange={(e) => {
                          setModel(e.target.value);
                          localStorage.setItem(
                            "addy-gemini-model",
                            e.target.value
                          );
                        }}
                      >
                        {models.map((m) => (
                          <option key={m}>{m}</option>
                        ))}
                      </select>
                      <ChevronDown size={14} />
                    </div>
                  </div>
                </div>
                {keyStatus && (
                  <div
                    className={`key-status ${
                      keyStatus.includes("accepted") ||
                      keyStatus.includes("Saved")
                        ? "success"
                        : ""
                    }`}
                  >
                    {keyStatus.includes("accepted") ||
                    keyStatus.includes("Saved") ? (
                      <Check size={15} />
                    ) : (
                      <CircleHelp size={15} />
                    )}{" "}
                    {keyStatus}
                  </div>
                )}
                <div className="settings-actions">
                  <a
                    href="https://aistudio.google.com/apikey"
                    target="_blank"
                    rel="noreferrer"
                    className="text-link"
                  >
                    Get a Gemini API key <ArrowRight size={14} />
                  </a>
                  <div>
                    <button
                      className="btn-secondary"
                      onClick={testKey}
                      disabled={!apiKey}
                    >
                      <BadgeCheck size={15} /> Test key
                    </button>
                    <button className="btn-primary save-key" onClick={saveKey}>
                      <Check size={15} /> Save key
                    </button>
                  </div>
                </div>
              </div>
              <div className="settings-card integration-card">
                <div className="settings-heading">
                  <span className="settings-icon muted-icon">
                    <Radio size={18} />
                  </span>
                  <div>
                    <h2>Source integrations</h2>
                    <p>
                      Metadata lookup and permitted video access are separate
                      capabilities.
                    </p>
                  </div>
                </div>
                <div className="integration-row">
                  <span className="integration-symbol youtube">▶</span>
                  <div>
                    <b>YouTube Data API</b>
                    <span className="beta-badge-inline">BETA</span>
                    <small>
                      {"YOUTUBE_API_KEY is " +
                        (youtubeMetadataEnabled
                          ? "configured in the API"
                          : "not configured")}
                    </small>
                  </div>
                  <span className="integration-state">
                    <i /> Metadata only
                  </span>
                </div>
                <p className="integration-note">
                  <strong>Status:</strong> YouTube Live/VOD clipping is experimental (Beta).
                  The official YouTube Data API returns public metadata only — it does not
                  provide arbitrary video stream access. Creator-authorized OAuth is required
                  for permitted video bytes. Local uploads and Twitch VODs work reliably today.
                </p>
              </div>
              <div className="settings-card">
                <div className="settings-heading">
                  <span className="settings-icon muted-icon">
                    <HardDrive size={18} />
                  </span>
                  <div>
                    <h2>Local storage</h2>
                    <p>
                      Runtime files persist on the host in your configured data
                      folder.
                    </p>
                  </div>
                </div>
                <div className="storage-path">
                  <code>data/clips/</code>
                  <span>Completed vertical and landscape MP4s</span>
                  <code>data/database/</code>
                  <span>Projects, jobs, and clip metadata</span>
                </div>
              </div>
            </section>
          )}
        </div>
        <footer className="footer">
          <span>© {new Date().getFullYear()} Addy Clips</span>
          <span>Built for the moments between missions.</span>
          <span>
            <i /> Local-first by design
          </span>
        </footer>
      </section>
      {editing && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => e.target === e.currentTarget && setEditing(null)}
        >
          <section className="editor-modal">
            <header>
              <div>
                <span className="section-kicker">CLIP EDITOR</span>
                <h2>Edit your moment</h2>
              </div>
              <button
                className="icon-btn"
                onClick={() => setEditing(null)}
                aria-label="Close editor"
              >
                <X size={18} />
              </button>
            </header>
            <div className="editor-body">
              <div className={`video-preview ${format}`}>
                <video
                  controls
                  src={`${API}/api/clips/${editing.id}/stream?format=${format}`}
                >
                  <track kind="captions" />
                </video>
                <span className="preview-format">
                  {format === "vertical" ? "9:16 VERTICAL" : "16:9 LANDSCAPE"}
                </span>
              </div>
              <div className="format-switch">
                <button
                  className={format === "vertical" ? "active" : ""}
                  onClick={() => setFormat("vertical")}
                >
                  Vertical <small>1080 × 1920</small>
                </button>
                <button
                  className={format === "landscape" ? "active" : ""}
                  onClick={() => setFormat("landscape")}
                >
                  Landscape <small>1920 × 1080</small>
                </button>
              </div>
              <label className="field-label" htmlFor="edit-title">
                Clip title
              </label>
              <input
                className="editor-input"
                id="edit-title"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
              />
              <label className="field-label" htmlFor="edit-desc">
                Description
              </label>
              <textarea
                className="editor-input"
                id="edit-desc"
                rows={3}
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                placeholder="Add a description"
              />
              <div className="editor-meta">
                <span>
                  <Gauge size={14} /> {editing.score} excitement
                </span>
                <span>
                  <Clock3 size={14} /> {fmt(editing.end - editing.start)}
                </span>
                <span>
                  <Sparkles size={14} /> {editing.category}
                </span>
              </div>
              <div className="editor-note">
                <AudioLines size={14} /> Center-crop fallback used. Captions are
                generated locally only when enabled for an analysis.
              </div>
            </div>
            <footer>
              <button
                className="delete-btn"
                onClick={() => removeClip(editing)}
              >
                <X size={14} /> Delete clip
              </button>
              <div>
                <a
                  className="btn-secondary download-link"
                  href={`${API}/api/clips/${editing.id}/download?format=${format}`}
                >
                  <ArrowDownToLine size={15} /> Download {format}
                </a>
                <button className="btn-primary" onClick={saveEdit}>
                  <Check size={15} /> Save changes
                </button>
              </div>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}

function clipGrid(items: Clip[], open: (c: Clip) => void) {
  return items.length ? (
    <div className="clip-grid">
      {items.map((c, i) => (
        <article className="clip-card" key={c.id}>
          <button
            className="clip-visual"
            onClick={() => open(c)}
            aria-label={`Preview ${c.title}`}
          >
            <div className="thumbnail-fallback">
              <span className="thumb-grid" />
              <span className="thumb-glow" />
              <span className="thumb-symbol">
                <Scissors size={28} />
              </span>
              <span className="thumb-label">
                MOMENT {String(i + 1).padStart(2, "0")}
              </span>
            </div>
            <img
              src={`${API}/api/clips/${c.id}/thumbnail`}
              alt=""
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
            <span className="play-overlay">
              <Play size={17} fill="currentColor" />
            </span>
            <span className="clip-duration">{fmt(c.end - c.start)}</span>
          </button>
          <div className="clip-card-body">
            <div className="clip-card-title">
              <button onClick={() => open(c)}>{c.title}</button>
              <button
                className="card-more"
                onClick={() => open(c)}
                aria-label="Edit clip"
              >
                <MoreHorizontal size={17} />
              </button>
            </div>
            <div className="clip-card-meta">
              <span className="score">
                <Zap size={12} />
                {c.score}
              </span>
              <span className="category-tag">{c.category}</span>
            </div>
            <div className="clip-card-footer">
              <span>
                <Clock3 size={12} />
                {new Date(c.created_at).toLocaleDateString()}
              </span>
              <div className="format-icons">
                <span title="Vertical export ready">9:16</span>
                <span title="Landscape export ready">16:9</span>
              </div>
            </div>
          </div>
        </article>
      ))}
    </div>
  ) : (
    <div className="clips-empty">
      <div className="empty-art">
        <span className="empty-orbit orbit-a" />
        <span className="empty-orbit orbit-b" />
        <span className="empty-core">
          <Scissors size={22} />
        </span>
        <span className="empty-spark spark-a">✦</span>
        <span className="empty-spark spark-b">✧</span>
      </div>
      <h3>No highlights yet</h3>
      <p>
        Good moments are worth keeping. Start an analysis and your clips will
        show up here.
      </p>
      <button
        className="btn-primary"
        onClick={() =>
          window.dispatchEvent(new CustomEvent("addy-new-analysis"))
        }
      >
        <Plus size={15} /> Start your first analysis <ArrowRight size={14} />
      </button>
    </div>
  );
}
