// src/components/shared/StatusBar.tsx
// Thin bottom status bar showing connection state, event buffer size, seed info,
// and the active run's algorithm + delivery context.

import { useStore, useConnected, useRunStatus, useActiveAlgorithm, useActiveDelivery } from "@/store";
import { useEvents } from "@/store";
import { ALGORITHM_SHORT, ALGORITHM_COLOR } from "@/lib/constants";

export function StatusBar() {
  const connected      = useConnected();
  const runStatus      = useRunStatus();
  const events         = useEvents();
  const profile        = useStore((s) => s.profile);
  const runId          = useStore((s) => s.runId);
  const activeAlgo     = useActiveAlgorithm();
  const activeDelivery = useActiveDelivery();

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

      {/* Active run ID (truncated) */}
      {runId && runStatus !== "idle" && (
        <>
          <Divider />
          <span title={runId}>
            ID:{" "}
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
              {runId.slice(0, 8)}…
            </span>
          </span>
        </>
      )}

      {/* Active (algo : delivery) context */}
      {runStatus !== "idle" && (
        <>
          <Divider />
          <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <span
              style={{
                display:      "inline-block",
                width:        "6px",
                height:       "6px",
                borderRadius: "50%",
                background:   ALGORITHM_COLOR[activeAlgo],
                flexShrink:   0,
              }}
            />
            <span style={{ color: ALGORITHM_COLOR[activeAlgo], fontWeight: 600 }}>
              {ALGORITHM_SHORT[activeAlgo]}
            </span>
            <span style={{ color: "var(--border-strong)" }}>·</span>
            <span style={{ color: "var(--accent-amber)", fontWeight: 600 }}>{activeDelivery}</span>
          </span>
        </>
      )}

      {/* Seed + profile */}
      {profile && (
        <>
          <Divider />
          <span>
            Seed:{" "}
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
              {profile.meta.seed}
            </span>
          </span>
          <span>
            Profile: <span style={{ color: "var(--text-secondary)" }}>{profile.meta.name}</span>
          </span>
        </>
      )}

      {/* Event buffer */}
      <Divider />
      <span>
        Events:{" "}
        <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
          {events.length}
        </span>
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


