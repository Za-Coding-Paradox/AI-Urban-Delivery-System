// src/hooks/useSimulation.ts
//
// High-level hook for controlling the simulation.
// Wraps the API calls and feeds results into the store.
// Components call these functions directly — no prop drilling.

import { useState, useCallback } from "react";
import * as api from "@/lib/api";
import { useStore } from "@/store";
import type { AlgorithmId, CityProfile } from "@/types";

interface UseSimulationReturn {
  // Profile management
  generateProfile:  (seed: number, name?: string) => Promise<CityProfile | null>;
  loadProfile:      (name: string) => Promise<CityProfile | null>;
  saveProfile:      (name: string, profile: CityProfile) => Promise<boolean>;
  listProfiles:     () => Promise<string[]>;

  // Run control
  startRun:         (options?: StartRunOptions) => Promise<string | null>;
  resetRun:         () => void;

  // State
  loading:          boolean;
  error:            string | null;
  clearError:       () => void;
}

interface StartRunOptions {
  profileName?:  string;
  profile?:      CityProfile;
  algorithmIds?: AlgorithmId[];
}

export function useSimulation(): UseSimulationReturn {
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const store = useStore();

  const clearError = useCallback(() => setError(null), []);

  // ── profile management ───────────────────────────────────────────────────

  const generateProfile = useCallback(
    async (seed: number, name?: string): Promise<CityProfile | null> => {
      setLoading(true);
      setError(null);
      try {
        const profile = await api.generateProfile({ seed, name });
        store.setProfile(profile);
        return profile;
      } catch (err) {
        setError((err as Error).message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [store]
  );

  const loadProfile = useCallback(
    async (name: string): Promise<CityProfile | null> => {
      setLoading(true);
      setError(null);
      try {
        const profile = await api.getProfile(name);
        store.setProfile(profile);
        return profile;
      } catch (err) {
        setError((err as Error).message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [store]
  );

  const saveProfile = useCallback(
    async (name: string, profile: CityProfile): Promise<boolean> => {
      setLoading(true);
      setError(null);
      try {
        await api.saveProfile(name, profile);
        return true;
      } catch (err) {
        setError((err as Error).message);
        return false;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const listProfiles = useCallback(async (): Promise<string[]> => {
    try {
      return await api.listProfiles();
    } catch (err) {
      setError((err as Error).message);
      return [];
    }
  }, []);

  // ── run control ──────────────────────────────────────────────────────────

  const startRun = useCallback(
    async (options: StartRunOptions = {}): Promise<string | null> => {
      setLoading(true);
      setError(null);
      store.resetRun();

      try {
        const response = await api.startRun({
          profile_name:  options.profileName,
          profile:       options.profile ?? store.profile ?? undefined,
          algorithm_ids: options.algorithmIds,
        });

        store.setRunId(response.run_id);
        store.setRunStatus("running");
        return response.run_id;
      } catch (err) {
        setError((err as Error).message);
        store.setRunStatus("failed");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [store]
  );

  const resetRun = useCallback(() => {
    store.resetRun();
    setError(null);
  }, [store]);

  return {
    generateProfile,
    loadProfile,
    saveProfile,
    listProfiles,
    startRun,
    resetRun,
    loading,
    error,
    clearError,
  };
}
