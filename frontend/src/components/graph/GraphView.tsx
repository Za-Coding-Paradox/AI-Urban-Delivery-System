// src/components/graph/GraphView.tsx
// 3D node graph — renders TraceGraph as a spatial search tree.
// X = grid.x * scale, Y = depth * yScale, Z = grid.y * scale.
// Node size encodes g-cost; color encodes status. Edge lines show edge_type.
// Built with @react-three/fiber + @react-three/drei.

import { Suspense, useRef, useState, useMemo } from "react";
import { Canvas, useFrame, useThree }          from "@react-three/fiber";
import { OrbitControls, Html, Line }            from "@react-three/drei";
import * as THREE                               from "three";
import { useGraphs, useStore, useMetrics }      from "@/store";
import {
  ALGORITHM_IDS, ALGORITHM_SHORT, ALGORITHM_COLOR,
  NODE_STATUS_COLORS, EDGE_COLORS,
} from "@/lib/constants";
import { nodeRadius, nodeVisualType }           from "@/lib/utils";
import type { AlgorithmId, TraceGraph, TraceGraphNode, TraceGraphEdge } from "@/types";

const X_SCALE = 1.8;
const Y_SCALE = 2.2;
const Z_SCALE = 1.8;

export function GraphView() {
  const graphs    = useGraphs();
  const metrics   = useMetrics();
  const store     = useStore();
  const selectedNode = useStore((s) => s.selectedNode);

  const [selectedAlgo,     setSelectedAlgo]     = useState<AlgorithmId>("astar");
  const [selectedDelivery, setSelectedDelivery]  = useState("D1");
  const [showFrontier,     setShowFrontier]      = useState(true);
  const [showExpanded,     setShowExpanded]      = useState(true);
  const [showEdges,        setShowEdges]         = useState(true);
  const [yScale,           setYScale]            = useState(Y_SCALE);
  const [xzScale,          setXzScale]           = useState(X_SCALE);

  const graphKey = `${selectedAlgo}:${selectedDelivery}`;
  const graph: TraceGraph | null = graphs[graphKey] ?? null;

  const goalId = useMemo(() => {
    const m = metrics.find(
      (m) => m.algorithm_id === selectedAlgo && m.delivery_id === selectedDelivery
    );
    return m?.path[m.path.length - 1]
      ? `${m.path[m.path.length - 1].x},${m.path[m.path.length - 1].y}`
      : "";
  }, [metrics, selectedAlgo, selectedDelivery]);

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* ── 3D canvas ────────────────────────────────────────── */}
      <div style={{ flex: 1, position: "relative" }}>
        {/* Toolbar */}
        <div
          style={{
            position:     "absolute",
            top:          0, left: 0, right: 0,
            zIndex:       10,
            display:      "flex",
            alignItems:   "center",
            gap:          "6px",
            padding:      "8px 12px",
            background:   "rgba(13,15,18,0.85)",
            backdropFilter:"blur(8px)",
            borderBottom: "1px solid var(--border-subtle)",
            flexWrap:     "wrap",
          }}
        >
          {/* Algorithm tabs */}
          {ALGORITHM_IDS.map((id) => {
            const hasGraph = !!graphs[`${id}:${selectedDelivery}`];
            return (
              <button
                key={id}
                onClick={() => setSelectedAlgo(id)}
                disabled={!hasGraph}
                style={{
                  padding:      "3px 10px",
                  borderRadius: "4px",
                  border:       `1px solid ${selectedAlgo === id ? ALGORITHM_COLOR[id] : "var(--border-default)"}`,
                  background:   selectedAlgo === id ? `${ALGORITHM_COLOR[id]}22` : "transparent",
                  color:        !hasGraph ? "var(--text-muted)" : selectedAlgo === id ? ALGORITHM_COLOR[id] : "var(--text-secondary)",
                  fontSize:     "11px",
                  fontWeight:   selectedAlgo === id ? 600 : 400,
                  cursor:       hasGraph ? "pointer" : "not-allowed",
                  transition:   "all 120ms",
                }}
              >
                {ALGORITHM_SHORT[id]}
              </button>
            );
          })}

          {/* Delivery tabs */}
          <div style={{ display: "flex", gap: "3px", marginLeft: "8px", borderLeft: "1px solid var(--border-subtle)", paddingLeft: "8px" }}>
            {["D1","D2","D3","D4","D5"].map((d) => (
              <button
                key={d}
                onClick={() => setSelectedDelivery(d)}
                style={{
                  padding:      "3px 7px",
                  borderRadius: "4px",
                  border:       `1px solid ${selectedDelivery === d ? "var(--accent-amber)" : "var(--border-default)"}`,
                  background:   selectedDelivery === d ? "var(--accent-amber)20" : "transparent",
                  color:        selectedDelivery === d ? "var(--accent-amber)" : "var(--text-muted)",
                  fontSize:     "10px",
                  cursor:       "pointer",
                }}
              >
                {d}
              </button>
            ))}
          </div>

          {/* Visibility toggles */}
          <div style={{ marginLeft: "auto", display: "flex", gap: "6px", alignItems: "center" }}>
            <ToggleChip label="Frontier" active={showFrontier} color="var(--accent-blue)"    onClick={() => setShowFrontier(!showFrontier)} />
            <ToggleChip label="Expanded" active={showExpanded} color="var(--accent-purple)"  onClick={() => setShowExpanded(!showExpanded)} />
            <ToggleChip label="Edges"    active={showEdges}    color="var(--accent-gray)"    onClick={() => setShowEdges(!showEdges)} />
          </div>
        </div>

        {/* Canvas */}
        <Canvas
          camera={{ position: [15, 18, 28], fov: 45 }}
          style={{ background: "#0a0c10" }}
          gl={{ antialias: true }}
        >
          <ambientLight intensity={0.4} />
          <directionalLight position={[10, 20, 10]} intensity={0.8} />
          <pointLight position={[-10, 10, -10]} intensity={0.4} color="#7f77dd" />

          <OrbitControls
            enablePan
            enableZoom
            enableRotate
            minDistance={3}
            maxDistance={120}
            target={[GRID_CENTER * xzScale, 0, GRID_CENTER * xzScale]}
          />

          {/* Grid floor plane */}
          <gridHelper
            args={[30, 30, "#1a1e26", "#13161b"]}
            position={[GRID_CENTER * xzScale, -0.2, GRID_CENTER * xzScale]}
          />

          <Suspense fallback={null}>
            {graph ? (
              <GraphScene
                graph={graph}
                goalId={goalId}
                showFrontier={showFrontier}
                showExpanded={showExpanded}
                showEdges={showEdges}
                yScale={yScale}
                xzScale={xzScale}
                onNodeClick={(node) =>
                  store.selectNode({ node, algorithm_id: selectedAlgo, delivery_id: selectedDelivery })
                }
                selectedId={selectedNode?.node.id ?? null}
              />
            ) : (
              <EmptyGraph />
            )}
          </Suspense>
        </Canvas>

        {/* No graph message */}
        {!graph && (
          <div
            style={{
              position:       "absolute",
              inset:          0,
              display:        "flex",
              alignItems:     "center",
              justifyContent: "center",
              flexDirection:  "column",
              gap:            "12px",
              pointerEvents:  "none",
            }}
          >
            <div style={{ fontSize: "32px", opacity: 0.3 }}>⬡</div>
            <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
              {Object.keys(graphs).length === 0
                ? "Run a simulation to see the search tree"
                : `No graph for ${ALGORITHM_SHORT[selectedAlgo]} · ${selectedDelivery}`}
            </div>
          </div>
        )}

        {/* Axis scale controls */}
        <div
          style={{
            position:   "absolute",
            bottom:     "12px",
            left:       "12px",
            background: "rgba(13,15,18,0.8)",
            border:     "1px solid var(--border-subtle)",
            borderRadius:"8px",
            padding:    "10px 12px",
            zIndex:     10,
          }}
        >
          <ScaleSlider label="Depth (Y)" value={yScale}  min={0.5} max={6} step={0.1} onChange={setYScale}  />
          <ScaleSlider label="Spread (XZ)" value={xzScale} min={0.5} max={4} step={0.1} onChange={setXzScale} />
        </div>

        {/* Graph stats */}
        {graph && (
          <div
            style={{
              position:   "absolute",
              bottom:     "12px",
              right:      "12px",
              background: "rgba(13,15,18,0.8)",
              border:     "1px solid var(--border-subtle)",
              borderRadius:"8px",
              padding:    "8px 12px",
              zIndex:     10,
              fontSize:   "11px",
              color:      "var(--text-secondary)",
              lineHeight: "1.8",
            }}
          >
            <div><span style={{ color: "var(--text-muted)" }}>Nodes </span>{graph.metadata.node_count}</div>
            <div><span style={{ color: "var(--text-muted)" }}>Edges </span>{graph.metadata.edge_count}</div>
            <div><span style={{ color: "var(--text-muted)" }}>Depth </span>{graph.metadata.max_depth}</div>
            <div><span style={{ color: "var(--text-muted)" }}>Steps </span>{graph.metadata.total_steps}</div>
          </div>
        )}
      </div>

      {/* Inspector panel is now managed globally in App.tsx via the Inspector toggle */}
    </div>
  );
}

