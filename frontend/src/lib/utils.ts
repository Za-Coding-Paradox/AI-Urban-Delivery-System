// src/lib/utils.ts
//
// Pure utility functions. No React, no state, no side effects.
// Each function does one thing and is independently testable.

import type { AlgorithmId, Cell, CellType, NodeStatus, TraceGraphNode } from "@/types";
import { ALGORITHM_COLOR, CELL_COLORS, NODE_STATUS_COLORS } from "@/lib/constants";

// ── grid ───────────────────────────────────────────────────────────────────

/**
 * Convert (x, y) grid coordinates to a flat array index.
 * The backend stores cells in row-major order: index = y * width + x.
 */
export function cellIndex(x: number, y: number, width = 15): number {
  return y * width + x;
}

/**
 * Convert a cell id string "x,y" to a coordinate object.
 */
export function parseCellId(id: string): { x: number; y: number } {
  const [x, y] = id.split(",").map(Number);
  return { x, y };
}

/**
 * Format a coordinate pair for display.
 */
export function formatCoord(x: number, y: number): string {
  return `(${x}, ${y})`;
}

/**
 * Find a cell in the flat cells array by its (x, y) coordinates.
 */
export function findCell(cells: Cell[], x: number, y: number): Cell | undefined {
  return cells[cellIndex(x, y)];
}

// ── colour helpers ─────────────────────────────────────────────────────────

/**
 * Returns the CSS colour for a cell type.
 * Used by GridCell to avoid hardcoding colours in components.
 */
export function cellColor(type: CellType): string {
  return CELL_COLORS[type];
}

/**
 * Returns the CSS colour for a node status.
 * Used by the 3D graph and inspector badge.
 */
export function nodeStatusColor(status: NodeStatus): string {
  return NODE_STATUS_COLORS[status];
}

/**
 * Returns the CSS colour for an algorithm.
 */
export function algorithmColor(id: AlgorithmId): string {
  return ALGORITHM_COLOR[id];
}

/**
 * Converts a hex colour string to an RGB triple [r, g, b] in 0-255 range.
 * Used by Three.js which needs numeric RGB, not CSS strings.
 *
 * Example: hexToRgb("#1d9e75") → [29, 158, 117]
 */
export function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return [r, g, b];
}

/**
 * Converts a hex colour to a Three.js-compatible 0xRRGGBB integer.
 *
 * Example: hexToThree("#1d9e75") → 0x1d9e75
 */
export function hexToThree(hex: string): number {
  return parseInt(hex.replace("#", ""), 16);
}

// ── number formatting ──────────────────────────────────────────────────────

/**
 * Format a floating-point number for display in the metrics table.
 * Uses fixed decimal places based on the magnitude.
 *
 * Examples:
 *   formatCost(12.0)    → "12.0"
 *   formatCost(3.14159) → "3.14"
 *   formatCost(0)       → "0"
 */
export function formatCost(value: number): string {
  if (value === 0) return "0";
  if (Number.isInteger(value)) return value.toString();
  return value.toFixed(2);
}

/**
 * Format execution time for display.
 * Sub-millisecond values show microseconds; larger values show ms.
 *
 * Examples:
 *   formatTime(0.045)  → "45 µs"
 *   formatTime(1.23)   → "1.23 ms"
 *   formatTime(120.5)  → "120.5 ms"
 */
export function formatTime(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)} µs`;
  return `${ms.toFixed(2)} ms`;
}

/**
 * Format a large integer with thousands separators.
 * Used for nodes_explored counts.
 *
 * Example: formatCount(12345) → "12,345"
 */
export function formatCount(n: number): string {
  return n.toLocaleString();
}

// ── trace graph helpers ─────────────────────────────────────────────────────

/**
 * Given a TraceGraphNode, determines its visual "node type" for the 3D graph.
 * This is the seven-category encoding from the plan.
 *
 * Returns one of: "start" | "goal" | "path_node" | "expanded" |
 *                 "visited" | "pruned" | "frontier"
 */
export type NodeVisualType =
  | "start"
  | "goal"
  | "path_node"
  | "expanded"
  | "visited"
  | "pruned"
  | "frontier";

export function nodeVisualType(
  node: TraceGraphNode,
  goalId: string
): NodeVisualType {
  if (node.depth === 0 && node.parent_id === null) return "start";
  if (node.id === goalId) return "goal";
  if (node.status === "path") return "path_node";
  if (node.status === "closed") return "expanded";
  if (node.status === "open") return "frontier";
  return "visited";
}

/**
 * Normalises a value between 0 and 1 given a known min and max.
 * Used for sphere size encoding (g cost) in the 3D graph.
 * Clamps to [0, 1] to handle edge cases.
 */
export function normalise(value: number, min: number, max: number): number {
  if (max === min) return 0;
  return Math.max(0, Math.min(1, (value - min) / (max - min)));
}

/**
 * Returns a sphere radius for a node in the 3D graph.
 * Base radius varies by visual type; g cost adds a small size increment.
 *
 * From the plan:
 *   start/goal  → large
 *   path_node   → medium
 *   expanded    → medium
 *   frontier    → medium (pulsing)
 *   visited     → small
 *   pruned      → tiny
 *
 * g cost adds up to 0.05 additional radius (normalised against max_g).
 */
export function nodeRadius(
  type: NodeVisualType,
  g: number,
  maxG: number
): number {
  const base: Record<NodeVisualType, number> = {
    start:     0.35,
    goal:      0.35,
    path_node: 0.25,
    expanded:  0.22,
    frontier:  0.22,
    visited:   0.15,
    pruned:    0.10,
  };
  const gBonus = normalise(g, 0, maxG) * 0.05;
  return base[type] + gBonus;
}

// ── string helpers ─────────────────────────────────────────────────────────

/**
 * Converts an algorithm id to its display colour class name.
 * Used in JSX: <span className={algorithmBadgeClass("bfs")}>BFS</span>
 */
export function algorithmBadgeClass(id: AlgorithmId): string {
  return `badge badge-${id}`;
}

/**
 * Converts a node status to its display badge class name.
 */
export function statusBadgeClass(status: NodeStatus): string {
  return `badge badge-${status}`;
}

/**
 * Truncates a string to maxLen characters, adding "…" if truncated.
 */
export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen - 1) + "…";
}
