# Prep-Rashan Step 5 poster – runs INSIDE the Composio remote workbench (uses its helpers run_composio_tool,
# proxy_execute, upload_local_file). It is published on the main branch of the public repo
# preprashan-arch/prep-rashan-daily (no secrets in it) and loaded with:
#   import urllib.request; exec(urllib.request.urlopen(URL).read().decode())
#   print(post("<file>", "<post id>", {"YT_PPT": "...", ...}))
# Every function returns a dict: {"status": "done"|"pending"|"error", ...}. "pending" = call again later with the
# returned "resume" value (Reels still processing). Approved captions come from the day's manifest unchanged.
import datetime as dt, hashlib, html, json, os, re, shutil, time, urllib.request

RAWBASE = "https://raw.githubusercontent.com/preprashan-arch/prep-rashan-daily/"
PAGE_ID = "1465479556641770"; TG_CHAT = "@Prep_Rashan"; TG_LINK = "https://t.me/Prep_Rashan"
YT_CHANNEL = "https://www.youtube.com/channel/UCSIYewCD5ru2dFNBJ373IPQ"
_MAN = {}

def manifest(file):
    if file not in _MAN:
        _MAN[file] = json.loads(urllib.request.urlopen(RAWBASE + f"d/{file}/manifest.json?t={int(time.time())}", timeout=60).read())
    return _MAN[file]

def item(file, pid):
    x = next(x for x in manifest(file)["posts"] if x["id"] == pid)
    # owner, 14 Nov 2026 11:01: the Full MCQs with Explanations (Complete) video of editions from 13 Nov 2026 is uploaded the day
    # before (with its edition's Full MCQs video) private + publishAt = its own day 05:00 IST – same rule as run_due.exp_early_patch
    if x.get("platform") == "youtube" and x.get("kind_yt") == "complete" and x.get("deck") == "d2" and not x.get("publish_at") \
            and not file.startswith("Compilation_"):
        try: d = dt.datetime.strptime(file, "%d_%B_%Y").date()
        except ValueError: d = None
        if d and d >= dt.date(2026, 11, 13):
            ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
            x = dict(x, exp_early=True, privacyStatus="private",
                     publish_at=dt.datetime.combine(d + dt.timedelta(days=x["day"]), dt.time(5, 0), ist).isoformat(timespec="minutes"))
    return x

# Owner's standing rule (5 Nov 2026): the first line of EVERY post (captions and YouTube descriptions; not the Telegram
# link replies) is this standard line. Added here so it also reaches posts staged before the rule; never added twice.
STD_LINE = f"Telegram – Daily PDFs: {TG_LINK} | YouTube – Full Videos: {YT_CHANNEL}"

def with_std(text):
    # 8 Nov 2026 fix: Instagram/Facebook captions carry the links line as LINE 2 (hook first – owner's rule 5 Nov evening);
    # this used to add it again on top, so those posts showed the links line twice. Now it is added only when missing.
    text = (text or "").strip()
    # 9 Nov 2026 (owner): compilation posts carry "Telegram – Daily PDFs: …" + the direct video links instead of the channel
    # link – any line that already names the Telegram link means the post has its links line, so nothing is added
    return text if (STD_LINE in text or f"Telegram – Daily PDFs: {TG_LINK}" in text) else (STD_LINE + "\n\n" + text).strip()

def fill_links(text, links):
    """Owner's rule (4 Nov 2026): a YouTube link is given only once that video is actually on YouTube – a line whose video
    is not uploaded yet is left out (no channel link as a stand-in), and no 'GS-wise clips (Instagram)' line, so a post
    never carries several confusing links. The video link reaches Telegram as a reply once the video is up."""
    out = []
    for line in text.split("\n"):
        if "GS-wise clips (Instagram)" in line: continue
        miss = False
        for k in ("YT_PPT", "YT_MCQ", "YT_EXP"):
            if "{" + k + "}" in line:
                if (links or {}).get(k): line = line.replace("{" + k + "}", links[k])
                else: miss = True
        if not miss: out.append(line)
    text = "\n".join(out)
    while "\n\n\n" in text: text = text.replace("\n\n\n", "\n\n")
    return direct(with_std(text), _CUR.get("x"), links)

