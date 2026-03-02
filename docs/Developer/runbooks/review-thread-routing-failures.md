# Review Thread Routing Failures

## Scope

Incident response for failures to post replies into PR review comment threads.

## Detection Signals

- `CommentRoutingError` with missing review-thread metadata.
- Job transitions to `blocked` after review-thread reply attempt.
- Missing in-thread reply where source context is a review comment.

## Immediate Containment

1. Keep strict routing behavior enabled (`require_review_thread_reply: true`).
2. Do not enable top-level fallback as an emergency workaround.
3. Continue in `shadow` mode if repeated failures affect active throughput.

## Diagnosis

1. Confirm ingress event details include:
   - `thread_id`
   - `review_comment_id`
   - `path`
   - `line`
   - `side`
2. Verify timeline mapping preserved thread metadata.
3. Verify `CommentRouter` target classification is `pr_review_thread`.
4. Verify GitHub API reply call uses `post_pull_review_comment_reply`.

## Remediation

1. Fix metadata extraction in timeline or scanner mapping path.
2. Add or update deterministic tests for the failing metadata shape.
3. Validate with:
   - `pytest -q`
   - targeted review-thread routing tests.

## Exit Criteria

- Thread-reply tests are green.
- Live sandbox scenario posts reply into the same review thread.
- No top-level fallback messages were emitted for thread contexts.
