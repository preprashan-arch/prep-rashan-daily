# Prep-Rashan reply checker (owner, 16 Nov 2026 13:04 / 13:08: "Develop a individual checker for follow to answers every hour so
# that no reply is missed.") – loaded in the Composio workbench by its own hourly scheduled run (HH:20), separate from posting:
#   exec(urllib.request.urlopen("https://raw.githubusercontent.com/preprashan-arch/prep-rashan-daily/main/reply_check.py?t=%d" % time.time()).read().decode())
#   output = json.dumps(sweep())           # -> {"unanswered": [...], "checked": {...}, "errors": [...]}
# It reads EVERY post of the last DAYS days on Instagram, Facebook and YouTube (+ Telegram discussion messages after OFFSET)
# and lists each viewer comment that has no reply from us. The run then replies to each one (reply_ig / reply_fb / reply_yt /
# reply_tg) and records it (boost.py replied). Never wrap the thread pools in contextlib.redirect_stdout (16 Nov 2026).
import time
import datetime as _dt, json as _json
from concurrent.futures import ThreadPoolExecutor as _TPE

RC_PAGE = "1465479556641770"; RC_IG_USER = "prep_rashan"; RC_YT_CHANNEL = "UCSIYewCD5ru2dFNBJ373IPQ"
RC_TG_CHAT = "@Prep_Rashan"; RC_TG_GROUP = -1004345307059

