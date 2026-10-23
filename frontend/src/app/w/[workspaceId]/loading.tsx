export default function Loading() {
  return (
    <div
      role="status"
      aria-label="Loading workspace"
      className="loading-content"
    >
      <div className="skeleton skeleton-title" />
      <div className="metric-grid">
        {[1, 2, 3].map((n) => (
          <div className="skeleton skeleton-card" key={n} />
        ))}
      </div>
      <div className="skeleton skeleton-panel" />
      <span className="sr-only">Loading workspace…</span>
    </div>
  );
}
