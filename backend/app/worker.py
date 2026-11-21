import base64, json, os, re, shutil, socket, ssl, subprocess, threading, time, uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from .config import DATA_DIR, API_INTERNAL_URL, DOWNLOAD_DIR, YOUTUBE_LIVE_DOWNLOAD_DURATION_MINUTES
from .database import db, now
from .services.video import probe
from .services.signals import audio_levels, rank_vod_moments, LiveHypeDetector
from .services.sources import twitch_source
from .services.youtube_live import download_youtube_live
from .services.captions import transcribe, write_srt

class TwitchChat:
    """Optional Twitch IRC message counter; requires a user OAuth token with chat:read."""
    def __init__(self, channel):
        self.counts=deque(); self.stop=threading.Event(); self.enabled=False
        username=os.getenv("TWITCH_CHAT_USERNAME","").strip().lower(); token=os.getenv("TWITCH_CHAT_OAUTH_TOKEN","").strip()
        if not username or not token: return
        self.enabled=True
        def listen():
            try:
                with ssl.create_default_context().wrap_socket(socket.create_connection(("irc.chat.twitch.tv",6697),timeout=15),server_hostname="irc.chat.twitch.tv") as sock:
                    sock.settimeout(1); sock.sendall(f"PASS oauth:{token}\r\nNICK {username}\r\nCAP REQ :twitch.tv/tags twitch.tv/commands\r\nJOIN #{channel}\r\n".encode())
                    buf=b""
                    while not self.stop.is_set():
                        try: data=sock.recv(4096)
                        except socket.timeout: continue
                        if not data: break
                        buf+=data
                        while b"\r\n" in buf:
                            line,buf=buf.split(b"\r\n",1)
                            if line.startswith(b"PING "): sock.sendall(b"PONG "+line[5:]+b"\r\n")
                            elif b" PRIVMSG #" in line:
                                message=line.rsplit(b" :",1)[-1].decode("utf-8","ignore").lower()
                                hype=bool(re.search(r"\b(pog|poggers|pogchamp|clip|clutch|insane|no way|wow|lmao|lol|wtf|gg)\b|[🔥😱😂💀]",message))
                                self.counts.append((time.time(),2.0 if hype else 1.0))
            except Exception: self.enabled=False
        self.thread=threading.Thread(target=listen,daemon=True); self.thread.start()
    def recent(self, seconds=2):
        cutoff=time.time()-seconds
        while self.counts and self.counts[0][0]<cutoff: self.counts.popleft()
        return sum(weight for _,weight in self.counts)
    def close(self): self.stop.set()

class MissingTitleKey(RuntimeError): pass

def run(cmd, timeout=3600):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode: raise RuntimeError((result.stderr or "FFmpeg failed")[-1200:])

def set_job(job_id, stage, progress, status="running", error=None):
    with db() as c: c.execute("UPDATE jobs SET stage=?,progress=?,status=?,error=?,updated_at=? WHERE id=?", (stage, progress, status, error, now(), job_id))

def canceled(job_id):
    with db() as c: row = c.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
    return not row or bool(row[0])

