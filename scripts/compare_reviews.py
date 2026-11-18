#!/usr/bin/env python3
"""Compare a filled review file against the author grades: percent agreement, Cohen's kappa, disputed labels.

Usage: python3 scripts/compare_reviews.py path/to/filled_review.json

Rows with reviewer_grade null are skipped. Kappa is computed over the grades 0, 1, 2 (unweighted).
No independent review has happened as of phase 6, so this script has only been run on a synthetic file.
"""
import json
import sys


def cohen_kappa(a, b, categories=(0, 1, 2)):
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in categories)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def compare(doc):
    rows = [r for r in doc["rows"] if r.get("reviewer_grade") is not None]
    author = [int(r["author_grade"]) for r in rows]
    rev = [int(r["reviewer_grade"]) for r in rows]
    n = len(rows)
    agree = sum(x == y for x, y in zip(author, rev))
    disputed = [{"item_id": r["item_id"], "author_grade": r["author_grade"], "reviewer_grade": r["reviewer_grade"],
                 "comment": r.get("comment", "")} for r in rows if int(r["author_grade"]) != int(r["reviewer_grade"])]
    return {"rows_reviewed": n, "rows_total": len(doc["rows"]),
            "percent_agreement": round(100.0 * agree / n, 2) if n else None,
            "cohens_kappa": round(cohen_kappa(author, rev), 4) if n else None, "disputed": disputed}


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1]) as f:
        res = compare(json.load(f))
    print(f"reviewed {res['rows_reviewed']} of {res['rows_total']} rows")
    print(f"percent agreement: {res['percent_agreement']}")
    print(f"Cohen's kappa: {res['cohens_kappa']}")
    print("disputed labels:")
    for d in res["disputed"]:
        print(f"  {d['item_id']}: author {d['author_grade']} reviewer {d['reviewer_grade']} {d['comment']}")
    if not res["disputed"]:
        print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