# ---- owner's rule (9 Nov 2026, "always make it a rule"): ANY link posted under any content opens that content directly –
# a video link opens the video (never the channel page), a PDF link opens the PDF (the Telegram message), and so on.
# The standard links line (channel links) stays (owner 9 Nov 2026 16:22) and the post's own content links are added under
# it (links: YT_PPT/YT_MCQ/YT_EXP, TG_DCA/TG_MCQ/TG_EXP, TG_COMP from run_due.content_links); a content link is added only
# once that content is posted.
import re as _re
_CUR = {}
_YT_CH = "https://www.youtube.com/channel/UCSIYewCD5ru2dFNBJ373IPQ"
def direct(text, x, links):
    if not x: return text
    links = links or {}; d = x.get("deck"); pl = x["platform"]
    pdf = links.get({"ppt": "TG_DCA", "top": "TG_DCA", "d1": "TG_MCQ", "d2": "TG_EXP", "comp": "TG_COMP"}.get(d, ""))
    if x.get("kind_yt") == "comp" or str(x.get("id", "")).startswith("c"): pdf = links.get("TG_COMP")   # compilation posts carry deck ppt/d1/d2 (10 Nov 2026)
    vid = None if d == "comp" else links.get({"ppt": "YT_PPT", "d1": "YT_MCQ", "d2": "YT_EXP"}.get(d, ""))
    if pl == "telegram" and x.get("kind") == "pdf": pdf = None              # the post IS the PDF
    if pl == "youtube" and x.get("kind_yt") in ("complete", "comp"): vid = None   # the post IS the video
    # owner 9 Nov 2026 16:22: "keep this as a rule beyond the link" – the standard links line (Telegram channel | YouTube
    # channel) STAYS as it is, and the post's own content links are added right under it (each opens the video / the PDF)
    add = [f"▶️ Video: {vid}"] if vid and vid not in text else []
    add += [f"📥 PDF: {pdf}"] if pdf and pdf not in text else []
    if not add: return text
    L = text.split("\n")
    k = next((n for n, l in enumerate(L) if l.startswith("Telegram – Daily PDFs:") or l.startswith("Telegram – PDFs:")), None)
    if k is None: return text
    L.insert(k + 1, " | ".join(add))
    text = "\n".join(L)
    return text

def fetch(entry, d="/tmp/pr"):
    os.makedirs(d, exist_ok=True); out = os.path.join(d, entry["name"])
    md5 = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()
    if os.path.exists(out) and (not entry.get("md5") or md5(out) == entry["md5"]): return out
    with open(out, "wb") as fh:
        for u in entry["urls"]:
            with urllib.request.urlopen(u, timeout=170) as r: shutil.copyfileobj(r, fh, 1 << 20)
    if entry.get("md5"): assert md5(out) == entry["md5"], "download checksum mismatch"
    return out

def s3key(entry):
    up, err = upload_local_file(fetch(entry))
    if err: raise RuntimeError(f"upload failed: {err}")
    return up["s3key"]

def _ok(res, err):
    if err: raise RuntimeError(str(err)[:500])
    return res

def _ig(method, path, body=None):
    r, e = proxy_execute(method, path, "instagram", body=body) if body is not None else proxy_execute(method, path, "instagram")
    if e: raise RuntimeError(f"instagram {path}: {str(e)[:400]}")
    if isinstance(r, dict) and "error" in r: raise RuntimeError(f"instagram {path}: {r['error']}")
    return r

