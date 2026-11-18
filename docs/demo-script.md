# Flagship demo script

Scenario: reduce the thickness of copper or silver strip by passing it between rolls. The scenario is demo only. Material parameters are recalled, labelled and unverified (not checked against any source), and the simulation shows how the method works, not how to run a real mill.

## Offline check of the engine (works today)
```bash
python3 scripts/run_demo.py
```
It prints the ranked cross-domain matches, the derived concepts with their constraint checks and the hypotheses with their seeded validation outcomes. Output is also written to `data/demo/sample_investigation.json` and summarised in `docs/sample-discovery-report.md`.

## Walkthrough in the app (needs the full stack, UNVERIFIED)
1. Register an account at `/login`.
2. Open **New Discovery**. Title: `Reduce strip thickness`. Paste the statement from `data/demo/roller_problem.json`. Add the hard constraint `Roll force must not exceed 90 kN`.
3. Choose **Save problem**, then **Start discovery**. Uploads are optional. A text or CSV file shows a proposed structure for review.
4. On the investigation page, watch the nine stages complete. Progress comes from the server event stream.
5. Select **Structural extraction** to see the graph as JSON. Open **Structural DNA** to see the graph, filter nodes, switch to the table and export JSON or CSV.
6. Open **Discovery Universe**. The chart plots match score against domain distance. Show the breakdown of one match and point out its differences and limitations.
7. Open **Transformation Studio**. Read a concept, expand its constraint report and choose **Save as hypothesis**. A blocked concept cannot be saved.
8. Open **Hypothesis Arena**. Select up to three hypotheses to compare side by side. Record decisions and notes (kept in the browser) and export Markdown.
9. Open **Validation Lab**. Point at the baseline versus proposed chart, the win rate and the caveat that outcomes are simulation under stated assumptions. A hypothesis without an applicable experiment stays `untested`.
10. Back on the investigation page, open the **Edit and rerun** tab for the perception stage, change a value, save, and rerun the downstream stages. Later stages show as stale first, then recompute.
11. Choose **Export report (Markdown)**, then open **Discovery Archive** to download it again.

## Talking points
- Cross-domain only: same domain candidates are excluded from the search and listed as excluded.
- Every claim has a provenance label. Nothing is presented as proven.
- Scores are heuristic. Weights are configurable and must total 100.