def _since(days): return (_dt.datetime.utcnow() - _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")

def _ig_media(days):
    out, after, since = [], None, _since(days)
    for _ in range(15):
        qp = {"fields": "id,permalink,timestamp,comments_count", "limit": "100"}
        if after: qp["after"] = after
        r, e = proxy_execute("GET", "/me/media", "instagram", query_params=qp)
        if e or not isinstance(r, dict): raise RuntimeError(f"instagram media list: {str(e)[:200]}")
        d = r.get("data", []); out += d
        if not d or d[-1]["timestamp"] < since: break
        after = ((r.get("paging") or {}).get("cursors") or {}).get("after")
        if not after: break
    return [m for m in out if m["timestamp"] >= since]

def _is_us_ig(c): return c.get("username") == RC_IG_USER or (c.get("from") or {}).get("username") == RC_IG_USER

def _ig_comments(m):
    r, e = run_composio_tool("INSTAGRAM_GET_IG_MEDIA_COMMENTS", {"ig_media_id": m["id"], "fields": "id,text,username,from,timestamp,replies{id,username,from,text,timestamp}"})
    if e: return [], [f"instagram {m['id']}: {str(e)[:120]}"]
    cs = (r.get("data") or {}).get("data") or []
    out = []
    # Instagram lists replies inside a thread as top-level items too: a comment counts as answered when we replied after it
    # in its thread (under it, or under the comment it belongs to)
    threads = {}
    for c in cs:
        for x in ((c.get("replies") or {}).get("data") or []): threads[x["id"]] = c["id"]
    our_reply_times = {}
    for c in cs:
        reps = (c.get("replies") or {}).get("data") or []
        ts = [x.get("timestamp", "") for x in reps if _is_us_ig(x)]
        # replies' from/username can come back empty – look the reply up in the top-level list, which carries them
        for x in reps:
            top = next((y for y in cs if y["id"] == x["id"]), None)
            if top and _is_us_ig(top): ts.append(top.get("timestamp", ""))
        if ts: our_reply_times[c["id"]] = max(ts)
    for c in cs:
        if _is_us_ig(c): continue
        root = threads.get(c["id"], c["id"])
        if our_reply_times.get(c["id"], "") >= c.get("timestamp", "z") or our_reply_times.get(root, "") >= c.get("timestamp", "z"): continue
        out.append(dict(platform="instagram", post=m["id"], link=m.get("permalink"), comment_id=c["id"],
                        reply_to=root, user=(c.get("from") or {}).get("username") or c.get("username"),
                        text=c.get("text", ""), time=c.get("timestamp", "")))
    return out, []

def _fb_objects(days):
    ids, errs, since = [], [], _since(days)
    for slug in ("FACEBOOK_GET_PAGE_POSTS", "FACEBOOK_GET_PAGE_VIDEOS"):
        after = None
        for _ in range(10):
            a = {"page_id": RC_PAGE, "limit": 100}
            if after: a["after"] = after
            r, e = run_composio_tool(slug, a)
            if e: errs.append(f"{slug}: {str(e)[:120]}"); break
            d = r.get("data") or {}; items = d.get("data") or []
            ids += [x["id"] for x in items if x.get("created_time", "") >= since]
            after = ((d.get("paging") or {}).get("cursors") or {}).get("after")
            if not after or not items or items[-1].get("created_time", "") < since: break
    return list(dict.fromkeys(ids)), errs

def _fb_comments(pid):
    r, e = run_composio_tool("FACEBOOK_GET_COMMENTS", {"object_id": pid, "fields": "id,message,created_time,from,comments{from,created_time}"})
    if e:
        return [], ([] if "does not exist" in str(e) else [f"facebook {pid}: {str(e)[:120]}"])
    out = []
    for c in (r.get("data") or {}).get("data") or []:
        if (c.get("from") or {}).get("id") == RC_PAGE: continue
        reps = (c.get("comments") or {}).get("data") or []
        if any((x.get("from") or {}).get("id") == RC_PAGE for x in reps): continue
        out.append(dict(platform="facebook", post=pid, link=f"https://www.facebook.com/{pid}", comment_id=c["id"], reply_to=c["id"],
                        user=(c.get("from") or {}).get("name"), text=c.get("message", ""), time=c.get("created_time", "")))
    return out, []

def _yt_threads(days):
    out, errs, token, since = [], [], None, _since(days)
    for _ in range(10):
        a = {"allThreadsRelatedToChannelId": RC_YT_CHANNEL, "part": "snippet,replies", "maxResults": 100}
        if token: a["pageToken"] = token
        # 22 Nov 2026: YouTube refuses some comment-thread pages at random ("Access forbidden") – the same call works
        # on a retry or with another page size, so try up to 4 times (100, 50, 50, 20) before calling it an error
        for mr in (100, 50, 50, 20):
            a["maxResults"] = mr
            r, e = run_composio_tool("YOUTUBE_LIST_COMMENT_THREADS", a)
            if not e: break
            time.sleep(2)
        if e: errs.append(f"youtube: {str(e)[:160]}"); break
        d = r.get("data") or {}
        for t in d.get("items", []):
            s = t["snippet"]["topLevelComment"]["snippet"]
            if s.get("publishedAt", "") < since: continue
            if (s.get("authorChannelId") or {}).get("value") == RC_YT_CHANNEL: continue
            reps = (t.get("replies") or {}).get("comments") or []
            if any((x["snippet"].get("authorChannelId") or {}).get("value") == RC_YT_CHANNEL for x in reps): continue
            out.append(dict(platform="youtube", post=s.get("videoId"), link=f"https://youtu.be/{s.get('videoId')}", comment_id=t["id"],
                            reply_to=t["snippet"]["topLevelComment"]["id"], user=s.get("authorDisplayName"),
                            text=s.get("textOriginal", ""), time=s.get("publishedAt", "")))
        token = d.get("nextPageToken")
        if not token: break
    return out, errs

TG_POLLS = {}      # owner 23 Nov 2026 02:21 ("Okay"): the latest state of every poll our bot sent (Mains vote poll) – sweep()["polls"]
def _tg(offset):
    r, e = run_composio_tool("TELEGRAM_GET_UPDATES", {"offset": offset, "allowed_updates": ["message", "poll"]})
    if e: return [], [f"telegram: {str(e)[:120]}"], offset
    rs = ((r.get("data") or {}).get("result") or [])
    out = []
    for u in rs:
        p = u.get("poll")
        if p:      # bots receive the new state of polls they sent: option texts with voter counts
            TG_POLLS[p.get("id")] = dict(question=p.get("question", ""), total=p.get("total_voter_count", 0),
                                         options=[(o.get("text", ""), o.get("voter_count", 0)) for o in p.get("options", [])])
            continue
        m = u.get("message") or {}
        if m.get("is_automatic_forward") or (m.get("sender_chat") or {}).get("username") == RC_TG_CHAT.lstrip("@"): continue
        if m.get("from", {}).get("is_bot"): continue
        out.append(dict(platform="telegram", post=(m.get("reply_to_message") or {}).get("message_id"), link=None,
                        comment_id=m.get("message_id"), reply_to=m.get("message_id"), chat=(m.get("chat") or {}).get("id"),
                        user=(m.get("from") or {}).get("username") or (m.get("from") or {}).get("first_name"),
                        text=m.get("text") or m.get("caption") or "", time=_dt.datetime.utcfromtimestamp(m.get("date", 0)).isoformat()))
    nxt = max([u["update_id"] for u in rs] + [offset - 1]) + 1
    return out, [], nxt

def sweep(days=10, tg_offset=None, youtube=True):
    """-> dict(unanswered=[...], checked={platform: count}, errors=[...], tg_next=offset)"""
    U, E, C = [], [], {}
    try:
        media = [m for m in _ig_media(days) if m.get("comments_count", 0) > 0]
        with _TPE(12) as ex: res = list(ex.map(_ig_comments, media))
        for o, e in res: U += o; E += e
        C["instagram_posts_with_comments"] = len(media)
    except Exception as ex: E.append(f"instagram: {ex}"[:200])
    ids, e = _fb_objects(days); E += e
    with _TPE(12) as ex: res = list(ex.map(_fb_comments, ids))
    for o, e in res: U += o; E += e
    C["facebook_posts"] = len(ids)
    if youtube:
        o, e = _yt_threads(days); U += o; E += e; C["youtube_threads_unanswered"] = len(o)
    nxt = tg_offset
    if tg_offset is not None:
        o, e, nxt = _tg(tg_offset); U += o; E += e; C["telegram_messages"] = len(o)
    U.sort(key=lambda x: x.get("time", ""))
    return dict(unanswered=U, checked=C, errors=E, tg_next=nxt, polls=dict(TG_POLLS))

def reply_ig(comment_id, text):
    r, e = run_composio_tool("INSTAGRAM_POST_IG_COMMENT_REPLIES", {"ig_comment_id": comment_id, "message": text}); return e or (r.get("data") or {}).get("id")
def reply_fb(comment_id, text):
    r, e = run_composio_tool("FACEBOOK_CREATE_COMMENT", {"object_id": comment_id, "message": text}); return e or (r.get("data") or {}).get("id")
def reply_yt(parent_id, text):
    # 22 Nov 2026: the Composio tool YOUTUBE_REPLY_TO_COMMENT is gone (404 ToolNotFound) – the YouTube API directly
    r, e = proxy_execute("POST", "https://www.googleapis.com/youtube/v3/comments", "youtube", query_params={"part": "snippet"},
                         body={"snippet": {"parentId": parent_id, "textOriginal": text}})
    return e or (r or {}).get("id")
def reply_tg(chat, message_id, text):
    r, e = run_composio_tool("TELEGRAM_SEND_MESSAGE", {"chat_id": chat, "text": text, "reply_to_message_id": message_id})
    return e or ((r.get("data") or {}).get("result") or {}).get("message_id")