const GRID_CENTER = 7;

// ── Three.js scene ─────────────────────────────────────────────────────────

function GraphScene({
  graph, goalId, showFrontier, showExpanded, showEdges,
  yScale, xzScale, onNodeClick, selectedId,
}: {
  graph: TraceGraph;
  goalId: string;
  showFrontier: boolean;
  showExpanded: boolean;
  showEdges: boolean;
  yScale: number;
  xzScale: number;
  onNodeClick: (n: TraceGraphNode) => void;
  selectedId: string | null;
}) {
  const { metadata } = graph;

  const visibleNodes = useMemo(
    () =>
      graph.nodes.filter((n) => {
        if (!showFrontier && n.status === "open")   return false;
        if (!showExpanded && n.status === "closed") return false;
        return true;
      }),
    [graph.nodes, showFrontier, showExpanded]
  );

  return (
    <group>
      {/* Edges */}
      {showEdges &&
        graph.edges.map((edge) => (
          <GraphEdge
            key={`${edge.from_id}-${edge.to_id}`}
            edge={edge}
            nodes={graph.nodes}
            yScale={yScale}
            xzScale={xzScale}
          />
        ))}

      {/* Nodes */}
      {visibleNodes.map((node) => (
        <GraphNode
          key={node.id}
          node={node}
          goalId={goalId}
          metadata={metadata}
          yScale={yScale}
          xzScale={xzScale}
          onClick={onNodeClick}
          selected={selectedId === node.id}
        />
      ))}
    </group>
  );
}

