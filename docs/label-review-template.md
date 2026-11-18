# Label review template

Purpose: let a person other than the author re-grade the held-out labels in
`data/benchmark_problems/heldout_labels.json`. As of phase 6 no such review has happened. Every label is
`author_labelled` and `independent_review: none`.

## Steps for a reviewer

1. Read `docs/labelling-guide.md`. Do not run the matcher or read any evaluation output while grading.
2. Copy `data/benchmark_problems/review_template.json` to a new file. Do not edit the template in place.
3. For each row, open the query (`query_id`) and the candidate system (`system_id`) in the data folders. Decide a grade
   (2, 1 or 0) from the guide and fill in:
   - `reviewer_grade`: 0, 1 or 2
   - `agree`: true if your grade equals `author_grade`, otherwise false
   - `role_mapping_correct`: true or false, judged against the `role_mapping` in the label file (use null if grade is 0 and the label has no mapping)
   - `comment`: free text, including any unlabelled candidate you think is a genuine analog
   - `reviewer_name` and `review_date`
4. Save and run `python3 scripts/compare_reviews.py path/to/filled_review.json` to get percent agreement, Cohen's kappa
   and the list of disputed labels.

## Rules

- The author labels are never overwritten by the review. Disputes are resolved by a logged amendment in
  `docs/benchmark-notes.md`, not by editing the file silently.
- If kappa is below 0.6 the guide is ambiguous. Fix the guide before relabelling.
