# rankpilotai-blog-publisher

Publishes new RankPilotAI blog posts to https://rankpilotai.com on a daily schedule.

**Why this exists:** the blog content lives in the private `rankpilotai-marketing` repo, whose own publish workflow fails because the account's GitHub Actions spending limit is exhausted (private-repo minutes). Public repos get unlimited free Actions, so the publishing runs from here instead.

**No secrets in this repo's code.** Everything sensitive is a GitHub Actions secret:
- `MARKETING_SSH_KEY` — read-only deploy key for the private `rankpilotai-marketing` repo (lets the workflow clone the blog HTML).
- `WP_USERNAME` / `WP_APP_PASSWORD` — WordPress REST API credentials.

**Flow** (`.github/workflows/publish-blog.yml`, daily 06:00 UTC + manual `workflow_dispatch`):
1. Clone `rankpilotai-marketing` (read-only) to get `blog-posts/*.html`.
2. Read the latest published post date from the WordPress REST API.
3. Publish any post whose filename date is newer (date-based, idempotent — never re-publishes, self-heals missed days).

The writer (daily job that generates `blog-posts/YYYY-MM-DD-*.html` and pushes to `rankpilotai-marketing`) is unchanged.
