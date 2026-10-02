"use client";

import { useCallback, useState } from "react";
import { isNumberArray, readSession, writeSession } from "./utils";

/**
 * A set of completed step numbers, remembered in sessionStorage under `key`.
 * Purely client-side: ticking a box never calls the API.
 */
export function useStoredProgress(key: string): [ReadonlySet<number>, (step: number) => void] {
  const [done, setDone] = useState<ReadonlySet<number>>(() => new Set(readSession(key, isNumberArray) ?? []));

  const toggle = useCallback(
    (step: number) => {
      setDone((current) => {
        const next = new Set(current);
        if (next.has(step)) next.delete(step);
        else next.add(step);
        writeSession(key, [...next].sort((a, b) => a - b));
        return next;
      });
    },
    [key],
  );

  return [done, toggle];
}

export function progressKey(analysisId: string, list: "first30" | "path"): string {
  return `repolens:progress:${analysisId}:${list}`;
}
