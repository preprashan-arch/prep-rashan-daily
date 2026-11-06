# Prep-Rashan Step 5 poster – runs INSIDE the Composio remote workbench (uses its helpers run_composio_tool,
# proxy_execute, upload_local_file). It is published on the main branch of the public repo
# preprashan-arch/prep-rashan-daily (no secrets in it) and loaded with:
#   import urllib.request; exec(urllib.request.urlopen(URL).read().decode())
#   print(post("<file>", "<post id>", {"YT_PPT": "...", ...}))
# Every function returns a dict: {"status": "done"|"pending"|"error", ...}. "pending" = call again later with the
# returned "resume" value (Reels still processing). Approved captions come from the day's manifest unchanged.
import hashlib, html, json, os, re, shutil, time, urllib.request

RAWBASE = "https://raw.githubusercontent.com/preprashan-arch/prep-rashan-daily/"
PAGE_ID = "1465479556641770"; TG_CHAT = "@Prep_Rashan"; TG_LINK = "https://t.me/Prep_Rashan"
YT_CHANNEL = "https://www.youtube.com/channel/UCSIYewCD5ru2dFNBJ373IPQ"
_MAN = {}

def manifest(file):
    if file not in _MAN:
        _MAN[file] = json.loads(urllib.request.urlopen(RAWBASE + f"d/{file}/manifest.json?t={int(time.time())}", timeout=60).read())
    return _MAN[file]

def item(file, pid):
    return next(x for x in manifest(file)["posts"] if x["id"] == pid)

# Owner's standing rule (5 Nov 2026): the first line of EVERY post (captions and YouTube descriptions; not the Telegram
# link replies) is this standard line. Added here so it also reaches posts staged before the rule; never added twice.
STD_LINE = f"Telegram – Daily PDFs: {TG_LINK} | YouTube – Full Videos: {YT_CHANNEL}"

def with_std(text):
    text = (text or "").strip()
    return text if text.startswith(STD_LINE) else (STD_LINE + "\n\n" + text).strip()

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
    return with_std(text)

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
    cid = resume or _ig("POST", "/me/media", {"media_type": "REELS", "video_url": x["urls"][0]["urls"][0],
                                              "caption": fill_links(x["caption"], links), "share_to_feed": True})["id"]
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

def tg_html(text):
    parts = re.split(r"(</?b>)", text)
    return "".join(p if p in ("<b>", "</b>") else html.escape(p, quote=False) for p in parts)

def tg_pdf(x, links):
    res = _ok(*run_composio_tool("TELEGRAM_SEND_DOCUMENT", {"chat_id": TG_CHAT, "document": x["urls"][0]["urls"][0],
                                                          "caption": tg_html(fill_links(x["caption"], links)), "parse_mode": "HTML"}))
    s = json.dumps(res); m = re.search(r'"message_id"\s*:\s*(\d+)', s); mid = int(m.group(1)) if m else None
    return {"status": "done", "id": mid, "url": f"{TG_LINK}/{mid}" if mid else None}

def tg_links(reply_to, text):
    res = _ok(*run_composio_tool("TELEGRAM_SEND_MESSAGE", {"chat_id": TG_CHAT, "text": text, "reply_to_message_id": reply_to,
                                                         "disable_web_page_preview": False}))
    m = re.search(r'"message_id"\s*:\s*(\d+)', json.dumps(res)); return {"status": "done", "id": int(m.group(1)) if m else None}

def yt_prepare(x):
    """stage the video (and thumbnail) for YouTube; the upload itself is one direct tool call (can exceed a cell)"""
    return {"status": "prepared", "s3key": s3key(x["urls"][0]), "name": x["urls"][0]["name"],
            "thumb_url": x.get("thumb_url")}

def yt_args(x, links, prep):
    return {"title": x["title"], "description": fill_links(x["description"], links), "tags": x["tags"], "categoryId": x["categoryId"],
            "privacyStatus": x["privacyStatus"], "videoFile": {"name": prep["name"], "mimetype": "video/mp4", "s3key": prep["s3key"]}}

def _head(u):
    r = urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=60)
    return r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length")

def post(file, pid, links=None, resume=None, dry=False):
    """dry=True: everything except making it public (Instagram containers are created but not published;
    Facebook/Telegram/YouTube only check that the files can be fetched)"""
    x = item(file, pid)
    try:
        if dry and x["platform"] in ("facebook", "telegram"):
            return {"status": "dry", "files": [_head(e["urls"][0]) for e in x["urls"]], "text": fill_links(x.get("caption", ""), links)[:120]}
        if dry and x["platform"] == "youtube":
            return {"status": "dry", "files": [_head(u) for u in x["urls"][0]["urls"]], "title": x["title"]}
        if x["platform"] == "instagram": return ig_carousel(x, links, dry) if x["kind"] == "carousel" else ig_reel(x, links, resume, dry)
        if x["platform"] == "facebook": return fb_carousel(x, links) if x["kind"] == "carousel" else fb_video(x, links)
        if x["platform"] == "telegram": return tg_pdf(x, links)
        if x["platform"] == "youtube":
            prep = yt_prepare(x); return {"status": "prepared", "prep": prep, "args": yt_args(x, links, prep)}
        return {"status": "error", "error": f"platform {x['platform']} not enabled"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:600]}
