#!/usr/bin/env python3
"""
youtube_upload.py - upload a finished MRGoodGuy Short with the YouTube Data API v3.

ONE-TIME SETUP (on your own PC, once):
  pip install google-api-python-client google-auth-oauthlib
  python youtube_upload.py --auth --client-secrets client_secret.json --token token.json
  -> a browser window opens, sign in with the MRGoodGuy Google account, allow access.
     token.json is written next to the script. Keep it private (never commit it).

DAILY USE (what the agent runs):
  python youtube_upload.py --video short.mp4 --meta package.json \
      --thumbnail thumbnail.jpg --token token.json --client-secrets client_secret.json \
      [--publish-at 2026-11-11T16:00:00+01:00] [--privacy public|unlisted|private] [--comment] [--dry-run]

package.json needs: "title", "description", "tags" (list). Optional: "pinned_comment",
"category_id" (default 27 Education), "synthetic_media" (true only for realistic AI people/events).

Output: one JSON line on stdout, e.g.
  {"ok": true, "video_id": "...", "url": "https://youtube.com/shorts/...", "privacy": "public", "locked_private": false, ...}

IMPORTANT: Google Cloud projects created after 28 Jul 2020 that have NOT passed the YouTube API
compliance audit get every upload locked to PRIVATE (it cannot be made public later). The script
detects this and reports "locked_private": true so the agent can fall back to the Chrome upload.
"""
import argparse
import json
import os
import random
import sys
import time

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",     # videos.insert
    "https://www.googleapis.com/auth/youtube.force-ssl",  # thumbnails.set, comments, videos.list(mine)
]
RETRY_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 8


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load_meta(path):
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    title = (m.get("title") or "").strip()
    if not title:
        raise SystemExit("package.json: 'title' is required")
    if len(title) > 100:
        raise SystemExit(f"title is {len(title)} chars; YouTube allows 100 (aim for <= 50)")
    desc = m.get("description", "")
    if len(desc.encode("utf-8")) > 5000:
        raise SystemExit("description is over 5000 bytes")
    tags = [t.strip() for t in m.get("tags", []) if t and t.strip()]
    # YouTube rejects tags containing < or > and caps the combined length at ~500 chars
    tags = [t.replace("<", "").replace(">", "") for t in tags]
    while tags and sum(len(t) + 2 for t in tags) > 480:
        tags.pop()
    return {
        "title": title,
        "description": desc,
        "tags": tags,
        "category_id": str(m.get("category_id", "27")),
        "synthetic": bool(m.get("synthetic_media", False)),
        "comment": (m.get("pinned_comment") or "").strip(),
    }


def get_credentials(client_secrets, token_path, interactive=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            return creds
        except Exception as e:  # invalid_grant = token revoked/expired (7-day Testing mode!)
            if not interactive:
                raise SystemExit(f"token refresh failed ({e}). Re-run with --auth on your PC. "
                                 "If this happens every 7 days, set the OAuth consent screen to 'In production'.")
    if not interactive:
        raise SystemExit("no valid token. Run once with --auth on your PC.")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    log(f"saved {token_path}")
    return creds


def resumable_upload(request):
    from googleapiclient.errors import HttpError
    response, retry = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                log(f"uploaded {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in RETRY_STATUS:
                err = f"server error {e.resp.status}"
            else:
                raise
        except (ConnectionError, TimeoutError, OSError) as e:
            err = f"network error {e}"
        else:
            continue
        retry += 1
        if retry > MAX_RETRIES:
            raise SystemExit(f"giving up after {MAX_RETRIES} retries: {err}")
        wait = min(64, 2 ** retry) * random.random() + 1
        log(f"{err}; retry {retry} in {wait:.1f}s")
        time.sleep(wait)
    return response


def main():
    ap = argparse.ArgumentParser(description="Upload a Short via YouTube Data API v3")
    ap.add_argument("--auth", action="store_true", help="one-time interactive sign-in, writes --token")
    ap.add_argument("--client-secrets", default="client_secret.json")
    ap.add_argument("--token", default="token.json")
    ap.add_argument("--video")
    ap.add_argument("--meta", help="package.json with title/description/tags")
    ap.add_argument("--thumbnail")
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--publish-at", help="ISO 8601 time to go public (video is uploaded private until then)")
    ap.add_argument("--comment", action="store_true", help="post package.pinned_comment as the first comment")
    ap.add_argument("--no-notify", action="store_true", help="do not notify subscribers")
    ap.add_argument("--dry-run", action="store_true", help="validate inputs and print the request, upload nothing")
    a = ap.parse_args()

    if a.auth:
        get_credentials(a.client_secrets, a.token, interactive=True)
        print(json.dumps({"ok": True, "token": a.token}))
        return

    if not (a.video and a.meta):
        ap.error("--video and --meta are required (or use --auth)")
    if not os.path.isfile(a.video):
        raise SystemExit(f"video not found: {a.video}")
    size_mb = os.path.getsize(a.video) / 1e6
    m = load_meta(a.meta)

    status = {
        "privacyStatus": "private" if a.publish_at else a.privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": m["synthetic"],
        "embeddable": True,
        "license": "youtube",
    }
    if a.publish_at:
        status["publishAt"] = a.publish_at  # must be private + never published before
    body = {
        "snippet": {
            "title": m["title"],
            "description": m["description"],
            "tags": m["tags"],
            "categoryId": m["category_id"],
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status,
    }

    if a.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "video_mb": round(size_mb, 2), "body": body,
                          "thumbnail": a.thumbnail, "comment": m["comment"] if a.comment else None},
                         ensure_ascii=False))
        return

    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    creds = get_credentials(a.client_secrets, a.token)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    media = MediaFileUpload(a.video, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media,
                             notifySubscribers=not a.no_notify)
    log(f"uploading {a.video} ({size_mb:.1f} MB)...")
    resp = resumable_upload(req)
    vid = resp["id"]
    result = {"ok": True, "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
              "requested_privacy": status["privacyStatus"], "publish_at": a.publish_at}

    # thumbnail (needs a phone-verified channel; Shorts feed shows the video anyway)
    if a.thumbnail and os.path.isfile(a.thumbnail):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(a.thumbnail)).execute()
            result["thumbnail"] = "set"
        except HttpError as e:
            result["thumbnail"] = f"skipped ({e.resp.status}: verify the channel by phone to allow custom thumbnails)"

    # read back the real status: unaudited API projects are forced to private
    time.sleep(5)
    info = yt.videos().list(part="status", id=vid).execute().get("items", [{}])[0].get("status", {})
    result["privacy"] = info.get("privacyStatus")
    result["upload_status"] = info.get("uploadStatus")
    want_public = a.privacy in ("public", "unlisted") and not a.publish_at
    result["locked_private"] = bool(want_public and info.get("privacyStatus") == "private")
    if result["locked_private"]:
        result["note"] = ("Video was forced to PRIVATE: this Google Cloud project has not passed the "
                          "YouTube API audit. Delete it in Studio and upload via Chrome instead.")

    if a.comment and m["comment"] and not result["locked_private"]:
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid,
                "topLevelComment": {"snippet": {"textOriginal": m["comment"]}}}}).execute()
            result["comment"] = "posted (pin it in Studio: the API cannot pin)"
        except HttpError as e:
            result["comment"] = f"failed ({e.resp.status})"

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
