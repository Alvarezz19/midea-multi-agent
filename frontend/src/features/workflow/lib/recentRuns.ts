import type { CreateRunResponse } from "../../../types/workflow";

const STORAGE_KEY = "midea.workflow.recentRuns";

export interface RecentRun {
  thread_id: string;
  attempt_id: string;
  title: string;
  user_query: string;
  created_at: string;
}

export function loadRecentRuns(): RecentRun[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as RecentRun[]) : [];
  } catch {
    return [];
  }
}

export function saveRecentRun(response: CreateRunResponse, title: string, userQuery: string) {
  const next: RecentRun = {
    thread_id: response.thread_id,
    attempt_id: response.attempt_id,
    title,
    user_query: userQuery,
    created_at: new Date().toISOString()
  };
  const merged = [
    next,
    ...loadRecentRuns().filter((item) => item.thread_id !== next.thread_id || item.attempt_id !== next.attempt_id)
  ].slice(0, 8);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
}
