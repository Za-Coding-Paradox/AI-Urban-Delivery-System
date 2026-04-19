// src/types/index.ts
// Re-exports everything from simulation.ts.
// Components import from "@/types" rather than "@/types/simulation" —
// this lets us split types into multiple files later without touching imports.
export * from "./simulation";
