import { describe, expect, it } from "vitest";
import { ApiError, buildQuery, toApiError } from "@/services/api";

describe("toApiError", () => {
  it("reads the backend error envelope", () => {
    const e = toApiError(422, { error: { code: "validation_error", message: "bad", details: [1] } });
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.message, e.details]).toEqual([422, "validation_error", "bad", [1]]);
  });
  it("falls back when the body is not an envelope", () => {
    const e = toApiError(500, null);
    expect(e.code).toBe("http_error");
    expect(e.message).toContain("500");
  });
});

describe("buildQuery", () => {
  it("skips empty values and encodes the rest", () => {
    expect(buildQuery({ limit: 5, q: "a b", domain: "", x: undefined, y: null })).toBe("?limit=5&q=a+b");
    expect(buildQuery({})).toBe("");
  });
});
