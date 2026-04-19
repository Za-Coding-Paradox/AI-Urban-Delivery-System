// src/components/shared/StatusBar.tsx
// Thin bottom status bar showing connection state, event buffer size, seed info.

import { useStore, useConnected, useRunStatus } from "@/store";
import { useEvents } from "@/store";

export function StatusBar() {
  const connected  = useConnected();
  const runStatus  = useRunStatus();
  const events     = useEvents();
  const profile    = useStore((s) => s.profile);

  return (
    <div
      style={{
        display:       "flex",
        alignItems:    "center",
        gap:           "16px",
        height:        "22px",
        padding:       "0 14px",
        background:    "var(--bg-surface)",
        borderTop:     "1px solid var(--border-subtle)",
        fontSize:      "10px",
        color:         "var(--text-muted)",
        flexShrink:    0,
      }}
    >
      {/* WS status */}
      <span style={{ color: connected ? "var(--accent-green)" : "var(--accent-red)" }}>
        {connected ? "● WebSocket connected" : "● WebSocket disconnected"}
      </span>

      <Divider />

      {/* Run status */}
      <span>
        Run: <span style={{ color: "var(--text-secondary)" }}>{runStatus}</span>
      </span>

      {/* Seed */}
      {profile && (
        <>
          <Divider />
          <span>
            Seed: <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{profile.meta.seed}</span>
          </span>
          <span>
            Profile: <span style={{ color: "var(--text-secondary)" }}>{profile.meta.name}</span>
          </span>
        </>
      )}

      {/* Event buffer */}
      <Divider />
      <span>
        Events: <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{events.length}</span>
      </span>

      {/* Version / brand */}
      <span style={{ marginLeft: "auto", opacity: 0.5 }}>
        Positron v0.1 · 15×15 grid
      </span>
    </div>
  );
}

function Divider() {
  return (
    <span style={{ color: "var(--border-default)", userSelect: "none" }}>|</span>
  );
}
