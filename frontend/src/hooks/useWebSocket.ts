// src/hooks/useWebSocket.ts
//
// Manages the persistent WebSocket connection to the simulation server.
// Uses the `reconnecting-websocket` package which automatically reconnects
// on disconnect with exponential backoff — so if the backend restarts,
// the frontend reconnects without any user action.
//
// Design: this hook has one job — maintain the connection and pipe every
// incoming message into the store via ingestEvent(). It does not parse,
// filter, or transform events. That is the store's responsibility.
//
// Mount this hook once, high in the component tree (App.tsx).
// It runs for the lifetime of the application.

import { useEffect, useRef } from "react";
import ReconnectingWebSocket from "reconnecting-websocket";

import { WS_URL } from "@/lib/constants";
import { useStore } from "@/store";
import type { ServerEvent } from "@/types";

export function useWebSocket(): void {
  const wsRef = useRef<ReconnectingWebSocket | null>(null);

  const setConnected = useStore((s) => s.setConnected);
  const ingestEvent  = useStore((s) => s.ingestEvent);

  useEffect(() => {
    // ReconnectingWebSocket wraps the native WebSocket API and adds:
    //   - Automatic reconnection with configurable delay/backoff
    //   - Event listeners survive reconnects (you don't re-add them)
    //   - maxRetries prevents infinite loops if server is permanently down
    const ws = new ReconnectingWebSocket(WS_URL, [], {
      maxRetries:         10,
      reconnectionDelayGrowFactor: 1.5,  // exponential backoff
      minReconnectionDelay:        500,  // ms before first retry
      maxReconnectionDelay:        5000, // ms cap on backoff
    });

    wsRef.current = ws;

    // ── connection opened ────────────────────────────────────────────────
    ws.addEventListener("open", () => {
      setConnected(true);
    });

    // ── connection closed / lost ─────────────────────────────────────────
    ws.addEventListener("close", () => {
      setConnected(false);
      // ReconnectingWebSocket will attempt to reconnect automatically
    });

    // ── message received ─────────────────────────────────────────────────
    ws.addEventListener("message", (messageEvent) => {
      try {
        const event = JSON.parse(messageEvent.data) as ServerEvent;

        // Keep the connection alive — pong to pings from the server
        // The server sends a ping every 30s if no client message arrives
        if (event.event_type === "ping") {
          ws.send(JSON.stringify({ type: "pong" }));
          return;  // don't ingest keepalive events into the store
        }

        ingestEvent(event);
      } catch {
        // Malformed JSON from the server — log but don't crash
        console.warn("[WS] Received non-JSON message:", messageEvent.data);
      }
    });

    // ── error ────────────────────────────────────────────────────────────
    ws.addEventListener("error", (err) => {
      // ReconnectingWebSocket handles retry — we just log
      console.warn("[WS] Connection error:", err);
    });

    // ── cleanup ──────────────────────────────────────────────────────────
    // When the component unmounts (app closes), close the WS cleanly
    return () => {
      ws.close();
      setConnected(false);
    };
  }, []);  // empty deps — runs once on mount, cleanup on unmount
           // setConnected and ingestEvent are stable references from Zustand
}
