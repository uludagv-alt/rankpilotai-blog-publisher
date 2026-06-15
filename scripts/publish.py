#!/usr/bin/env python3
"""
Publish new RankPilotAI blog posts to WordPress.

Reads blog-post HTML files from a directory (the read-only clone of the private
rankpilotai-marketing repo) and publishes any whose date is newer than the most
recent post already on WordPress. Date-based dedup makes it idempotent and
self-healing: a missed/failed day is picked up on the next run, and already
published posts are never re-published.

Runs from a PUBLIC repo so GitHub Actions is free (no spending-limit block). No
secrets live in this repo's code; WP credentials come from env (GitHub Secrets).

Usage: python3 publish.py <blog-posts-dir>
"""
import os
import re
import sys
import time
import json
from base64 import b64encode

import requests
from bs4 import BeautifulSoup, Comment

API = "https://rankpilotai.com/wp-json/wp/v2"
MAX_RETRIES, RETRY_DELAY = 3, 15

posts_dir = sys.argv[1] if len(sys.argv) > 1 else "content/blog-posts"

wp_user = os.environ["WP_USERNAME"]
wp_pass = os.environ["WP_APP_PASSWORD"]
auth_header = {"Authorization": "Basic " + b64encode(f"{wp_user}:{wp_pass}".encode()).decode()}

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def wp(method, url, **kw):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.request(method, url, timeout=60, **kw)
            if r.status_code in (200, 201):
                try:
                    return r.json(), r.status_code
                except ValueError:
                    print(f"    attempt {attempt}: {r.status_code} non-JSON (WAF/cache): {r.text[:160]}")
            else:
                print(f"    attempt {attempt}: HTTP {r.status_code} {r.text[:160]}")
        except requests.RequestException as e:
            print(f"    attempt {attempt}: {e}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
    return None, 0


def latest_wp_date():
    """Most recent published post date on WordPress, as 'YYYY-MM-DD' (or '' )."""
    try:
        r = requests.get(f"{API}/posts", params={"per_page": 1, "orderby": "date",
                         "order": "desc", "_fields": "date"}, timeout=30)
        if r.status_code == 200 and r.json():
            return r.json()[0]["date"][:10]
    except Exception as e:
        print(f"  could not read latest WP date: {e}")
    return ""


def upload_image(image_url, title):
    try:
        ir = requests.get(image_url, timeout=30)
        if ir.status_code != 200:
            return None
        ct = ir.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(ct, ".jpg")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
        data, _ = wp("POST", f"{API}/media",
                     headers={**auth_header, "Content-Type": ct,
                              "Content-Disposition": f'attachment; filename="{slug}{ext}"'},
                     data=ir.content)
        if data and "id" in data:
            print(f"    featured image id {data['id']}")
            return data["id"]
    except Exception as e:
        print(f"    image err {e}")
    return None


def publish_file(path, date):
    html = open(path, encoding="utf-8").read()
    soup = BeautifulSoup(html, "html.parser")

    t = soup.find("title") or soup.find("h1")
    title = t.get_text().strip() if t else os.path.basename(path)
    meta = soup.find("meta", attrs={"name": "description"})
    excerpt = meta["content"].strip() if meta and meta.get("content") else ""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:75]

    feat_url = None
    body_tag = soup.find("body")
    img = (body_tag.find("img") if body_tag else soup.find("img"))
    if img and img.get("src"):
        feat_url = img["src"]
        img.decompose()
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    body = soup.find("body")
    content = body.decode_contents() if body else str(soup)

    print(f"\n== {date}  {title}")
    feat_id = upload_image(feat_url, title) if feat_url else None

    post = {"title": title, "slug": slug, "content": content,
            "status": "publish", "comment_status": "open", "date": f"{date}T09:00:00"}
    if excerpt:
        post["excerpt"] = excerpt
    if feat_id:
        post["featured_media"] = feat_id

    data, status = wp("POST", f"{API}/posts",
                      headers={**auth_header, "Content-Type": "application/json"}, json=post)
    if data and ("link" in data or "id" in data):
        print(f"    PUBLISHED -> {data.get('link', data.get('id'))}")
        return True
    print(f"    FAILED (HTTP {status})")
    return False


def main():
    if not os.path.isdir(posts_dir):
        print(f"blog-posts dir not found: {posts_dir}")
        sys.exit(1)

    wp_latest = latest_wp_date()
    print(f"Latest post on WordPress: {wp_latest or '(none)'}")

    files = []
    for name in sorted(os.listdir(posts_dir)):
        if not name.endswith(".html"):
            continue
        m = DATE_RE.match(name)
        if not m:
            continue
        date = m.group(1)
        if not wp_latest or date > wp_latest:
            files.append((date, os.path.join(posts_dir, name)))

    if not files:
        print("Nothing new to publish. WordPress is up to date.")
        return

    print(f"{len(files)} new post(s) to publish: {[d for d, _ in files]}")
    failed = 0
    for date, path in files:
        if not publish_file(path, date):
            failed += 1

    print("")
    if failed:
        print(f"{failed} post(s) failed (will retry next run).")
        sys.exit(1)
    print(f"Done. Published {len(files)} post(s).")


if __name__ == "__main__":
    main()
