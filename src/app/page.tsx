"use client";

import { useEffect, useRef, useState } from "react";
import { Activity, ArrowUpRight, Captions, Check, ChevronDown, CircleHelp, Clapperboard, Clock3, Film, FolderOpen, KeyRound, LoaderCircle, MonitorPlay, MoreHorizontal, Play, Radio, Settings2, Sparkles, Upload, WandSparkles, X } from "lucide-react";
import { JobCard, type Job } from "@/components/job-card";
import { StatCard } from "@/components/stat-card";
const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const initialJobs: Job[] = [];

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [source, setSource] = useState("");
  const [mode, setMode] = useState<"video" | "live">("video");
  const [ratio, setRatio] = useState<"9:16" | "16:9">("9:16");
  const [duration, setDuration] = useState(30);
  const [quality, setQuality] = useState("Source resolution");
  const [clips, setClips] = useState(5);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [keySaved, setKeySaved] = useState(false);
  const [notice, setNotice] = useState("");
  const [activeNav, setActiveNav] = useState("Studio");
  const [showSettings, setShowSettings] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch(`${API}/api/jobs`).then(r => r.ok ? r.json() : null).then(data => { if (data?.jobs) setJobs(data.jobs); }).catch(() => {});
    fetch(`${API}/api/settings`).then(r => r.ok ? r.json() : null).then(data => { if (data?.gemini_configured) setKeySaved(true); }).catch(() => {});
  }, []);

  async function startJob(file?: File) {
    if (!file && !source.trim()) { setNotice("Add a YouTube link or choose a video file to get started."); return; }
    setBusy(true); setNotice("");
    const form = new FormData();
    if (file) form.append("file", file);
    form.append("source", file ? file.name : source.trim());
    form.append("source_type", file ? "upload" : mode === "live" ? "live" : "youtube");
    form.append("clip_count", String(clips)); form.append("duration", String(duration)); form.append("aspect_ratio", ratio); form.append("quality", quality); form.append("prompt", prompt);
    try {
      const res = await fetch(`${API}/api/jobs`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not start the job.");
      setJobs(current => [data.job, ...current.filter(j => !j.id.startsWith("demo-"))]);
      setNotice("Job added to the local queue. Video processing is the next implementation phase."); setSource("");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Backend is offline.";
      setNotice(msg.includes("fetch") ? "Backend not running yet. Follow the README setup steps, then try again." : msg);
    } finally { setBusy(false); }
  }

  async function saveKey() {
    try {
      const res = await fetch(`${API}/api/settings`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ gemini_api_key: apiKey }) });
      if (!res.ok) throw new Error("Could not save key");
      setKeySaved(true); setApiKey(""); setNotice("Gemini API key saved locally.");
    } catch { setNotice("Could not reach the backend. Start FastAPI to save your key locally."); }
  }

  const completed = jobs.filter(j => j.status === "completed").length;
  const watching = jobs.filter(j => j.status === "watching").length;
  const queued = jobs.filter(j => ["queued", "processing"].includes(j.status)).length;
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#studio" aria-label="Addy Clips home"><span className="brand-mark"><Clapperboard size={19} strokeWidth={2.3}/></span><span>Addy Clips<small>GTA VI CLIP STUDIO</small></span></a>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav-list" aria-label="Main navigation">
          {[{name:"Studio",icon:WandSparkles},{name:"My clips",icon:Film},{name:"Live monitor",icon:Radio}].map(({name,icon:Icon}) => <button key={name} onClick={() => {setActiveNav(name); if(name === "Live monitor") setMode("live");}} className={`nav-item ${activeNav===name?"selected":""}`}><Icon size={17}/>{name}{name==="My clips"&&completed>0&&<span className="nav-count">{completed}</span>}{name==="Live monitor"&&watching>0&&<span className="live-dot"/>}</button>)}
        </nav>
        <div className="sidebar-bottom"><div className="local-card"><span className="local-icon"><FolderOpen size={16}/></span><div><b>Saved on this device</b><small>Local workspace</small></div><span className="online-dot"/></div><button className="nav-item settings-link" onClick={()=>setShowSettings(true)}><Settings2 size={17}/>Settings<ArrowUpRight size={14} className="settings-arrow"/></button><div className="sidebar-foot">ADDY CLIPS <span>v0.1.0</span></div></div>
      </aside>
      <section className="main-area" id="studio">
        <header className="topbar"><div className="crumb">Workspace <span>/</span> <b>{activeNav}</b></div><div className="top-actions"><span className="local-pill"><span className="online-dot"/>Local only</span><button className="icon-button help-button" aria-label="Help"><CircleHelp size={18}/></button><button className="avatar" aria-label="Open settings" onClick={()=>setShowSettings(true)}>A</button></div></header>
        <div className="content-wrap">
          <div className="page-heading"><div><div className="eyebrow"><Sparkles size={13}/> YOUR MOMENTS, EDITED</div><h1>{activeNav === "Live monitor" ? "Live monitor" : activeNav === "My clips" ? "Your clips" : "Clip studio"}</h1><p>Turn your best GTA VI moments into clips worth sharing.</p></div><button className="outline-button" onClick={()=>setShowSettings(true)}><Settings2 size={16}/> Configure AI</button></div>
          <div className="stats-row"><StatCard icon={Film} label="CLIPS CREATED" value={String(jobs.reduce((s,j)=>s+(j.status==="completed"?j.clips:0),0)).padStart(2,"0")} helper="Saved to your device"/><StatCard icon={Activity} label="IN PROGRESS" value={String(queued+watching).padStart(2,"0")} helper={watching?"Live monitor active":"Ready when you are"}/><StatCard icon={Clock3} label="PROCESSING" value={queued?"Working":"Idle"} helper={queued?"One job at a time":"Queue is clear"} compact/></div>
          <div className="workspace-grid">
            <section className="panel create-panel">
              <div className="panel-heading"><div><span className="section-index">01</span><h2>Start a new clip job</h2></div><span className="step-chip"><span/> READY</span></div>
              <div className="mode-tabs" role="tablist" aria-label="Source type"><button role="tab" aria-selected={mode==="video"} className={mode==="video"?"active":""} onClick={()=>setMode("video")}><MonitorPlay size={16}/> Video</button><button role="tab" aria-selected={mode==="live"} className={mode==="live"?"active":""} onClick={()=>setMode("live")}><Radio size={16}/> Live stream<span className="new-badge">BETA</span></button></div>
              <label className="field-label" htmlFor="source">{mode==="live"?"YouTube live stream link":"YouTube video link"}<span>Link must be publicly accessible</span></label>
              <div className="source-input"><Play size={15} fill="currentColor"/><input id="source" value={source} onChange={e=>setSource(e.target.value)} placeholder="https://youtube.com/watch?v=..."/><button aria-label="Clear link" onClick={()=>setSource("")} className="clear-input"><X size={15}/></button></div>
              <div className="or-divider"><span>OR UPLOAD A VIDEO</span></div>
              <button className={`upload-box ${dragging?"dragging":""}`} onClick={()=>fileRef.current?.click()} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);const f=e.dataTransfer.files[0];if(f)void startJob(f);}}><span className="upload-icon"><Upload size={19}/></span><span><b>Drop your video here, or <em>browse files</em></b><small>MP4 video · processed locally</small></span><input ref={fileRef} type="file" accept="video/mp4,video/*" hidden onChange={e=>{const f=e.target.files?.[0];if(f)void startJob(f);e.currentTarget.value="";}}/></button>
              <div className="divider-line"/><div className="panel-heading options-heading"><div><span className="section-index">02</span><h2>Clip preferences</h2></div><span className="auto-chip"><Sparkles size={12}/> AI ASSISTED</span></div>
              <div className="options-grid"><div><label className="field-label" htmlFor="clip-count">Number of clips</label><div className="select-wrap"><select id="clip-count" value={clips} onChange={e=>setClips(Number(e.target.value))}>{[1,3,5,10,15].map(n=><option value={n} key={n}>{n} clips</option>)}</select><ChevronDown size={15}/></div></div><div><label className="field-label" htmlFor="duration">Clip duration <b className="value-tag">{duration}s</b></label><input id="duration" className="range" type="range" min="15" max="60" step="5" value={duration} onChange={e=>setDuration(Number(e.target.value))}/><div className="range-ends"><span>15 sec</span><span>60 sec</span></div></div></div>
              <div className="options-grid second-options"><fieldset><legend>Aspect ratio</legend><div className="ratio-options"><button onClick={()=>setRatio("9:16")} className={ratio==="9:16"?"ratio-card active":"ratio-card"}><span className="ratio-icon vertical"/>9:16 <small>Vertical</small></button><button onClick={()=>setRatio("16:9")} className={ratio==="16:9"?"ratio-card active":"ratio-card"}><span className="ratio-icon horizontal"/>16:9 <small>Landscape</small></button></div></fieldset><div><label className="field-label" htmlFor="quality">Export quality</label><div className="select-wrap"><select id="quality" value={quality} onChange={e=>setQuality(e.target.value)}><option>Source resolution</option><option>1080p maximum</option><option>720p maximum</option></select><ChevronDown size={15}/></div><div className="muted-note">Original video resolution</div></div></div>
              <label className="field-label prompt-label" htmlFor="prompt">What moments should the AI look for? <span>Optional</span></label><textarea id="prompt" value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="e.g. wild car chases, funny NPC moments, close calls..." rows={2}/>
              {mode==="live"&&<div className="live-note"><Activity size={15}/><span><b>Chat spike detection</b> learns the stream’s usual chat rate and flags unusual activity. Clips include 20 seconds before the spike.</span></div>}
              {notice&&<div className="notice" role="status">{notice}</div>}
              <button className="primary-button" onClick={()=>void startJob()} disabled={busy}>{busy?<LoaderCircle className="spin" size={17}/>:<Sparkles size={16}/>} {busy?"Adding job…":mode==="live"?"Start live monitoring":"Find my best moments"}<ArrowUpRight size={16}/></button>
              <div className="privacy-note"><span className="online-dot"/> Videos and clips stay on your device</div>
            </section>
            <aside className="right-column"><section className="panel queue-panel"><div className="panel-heading"><div><span className="section-index">03</span><h2>Recent jobs</h2></div><button className="more-button" aria-label="More job options"><MoreHorizontal size={19}/></button></div>{jobs.length===0?<div className="empty-state"><span className="empty-icon"><Clapperboard size={20}/></span><b>No clip jobs yet</b><span>Your clips will show up here.</span></div>:<div className="job-list">{jobs.map(job=><JobCard key={job.id} job={job}/>)}</div>}<button className="text-button" onClick={()=>setActiveNav("My clips")}>View all jobs <ArrowUpRight size={14}/></button></section>
              <section className="panel tip-panel"><div className="tip-top"><span className="tip-icon"><Activity size={16}/></span><span className="tip-label">LIVE CLIPPER</span><span className="coming-badge">IN DEVELOPMENT</span></div><h3>Catch the moment<br/>the chat goes wild.</h3><p>Add a live stream and Addy Clips will learn its normal chat pace, then save a clip when activity surges.</p><div className="buffer-row"><span><span className="buffer-dot"/> Rolling buffer</span><b>Ready when live starts</b></div><div className="tip-footer"><span><Check size={13}/> 20 sec pre-roll</span><span><Check size={13}/> One clip per spike</span></div></section>
              <section className="local-storage"><span className="storage-icon"><FolderOpen size={16}/></span><div><b>Local by design</b><span>Files save on your computer.<br/>Nothing is uploaded to our servers.</span></div><button onClick={()=>setShowSettings(true)} aria-label="Open local storage settings"><ArrowUpRight size={15}/></button></section>
            </aside>
          </div>
          <footer className="page-footer"><span>ADDY CLIPS <i>•</i> MADE FOR THE MOMENT</span><span>AI powered by Gemini <Sparkles size={12}/></span></footer>
        </div>
      </section>
      {showSettings&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setShowSettings(false);}}><section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title"><div className="modal-heading"><div><span className="section-index">SETUP</span><h2 id="settings-title">AI settings</h2></div><button className="icon-button" onClick={()=>setShowSettings(false)} aria-label="Close settings"><X size={18}/></button></div><p className="modal-intro">Connect your Gemini API key to generate titles, captions, and AI-selected moments. Your key is stored locally on this computer.</p><label className="field-label" htmlFor="gemini-key">Google Gemini API key {keySaved&&<b className="configured"><Check size={12}/> CONFIGURED</b>}</label><div className="key-input"><KeyRound size={16}/><input id="gemini-key" type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder={keySaved?"Saved on this device":"Paste your Gemini API key"} autoComplete="off"/></div><a className="get-key" href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Get a Gemini API key <ArrowUpRight size={13}/></a><div className="settings-info"><Captions size={15}/><span>Gemini is used for moment analysis, English captions, and clip titles. FFmpeg handles video processing locally.</span></div>{notice&&<div className="notice" role="status">{notice}</div>}<div className="modal-actions"><button className="outline-button" onClick={()=>setShowSettings(false)}>Cancel</button><button className="primary-button" onClick={()=>void saveKey()} disabled={!apiKey.trim()}><Check size={15}/> Save API key</button></div></section></div>}
    </main>
  );
}

