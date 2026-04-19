// src/components/controls/ProfilePanel.tsx
// Left sidebar: seed input, profile selector, algorithm toggles, run button.
// Wires directly to useSimulation() hook and store.

import { useState, useEffect } from "react";
import { useSimulation }       from "@/hooks/useSimulation";
import {
  useStore, useProfile, useRunStatus, useAlgorithmStates,
} from "@/store";
import { ALGORITHM_IDS, ALGORITHM_LABELS, ALGORITHM_COLOR, ALGORITHM_OPTIMAL } from "@/lib/constants";
import type { AlgorithmId } from "@/types";

export function ProfilePanel() {
  const { generateProfile, startRun, resetRun, saveProfile, listProfiles, loading, error } = useSimulation();
  const profile        = useProfile();
  const runStatus      = useRunStatus();
  const algorithmStates = useAlgorithmStates();
  const store          = useStore();

  const [seed, setSeed]             = useState(42);
  const [profileName, setProfileName] = useState("");
  const [enabledAlgos, setEnabledAlgos] = useState<Set<AlgorithmId>>(
    new Set(ALGORITHM_IDS)
  );
  const [savedProfiles, setSavedProfiles] = useState<string[]>([]);
  const [saveStatus, setSaveStatus]       = useState<"idle" | "saving" | "saved" | "error">("idle");

  const isRunning = runStatus === "running" || runStatus === "pending";

  // Load saved profiles list via useSimulation (not raw fetch)
  useEffect(() => {
    listProfiles().then((profiles) => setSavedProfiles(profiles));
  }, [listProfiles]);

  function toggleAlgo(id: AlgorithmId) {
    setEnabledAlgos((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleGenerate() {
    await generateProfile(seed, profileName || undefined);
  }

  async function handleLoadProfile(name: string) {
    const loaded = await fetch(`/api/profiles/${name}`)
      .then((r) => r.json())
      .then((d) => d.profile)
      .catch(() => null);
    if (loaded) store.setProfile(loaded);
  }

  async function handleSaveProfile() {
    if (!profile) return;
    const name = profileName.trim() || profile.meta.name || profile.meta.id;
    setSaveStatus("saving");
    const ok = await saveProfile(name, profile);
    if (ok) {
      setSaveStatus("saved");
      // Refresh the saved-profiles dropdown
      listProfiles().then((profiles) => setSavedProfiles(profiles));
      setTimeout(() => setSaveStatus("idle"), 2000);
    } else {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  }

  async function handleRun() {
    if (!profile) return;
    // inject enabled state into profile algorithms
    const patched = {
      ...profile,
      algorithms: profile.algorithms.map((a) => ({
        ...a,
        enabled: enabledAlgos.has(a.id as AlgorithmId),
      })),
    };
    await startRun({ profile: patched as any });
  }

  function handleReset() {
    resetRun();
  }

  return (
    <div
      style={{
        display:       "flex",
        flexDirection: "column",
        height:        "100%",
        overflow:      "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding:      "14px 16px 10px",
          borderBottom: "1px solid var(--border-subtle)",
          flexShrink:   0,
        }}
      >
        <div style={{ color: "var(--text-primary)", fontSize: "12px", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
          Simulation Setup
        </div>
      </div>

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>

        {/* ── Profile generation ───────────────────────────── */}
        <Section label="City Profile">
          <Label>Seed</Label>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              style={inputStyle}
            />
            <button onClick={handleGenerate} disabled={loading} style={secondaryBtnStyle}>
              Generate
            </button>
          </div>

          <Label>Name (optional)</Label>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <input
              type="text"
              placeholder="my_city"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              style={inputStyle}
            />
            <button
              onClick={handleSaveProfile}
              disabled={!profile || saveStatus === "saving"}
              title="Save current profile to disk"
              style={{
                ...secondaryBtnStyle,
                width:      "auto",
                padding:    "6px 10px",
                flexShrink: 0,
                color:
                  saveStatus === "saved" ? "var(--accent-teal)"
                  : saveStatus === "error" ? "var(--accent-red)"
                  : "var(--text-secondary)",
                borderColor:
                  saveStatus === "saved" ? "var(--accent-teal)"
                  : saveStatus === "error" ? "var(--accent-red)"
                  : "var(--border-default)",
              }}
            >
              {saveStatus === "saving" ? "…"
               : saveStatus === "saved"  ? "✓"
               : saveStatus === "error"  ? "✗"
               : "Save"}
            </button>
          </div>

          {savedProfiles.length > 0 && (
            <>
              <Label>Load saved</Label>
              <select
                onChange={(e) => e.target.value && handleLoadProfile(e.target.value)}
                style={inputStyle}
                defaultValue=""
              >
                <option value="" disabled>Select profile…</option>
                {savedProfiles.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </>
          )}

          {profile && (
            <div
              style={{
                marginTop:    "8px",
                padding:      "8px 10px",
                borderRadius: "6px",
                background:   "var(--bg-raised)",
                border:       "1px solid var(--border-default)",
              }}
            >
              <ProfileInfo profile={profile} />
            </div>
          )}
        </Section>

        {/* ── Algorithm toggles ────────────────────────────── */}
        <Section label="Algorithms">
          {ALGORITHM_IDS.map((id) => {
            const enabled  = enabledAlgos.has(id);
            const algState = algorithmStates[id];
            const running  = algState.status === "running";
            const done     = algState.status === "complete";
            return (
              <div
                key={id}
                style={{
                  display:       "flex",
                  alignItems:    "center",
                  gap:           "8px",
                  padding:       "7px 10px",
                  borderRadius:  "6px",
                  marginBottom:  "4px",
                  background:    enabled ? "var(--bg-raised)" : "transparent",
                  border:        `1px solid ${enabled ? "var(--border-default)" : "transparent"}`,
                  cursor:        "pointer",
                  transition:    "all 120ms",
                }}
                onClick={() => !isRunning && toggleAlgo(id)}
              >
                {/* Color dot */}
                <div
                  style={{
                    width:        "8px",
                    height:       "8px",
                    borderRadius: "50%",
                    flexShrink:   0,
                    background:   enabled ? ALGORITHM_COLOR[id] : "var(--text-muted)",
                    boxShadow:    enabled ? `0 0 6px ${ALGORITHM_COLOR[id]}60` : "none",
                    transition:   "all 200ms",
                  }}
                />

                {/* Label */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "12px", fontWeight: 500, color: enabled ? "var(--text-primary)" : "var(--text-muted)" }}>
                    {ALGORITHM_LABELS[id]}
                  </div>
                  <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>
                    {ALGORITHM_OPTIMAL[id] ? "cost-optimal" : "not optimal"}
                  </div>
                </div>

                {/* Status pill */}
                {running && <Pill color="#ef9f27">running</Pill>}
                {done    && algState.path_found === true  && <Pill color="var(--accent-green)">✓</Pill>}
                {done    && algState.path_found === false && <Pill color="var(--accent-red)">✗</Pill>}

                {/* Toggle checkbox visual */}
                <div
                  style={{
                    width:        "14px",
                    height:       "14px",
                    borderRadius: "3px",
                    border:       `1px solid ${enabled ? ALGORITHM_COLOR[id] : "var(--border-strong)"}`,
                    background:   enabled ? ALGORITHM_COLOR[id] + "30" : "transparent",
                    display:      "flex",
                    alignItems:   "center",
                    justifyContent: "center",
                    flexShrink:   0,
                  }}
                >
                  {enabled && (
                    <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                      <path d="M1 4L3 6L7 2" stroke={ALGORITHM_COLOR[id]} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>
              </div>
            );
          })}
        </Section>

        {/* ── Deliveries preview ───────────────────────────── */}
        {profile && (
          <Section label="Deliveries">
            {profile.deliveries.destinations.map((d) => (
              <div
                key={d.id}
                style={{
                  display:      "flex",
                  alignItems:   "center",
                  gap:          "8px",
                  padding:      "5px 0",
                  borderBottom: "1px solid var(--border-subtle)",
                  fontSize:     "11px",
                }}
              >
                <span
                  style={{
                    width:        "18px",
                    height:       "18px",
                    borderRadius: "4px",
                    background:   "var(--accent-amber)20",
                    border:       "1px solid var(--accent-amber)40",
                    color:        "var(--accent-amber)",
                    display:      "flex",
                    alignItems:   "center",
                    justifyContent: "center",
                    fontSize:     "9px",
                    fontWeight:   700,
                    flexShrink:   0,
                  }}
                >
                  {d.id}
                </span>
                <span style={{ color: "var(--text-secondary)" }}>{d.label}</span>
                <span style={{ marginLeft: "auto", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  ({d.x},{d.y})
                </span>
              </div>
            ))}
          </Section>
        )}

        {/* Error */}
        {error && (
          <div
            style={{
              padding:      "8px 10px",
              borderRadius: "6px",
              background:   "var(--accent-red)15",
              border:       "1px solid var(--accent-red)30",
              color:        "var(--accent-red)",
              fontSize:     "11px",
              marginTop:    "8px",
            }}
          >
            {error}
          </div>
        )}
      </div>

      {/* ── Run / Reset buttons ───────────────────────────── */}
      <div
        style={{
          padding:      "12px 16px",
          borderTop:    "1px solid var(--border-subtle)",
          display:      "flex",
          flexDirection:"column",
          gap:          "6px",
          flexShrink:   0,
        }}
      >
        <button
          onClick={handleRun}
          disabled={!profile || isRunning || enabledAlgos.size === 0}
          style={runBtnStyle(!profile || isRunning || enabledAlgos.size === 0)}
        >
          {isRunning ? (
            <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <Spinner /> Running…
            </span>
          ) : "▶  Start Simulation"}
        </button>

        {runStatus !== "idle" && (
          <button onClick={handleReset} style={secondaryBtnStyle}>
            Reset
          </button>
        )}
      </div>
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "18px" }}>
      <div
        style={{
          fontSize:      "10px",
          fontWeight:    600,
          color:         "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          marginBottom:  "8px",
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginBottom: "4px" }}>
      {children}
    </div>
  );
}

function Pill({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize:     "9px",
        fontWeight:   600,
        color,
        background:   color + "20",
        border:       `1px solid ${color}40`,
        borderRadius: "3px",
        padding:      "1px 5px",
        letterSpacing:"0.04em",
        textTransform:"uppercase",
      }}
    >
      {children}
    </span>
  );
}

function Spinner() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      style={{ animation: "spin 1s linear infinite" }}
    >
      <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="20 8" strokeLinecap="round"/>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </svg>
  );
}

function ProfileInfo({ profile }: { profile: any }) {
  const obstacles = profile.grid.cells.filter((c: any) => c.type === "obstacle").length;
  const traffic   = profile.grid.cells.filter((c: any) => c.type === "traffic_zone").length;
  return (
    <div style={{ fontSize: "10px", color: "var(--text-secondary)", lineHeight: "1.8" }}>
      <div><span style={{ color: "var(--text-muted)" }}>Seed: </span><span style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>{profile.meta.seed}</span></div>
      <div><span style={{ color: "var(--text-muted)" }}>Grid: </span>15 × 15</div>
      <div><span style={{ color: "var(--text-muted)" }}>Obstacles: </span>{obstacles} cells</div>
      <div><span style={{ color: "var(--text-muted)" }}>Traffic zones: </span>{traffic} cells</div>
      <div>
        <span style={{ color: "var(--text-muted)" }}>Start: </span>
        <span style={{ fontFamily: "var(--font-mono)" }}>({profile.robot.start.x},{profile.robot.start.y})</span>
      </div>
    </div>
  );
}

// ── styles ────────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width:           "100%",
  padding:         "6px 9px",
  background:      "var(--bg-raised)",
  border:          "1px solid var(--border-default)",
  borderRadius:    "5px",
  color:           "var(--text-primary)",
  fontSize:        "12px",
  outline:         "none",
  boxSizing:       "border-box",
  fontFamily:      "var(--font-sans)",
};

const secondaryBtnStyle: React.CSSProperties = {
  width:        "100%",
  padding:      "7px 0",
  borderRadius: "6px",
  border:       "1px solid var(--border-default)",
  background:   "var(--bg-raised)",
  color:        "var(--text-secondary)",
  fontSize:     "12px",
  cursor:       "pointer",
  fontWeight:   500,
  transition:   "all 120ms",
};

const runBtnStyle = (disabled: boolean): React.CSSProperties => ({
  width:        "100%",
  padding:      "9px 0",
  borderRadius: "6px",
  border:       "none",
  background:   disabled ? "var(--bg-raised)" : "var(--accent-teal)",
  color:        disabled ? "var(--text-muted)" : "#fff",
  fontSize:     "13px",
  fontWeight:   600,
  cursor:       disabled ? "not-allowed" : "pointer",
  transition:   "all 120ms",
  display:      "flex",
  alignItems:   "center",
  justifyContent:"center",
  gap:          "6px",
  letterSpacing:"0.01em",
});
