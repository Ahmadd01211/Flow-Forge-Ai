import type { ReactNode } from "react";
import { AlertCircle, ArrowUpRight, Check, CircleDashed } from "lucide-react";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "purple" | "green" | "amber";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function ErrorNotice({ message }: { message: string }) {
  return (
    <div role="alert" className="error-notice">
      <AlertCircle size={17} />
      <span>{message}</span>
    </div>
  );
}
export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function ChecklistItem({
  done,
  title,
  description,
  action,
}: {
  done: boolean;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="checklist-item">
      <span className={done ? "step-icon complete" : "step-icon"}>
        {done ? <Check size={17} /> : <CircleDashed size={18} />}
      </span>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {action || <ArrowUpRight size={17} className="muted" />}
    </div>
  );
}
