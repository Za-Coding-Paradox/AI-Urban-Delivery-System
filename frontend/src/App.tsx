// src/App.tsx
// Application shell — mounts WebSocket, hosts layout, routes three main views.
// Left sidebar: profile controls + algorithm toggles + run button.
// Main area: one of [ GridView | GraphView | MetricsView ] depending on activeView.

import { useWebSocket } from "@/hooks/useWebSocket";
import { useConnected, useRunStatus, useActiveView, useStore, useInspectorOpen, useSelectedNode } from "@/store";
import type { ActiveView } from "@/types";
import { ProfilePanel }        from "@/components/controls/ProfilePanel";
import { GridView }            from "@/components/grid/GridView";
import { GraphView }           from "@/components/graph/GraphView";
import { MetricsView }         from "@/components/metrics/MetricsView";
import { PlaybackBar }         from "@/components/controls/PlaybackBar";
import { StatusBar }           from "@/components/shared/StatusBar";
import { NodeInspectorPanel }  from "@/components/inspector/NodeInspectorPanel";

export default function App() {
  useWebSocket();

  const connected     = useConnected();
  const runStatus     = useRunStatus();
  const activeView    = useActiveView();
  const setView       = useStore((s) => s.setActiveView);
  const inspectorOpen = useInspectorOpen();
  const selectedNode  = useSelectedNode();
  const setInspector  = useStore((s) => s.setInspectorOpen);
  const clearSelected = useStore((s) => s.clearSelected);

  return (
    <div
      style={{
        display:       "flex",
        flexDirection: "column",
        height:        "100vh",
        overflow:      "hidden",
        background:    "var(--bg-base)",
        fontFamily:    "var(--font-sans)",
      }}
    >
      {/* ── top navigation ─────────────────────────────────────────────── */}
      <header
        style={{
          display:        "flex",
          alignItems:     "center",
          height:         "48px",
          padding:        "0 20px",
          flexShrink:     0,
          background:     "var(--bg-surface)",
          borderBottom:   "1px solid var(--border-subtle)",
          gap:            "16px",
          zIndex:         100,
        }}
      >
        {/* Brand */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="9" stroke="var(--accent-teal)" strokeWidth="1.5"/>
            <circle cx="10" cy="10" r="4" fill="var(--accent-teal)" opacity="0.6"/>
            <line x1="10" y1="1" x2="10" y2="4" stroke="var(--accent-teal)" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="10" y1="16" x2="10" y2="19" stroke="var(--accent-teal)" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="1" y1="10" x2="4" y2="10" stroke="var(--accent-teal)" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="16" y1="10" x2="19" y2="10" stroke="var(--accent-teal)" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <span style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "13px", letterSpacing: "0.02em" }}>
            Positron
          </span>
          <span style={{ color: "var(--text-muted)", fontSize: "11px", fontWeight: 400 }}>
            Urban Delivery Simulator
          </span>
        </div>

        {/* View tabs */}
        <nav style={{ display: "flex", gap: "2px", marginLeft: "auto" }}>
          {(["grid", "graph", "metrics"] as ActiveView[]).map((view) => (
            <button
              key={view}
              onClick={() => setView(view)}
              style={{
                padding:       "5px 14px",
                borderRadius:  "6px",
                border:        "none",
                cursor:        "pointer",
                fontSize:      "12px",
                fontWeight:    activeView === view ? 500 : 400,
                background:    activeView === view ? "var(--bg-raised)" : "transparent",
                color:         activeView === view ? "var(--text-primary)" : "var(--text-secondary)",
                transition:    "all 120ms ease",
                letterSpacing: "0.01em",
              }}
            >
              {view === "grid" ? "2D Grid" : view === "graph" ? "3D Graph" : "Metrics"}
            </button>
          ))}
        </nav>

        {/* Inspector toggle button */}
        <button
          onClick={() => {
            if (inspectorOpen) {
              clearSelected();
            } else {
              setInspector(true);
            }
          }}
          title="Toggle node inspector"
          style={{
            padding:      "5px 10px",
            borderRadius: "6px",
            border:       `1px solid ${inspectorOpen ? "var(--accent-teal)" : "var(--border-default)"}`,
            background:   inspectorOpen ? "var(--accent-teal)18" : "transparent",
            color:        inspectorOpen ? "var(--accent-teal)" : "var(--text-secondary)",
            cursor:       "pointer",
            fontSize:     "11px",
            fontWeight:   inspectorOpen ? 600 : 400,
            display:      "flex",
            alignItems:   "center",
            gap:          "5px",
            transition:   "all 120ms",
          }}
        >
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <rect x="1" y="1" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.2"/>
            <line x1="4" y1="4.5" x2="9" y2="4.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
            <line x1="4" y1="6.5" x2="9" y2="6.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
            <line x1="4" y1="8.5" x2="7" y2="8.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
          </svg>
          Inspector
          {selectedNode && (
            <span style={{
              background: "var(--accent-teal)",
              color: "#fff",
              borderRadius: "8px",
              fontSize: "9px",
              padding: "1px 5px",
              fontWeight: 700,
            }}>
              {selectedNode.node.id}
            </span>
          )}
        </button>

        {/* Status indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <RunStatusChip status={runStatus} />
          <ConnectionDot connected={connected} />
        </div>
      </header>

      {/* ── workspace ──────────────────────────────────────────────────── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left sidebar — profile + algorithm controls */}
        <aside
          style={{
            width:        "260px",
            flexShrink:   0,
            background:   "var(--bg-surface)",
            borderRight:  "1px solid var(--border-subtle)",
            display:      "flex",
            flexDirection:"column",
            overflow:     "hidden",
          }}
        >
          <ProfilePanel />
        </aside>

        {/* Main content */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ flex: 1, overflow: "hidden", position: "relative", display: "flex" }}>
            <div style={{ flex: 1, overflow: "hidden" }}>
              {activeView === "grid"    && <GridView />}
              {activeView === "graph"   && <GraphView />}
              {activeView === "metrics" && <MetricsView />}
            </div>

            {/* Inspector panel — slides in from the right */}
            {inspectorOpen && <NodeInspectorPanel />}
          </div>

          {/* Playback bar — always visible at bottom */}
          <PlaybackBar />
        </div>
      </div>

      {/* Status bar — lowest tier */}
      <StatusBar />
    </div>
  );
}

// ── small inline status chips ────────────────────────────────────────────────

function RunStatusChip({ status }: { status: string }) {
  if (status === "idle") return null;
  const cfg: Record<string, { color: string; label: string }> = {
    running:  { color: "var(--accent-amber)", label: "● Running" },
    complete: { color: "var(--accent-green)", label: "✓ Complete" },
    failed:   { color: "var(--accent-red)",   label: "✗ Failed" },
    pending:  { color: "var(--text-muted)",   label: "○ Pending" },
  };
  const c = cfg[status] ?? cfg.pending;
  return (
    <span style={{ fontSize: "11px", color: c.color, fontWeight: 500 }}>
      {c.label}
    </span>
  );
}

function ConnectionDot({ connected }: { connected: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
      <div
        style={{
          width:        "6px",
          height:       "6px",
          borderRadius: "50%",
          background:   connected ? "var(--accent-green)" : "var(--accent-red)",
          boxShadow:    connected ? "0 0 6px var(--accent-green)" : "none",
          transition:   "all 300ms",
        }}
      />
      <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
        {connected ? "Live" : "Offline"}
      </span>
    </div>
  );
}
