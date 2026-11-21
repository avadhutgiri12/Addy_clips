import { Film, MoreHorizontal, Radio } from "lucide-react";

export type Job = {
  id: string;
  source: string;
  source_type: string;
  status: string;
  created_at: string;
  title?: string;
  clips: number;
  progress: number;
  message?: string;
};

export function JobCard({ job }: { job: Job }) {
  const live = job.status === "watching";
  const done = job.status === "completed";

  return (
    <article className="job-card">
      <div className={`job-thumb ${live ? "live-thumb" : ""}`}>
        {live ? <Radio size={18} /> : <Film size={18} />}
        <span className={live ? "thumb-live-label" : "thumb-duration"}>{live ? "LIVE" : "MP4"}</span>
      </div>
      <div className="job-info">
        <b title={job.source}>{job.source}</b>
        <span>{job.created_at}</span>
        <div className={`job-status ${live ? "status-live" : done ? "status-done" : "status-queued"}`}>
          <i />{live ? "Monitoring live chat" : done ? `${job.clips} clips ready` : job.status}
        </div>
      </div>
      <button className="job-more" aria-label={`Options for ${job.source}`}><MoreHorizontal size={17} /></button>
    </article>
  );
}
