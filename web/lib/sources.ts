import type { AgentRun } from "./api";

export type Source = { title: string; url: string };

/** Web sources (Tavily) behind each evidence id, from a risk run's tool steps. */
export function sourcesByEvidence(run: Pick<AgentRun, "steps">): Map<string, Source[]> {
  const map = new Map<string, Source[]>();
  for (const step of run.steps) {
    const sources = step.output?.sources;
    if (step.evidence_id && Array.isArray(sources)) {
      map.set(
        step.evidence_id,
        (sources as Partial<Source>[]).filter(
          (s): s is Source => typeof s.url === "string" && s.url.startsWith("http"),
        ),
      );
    }
  }
  return map;
}

/** The web sources a flag or finding cites through its evidence ids, without duplicates. */
export function citedSources(evidence: string[], sources: Map<string, Source[]>, limit = 4): Source[] {
  const seen = new Set<string>();
  const links: Source[] = [];
  for (const item of evidence) {
    for (const source of item.startsWith("http") ? [] : sources.get(item) ?? []) {
      if (!seen.has(source.url)) {
        seen.add(source.url);
        links.push(source);
      }
    }
  }
  return links.slice(0, limit);
}

export function domain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
