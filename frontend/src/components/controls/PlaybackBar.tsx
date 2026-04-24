// src/components/controls/PlaybackBar.tsx
// Playback timeline bar — scrubs through the event buffer.
// Auto-advances with useInterval at PLAYBACK_STEP_MS / speed cadence.
//
// The scrub range and counter reflect the active (algo:delivery) segment so
// users see progress for the pair they're currently watching, not the full
// interleaved event buffer. The underlying cursor stays in flat-event space
// (matching what GridView's segmentCursor derivation expects).

import { useEffect, useRef, useMemo } from "react";
import { usePlayback, useStore, useRunStatus, useActiveAlgorithm, useActiveDelivery } from "@/store";
import { PLAYBACK_STEP_MS } from "@/lib/constants";

export function PlaybackBar() {
  const playback    = usePlayback();
  const runStatus   = useRunStatus();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // useStore (the Zustand store function) has .getState() for imperative reads in callbacks.
  // Individual actions are pulled via the hook so they are stable references.
  const setPlaying   = useStore((s) => s.setPlaybackPlaying);
  const setSpeed     = useStore((s) => s.setPlaybackSpeed);
  const setCursor    = useStore((s) => s.setPlaybackCursor);
  const stepForward  = useStore((s) => s.stepForward);
  const stepBack     = useStore((s) => s.stepBack);

  const activeAlgo     = useActiveAlgorithm();
  const activeDelivery = useActiveDelivery();

  // Flat event array — needed to compute segment-local progress
  const flatEvents = useStore((s) => s.events);
  const segmentKey = `${activeAlgo}:${activeDelivery}`;

  // Build a lookup array: segmentFlatIndices[n] = flat index of the n-th segment event.
  // This is the single source of truth for translating between segment space and flat space.
  const segmentFlatIndices = useMemo(() => {
    const indices: number[] = [];
    for (let i = 0; i < flatEvents.length; i++) {
      const ev = flatEvents[i] as any;
      if (
        ev &&
        typeof ev.algorithm_id === "string" &&
        typeof ev.delivery_id  === "string" &&
        `${ev.algorithm_id}:${ev.delivery_id}` === segmentKey
      ) indices.push(i);
    }
    return indices;
  }, [flatEvents, segmentKey]);

  const segmentTotal = segmentFlatIndices.length;

  // How many segment events have been consumed up to the current flat cursor.
  // Binary-search the indices array for efficiency.
  const segmentCursor = useMemo(() => {
    let lo = 0, hi = segmentFlatIndices.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (segmentFlatIndices[mid] <= playback.cursor) lo = mid + 1;
      else hi = mid;
    }
    return lo; // number of segment events at or before playback.cursor
  }, [segmentFlatIndices, playback.cursor]);

  const { cursor, total, playing, speed } = playback;

  // Auto-advance timer — reads live state via store.getState() on every tick.
  // Only recreates when playing or speed changes — no stale closure on total.
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!playing) return;

    const delay = PLAYBACK_STEP_MS / speed;
    intervalRef.current = setInterval(() => {
      const { playback: pb } = useStore.getState();
      if (pb.total === 0) return;
      if (!pb.playing) { clearInterval(intervalRef.current!); return; }
      if (pb.cursor >= pb.total - 1) {
        useStore.getState().setPlaybackPlaying(false);
        if (intervalRef.current) clearInterval(intervalRef.current);
      } else {
        useStore.getState().stepForward();
      }
    }, delay);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [playing, speed]);

  // Don't render when no events
  if (total === 0 && runStatus === "idle") return null;

  // Segment-scoped progress percentage for the visual fill
  const pct = segmentTotal > 1 ? (segmentCursor / segmentTotal) * 100 : 0;

  return (
    <div
      style={{
        display:      "flex",
        alignItems:   "center",
        gap:          "10px",
        padding:      "8px 16px",
        borderTop:    "1px solid var(--border-subtle)",
        background:   "var(--bg-surface)",
        flexShrink:   0,
        height:       "46px",
      }}
    >
      {/* Play / Pause */}
      <button
        onClick={() => setPlaying(!playing)}
        disabled={total === 0}
        style={iconBtnStyle}
        title={playing ? "Pause" : "Play"}
      >
        {playing ? (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <rect x="2" y="2" width="3" height="8" rx="1" fill="currentColor"/>
            <rect x="7" y="2" width="3" height="8" rx="1" fill="currentColor"/>
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 2L10 6L3 10V2Z" fill="currentColor"/>
          </svg>
        )}
      </button>

      {/* Step back */}
      <button onClick={() => stepBack()} disabled={cursor === 0} style={iconBtnStyle} title="Step back">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M9 2L3 6L9 10V2Z" fill="currentColor"/>
          <rect x="1" y="2" width="2" height="8" rx="1" fill="currentColor"/>
        </svg>
      </button>

      {/* Step forward */}
      <button onClick={() => stepForward()} disabled={cursor >= total - 1} style={iconBtnStyle} title="Step forward">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M3 2L9 6L3 10V2Z" fill="currentColor"/>
          <rect x="9" y="2" width="2" height="8" rx="1" fill="currentColor"/>
        </svg>
      </button>

      {/* Scrub slider — range covers the full flat buffer but fill reflects segment */}
      <div style={{ flex: 1, position: "relative", height: "4px" }}>
        {/* Track */}
        <div
          style={{
            position:     "absolute",
            inset:        0,
            background:   "var(--bg-raised)",
            borderRadius: "2px",
          }}
        />
        {/* Segment fill */}
        <div
          style={{
            position:     "absolute",
            left:         0,
            top:          0,
            bottom:       0,
            width:        `${pct}%`,
            background:   "var(--accent-teal)",
            borderRadius: "2px",
            transition:   playing ? "width 80ms linear" : "none",
          }}
        />
        {/* Input — operates in segment space so thumb position matches fill */}
        <input
          type="range"
          min={0}
          max={Math.max(segmentTotal - 1, 1)}
          value={segmentCursor}
          onChange={(e) => {
            setPlaying(false);
            const segIdx = Number(e.target.value);
            // Translate segment position to flat index.
            // segIdx 0 means before any segment event, so flat cursor stays 0.
            // Otherwise jump to the flat index of the (segIdx-1)th segment event.
            const flatIdx = segIdx === 0 ? 0 : (segmentFlatIndices[segIdx - 1] ?? 0);
            setCursor(flatIdx);
          }}
          style={{
            position:   "absolute",
            inset:      "-8px 0",
            width:      "100%",
            opacity:    0,
            cursor:     "pointer",
            height:     "20px",
          }}
        />
      </div>

      {/* Counter — segment-scoped */}
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize:   "10px",
          color:      "var(--text-muted)",
          minWidth:   "80px",
          textAlign:  "right",
        }}
      >
        {segmentCursor} / {segmentTotal}
        {total !== segmentTotal && (
          <span style={{ opacity: 0.45 }}> ({total})</span>
        )}
      </span>

      {/* Speed selector */}
      <div style={{ display: "flex", gap: "2px" }}>
        {[0.5, 1, 2, 5].map((s) => (
          <button
            key={s}
            onClick={() => setSpeed(s as any)}
            style={{
              padding:      "2px 6px",
              borderRadius: "3px",
              border:       `1px solid ${speed === s ? "var(--accent-teal)" : "var(--border-default)"}`,
              background:   speed === s ? "var(--accent-teal)20" : "transparent",
              color:        speed === s ? "var(--accent-teal)" : "var(--text-muted)",
              fontSize:     "10px",
              cursor:       "pointer",
            }}
          >
            {s}×
          </button>
        ))}
      </div>

      {/* Run status dot */}
      {runStatus === "running" && (
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <div
            style={{
              width:        "6px",
              height:       "6px",
              borderRadius: "50%",
              background:   "var(--accent-amber)",
              animation:    "pulse 1s ease-in-out infinite",
            }}
          />
          <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}`}</style>
          <span style={{ fontSize: "10px", color: "var(--accent-amber)" }}>Live</span>
        </div>
      )}
    </div>
  );
}

const iconBtnStyle: React.CSSProperties = {
  width:        "26px",
  height:       "26px",
  borderRadius: "5px",
  border:       "1px solid var(--border-default)",
  background:   "var(--bg-raised)",
  color:        "var(--text-secondary)",
  cursor:       "pointer",
  display:      "flex",
  alignItems:   "center",
  justifyContent:"center",
  flexShrink:   0,
  transition:   "all 120ms",
};