def _ig_wait(cid, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        st = _ig("GET", f"/{cid}?fields=status_code,status").get("status_code")
        if st == "FINISHED": return True
        if st in ("ERROR", "EXPIRED"): raise RuntimeError(f"instagram container {cid} {st}")
        time.sleep(5)
    return False

def _ig_publish(cid):
    for i in range(6):
        try:
            mid = _ig("POST", "/me/media_publish", {"creation_id": cid})["id"]; break
        except RuntimeError as e:
            if "9007" in str(e) or "not ready" in str(e).lower(): time.sleep(5); continue
            raise
    else: raise RuntimeError("instagram: media not ready")
    link = _ig("GET", f"/{mid}?fields=permalink").get("permalink")
    return {"status": "done", "id": mid, "url": link}

def ig_carousel(x, links, dry=False):
    kids = [_ig("POST", "/me/media", {"image_url": e["urls"][0], "is_carousel_item": True})["id"] for e in x["urls"]]
    for k in kids: _ig_wait(k, 60)
    cid = _ig("POST", "/me/media", {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": fill_links(x["caption"], links)})["id"]
    ok = _ig_wait(cid, 60)
    if dry: return {"status": "dry", "container": cid, "finished": ok, "children": len(kids)}
    return _ig_publish(cid)

def ig_reel(x, links, resume=None, dry=False):
    body = {"media_type": "REELS", "video_url": x["urls"][0]["urls"][0], "caption": fill_links(x["caption"], links), "share_to_feed": True}
    if x.get("tag") == "pair" and x.get("thumb_url"): body["cover_url"] = x["thumb_url"]     # hook cover (P2, Option A 14 Nov 2026) – the question → answer pairs
    cid = resume or _ig("POST", "/me/media", body)["id"]
    if not _ig_wait(cid, 140): return {"status": "pending", "resume": cid}
    if dry: return {"status": "dry", "container": cid, "finished": True}
    return _ig_publish(cid)

def fb_carousel(x, links):
    res = _ok(*run_composio_tool("FACEBOOK_CREATE_MULTI_PHOTO_POST", {"page_id": PAGE_ID, "photo_urls": [e["urls"][0] for e in x["urls"]],
                                                                    "message": fill_links(x["caption"], links)}))
    pid = json.dumps(res); m = re.search(r'"(?:post_)?id"\s*:\s*"(\d+_\d+)"', pid)
    post_id = m.group(1) if m else None
    return {"status": "done", "id": post_id, "url": f"https://www.facebook.com/{post_id}" if post_id else None, "raw": pid[:300]}

def fb_video(x, links):
    e = x["urls"][0]
    args = {"page_id": PAGE_ID, "title": x.get("title", "")[:250], "description": fill_links(x["caption"], links)}
    if len(e["urls"]) == 1: args["file_url"] = e["urls"][0]
    else: args["video"] = {"name": e["name"], "mimetype": "video/mp4", "s3key": s3key(e)}
    res = _ok(*run_composio_tool("FACEBOOK_CREATE_VIDEO_POST", args)); s = json.dumps(res)
    m = re.search(r'"id"\s*:\s*"(\d+)"', s); vid = m.group(1) if m else None
    return {"status": "done", "id": vid, "url": f"https://www.facebook.com/{PAGE_ID}/videos/{vid}" if vid else None, "raw": s[:300]}

def reshare(c, dry=False):
    """owner's yes, 10 Nov 2026: on a day without a new edition re-share one of the week's best Reels on Instagram AND Facebook
    (c = one candidate from reshare.py plan: ig_id, caption, title). The video Instagram already holds is posted again."""
    src = _ig("GET", f"/{c['ig_id']}?fields=media_url,media_type").get("media_url")
    if not src: raise RuntimeError(f"instagram {c['ig_id']}: no media_url")
    if dry: return {"status": "dry", "media_url": src[:80]}
    cid = _ig("POST", "/me/media", {"media_type": "REELS", "video_url": src, "caption": c["caption"], "share_to_feed": True})["id"]
    ig = _ig_publish(cid) if _ig_wait(cid, 140) else {"status": "pending", "resume": cid}
    try:
        res = _ok(*run_composio_tool("FACEBOOK_CREATE_VIDEO_POST", {"page_id": PAGE_ID, "title": c.get("title", "")[:250],
                                                                    "description": c["caption"], "file_url": src}))
        m = re.search(r'"id"\s*:\s*"(\d+)"', json.dumps(res)); vid = m.group(1) if m else None
        fb = {"status": "done", "id": vid, "url": f"https://www.facebook.com/{PAGE_ID}/videos/{vid}" if vid else None}
    except Exception as e: fb = {"status": "error", "error": str(e)[:300]}
    return {"ig": ig, "fb": fb, "source": c["ig_id"]}

def story(ig_id, src=None, dry=False):
    """owner's yes, 12 Nov 2026: one Instagram Story a day at 7 PM – the day's best-performing Reel (most views so far)
    shared to Stories. The video Instagram already holds is posted again as a Story (Stories carry no caption)."""
    # 12 Nov 2026: Instagram refuses its own CDN media_url for Stories (container ERROR) – pass our file's URL (src)
    src = src or _ig("GET", f"/{ig_id}?fields=media_url,media_type").get("media_url")
    if not src: raise RuntimeError(f"instagram {ig_id}: no media_url")
    if dry: return {"status": "dry", "media_url": src[:80]}
    cid = _ig("POST", "/me/media", {"media_type": "STORIES", "video_url": src})["id"]
    r = _ig_publish(cid) if _ig_wait(cid, 140) else {"status": "pending", "resume": cid}
    return dict(r, source=ig_id)

def tg_html(text):
    parts = re.split(r"(</?b>)", text)
    return "".join(p if p in ("<b>", "</b>") else html.escape(p, quote=False) for p in parts)

def tg_pdf(x, links):
    res = _ok(*run_composio_tool("TELEGRAM_SEND_DOCUMENT", {"chat_id": TG_CHAT, "document": x["urls"][0]["urls"][0],
                                                          "caption": tg_html(fill_links(x["caption"], links)), "parse_mode": "HTML"}))
    s = json.dumps(res); m = re.search(r'"message_id"\s*:\s*(\d+)', s); mid = int(m.group(1)) if m else None
    return {"status": "done", "id": mid, "url": f"{TG_LINK}/{mid}" if mid else None}

def tg_pair(x, links):
    """owner, 14 Nov 2026 07:43: the hourly MCQ → answer pairs on Telegram – the slide as a photo with its caption (links line
    + the post's own Video | PDF links, added by fill_links/direct); under the question an anonymous regular poll a/b/c/d"""
    res = _ok(*run_composio_tool("TELEGRAM_SEND_PHOTO", {"chat_id": TG_CHAT, "photo": x["urls"][0]["urls"][0],
                                                       "caption": tg_html(fill_links(x["caption"], links)), "parse_mode": "HTML"}))
    m = re.search(r'"message_id"\s*:\s*(\d+)', json.dumps(res)); mid = int(m.group(1)) if m else None
    out = {"status": "done", "id": mid, "url": f"{TG_LINK}/{mid}" if mid else None}
    if x.get("poll"):
        try:
            pr = _ok(*run_composio_tool("TELEGRAM_SEND_POLL", {"chat_id": TG_CHAT, "question": x["poll"]["question"],
                                                             "options": x["poll"]["options"], "type": "regular", "is_anonymous": True,
                                                             **({"reply_to_message_id": mid} if mid else {})}))
            pm = re.search(r'"message_id"\s*:\s*(\d+)', json.dumps(pr)); out["poll"] = int(pm.group(1)) if pm else "sent"
        except Exception as e: out["poll"] = f"error: {str(e)[:200]}"      # the photo is out – the poll is noted, not retried twice
    return out

def tg_links(reply_to, text):
    res = _ok(*run_composio_tool("TELEGRAM_SEND_MESSAGE", {"chat_id": TG_CHAT, "text": text, "reply_to_message_id": reply_to,
                                                         "disable_web_page_preview": False}))
    m = re.search(r'"message_id"\s*:\s*(\d+)', json.dumps(res)); return {"status": "done", "id": int(m.group(1)) if m else None}

def yt_prepare(x):
    """stage the video (and thumbnail) for YouTube; the upload itself is one direct tool call (can exceed a cell)"""
    return {"status": "prepared", "s3key": s3key(x["urls"][0]), "name": x["urls"][0]["name"],
            "thumb_url": x.get("thumb_url")}

def yt_privacy(x):
    """morning Shorts (owner 13 Nov 2026): uploaded private with publish_at = their slot; once that moment has passed
    (e.g. a quota refusal rolled them to the next day's batch) they go up public straight away"""
    if x.get("publish_at"):
        return "private" if dt.datetime.fromisoformat(x["publish_at"]) > dt.datetime.now(dt.timezone.utc) else "public"
    return x["privacyStatus"]

def yt_args(x, links, prep):
    return {"title": x["title"], "description": fill_links(x["description"], links), "tags": x["tags"], "categoryId": x["categoryId"],
            "privacyStatus": yt_privacy(x), "videoFile": {"name": prep["name"], "mimetype": "video/mp4", "s3key": prep["s3key"]}}

def yt_lang(vid):
    """owner's yes (13 Nov 2026, step 4 "Fix the language setting to Hindi on every video"): the upload tool has no language
    fields, so after every upload set video language + audio language to Hindi (hi). Reads the snippet and writes it back
    unchanged (title, description, tags, category) + the two language fields. Returns (defaultLanguage, defaultAudioLanguage)."""
    r, e = proxy_execute("GET", "/videos", "youtube", query_params={"part": "snippet", "id": vid})
    if e: raise RuntimeError(f"read snippet: {str(e)[:200]}")
    items = (r.get("data", r) if isinstance(r, dict) else {}).get("items") or []
    if not items: raise RuntimeError(f"video {vid} not found")
    sn = items[0]["snippet"]
    if sn.get("defaultLanguage") == "hi" and sn.get("defaultAudioLanguage") == "hi": return ("hi", "hi")
    body = {k: sn[k] for k in ("title", "description", "categoryId", "tags") if sn.get(k)}
    body.update(defaultLanguage="hi", defaultAudioLanguage="hi")
    r, e = proxy_execute("PUT", "/videos", "youtube", query_params={"part": "snippet"}, body={"id": vid, "snippet": body})
    if e: raise RuntimeError(f"set language: {str(e)[:300]}")
    out = (r.get("data", r) if isinstance(r, dict) else {}).get("snippet") or {}
    if out.get("description", "") != body.get("description", "") or out.get("title") != body["title"]:
        raise RuntimeError("language update changed the title/description – check the video by hand")
    return (out.get("defaultLanguage"), out.get("defaultAudioLanguage"))

def yt_schedule(vid, publish_at):
    """set publishAt on a private upload (the upload tool has no such field): read the video's status, write it back
    unchanged + publishAt (a status update without a field would clear it). Returns the new status or raises."""
    when = dt.datetime.fromisoformat(publish_at).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    r, e = proxy_execute("GET", "/videos", "youtube", query_params={"part": "status", "id": vid})
    if e: raise RuntimeError(f"read status: {str(e)[:200]}")
    items = (r.get("data", r) if isinstance(r, dict) else {}).get("items") or []
    if not items: raise RuntimeError(f"video {vid} not found")
    st = {k: v for k, v in items[0]["status"].items() if k in ("embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia")}
    st.update(privacyStatus="private", publishAt=when)
    r, e = proxy_execute("PUT", "/videos", "youtube", query_params={"part": "status"}, body={"id": vid, "status": st})
    if e: raise RuntimeError(f"set publishAt: {str(e)[:300]}")
    return (r.get("data", r) if isinstance(r, dict) else {}).get("status")

def _head(u):
    r = urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=60)
    return r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length")

def post(file, pid, links=None, resume=None, dry=False):
    """dry=True: everything except making it public (Instagram containers are created but not published;
    Facebook/Telegram/YouTube only check that the files can be fetched)"""
    x = item(file, pid); _CUR["x"] = x
    try:
        if dry and x["platform"] in ("facebook", "telegram"):
            return {"status": "dry", "files": [_head(e["urls"][0]) for e in x["urls"]], "text": fill_links(x.get("caption", ""), links)[:120]}
        if dry and x["platform"] == "youtube":
            return {"status": "dry", "files": [_head(u) for u in x["urls"][0]["urls"]], "title": x["title"]}
        if x["platform"] == "instagram": return ig_carousel(x, links, dry) if x["kind"] == "carousel" else ig_reel(x, links, resume, dry)
        if x["platform"] == "facebook": return fb_carousel(x, links) if x["kind"] == "carousel" else fb_video(x, links)
        if x["platform"] == "telegram": return tg_pair(x, links) if x.get("tag") == "pair" else tg_pdf(x, links)
        if x["platform"] == "youtube":
            prep = yt_prepare(x); return {"status": "prepared", "prep": prep, "args": yt_args(x, links, prep)}
        return {"status": "error", "error": f"platform {x['platform']} not enabled"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:600]}
