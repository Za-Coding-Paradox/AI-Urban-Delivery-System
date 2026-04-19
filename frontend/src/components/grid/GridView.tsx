// src/components/grid/GridView.tsx
// 2D grid viewer: cell canvas + path overlay + robot sprite + per-cell tooltip.
// Uses an HTML5 Canvas for fast rendering of 225 cells, with SVG overlay for
// the robot and path trail drawn on top.

import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import {
  useGridCells, useStore, useRunStatus, useMetrics,
  useAlgorithmStates, useActiveDelivery, usePlayback,
} from "@/store";
import {
  CELL_COLORS, CELL_BORDER_COLORS, ALGORITHM_COLOR,
  ALGORITHM_IDS, ALGORITHM_SHORT,
} from "@/lib/constants";
import type { Cell, AlgorithmId, MetricsSummary } from "@/types";

const GRID = 15;

export function GridView() {
  const cells          = useGridCells();
  const runStatus      = useRunStatus();
  const metrics        = useMetrics();
  const algorithmStates = useAlgorithmStates();
  const activeDelivery = useActiveDelivery();
  const playback       = usePlayback();
  const setActiveDelivery = useStore((s) => s.setActiveDelivery);

  const canvasRef      = useRef<HTMLCanvasElement>(null);
  const containerRef   = useRef<HTMLDivElement>(null);
  const [cellSize, setCellSize] = useState(0);
  const [hoveredCell, setHoveredCell] = useState<Cell | null>(null);
  const [mousePos, setMousePos]       = useState({ x: 0, y: 0 });
  const [selectedAlgo, setSelectedAlgo] = useState<AlgorithmId>("astar");

  // Derive metric for selected algorithm + delivery
  const activeMetric: MetricsSummary | null = useMemo(() => {
    return metrics.find(
      (m) => m.algorithm_id === selectedAlgo && m.delivery_id === activeDelivery
    ) ?? null;
  }, [metrics, selectedAlgo, activeDelivery]);

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      const size = Math.floor(Math.min(width, height) / GRID) - 1;
      setCellSize(Math.max(size, 20));
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Draw grid on canvas whenever cells or cellSize changes
  useEffect(() => {
    if (!canvasRef.current || !cells.length || cellSize === 0) return;
    const ctx = canvasRef.current.getContext("2d")!;
    const totalSize = cellSize * GRID + GRID + 1;
    canvasRef.current.width  = totalSize;
    canvasRef.current.height = totalSize;

    ctx.clearRect(0, 0, totalSize, totalSize);

    cells.forEach((cell) => {
      const px = cell.x * (cellSize + 1) + 1;
      const py = cell.y * (cellSize + 1) + 1;

      // Cell fill
      ctx.fillStyle = CELL_COLORS[cell.type];
      ctx.fillRect(px, py, cellSize, cellSize);

      // Cell border
      ctx.strokeStyle = CELL_BORDER_COLORS[cell.type];
      ctx.lineWidth   = 0.5;
      ctx.strokeRect(px + 0.5, py + 0.5, cellSize - 1, cellSize - 1);

      // Cost label for road cells (only when cells are large enough)
      if (cell.cost !== null && cellSize >= 28) {
        ctx.fillStyle   = "rgba(255,255,255,0.18)";
        ctx.font        = `${Math.min(10, cellSize * 0.32)}px monospace`;
        ctx.textAlign   = "center";
        ctx.textBaseline= "middle";
        ctx.fillText(String(cell.cost), px + cellSize / 2, py + cellSize / 2);
      }
    });
  }, [cells, cellSize]);

  // Overlay path on canvas
  const pathCells = activeMetric?.path ?? [];
  const startCell = cells.find((c) => c.type === "base_station");
  const goalCell  = cells.find(
    (c) =>
      c.type === "delivery_point" &&
      activeMetric &&
      c.x === /* derived from delivery */ 0  // patched below
  );

  // Draw highlighted path overlay using separate canvas
  const overlayRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!overlayRef.current || cellSize === 0) return;
    const ctx = overlayRef.current.getContext("2d")!;
    const totalSize = cellSize * GRID + GRID + 1;
    overlayRef.current.width  = totalSize;
    overlayRef.current.height = totalSize;
    ctx.clearRect(0, 0, totalSize, totalSize);

    if (!pathCells.length) return;

    const color = ALGORITHM_COLOR[selectedAlgo];

    // Draw path line
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth   = Math.max(2, cellSize * 0.12);
    ctx.lineCap     = "round";
    ctx.lineJoin    = "round";
    ctx.globalAlpha = 0.75;

    pathCells.forEach(({ x, y }, i) => {
      const px = x * (cellSize + 1) + 1 + cellSize / 2;
      const py = y * (cellSize + 1) + 1 + cellSize / 2;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();

    // Draw dots at each path step
    ctx.globalAlpha = 1;
    pathCells.forEach(({ x, y }, i) => {
      const px = x * (cellSize + 1) + 1 + cellSize / 2;
      const py = y * (cellSize + 1) + 1 + cellSize / 2;
      const isFirst = i === 0;
      const isLast  = i === pathCells.length - 1;

      ctx.beginPath();
      ctx.arc(px, py, isFirst || isLast ? cellSize * 0.22 : cellSize * 0.12, 0, Math.PI * 2);
      ctx.fillStyle = isFirst ? "var(--accent-teal)" : isLast ? "var(--accent-amber)" : color;
      ctx.fill();
    });
  }, [pathCells, selectedAlgo, cellSize]);

  // Mouse handlers for tooltip
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!containerRef.current || cellSize === 0) return;
      const rect = containerRef.current.getBoundingClientRect();
      const localX = e.clientX - rect.left;
      const localY = e.clientY - rect.top;
      const cx = Math.floor(localX / (cellSize + 1));
      const cy = Math.floor(localY / (cellSize + 1));
      if (cx >= 0 && cx < GRID && cy >= 0 && cy < GRID) {
        const cell = cells.find((c) => c.x === cx && c.y === cy) ?? null;
        setHoveredCell(cell);
        setMousePos({ x: e.clientX - rect.left + 12, y: e.clientY - rect.top + 12 });
      } else {
        setHoveredCell(null);
      }
    },
    [cells, cellSize]
  );

  const canvasSize = cellSize * GRID + GRID + 1;

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
          gap:          "8px",
          padding:      "8px 16px",
          borderBottom: "1px solid var(--border-subtle)",
          flexShrink:   0,
          flexWrap:     "wrap",
        }}
      >
        <span style={{ fontSize: "11px", color: "var(--text-muted)", marginRight: "4px" }}>
          Path overlay:
        </span>
        {ALGORITHM_IDS.map((id) => {
          const hasMets = metrics.some(
            (m) => m.algorithm_id === id && m.delivery_id === activeDelivery && m.path_found
          );
          return (
            <button
	    <button
	    key={d}
	    onClick={() => setActiveDelivery(d)}
              disabled={!hasMets}
              style={{
                padding:      "3px 10px",
                borderRadius: "4px",
                border:       `1px solid ${selectedAlgo === id ? ALGORITHM_COLOR[id] : "var(--border-default)"}`,
                background:   selectedAlgo === id ? ALGORITHM_COLOR[id] + "20" : "transparent",
                color:        !hasMets ? "var(--text-muted)" : selectedAlgo === id ? ALGORITHM_COLOR[id] : "var(--text-secondary)",
                fontSize:     "11px",
                fontWeight:   selectedAlgo === id ? 600 : 400,
                cursor:       hasMets ? "pointer" : "not-allowed",
                transition:   "all 120ms",
              }}
            >
              {ALGORITHM_SHORT[id]}
            </button>
          );
        })}

        {/* Delivery selector */}
        <div style={{ marginLeft: "auto", display: "flex", gap: "4px" }}>
          <span style={{ fontSize: "11px", color: "var(--text-muted)", alignSelf: "center" }}>Delivery:</span>
          {["D1", "D2", "D3", "D4", "D5"].map((d) => (
            <button
              key={d}
              onClick={() => store.setActiveDelivery(d)}
              style={{
                padding:      "3px 8px",
                borderRadius: "4px",
                border:       `1px solid ${activeDelivery === d ? "var(--accent-amber)" : "var(--border-default)"}`,
                background:   activeDelivery === d ? "var(--accent-amber)20" : "transparent",
                color:        activeDelivery === d ? "var(--accent-amber)" : "var(--text-muted)",
                fontSize:     "10px",
                fontWeight:   activeDelivery === d ? 600 : 400,
                cursor:       "pointer",
              }}
            >
              {d}
            </button>
          ))}
        </div>

        {/* Metric summary inline */}
        {activeMetric && (
          <div style={{ display: "flex", gap: "12px", marginLeft: "8px" }}>
            <MetricChip label="Cost" value={activeMetric.path_cost.toFixed(1)} color={ALGORITHM_COLOR[selectedAlgo]} />
            <MetricChip label="Nodes" value={String(activeMetric.nodes_explored)} color={ALGORITHM_COLOR[selectedAlgo]} />
            <MetricChip label="Steps" value={String(activeMetric.path_length)} color={ALGORITHM_COLOR[selectedAlgo]} />
          </div>
        )}
      </div>

      {/* Canvas area */}
      <div style={{ flex: 1, overflow: "auto", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div
          ref={containerRef}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredCell(null)}
          style={{
            position: "relative",
            width:     `${canvasSize}px`,
            height:    `${canvasSize}px`,
            flexShrink:0,
          }}
        >
          {/* Base grid canvas */}
          <canvas
            ref={canvasRef}
            style={{ position: "absolute", top: 0, left: 0, imageRendering: "pixelated" }}
          />
          {/* Path overlay canvas */}
          <canvas
            ref={overlayRef}
            style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
          />

          {/* SVG overlay for robot and special markers */}
          {cellSize > 0 && (
            <svg
              width={canvasSize}
              height={canvasSize}
              style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
              viewBox={`0 0 ${canvasSize} ${canvasSize}`}
            >
              {/* Delivery destination markers */}
              {cells
                .filter((c) => c.type === "delivery_point")
                .map((c) => {
                  const px = c.x * (cellSize + 1) + 1 + cellSize / 2;
                  const py = c.y * (cellSize + 1) + 1 + cellSize / 2;
                  return (
                    <g key={c.id}>
                      <circle cx={px} cy={py} r={cellSize * 0.28} fill="var(--accent-amber)" opacity="0.25"/>
                      <circle cx={px} cy={py} r={cellSize * 0.12} fill="var(--accent-amber)"/>
                    </g>
                  );
                })}

              {/* Base station marker */}
              {cells
                .filter((c) => c.type === "base_station")
                .map((c) => {
                  const px = c.x * (cellSize + 1) + 1 + cellSize / 2;
                  const py = c.y * (cellSize + 1) + 1 + cellSize / 2;
                  return (
                    <g key={c.id}>
                      <circle cx={px} cy={py} r={cellSize * 0.32} fill="var(--accent-teal)" opacity="0.2"/>
                      <circle cx={px} cy={py} r={cellSize * 0.14} fill="var(--accent-teal)"/>
                    </g>
                  );
                })}
            </svg>
          )}

          {/* Tooltip */}
          {hoveredCell && (
            <CellTooltip cell={hoveredCell} x={mousePos.x} y={mousePos.y} />
          )}
        </div>
      </div>

      {/* Legend bar */}
      <GridLegend />
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function MetricChip({
  label, value, color,
}: {
  label: string; value: string; color: string;
}) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: "9px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </div>
      <div style={{ fontSize: "12px", fontWeight: 600, color, fontFamily: "var(--font-mono)" }}>
        {value}
      </div>
    </div>
  );
}