function GraphNode({
  node, goalId, metadata, yScale, xzScale, onClick, selected,
}: {
  node: TraceGraphNode;
  goalId: string;
  metadata: any;
  yScale: number;
  xzScale: number;
  onClick: (n: TraceGraphNode) => void;
  selected: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const vtype  = nodeVisualType(node, goalId);
  const radius = nodeRadius(vtype, node.g, Math.max(metadata.max_g, 1));
  const color  = useMemo(() => {
    switch (vtype) {
      case "start":     return "#1d9e75";
      case "goal":      return "#ef9f27";
      case "path_node": return "#639922";
      case "expanded":  return "#7f77dd";
      case "frontier":  return "#378add";
      case "visited":   return "#888780";
      default:          return "#555555";
    }
  }, [vtype]);

  const px = node.x * xzScale;
  const py = node.depth * yScale;
  const pz = node.y * xzScale;

  // Pulse animation for frontier nodes
  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    if (vtype === "frontier") {
      const s = 1 + Math.sin(clock.elapsedTime * 3 + node.x) * 0.15;
      meshRef.current.scale.setScalar(s);
    }
    if (hovered || selected) {
      meshRef.current.scale.setScalar(selected ? 1.4 : 1.2);
    } else if (vtype !== "frontier") {
      meshRef.current.scale.setScalar(1);
    }
  });

  return (
    <mesh
      ref={meshRef}
      position={[px, py, pz]}
      onClick={(e) => { e.stopPropagation(); onClick(node); }}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      <sphereGeometry args={[radius, 14, 14]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={selected ? 0.5 : hovered ? 0.3 : 0.1}
        roughness={0.4}
        metalness={0.2}
        transparent
        opacity={vtype === "pruned" ? 0.3 : 1}
      />

      {/* Selected ring */}
      {selected && (
        <mesh>
          <torusGeometry args={[radius * 1.5, radius * 0.1, 8, 24]} />
          <meshBasicMaterial color={color} transparent opacity={0.7} />
        </mesh>
      )}

      {/* Hover tooltip via @react-three/drei Html */}
      {hovered && (
        <Html distanceFactor={18} style={{ pointerEvents: "none" }}>
          <div
            style={{
              padding:      "5px 8px",
              background:   "rgba(13,15,18,0.92)",
              border:       `1px solid ${color}60`,
              borderRadius: "5px",
              fontSize:     "10px",
              color:        "#e8eaf0",
              whiteSpace:   "nowrap",
              fontFamily:   "monospace",
            }}
          >
            <div style={{ fontWeight: 600, color }}>{node.id}</div>
            <div>g={node.g.toFixed(1)} h={node.h.toFixed(1)} f={node.f.toFixed(1)}</div>
            <div>depth={node.depth} · {vtype}</div>
          </div>
        </Html>
      )}
    </mesh>
  );
}

