import type { LucideIcon } from "lucide-react";
import { ArrowDownToLine } from "lucide-react";

type StatCardProps = {
  icon: LucideIcon;
  label: string;
  value: string;
  helper: string;
  compact?: boolean;
};

export function StatCard({ icon: Icon, label, value, helper, compact = false }: StatCardProps) {
  return (
    <div className="stat-card">
      <span className="stat-icon"><Icon size={16} /></span>
      <div className="stat-meta">
        <span>{label}</span>
        <b className={compact ? "stat-word" : ""}>{value}</b>
        <small>{helper}</small>
      </div>
      <span className="stat-corner"><ArrowDownToLine size={13} /></span>
    </div>
  );
}
