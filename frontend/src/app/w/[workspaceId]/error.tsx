"use client";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <AlertTriangle />
      </div>
      <h2>We couldn’t load this workspace</h2>
      <p>
        Your saved drafts are still in the database. Check the connection and
        retry.
      </p>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
