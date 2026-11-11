"use client";

import { createElement, useSyncExternalStore } from "react";

const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

export function utcTimeLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}

/** SSR and the first client render agree; local formatting begins after hydration. */
export function LocalTime({ value, format = "datetime" }: { value: string; format?: "datetime" | "date" | "time" }) {
  const mounted = useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
  const fallback = utcTimeLabel(value);
  const date = new Date(value);
  const text = mounted && fallback !== "Time unavailable" ? format === "date" ? date.toLocaleDateString() : format === "time" ? date.toLocaleTimeString() : date.toLocaleString() : fallback;
  return createElement("time", { dateTime: value, title: fallback }, text);
}