function GraphEdge({
  edge, nodes, yScale, xzScale,
}: {
  edge: TraceGraphEdge;
  nodes: TraceGraphNode[];
  yScale: number;
  xzScale: number;
}) {
  const fromNode = useMemo(() => nodes.find((n) => n.id === edge.from_id), [nodes, edge.from_id]);
  const toNode   = useMemo(() => nodes.find((n) => n.id === edge.to_id),   [nodes, edge.to_id]);

  if (!fromNode || !toNode) return null;

  const start: [number, number, number] = [
    fromNode.x * xzScale,
    fromNode.depth * yScale,
    fromNode.y * xzScale,
  ];
  const end: [number, number, number] = [
    toNode.x * xzScale,
    toNode.depth * yScale,
    toNode.y * xzScale,
  ];

  const color     = EDGE_COLORS[edge.edge_type];
  const thickness = edge.edge_type === "path" ? 2.5 : 1;
  const opacity   = edge.edge_type === "path" ? 0.9 : 0.35;

  return (
    <Line
      points={[start, end]}
      color={color}
      lineWidth={thickness}
      transparent
      opacity={opacity}
      dashed={edge.edge_type === "backtrack"}
      dashSize={0.3}
      gapSize={0.15}
    />
  );
}

function EmptyGraph() {
  return null;
}

// ── small UI helpers ───────────────────────────────────────────────────────

function ToggleChip({
  label, active, color, onClick,
}: {
  label: string; active: boolean; color: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding:      "3px 8px",
        borderRadius: "4px",
        border:       `1px solid ${active ? color : "var(--border-default)"}`,
        background:   active ? color + "20" : "transparent",
        color:        active ? color : "var(--text-muted)",
        fontSize:     "10px",
        cursor:       "pointer",
        transition:   "all 120ms",
      }}
    >
      {label}
    </button>
  );
}

function ScaleSlider({
  label, value, min, max, step, onChange,
}: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
      <span style={{ fontSize: "10px", color: "var(--text-muted)", width: "60px" }}>{label}</span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "80px", accentColor: "var(--accent-teal)" }}
      />
      <span style={{ fontSize: "10px", color: "var(--text-secondary)", width: "28px", fontFamily: "monospace" }}>
        {value.toFixed(1)}
      </span>
    </div>
  );
}