function CellTooltip({ cell, x, y }: { cell: Cell; x: number; y: number }) {
  return (
    <div
      style={{
        position:     "absolute",
        left:         `${x}px`,
        top:          `${y}px`,
        padding:      "6px 10px",
        borderRadius: "6px",
        background:   "var(--bg-raised)",
        border:       "1px solid var(--border-default)",
        fontSize:     "11px",
        color:        "var(--text-primary)",
        pointerEvents:"none",
        whiteSpace:   "nowrap",
        zIndex:       10,
        boxShadow:    "0 4px 16px rgba(0,0,0,0.4)",
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: "2px" }}>
        {cell.type.replace(/_/g, " ")}
      </div>
      <div style={{ color: "var(--text-secondary)" }}>
        ({cell.x}, {cell.y})
        {cell.cost !== null && ` · cost ${cell.cost}`}
      </div>
    </div>
  );
}

function GridLegend() {
  const items: Array<{ label: string; color: string }> = [
    { label: "Road",          color: "#1e2330" },
    { label: "Traffic zone",  color: "#2d1f0a" },
    { label: "Building",      color: "#0d0f12" },
    { label: "Delivery point",color: "#1a2a1a" },
    { label: "Base station",  color: "#0d1f1a" },
  ];
  return (
    <div
      style={{
        display:      "flex",
        gap:          "14px",
        padding:      "7px 16px",
        borderTop:    "1px solid var(--border-subtle)",
        flexWrap:     "wrap",
        flexShrink:   0,
      }}
    >
      {items.map(({ label, color }) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: "5px" }}>
          <div
            style={{
              width:        "10px",
              height:       "10px",
              borderRadius: "2px",
              background:   color,
              border:       "1px solid rgba(255,255,255,0.1)",
              flexShrink:   0,
            }}
          />
          <span style={{ fontSize: "10px", color: "var(--text-secondary)" }}>{label}</span>
        </div>
      ))}
      <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
        <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "var(--accent-teal)", flexShrink: 0 }}/>
        <span style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Start</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
        <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "var(--accent-amber)", flexShrink: 0 }}/>
        <span style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Goal</span>
      </div>
    </div>
  );
}
