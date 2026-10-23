import { Workflow } from "lucide-react";
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand">
      <span className="brand-mark">
        <Workflow size={23} strokeWidth={2.3} />
      </span>
      {!compact && (
        <span>
          FlowForge <span className="brand-ai">AI</span>
        </span>
      )}
    </span>
  );
}
