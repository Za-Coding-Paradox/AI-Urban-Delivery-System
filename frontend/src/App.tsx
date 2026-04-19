// src/App.tsx
//
// Application shell. Responsibilities:
//   1. Mount the WebSocket hook (runs for the app's lifetime)
//   2. Provide the top-level layout frame
//   3. Route between the three main views (grid / graph / metrics)
//
// This file stays thin. All layout and logic lives in child components.

import { useWebSocket } from "@/hooks";
import { useConnected, useRunStatus, useActiveView, useStore } from "@/store";
import type { ActiveView } from "@/types";
import { ALGORITHM_SHORT } from "@/lib/constants";

export default function App() {
  // Mount the WebSocket connection for the app's lifetime
  useWebSocket();

  const connected    = useConnected();
  const runStatus    = useRunStatus();
  const activeView   = useActiveView();
  const setView      = useStore((s) => s.setActiveView);

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--bg-base)" }}>

      {/* ── top navigation bar ─────────────────────────────────────────── */}
      <header style={{
        background:   "var(--bg-surface)",
        borderBottom: "1px solid var(--border-subtle)",
        padding:      "0 var(--space-6)",
        height:       "48px",
        display:      "flex",
        alignItems:   "center",
        gap:          "var(--space-6)",
        flexShrink:   0,
      }}>
        {/* Brand */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <span style={{ fontSize: "16px" }}>🤖</span>
          <span style={{
            color:      "var(--text-primary)",
            fontWeight: 500,
            fontSize:   "14px",
            letterSpacing: "0.01em",
          }}>
            Urban Delivery Robot
          </span>
          <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
            AI Search Simulator
          </span>
        </div>

        {/* View switcher */}
        <nav style={{ display: "flex", gap: "var(--space-1)", marginLeft: "auto" }}>
          {(["grid", "graph", "metrics"] as ActiveView[]).map((view) => (
            <button
              key={view}
              onClick={() => setView(view)}
              style={{
                padding:      "4px 12px",
                borderRadius: "var(--radius-md)",
                border:       "none",
                cursor:       "pointer",
                fontSize:     "13px",
                fontWeight:   activeView === view ? 500 : 400,
                background:   activeView === view ? "var(--bg-raised)" : "transparent",
                color:        activeView === view ? "var(--text-primary)" : "var(--text-secondary)",
                transition:   "all var(--duration-fast)",
              }}
            >
              {view === "grid" ? "2D Grid" : view === "graph" ? "3D Graph" : "Metrics"}
            </button>
          ))}
        </nav>

        {/* Status indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
          {/* Run status */}
          {runStatus !== "idle" && (
            <span style={{
              fontSize: "11px",
              color: runStatus === "complete" ? "var(--accent-green)"
                   : runStatus === "failed"   ? "var(--accent-red)"
                   : "var(--accent-amber)",
            }}>
              {runStatus === "running" ? "● Running" :
               runStatus === "complete" ? "✓ Complete" :
               runStatus === "failed"   ? "✗ Failed" : ""}
            </span>
          )}

          {/* WebSocket connection dot */}
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }}>
            <div style={{
              width:        "6px",
              height:       "6px",
              borderRadius: "50%",
              background:   connected ? "var(--accent-green)" : "var(--accent-red)",
            }} />
            <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
              {connected ? "Live" : "Offline"}
            </span>
          </div>
        </div>
      </header>

      {/* ── main content area ───────────────────────────────────────────── */}
      <main style={{ flex: 1, overflow: "hidden", display: "flex" }}>

        {/* Placeholder content — components get built in the next phase */}
        <div style={{
          flex:           1,
          display:        "flex",
          alignItems:     "center",
          justifyContent: "center",
          flexDirection:  "column",
          gap:            "var(--space-4)",
          color:          "var(--text-muted)",
        }}>
          <div style={{ fontSize: "48px" }}>
            {activeView === "grid" ? "⬛" : activeView === "graph" ? "🕸️" : "📊"}
          </div>
          <div style={{ fontSize: "14px" }}>
            {activeView === "grid"    ? "2D Grid Viewer"    :
             activeView === "graph"   ? "3D Node Graph"     :
                                        "Metrics Dashboard"}
          </div>
          <div style={{ fontSize: "12px" }}>
            Components build next →
          </div>

          {/* Connection state feedback */}
          {!connected && (
            <div style={{
              marginTop:    "var(--space-4)",
              padding:      "var(--space-3) var(--space-4)",
              borderRadius: "var(--radius-lg)",
              background:   "var(--bg-raised)",
              border:       "1px solid var(--border-default)",
              fontSize:     "12px",
              color:        "var(--accent-amber)",
            }}>
              ⚠ Backend not connected — start the FastAPI server on port 8000
            </div>
          )}
        </div>

      </main>
    </div>
  );
}
