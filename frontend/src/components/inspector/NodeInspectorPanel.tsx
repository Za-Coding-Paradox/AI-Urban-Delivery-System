// src/components/inspector/NodeInspectorPanel.tsx
// Right-side drawer showing full TraceGraphNode details:
// identity, g/h/f values, cell data, ancestry chain, adjacent nodes, edge history, raw JSON.

import { useState } from "react";
import { useStore } from "@/store";
import { ALGORITHM_LABELS, ALGORITHM_COLOR } from "@/lib/constants";
import { formatCost, formatTime } from "@/lib/utils";

export function NodeInspectorPanel() {
  const selectedNode  = useStore((s) => s.selectedNode);
  const clearSelected = useStore((s) => s.clearSelected);
  const setInspector  = useStore((s) => s.setInspectorOpen);
  const [activeTab, setActiveTab] = useState<"info" | "history" | "raw">("info");

  const handleClose = () => {
    clearSelected();
    setInspector(false);
  };

  return (
    <div
      style={{
        width:         "300px",
        flexShrink:    0,
        background:    "var(--bg-surface)",
        borderLeft:    "1px solid var(--border-subtle)",
        display:       "flex",
        flexDirection: "column",
        overflow:      "hidden",
        animation:     "slideInRight 150ms ease",
      }}
    >
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(16px); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>

      {/* Header */}
      <div
        style={{
          padding:      "12px 14px 8px",
          borderBottom: "1px solid var(--border-subtle)",
          flexShrink:   0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "6px" }}>
          <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Node Inspector
          </span>
          <button
            onClick={handleClose}
            style={{
              background: "none", border: "none", color: "var(--text-muted)",
              cursor: "pointer", fontSize: "16px", lineHeight: 1, padding: "0 2px",
            }}
          >
            ×
          </button>
        </div>

        {selectedNode ? (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                {selectedNode.node.id}
              </div>
              <StatusBadge status={selectedNode.node.status} />
            </div>
            <div style={{ fontSize: "10px", color: ALGORITHM_COLOR[selectedNode.algorithm_id], marginTop: "2px" }}>
              {ALGORITHM_LABELS[selectedNode.algorithm_id]} · {selectedNode.delivery_id}
            </div>
          </>
        ) : (
          <div style={{ fontSize: "11px", color: "var(--text-muted)", fontStyle: "italic" }}>
            Click a node in the 3D graph to inspect it
          </div>
        )}
      </div>

      {!selectedNode ? (
        <div style={{
          flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", gap: "10px", padding: "24px",
          color: "var(--text-muted)", textAlign: "center",
        }}>
          <svg width="36" height="36" viewBox="0 0 36 36" fill="none" opacity="0.3">
            <circle cx="18" cy="18" r="16" stroke="currentColor" strokeWidth="1.5"/>
            <circle cx="18" cy="18" r="6" stroke="currentColor" strokeWidth="1.5"/>
            <line x1="18" y1="2" x2="18" y2="8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="18" y1="28" x2="18" y2="34" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="2" y1="18" x2="8" y2="18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="28" y1="18" x2="34" y2="18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <div style={{ fontSize: "12px" }}>No node selected</div>
          <div style={{ fontSize: "11px" }}>Click any node in the 3D Graph view to inspect its g, h, f values and search history</div>
        </div>
      ) : (
        <>
          {/* Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border-subtle)", flexShrink: 0 }}>
            {(["info", "history", "raw"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  flex:       1,
                  padding:    "7px 0",
                  border:     "none",
                  background: "none",
                  fontSize:   "11px",
                  cursor:     "pointer",
                  color:      activeTab === tab ? "var(--text-primary)" : "var(--text-muted)",
                  fontWeight: activeTab === tab ? 600 : 400,
                  borderBottom: activeTab === tab ? `2px solid ${ALGORITHM_COLOR[selectedNode.algorithm_id]}` : "2px solid transparent",
                  transition: "all 120ms",
                }}
              >
                {tab === "info" ? "Details" : tab === "history" ? "History" : "Raw"}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px" }}>
            {activeTab === "info"    && <InfoTab    node={selectedNode.node} algoColor={ALGORITHM_COLOR[selectedNode.algorithm_id]} />}
            {activeTab === "history" && <HistoryTab node={selectedNode.node} algoColor={ALGORITHM_COLOR[selectedNode.algorithm_id]} />}
            {activeTab === "raw"     && <RawTab     node={selectedNode.node} algorithm_id={selectedNode.algorithm_id} delivery_id={selectedNode.delivery_id} />}
          </div>
        </>
      )}
    </div>
  );
}

// ── Info tab ─────────────────────────────────────────────────────────────────

function InfoTab({ node, algoColor }: { node: any; algoColor: string }) {
  return (
    <div>
      {/* Search values */}
      <SectionHeader>Search values</SectionHeader>
      <div
        style={{
          display:             "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap:                 "6px",
          marginBottom:        "14px",
        }}
      >
        <ValueCard label="g (cost)" value={formatCost(node.g)} color={algoColor} />
        <ValueCard label="h (heuristic)" value={formatCost(node.h)} color="var(--accent-amber)" />
        <ValueCard label="f = g+h" value={formatCost(node.f)} color="var(--accent-green)" />
      </div>

      {/* Position */}
      <SectionHeader>Position</SectionHeader>
      <InfoRow label="Grid"  value={`(${node.x}, ${node.y})`} mono />
      <InfoRow label="Depth" value={String(node.depth)} mono />
      <InfoRow label="Step"  value={String(node.step)} mono />
      <InfoRow label="Status" value={node.status} />
      <InfoRow label="Cell type" value={node.cell_type?.replace(/_/g, " ") ?? "—"} />

      {/* Parent */}
      {node.parent_id && (
        <>
          <SectionHeader>Parent</SectionHeader>
          <InfoRow label="Parent ID" value={node.parent_id} mono />
        </>
      )}

      {/* g / f bars */}
      <SectionHeader>Cost visualized</SectionHeader>
      <ProgressBar label="g cost" value={node.g} max={Math.max(node.g, node.f, 1)} color={algoColor} />
      <ProgressBar label="h estimate" value={node.h} max={Math.max(node.g, node.f, 1)} color="var(--accent-amber)" />
      <ProgressBar label="f total" value={node.f} max={Math.max(node.g, node.f, 1)} color="var(--accent-green)" />
    </div>
  );
}

// ── History tab ───────────────────────────────────────────────────────────────

function HistoryTab({ node, algoColor }: { node: any; algoColor: string }) {
  return (
    <div>
      <SectionHeader>Node recorded at step {node.step}</SectionHeader>
      <div
        style={{
          padding:      "8px 10px",
          borderRadius: "6px",
          background:   "var(--bg-raised)",
          border:       "1px solid var(--border-default)",
          fontSize:     "11px",
          color:        "var(--text-secondary)",
          lineHeight:   "1.9",
        }}
      >
        <div>Status when recorded: <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{node.status}</span></div>
        <div>g at recording: <span style={{ color: algoColor, fontFamily: "var(--font-mono)" }}>{node.g}</span></div>
        <div>h at recording: <span style={{ color: "var(--accent-amber)", fontFamily: "var(--font-mono)" }}>{node.h}</span></div>
        <div>depth: <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{node.depth}</span></div>
      </div>

      <div style={{ marginTop: "12px" }}>
        <SectionHeader>Ancestry chain</SectionHeader>
        <AncestryChain node={node} algoColor={algoColor} />
      </div>
    </div>
  );
}

function AncestryChain({ node, algoColor }: { node: any; algoColor: string }) {
  // Show the chain of IDs from root to this node using parent_id
  // (depth-limited since we only have the current node in view here)
  const chain = [node.id];
  if (node.parent_id) chain.unshift(node.parent_id);
  if (node.depth > 1) chain.unshift("…");

  return (
    <div
      style={{
        display:       "flex",
        flexDirection: "column",
        gap:           "2px",
      }}
    >
      {chain.map((id, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {i > 0 && (
            <div style={{ width: "1px", height: "10px", background: "var(--border-default)", marginLeft: "6px" }} />
          )}
          <div
            style={{
              padding:      "3px 8px",
              borderRadius: "4px",
              background:   id === node.id ? `${algoColor}20` : "var(--bg-raised)",
              border:       `1px solid ${id === node.id ? algoColor + "50" : "var(--border-default)"}`,
              fontSize:     "11px",
              fontFamily:   "var(--font-mono)",
              color:        id === node.id ? algoColor : "var(--text-secondary)",
              fontWeight:   id === node.id ? 600 : 400,
            }}
          >
            {id}
          </div>
          {id === node.id && (
            <span style={{ fontSize: "9px", color: "var(--text-muted)" }}>← selected</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Raw tab ───────────────────────────────────────────────────────────────────

function RawTab({ node, algorithm_id, delivery_id }: { node: any; algorithm_id: string; delivery_id: string }) {
  const data = JSON.stringify({ node, algorithm_id, delivery_id }, null, 2);
  return (
    <div>
      <SectionHeader>Raw TraceGraphNode</SectionHeader>
      <pre
        style={{
          fontSize:     "9px",
          fontFamily:   "var(--font-mono)",
          color:        "var(--text-secondary)",
          background:   "var(--bg-raised)",
          border:       "1px solid var(--border-default)",
          borderRadius: "5px",
          padding:      "10px",
          overflow:     "auto",
          maxHeight:    "400px",
          whiteSpace:   "pre-wrap",
          wordBreak:    "break-word",
          lineHeight:   "1.5",
        }}
      >
        {data}
      </pre>
    </div>
  );
}

// ── shared micro-components ───────────────────────────────────────────────────

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize:      "9px",
        fontWeight:    600,
        color:         "var(--text-muted)",
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        marginTop:     "14px",
        marginBottom:  "6px",
      }}
    >
      {children}
    </div>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div
      style={{
        display:       "flex",
        justifyContent:"space-between",
        alignItems:    "center",
        padding:       "4px 0",
        borderBottom:  "1px solid var(--border-subtle)",
        fontSize:      "11px",
      }}
    >
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span
        style={{
          color:      "var(--text-primary)",
          fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
          fontWeight: 500,
        }}
      >
        {value}
      </span>
    </div>
  );
}

function ValueCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div
      style={{
        padding:      "8px",
        borderRadius: "6px",
        background:   color + "12",
        border:       `1px solid ${color}30`,
        textAlign:    "center",
      }}
    >
      <div style={{ fontSize: "8px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "3px" }}>
        {label}
      </div>
      <div style={{ fontSize: "14px", fontWeight: 700, color, fontFamily: "var(--font-mono)" }}>
        {value}
      </div>
    </div>
  );
}

function ProgressBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min(100, (value / Math.max(max, 1)) * 100);
  return (
    <div style={{ marginBottom: "6px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", marginBottom: "3px" }}>
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <span style={{ color, fontFamily: "var(--font-mono)" }}>{formatCost(value)}</span>
      </div>
      <div style={{ height: "4px", background: "var(--bg-raised)", borderRadius: "2px", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: "2px", transition: "width 300ms" }} />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { color: string; bg: string }> = {
    open:   { color: "var(--accent-blue)",   bg: "var(--accent-blue)15"   },
    closed: { color: "var(--accent-purple)", bg: "var(--accent-purple)15" },
    path:   { color: "var(--accent-green)",  bg: "var(--accent-green)15"  },
  };
  const c = cfg[status] ?? cfg.open;
  return (
    <span
      style={{
        fontSize:      "9px",
        fontWeight:    600,
        color:         c.color,
        background:    c.bg,
        border:        `1px solid ${c.color}40`,
        borderRadius:  "3px",
        padding:       "2px 6px",
        textTransform: "uppercase",
        letterSpacing: "0.06em",
      }}
    >
      {status}
    </span>
  );
}
