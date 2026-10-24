// Run with: npm test (node --test; Node 22.18+ runs TypeScript directly)
import assert from "node:assert/strict";
import { test } from "node:test";
import { citedSources, domain, sourcesByEvidence } from "./sources.ts";

const run = {
  steps: [
    { evidence_id: "E3", output: { verdict: "infeasible" } },
    {
      evidence_id: "E6",
      output: {
        sources: [
          { title: "Clothing Labelling Requirements by Country", url: "https://www.collectivestudioltd.com/journal/labelling" },
          { title: "", url: "https://eur-lex.europa.eu/eli/reg/2011/1007" },
          { title: "not a link", url: "ftp://example.org/x" },
        ],
      },
    },
    { evidence_id: "E7", output: { sources: [{ title: "Again", url: "https://www.collectivestudioltd.com/journal/labelling" }] } },
    { evidence_id: null, output: { sources: [{ title: "No id", url: "https://ignored.example" }] } },
  ],
} as unknown as Parameters<typeof sourcesByEvidence>[0];

test("maps each web-search evidence id to its http(s) sources", () => {
  const map = sourcesByEvidence(run);
  assert.deepEqual([...map.keys()], ["E6", "E7"]);
  assert.equal(map.get("E6")?.length, 2);
});

test("a finding gets the sources of the evidence it cites, without duplicates", () => {
  const map = sourcesByEvidence(run);
  const links = citedSources(["E3", "E6", "E7", "https://direct.example/rule"], map);
  assert.deepEqual(
    links.map((s) => s.url),
    ["https://www.collectivestudioltd.com/journal/labelling", "https://eur-lex.europa.eu/eli/reg/2011/1007"],
  );
  assert.deepEqual(citedSources(["E3"], map), []);
});

test("domain drops www and survives a bad URL", () => {
  assert.equal(domain("https://www.collectivestudioltd.com/journal"), "collectivestudioltd.com");
  assert.equal(domain("not a url"), "not a url");
});
