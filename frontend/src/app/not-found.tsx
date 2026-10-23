import Link from "next/link";
import { Button } from "@/components/ui/button";
export default function NotFound() {
  return (
    <div className="empty-state">
      <h1>Page not found</h1>
      <p>This page may not exist, or you may not have access.</p>
      <Button asChild>
        <Link href="/app">Back to your workspace</Link>
      </Button>
    </div>
  );
}
