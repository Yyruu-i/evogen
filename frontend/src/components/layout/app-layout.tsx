import { Outlet } from 'react-router-dom';
import { Sidebar } from './sidebar';
import { ArtifactPanel } from './artifact-panel';

export function AppLayout() {
  return (
    <div className="h-screen overflow-hidden relative" style={{ background: 'var(--color-bg-deep)' }}>
      <div className="flex h-full relative z-10">
        {/* ── Left: Sidebar ──────────────────────────────────── */}
        <Sidebar />

        {/* ── Center: Main content ───────────────────────────── */}
        <main
          className="flex-1 overflow-auto"
          style={{ scrollbarGutter: 'stable' }}
        >
          <Outlet />
        </main>

        {/* ── Right: Artifact Panel ──────────────────────────── */}
        <ArtifactPanel />
      </div>
    </div>
  );
}
