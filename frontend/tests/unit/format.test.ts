import { describe, expect, it } from "vitest";
import {
  DEFAULT_WEIGHTS, csvCell, formatScore, isTerminal, numericEntries, parseJsonObject, titleCase, toCsv, weightsTotal, weightsValid,
} from "@/lib/format";

describe("weights", () => {
  it("default weights total 100 and are valid", () => {
    expect(weightsTotal(DEFAULT_WEIGHTS)).toBe(100);
    expect(weightsValid(DEFAULT_WEIGHTS)).toBe(true);
  });
  it("rejects totals other than 100, negatives and NaN", () => {
    expect(weightsValid({ ...DEFAULT_WEIGHTS, functional: 30 })).toBe(false);
    expect(weightsValid({ ...DEFAULT_WEIGHTS, functional: -5, relationship: 55 })).toBe(false);
    expect(weightsValid({ ...DEFAULT_WEIGHTS, functional: Number.NaN })).toBe(false);
  });
});

describe("formatting", () => {
  it("formats scores and missing values", () => {
    expect(formatScore(36.4847)).toBe("36.5");
    expect(formatScore(null)).toBe("n/a");
    expect(formatScore(Number.NaN)).toBe("n/a");
  });
  it("title cases keys", () => {
    expect(titleCase("structural_dna")).toBe("Structural dna");
  });
  it("detects terminal statuses", () => {
    expect(isTerminal("done")).toBe(true);
    expect(isTerminal("running")).toBe(false);
  });
});

describe("csv", () => {
  it("quotes commas, quotes and newlines", () => {
    expect(csvCell('a,"b"')).toBe('"a,""b"""');
    expect(csvCell("x\ny")).toBe('"x\ny"');
  });
  it("neutralises formula injection", () => {
    expect(csvCell("=SUM(A1)")).toBe("'=SUM(A1)");
    expect(csvCell("@cmd")).toBe("'@cmd");
  });
  it("builds rows in column order", () => {
    expect(toCsv([{ a: 1, b: "x" }], ["b", "a"])).toBe("b,a\nx,1\n");
  });
});

describe("parseJsonObject", () => {
  it("accepts objects", () => {
    expect(parseJsonObject('{"a":1}')).toEqual({ ok: true, value: { a: 1 } });
  });
  it("rejects arrays, scalars and invalid JSON", () => {
    expect(parseJsonObject("[1]").ok).toBe(false);
    expect(parseJsonObject("3").ok).toBe(false);
    expect(parseJsonObject("{").ok).toBe(false);
  });
});

describe("numericEntries", () => {
  it("keeps only finite top level numbers", () => {
    expect(numericEntries({ a: 1, b: "x", c: Number.NaN, d: { e: 2 }, f: 0 })).toEqual([
      { name: "a", value: 1 },
      { name: "f", value: 0 },
    ]);
    expect(numericEntries(null)).toEqual([]);
  });
});