def _render_clip(job_id, project_id, source, moment, config, index, total):
    clip_id = str(uuid.uuid4()); folder = DATA_DIR / "clips" / project_id / clip_id; folder.mkdir(parents=True, exist_ok=True)
    work = DATA_DIR / "temp" / job_id; work.mkdir(parents=True, exist_ok=True)
    clip_seconds = max(1, float(moment["end"] - moment["start"]))
    v, l, thumb = folder / "vertical_9_16.mp4", folder / "landscape_16_9.mp4", folder / "thumbnail.jpg"
    captions = []
    input_clip = work / f"clip-{index}.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(moment["start"]), "-i", str(source), "-t", str(clip_seconds), "-c", "copy", "-avoid_negative_ts", "make_zero", str(input_clip)])
    srt = folder / "captions.srt"
    if config.get("generate_captions"):
        wav = work / f"audio-{index}.wav"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_clip), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        captions = transcribe(wav, DATA_DIR / "models" / "whisper")
        if captions: write_srt(captions, srt)
    clip_info=probe(input_clip)
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_clip)]
    for dest, vf in ((v,"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"),(l,"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080")):
        if dest==l and not captions and clip_info["video_codec"]=="h264" and clip_info["audio_codec"] in (None,"aac") and clip_info["height"] and abs(clip_info["width"]/clip_info["height"]-16/9)<0.04:
            run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(input_clip),"-map","0","-c","copy","-movflags","+faststart",str(dest)])
            continue
        filters = vf
        if captions:
            subpath = str(srt).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            filters += f",subtitles='{subpath}':force_style='FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2,MarginV=60'"
        run(base + ["-vf", filters, "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", str(dest)])
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(min(clip_seconds/2,3)), "-i", str(v), "-frames:v", "1", "-vf", "scale=360:-2", str(thumb)])
    title = moment.get("title", "") or f"Highlight at {int(moment['start']//60):02d}:{int(moment['start']%60):02d}"
    description = moment.get("description", "") or moment.get("explanation", "")
    metadata = {"id":clip_id,"project_id":project_id,"title":title,"description":description,"hashtags":moment.get("hashtags",[]),"start":moment["start"],"end":moment["end"],"score":moment["score"],"category":moment["category"],"explanation":moment.get("explanation",""),"evidence":moment.get("audio_evidence",{}),"chat_evidence":moment.get("chat_evidence"),"captions":captions,"caption_status":"Generated locally" if captions else ("No speech detected" if config.get("generate_captions") else "Disabled"),"smart_crop":"center crop"}
    (folder/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    with db() as c:
        c.execute("INSERT INTO clips(id,project_id,title,description,hashtags_json,start,end,score,category,caption_json,evidence_json,vertical_path,landscape_path,thumbnail_path,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (clip_id,project_id,title,description,json.dumps(moment.get("hashtags",[])),moment["start"],moment["end"],moment["score"],moment["category"],json.dumps(captions),json.dumps({"audio":moment.get("audio_evidence"),"chat":moment.get("chat_evidence")}),str(v),str(l),str(thumb),"complete",now(),now()))
    set_job(job_id, f"Rendered clip {index} of {total}", 55 + int(40*index/max(1,total)))

def _titles(job_id, config, moments, source, work):
    if not config.get("generate_titles"): return
    candidates=[]
    for i,m in enumerate(moments[:20]):
        frame=work/f"candidate-{i}.jpg"
        run(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss",str(m.get("timestamp",m["start"])),"-i",str(source),"-frames:v","1","-vf","scale=640:-2","-q:v","5",str(frame)])
        candidates.append({"timestamp":m.get("timestamp",m["start"]),"score":m["score"],"category":m["category"],"explanation":m.get("explanation",""),"frame":base64.b64encode(frame.read_bytes()).decode("ascii")})
    response=httpx.post(f"{API_INTERNAL_URL}/api/internal/jobs/{job_id}/analyze",json={"candidates":candidates,"model":config.get("model")},timeout=180)
    if response.status_code==428: raise MissingTitleKey("The API restarted and cleared its optional Gemini title key. Re-submit it to retry.")
    response.raise_for_status()
    for item in response.json().get("items",[]):
        i=int(item.get("index",-1))
        if 0<=i<len(moments): moments[i].update({k:item[k] for k in ("title","description","hashtags") if k in item})

def process_youtube_live(job, project):
    """Process a YouTube live stream: download last N minutes, then analyze like a VOD."""
    job_id, project_id = job["id"], job["project_id"]
    config = json.loads(job["config_json"])
    work = DATA_DIR / "temp" / job_id
    work.mkdir(parents=True, exist_ok=True)

    downloaded_file = None

    # Define progress_callback and cancel_check outside try so they're available in finally
    def progress_callback(percent, message):
        if canceled(job_id):
            raise RuntimeError("Cancelled")
        set_job(job_id, message, percent)

    def cancel_check():
        return canceled(job_id)

    try:
        # Step 1: Download YouTube live stream (0-30% progress)
        set_job(job_id, "Downloading stream", 5)

        downloaded_file = download_youtube_live(
            project["source_url"],
            DOWNLOAD_DIR,
            duration_minutes=YOUTUBE_LIVE_DOWNLOAD_DURATION_MINUTES,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

        if canceled(job_id):
            return set_job(job_id, "Canceled", 100, "canceled")

        source = downloaded_file

        # Step 2: Probe video (30-35%)
        set_job(job_id, "Probing video", 32)
        info = probe(source)
        duration = float(info["duration"])

        # Update project with actual duration and path
        with db() as c:
            c.execute("UPDATE projects SET source_path=?,duration=? WHERE id=?", (str(source), duration, project_id))

        if duration < 2:
            raise RuntimeError("Downloaded video must be at least two seconds long.")

        # Step 3: Audio analysis and moment ranking (35-55%)
        set_job(job_id, "Measuring audio and ranking moments", 38)
        levels = list(audio_levels(source))
        moments = rank_vod_moments(levels, duration, config)

        if not moments:
            set_job(job_id, "Complete · no clear hype spikes found", 100, "complete")
            return

        # Step 4: Optional AI titles
        _titles(job_id, config, moments, source, work)

        # Step 5: Render clips (55-95%)
        for i, m in enumerate(moments, 1):
            if canceled(job_id):
                return set_job(job_id, "Canceled", 100, "canceled")
            _render_clip(job_id, project_id, source, m, config, i, len(moments))

        # Step 6: Cleanup (95-100%)
        set_job(job_id, "Cleaning up", 97)

        set_job(job_id, "Complete", 100, "complete")

    except Exception as exc:
        if "Cancelled" in str(exc) or canceled(job_id):
            set_job(job_id, "Canceled", 100, "canceled")
        else:
            raise
    finally:
        # Always clean up the downloaded file
        if downloaded_file and downloaded_file.exists():
            try:
                downloaded_file.unlink()
                progress_callback(99, "Cleaned up download")
            except Exception:
                pass
        shutil.rmtree(work, ignore_errors=True)


def process_vod(job, project):
    job_id, project_id = job["id"],job["project_id"]; config=json.loads(job["config_json"])
    source=Path(project["source_path"] or "")
    work=DATA_DIR/"temp"/job_id; work.mkdir(parents=True,exist_ok=True)
    try:
        if project["source_type"]=="twitch_vod":
            url=project["source_url"]; source=DATA_DIR/"projects"/project_id/"source.ts"; source.parent.mkdir(parents=True,exist_ok=True)
            set_job(job_id,"Downloading Twitch VOD",5)
            with source.open("wb") as output:
                p=subprocess.run(["streamlink","--stdout",url,"best"],stdout=output,stderr=subprocess.PIPE,text=True,timeout=7200)
            if p.returncode: raise RuntimeError("Could not access Twitch VOD: "+(p.stderr or "Streamlink failed")[-800:])
        if not source.is_file(): raise RuntimeError("The source video is unavailable.")
        set_job(job_id,"Measuring audio and ranking moments",12)
        info=probe(source); duration=float(info["duration"])
        with db() as c: c.execute("UPDATE projects SET source_path=?,duration=? WHERE id=?",(str(source),duration,project_id))
        if duration<2: raise RuntimeError("Video must be at least two seconds long.")
        levels=list(audio_levels(source))
        moments=rank_vod_moments(levels,duration,config)
        if not moments:
            set_job(job_id,"Complete · no clear hype spikes found",100,"complete"); return
        _titles(job_id,config,moments,source,work)
        for i,m in enumerate(moments,1):
            if canceled(job_id): return set_job(job_id,"Canceled",100,"canceled")
            _render_clip(job_id,project_id,source,m,config,i,len(moments))
        set_job(job_id,"Complete",100,"complete")
    finally: shutil.rmtree(work,ignore_errors=True)

def process_live(job,project):
    job_id,project_id=job["id"],job["project_id"]; config=json.loads(job["config_json"]); src=twitch_source(project["source_url"])
    work=DATA_DIR/"temp"/job_id; segments=work/"buffer"; segments.mkdir(parents=True,exist_ok=True)
    stream=subprocess.Popen(["streamlink","--stdout",project["source_url"],"best"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    ff=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-i","pipe:0","-map","0","-c","copy","-f","segment","-segment_time","2","-reset_timestamps","1","-segment_format","mpegts",str(segments/"seg_%08d.ts")],stdin=stream.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if stream.stdout: stream.stdout.close()
    chat=TwitchChat(src["channel"]); detector=LiveHypeDetector(config.get("sensitivity","balanced"),chat.enabled,cooldown=max(45,int(config.get("duration",45)*.75)))
    files=[]; processed=0; pending=[]; made=0; sample=segments/"sample.wav"
    try:
        set_job(job_id,"Live · filling replay buffer",0)
        while not canceled(job_id) and ff.poll() is None:
            current=sorted(segments.glob("seg_*.ts"))
            if ff.poll() is None and current: current=current[:-1] # the muxer is still writing the newest segment
            while processed<len(current):
                path=current[processed]; idx=processed; processed+=1; files.append((idx,path))
                try:
                    levels=list(audio_levels(path)); dbfs=levels[0][1] if levels else -90
                    trigger=detector.observe(idx*2,dbfs,chat.recent(2))
                    if trigger: pending.append((idx,trigger)); set_job(job_id,f"Live · hype spike at {idx*2//60:02d}:{idx*2%60:02d}",0)
                except Exception: pass
                max_segments=int(os.getenv("LIVE_BUFFER_MINUTES","10"))*30
                while len(files)>max_segments:
                    old_i,old_path=files.pop(0)
                    if any(old_i>=trig_i-10 for trig_i,_ in pending): files.insert(0,(old_i,old_path)); break
                    old_path.unlink(missing_ok=True)
                for trig_i,trig in list(pending):
                    if idx>=trig_i+4 and made<int(config.get("count",5)):
                        chosen=[p for si,p in files if trig_i-10<=si<=trig_i+4]
                        if chosen:
                            concat=work/f"live-{made}.ts"; listing=work/f"concat-{made}.txt"
                            listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in chosen),encoding="utf-8")
                            run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(listing),"-c","copy",str(concat)])
                            live_start=max(0,(trig_i-10)*2)
                            moment={**trig,"start":0.0,"end":max(10,(len(chosen)*2)-1),"timestamp":max(0,trig_i*2-live_start),"title":f"Live highlight {made+1}"}
                            _titles(job_id,config,[moment],concat,work)
                            _render_clip(job_id,project_id,concat,moment,config,made+1,int(config.get("count",5))); made+=1
                        pending.remove((trig_i,trig))
                        if made>=int(config.get("count",5)):
                            ff.terminate(); stream.terminate(); break
            time.sleep(.5)
        if canceled(job_id): set_job(job_id,"Canceled",100,"canceled")
        elif made==0 and stream.returncode not in (0,None): raise RuntimeError("Streamlink could not open the Twitch channel. Check source access and try again.")
        elif made>=int(config.get("count",5)): set_job(job_id,"Complete · requested clips generated",100,"complete")
        else: set_job(job_id,"Complete · stream ended",100,"complete")
    finally:
        chat.close()
        for proc in (ff,stream):
            if proc.poll() is None: proc.terminate()
        shutil.rmtree(work,ignore_errors=True)

def process(job):
    job_id=job["id"]
    try:
        with db() as c: project=dict(c.execute("SELECT * FROM projects WHERE id=?",(job["project_id"],)).fetchone())
        config=json.loads(job["config_json"])

        source_type = project.get("source_type", "")

        if config.get("mode") == "live":
            process_live(job, project)
        elif source_type == "youtube_live":
            process_youtube_live(job, project)
        else:
            process_vod(job, project)
    except MissingTitleKey as exc: set_job(job_id,"Waiting for Gemini key",36,"waiting_for_key",str(exc)[:1800])
    except Exception as exc: set_job(job_id,"Failed",100,"failed",str(exc)[:1800])
    finally:
        try: httpx.post(f"{API_INTERNAL_URL}/api/internal/jobs/{job_id}/release",timeout=8)
        except Exception: pass

def main():
    print("Addy Clips worker started",flush=True)
    with db() as c:
        c.execute("UPDATE jobs SET status='failed',stage='Interrupted by worker restart',error='Live capture or processing was interrupted by a worker restart.',updated_at=? WHERE status='running'",(now(),))
    concurrency=max(1,min(4,int(os.getenv("WORKER_CONCURRENCY","1"))))
    with ThreadPoolExecutor(max_workers=concurrency,thread_name_prefix="addy-worker") as pool:
        active={}
        while True:
            active={job_id:future for job_id,future in active.items() if not future.done()}
            while len(active)<concurrency:
                with db() as c:
                    row=c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                    if not row: break
                    claimed=c.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=? AND status='queued'",(now(),row["id"]))
                    if not claimed.rowcount: continue
                    job=dict(row)
                active[job["id"]]=pool.submit(process,job)
            time.sleep(1 if active else 2)

if __name__=="__main__": main()
