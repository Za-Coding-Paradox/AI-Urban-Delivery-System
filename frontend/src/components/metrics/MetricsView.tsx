// src/components/metrics/MetricsView.tsx
// Metrics dashboard: per-delivery comparison table + bar charts + time chart.
// Reads from store.metrics (populated by simulation_complete event).

import { useMemo, useState }    from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line, Legend, ResponsiveContainer,
} from "recharts";
import { useMetrics, useStore } from "@/store";
import {
  ALGORITHM_IDS, ALGORITHM_SHORT, ALGORITHM_LABELS,
  ALGORITHM_COLOR, ALGORITHM_OPTIMAL,
} from "@/lib/constants";
import { formatCost, formatTime, formatCount } from "@/lib/utils";
import type { AlgorithmId } from "@/types";

const DELIVERIES = ["D1", "D2", "D3", "D4", "D5"];

export function MetricsView() {
  const metrics        = useMetrics();
  const activeDelivery = useStore((s) => s.activeDelivery);
  const store          = useStore();

  const [chartMode, setChartMode] = useState<"cost" | "nodes" | "time">("cost");

  // Group metrics by delivery
  const byDelivery = useMemo(() => {
    const map: Record<string, Record<AlgorithmId, any>> = {};
    DELIVERIES.forEach((d) => { map[d] = {} as any; });
    metrics.forEach((m) => {
      if (map[m.delivery_id]) {
        map[m.delivery_id][m.algorithm_id as AlgorithmId] = m;
      }
    });
    return map;
  }, [metrics]);

  // Chart data — per delivery, all algorithms
  const chartData = useMemo(() => {
    return DELIVERIES.map((d) => {
      const row: any = { delivery: d };
      ALGORITHM_IDS.forEach((id) => {
        const m = byDelivery[d]?.[id];
        if (m && m.path_found) {
          row[`${id}_cost`]  = m.path_cost;
          row[`${id}_nodes`] = m.nodes_explored;
          row[`${id}_time`]  = +m.execution_time_ms.toFixed(3);
        }
      });
      return row;
    });
  }, [byDelivery]);

  if (metrics.length === 0) {
    return (
      <EmptyMetrics />
    );
  }

  const activeDel = byDelivery[activeDelivery] ?? {};

  // Best cost for highlighting
  const bestCost = Math.min(
    ...ALGORITHM_IDS.filter((id) => activeDel[id]?.path_found).map((id) => activeDel[id].path_cost)
  );

  return (
    <div
      style={{
        display:       "flex",
        flexDirection: "column",
        height:        "100%",
        overflow:      "hidden",
        background:    "var(--bg-base)",
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display:      "flex",
          alignItems:   "center",
          gap:          "6px",
          padding:      "8px 16px",
          borderBottom: "1px solid var(--border-subtle)",
          flexShrink:   0,
          flexWrap:     "wrap",
        }}
      >
        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Delivery:</span>
        {DELIVERIES.map((d) => (
          <button
            key={d}
            onClick={() => store.setActiveDelivery(d)}
            style={{
              padding:    "3px 9px",
              borderRadius:"4px",
              border:     `1px solid ${activeDelivery === d ? "var(--accent-amber)" : "var(--border-default)"}`,
              background: activeDelivery === d ? "var(--accent-amber)18" : "transparent",
              color:      activeDelivery === d ? "var(--accent-amber)" : "var(--text-muted)",
              fontSize:   "11px",
              fontWeight: activeDelivery === d ? 600 : 400,
              cursor:     "pointer",
            }}
          >
            {d}
          </button>
        ))}

        <div style={{ marginLeft: "auto", display: "flex", gap: "4px" }}>
          {(["cost", "nodes", "time"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setChartMode(m)}
              style={{
                padding:    "3px 10px",
                borderRadius:"4px",
                border:     `1px solid ${chartMode === m ? "var(--accent-teal)" : "var(--border-default)"}`,
                background: chartMode === m ? "var(--accent-teal)20" : "transparent",
                color:      chartMode === m ? "var(--accent-teal)" : "var(--text-muted)",
                fontSize:   "10px",
                cursor:     "pointer",
              }}
            >
              {m === "cost" ? "Path cost" : m === "nodes" ? "Nodes" : "Time"}
            </button>
          ))}
        </div>

        {/* Export CSV */}
        <button
          onClick={() => exportCSV(metrics)}
          style={{
            padding:      "3px 10px",
            borderRadius: "4px",
            border:       "1px solid var(--border-default)",
            background:   "transparent",
            color:        "var(--text-secondary)",
            fontSize:     "10px",
            cursor:       "pointer",
          }}
        >
          ↓ CSV
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: "16px" }}>
        {/* ── Comparison table ────────────────────────────── */}
        <div style={{ marginBottom: "24px" }}>
          <SectionLabel>Algorithm comparison — {activeDelivery}</SectionLabel>
          <div
            style={{
              background:   "var(--bg-surface)",
              border:       "1px solid var(--border-subtle)",
              borderRadius: "8px",
              overflow:     "hidden",
            }}
          >
            {/* Table header */}
            <div
              style={{
                display:             "grid",
                gridTemplateColumns: "160px 90px 90px 80px 80px 70px",
                padding:             "8px 14px",
                borderBottom:        "1px solid var(--border-subtle)",
                fontSize:            "10px",
                color:               "var(--text-muted)",
                textTransform:       "uppercase",
                letterSpacing:       "0.06em",
              }}
            >
              <span>Algorithm</span>
              <span>Path cost</span>
              <span>Nodes explored</span>
              <span>Steps</span>
              <span>Time</span>
              <span>Status</span>
            </div>

            {/* Table rows */}
            {ALGORITHM_IDS.map((id) => {
              const m = activeDel[id];
              const isBest = m?.path_found && m.path_cost === bestCost;
              return (
                <div
                  key={id}
                  style={{
                    display:             "grid",
                    gridTemplateColumns: "160px 90px 90px 80px 80px 70px",
                    padding:             "10px 14px",
                    borderBottom:        "1px solid var(--border-subtle)",
                    background:          isBest ? `${ALGORITHM_COLOR[id]}08` : "transparent",
                    alignItems:          "center",
                    transition:          "background 200ms",
                  }}
                >
                  {/* Algorithm name */}
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <div
                      style={{
                        width:        "8px",
                        height:       "8px",
                        borderRadius: "50%",
                        background:   ALGORITHM_COLOR[id],
                        flexShrink:   0,
                        boxShadow:    `0 0 6px ${ALGORITHM_COLOR[id]}80`,
                      }}
                    />
                    <div>
                      <div style={{ fontSize: "12px", fontWeight: 500, color: "var(--text-primary)" }}>
                        {ALGORITHM_LABELS[id]}
                      </div>
                      <div style={{ fontSize: "9px", color: "var(--text-muted)" }}>
                        {ALGORITHM_OPTIMAL[id] ? "cost-optimal" : "not optimal"}
                      </div>
                    </div>
                  </div>

                  {/* Metrics cells */}
                  <MonoCell value={m?.path_found ? formatCost(m.path_cost) : "—"} highlight={isBest} color={ALGORITHM_COLOR[id]} />
                  <MonoCell value={m ? formatCount(m.nodes_explored) : "—"} />
                  <MonoCell value={m?.path_found ? String(m.path_length) : "—"} />
                  <MonoCell value={m ? formatTime(m.execution_time_ms) : "—"} />

                  {/* Status */}
                  <div>
                    {!m && <StatusPill color="var(--text-muted)">pending</StatusPill>}
                    {m?.path_found  === true  && <StatusPill color="var(--accent-green)">found ✓</StatusPill>}
                    {m?.path_found  === false && <StatusPill color="var(--accent-red)">no path</StatusPill>}
                  </div>
                </div>
              );
            })}

            {/* ── Totals summary row ───────────────────────────────────── */}
            {/* Sums across ALL deliveries for each algo — gives a single
                at-a-glance comparison of overall algorithm performance.    */}
            <TotalsRow metrics={metrics} />
          </div>
        </div>

        {/* ── Charts ───────────────────────────────────────── */}
        <div style={{ marginBottom: "24px" }}>
          <SectionLabel>
            {chartMode === "cost"  ? "Path cost by delivery"  :
             chartMode === "nodes" ? "Nodes explored by delivery" :
                                     "Execution time (ms) by delivery"}
          </SectionLabel>
          <div
            style={{
              background:   "var(--bg-surface)",
              border:       "1px solid var(--border-subtle)",
              borderRadius: "8px",
              padding:      "16px",
            }}
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="delivery" tick={{ fontSize: 11, fill: "var(--text-muted)" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "var(--text-muted)" }} axisLine={false} tickLine={false} width={40} />
                <Tooltip content={<CustomTooltip mode={chartMode} />} />
                {ALGORITHM_IDS.map((id) => (
                  <Bar
                    key={id}
                    dataKey={`${id}_${chartMode}`}
                    name={ALGORITHM_SHORT[id]}
                    fill={ALGORITHM_COLOR[id]}
                    radius={[2, 2, 0, 0]}
                    maxBarSize={18}
                    opacity={0.85}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ── Path cost trend (line chart) ──────────────────── */}
        <div>
          <SectionLabel>Path cost trend across deliveries</SectionLabel>
          <div
            style={{
              background:   "var(--bg-surface)",
              border:       "1px solid var(--border-subtle)",
              borderRadius: "8px",
              padding:      "16px",
            }}
          >
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData} margin={{ top: 4, right: 10, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="delivery" tick={{ fontSize: 11, fill: "var(--text-muted)" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "var(--text-muted)" }} axisLine={false} tickLine={false} width={40} />
                <Tooltip content={<CustomTooltip mode="cost" />} />
                <Legend
                  formatter={(value) => (
                    <span style={{ fontSize: "10px", color: "var(--text-secondary)" }}>{value}</span>
                  )}
                />
                {ALGORITHM_IDS.map((id) => (
                  <Line
                    key={id}
                    type="monotone"
                    dataKey={`${id}_cost`}
                    name={ALGORITHM_SHORT[id]}
                    stroke={ALGORITHM_COLOR[id]}
                    strokeWidth={2}
                    dot={{ r: 3, fill: ALGORITHM_COLOR[id] }}
                    connectNulls={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── helpers ────────────────────────────────────────────────────────────────────

// Totals row — shows per-algorithm sums across ALL deliveries at the bottom
// of the comparison table. Each algorithm gets one summarised cell so you
// can compare overall performance at a glance without switching delivery tabs.
function TotalsRow({ metrics }: { metrics: any[] }) {
  type AlgoTotals = {
    id: AlgorithmId;
    totalCost:  number;
    totalNodes: number;
    totalSteps: number;
    totalTime:  number;
    foundCount: number;
    rowCount:   number;
  };

  const totals = useMemo<AlgoTotals[]>(() => {
    return ALGORITHM_IDS.map((id) => {
      const rows  = metrics.filter((m) => m.algorithm_id === id);
      const found = rows.filter((m) => m.path_found);
      return {
        id,
        totalCost:  found.reduce((s, m) => s + m.path_cost, 0),
        totalNodes: rows.reduce((s, m) => s + m.nodes_explored, 0),
        totalSteps: found.reduce((s, m) => s + m.path_length, 0),
        totalTime:  rows.reduce((s, m) => s + m.execution_time_ms, 0),
        foundCount: found.length,
        rowCount:   rows.length,
      };
    });
  }, [metrics]);

  const validTotals  = totals.filter((t) => t.rowCount > 0);
  const allComplete  = validTotals.filter((t) => t.foundCount === t.rowCount);
  const lowestCost   = allComplete.length
    ? Math.min(...allComplete.map((t) => t.totalCost))
    : Infinity;

  if (validTotals.length === 0) return null;

  return (
    <>
      {/* Section divider label */}
      <div
        style={{
          gridColumn:    "1 / -1",
          padding:       "6px 14px 4px",
          fontSize:      "9px",
          fontWeight:    700,
          color:         "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: "0.1em",
          background:    "var(--bg-raised)",
          borderTop:     "2px solid var(--border-default)",
        }}
      >
        Totals — all {DELIVERIES.length} deliveries
      </div>

      {/* One row per algorithm, same grid as data rows */}
      {totals.map((t) => {
        if (t.rowCount === 0) return null;
        const isBest = t.foundCount === t.rowCount && t.totalCost === lowestCost;
        return (
          <div
            key={t.id}
            style={{
              display:             "grid",
              gridTemplateColumns: "160px 90px 90px 80px 80px 70px",
              padding:             "8px 14px",
              borderTop:           "1px solid var(--border-subtle)",
              background:          isBest ? `${ALGORITHM_COLOR[t.id]}06` : "var(--bg-raised)",
              alignItems:          "center",
            }}
          >
            {/* Name */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div
                style={{
                  width:        "6px",
                  height:       "6px",
                  borderRadius: "50%",
                  background:   ALGORITHM_COLOR[t.id],
                  flexShrink:   0,
                  opacity:      0.7,
                }}
              />
              <span style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                {ALGORITHM_SHORT[t.id]}
              </span>
            </div>

            {/* Total cost — only paths found */}
            <MonoCell
              value={t.foundCount > 0 ? formatCost(t.totalCost) : "—"}
              highlight={isBest}
              color={ALGORITHM_COLOR[t.id]}
            />
            {/* Total nodes explored */}
            <MonoCell value={formatCount(t.totalNodes)} />
            {/* Total steps */}
            <MonoCell value={t.foundCount > 0 ? formatCount(t.totalSteps) : "—"} />
            {/* Total time */}
            <MonoCell value={formatTime(t.totalTime)} />
            {/* Paths found ratio */}
            <div>
              <StatusPill
                color={
                  t.foundCount === t.rowCount ? "var(--accent-green)"
                  : t.foundCount === 0        ? "var(--accent-red)"
                  :                             "var(--accent-amber)"
                }
              >
                {t.foundCount}/{t.rowCount}
              </StatusPill>
            </div>
          </div>
        );
      })}
    </>
  );
}


function EmptyMetrics() {
  return (
    <div
      style={{
        height:         "100%",
        display:        "flex",
        alignItems:     "center",
        justifyContent: "center",
        flexDirection:  "column",
        gap:            "12px",
        color:          "var(--text-muted)",
      }}
    >
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity="0.3">
        <rect x="6" y="28" width="8" height="14" rx="2" fill="var(--accent-blue)"/>
        <rect x="18" y="18" width="8" height="24" rx="2" fill="var(--accent-purple)"/>
        <rect x="30" y="10" width="8" height="32" rx="2" fill="var(--accent-teal)"/>
      </svg>
      <div style={{ fontSize: "14px" }}>No metrics yet</div>
      <div style={{ fontSize: "12px" }}>Generate a profile and start the simulation</div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
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
      {children}
    </div>
  );
}

function MonoCell({ value, highlight = false, color = "var(--text-secondary)" }: {
  value: string; highlight?: boolean; color?: string;
}) {
  return (
    <div
      style={{
        fontFamily: "var(--font-mono)",
        fontSize:   "12px",
        color:      highlight ? color : "var(--text-secondary)",
        fontWeight: highlight ? 700 : 400,
      }}
    >
      {value}
      {highlight && (
        <span
          style={{
            marginLeft:   "4px",
            fontSize:     "9px",
            color,
            opacity:      0.7,
          }}
        >
          ★
        </span>
      )}
    </div>
  );
}

function StatusPill({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize:      "9px",
        fontWeight:    600,
        color,
        background:    color + "18",
        border:        `1px solid ${color}40`,
        borderRadius:  "3px",
        padding:       "2px 5px",
        textTransform: "uppercase",
        letterSpacing: "0.04em",
      }}
    >
      {children}
    </span>
  );
}

function CustomTooltip({ active, payload, label, mode }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background:   "var(--bg-raised)",
        border:       "1px solid var(--border-default)",
        borderRadius: "6px",
        padding:      "8px 12px",
        fontSize:     "11px",
      }}
    >
      <div style={{ color: "var(--text-muted)", marginBottom: "4px", fontWeight: 600 }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.name} style={{ display: "flex", gap: "8px", alignItems: "center", padding: "2px 0" }}>
          <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: p.fill, flexShrink: 0 }} />
          <span style={{ color: "var(--text-secondary)", minWidth: "40px" }}>{p.name}</span>
          <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)", fontWeight: 600 }}>
            {mode === "time" ? formatTime(p.value) : formatCost(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function exportCSV(metrics: any[]) {
  const headers = "algorithm_id,delivery_id,path_cost,nodes_explored,path_length,execution_time_ms,path_found,heuristic_used";
  const rows = metrics.map((m) =>
    `${m.algorithm_id},${m.delivery_id},${m.path_cost},${m.nodes_explored},${m.path_length},${m.execution_time_ms},${m.path_found},${m.heuristic_used}`
  );
  const csv  = [headers, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = "positron_metrics.csv";
  a.click();
  URL.revokeObjectURL(url);
}
