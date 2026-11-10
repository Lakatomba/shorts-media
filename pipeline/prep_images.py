#!/usr/bin/env python3
"""prep_images.py <workdir> - fetch real, free-to-reuse photos from Wikimedia Commons for a Short.

Reads <wd>/script.json. Any entry may carry "image_query": "search words" (or a list of fallbacks)
and optionally "image_pick": N (use the Nth valid result, default 0).
For each one it downloads the photo to <wd>/img/<line>.jpg, sets entry["data"]["image"], and writes:
  <wd>/credits.json  [{line, title, author, license, page}]
  <wd>/credits.txt   ready-to-paste "Images:" block for the video description
  <wd>/img/contact.jpg   a sheet of all chosen photos - LOOK at it and fix wrong ones (change query/pick, re-run)
Only Public domain / CC0 / CC BY / CC BY-SA files are used. Needs network access to
commons.wikimedia.org and upload.wikimedia.org.
"""
import io, json, os, re, sys, time, urllib.parse, urllib.request
from PIL import Image, ImageDraw, ImageFont

UA = "MRGoodGuyShorts/1.0 (github.com/Lakatomba/shorts-media)"
API = "https://commons.wikimedia.org/w/api.php"
OK_LIC = re.compile(r"^(public domain|pd\b|cc0|cc[ -]by(-sa)?\b|no restrictions|attribution)", re.I)

def get(url, binary=False, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
                return b if binary else json.loads(b)
        except Exception as e:
            err = e; time.sleep(4 + 10 * k)
    raise RuntimeError(f"{url[:90]}: {err}")

def strip(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()[:80]

def search(q, limit=12):
    p = dict(action="query", format="json", generator="search", gsrsearch=q + " filetype:bitmap", gsrnamespace=6,
             gsrlimit=limit, prop="imageinfo", iiprop="url|extmetadata|size|mime")
    d = get(API + "?" + urllib.parse.urlencode(p))
    out = []
    for pg in sorted(d.get("query", {}).get("pages", {}).values(), key=lambda x: x.get("index", 99)):
        ii = pg["imageinfo"][0]; m = ii.get("extmetadata", {})
        lic = m.get("LicenseShortName", {}).get("value", "")
        if ii.get("mime") not in ("image/jpeg", "image/png"): continue
        if min(ii["width"], ii["height"]) < 380 or ii["size"] > 25e6: continue
        if not OK_LIC.match(lic): continue
        out.append(dict(title=pg["title"].replace("File:", ""), url=ii["url"].split("?")[0], license=lic,
                        author=strip(m.get("Artist", {}).get("value")) or "unknown",
                        page=ii.get("descriptionurl", ""), w=ii["width"], h=ii["height"]))
    return out

def main():
    wd = sys.argv[1]; os.makedirs(f"{wd}/img", exist_ok=True)
    script = json.load(open(f"{wd}/script.json")); credits = []; thumbs = []
    try: old = {(c["line"], json.dumps(c.get("asked")), c.get("pick", 0)): c for c in json.load(open(f"{wd}/credits.json"))}
    except Exception: old = {}
    for n, s in enumerate(script):
        qs = s.get("image_query")
        if not qs: continue
        qs = [qs] if isinstance(qs, str) else qs
        pick = int(s.get("image_pick", 0)); done = False
        hit = old.get((n, json.dumps(qs), pick)); path = f"{wd}/img/{n:02d}.jpg"
        if hit and os.path.exists(path):  # cached from an earlier run: no new download
            s.setdefault("data", {})["image"] = path; credits.append(hit)
            thumbs.append((n, hit["query"], Image.open(path).convert("RGB"))); continue
        for q in qs:
            try: res = search(q)
            except Exception as e: print("search failed:", q, e); continue
            if len(res) <= pick: continue
            c = res[pick]
            try:
                u = c["url"]
                for size in (1920, 1280, 960):  # Wikimedia asks bots to use standard thumbnail sizes
                    if c["w"] > size:
                        u = u.replace("/commons/", "/commons/thumb/", 1) + f"/{size}px-" + u.rsplit("/", 1)[1]; break
                im = Image.open(io.BytesIO(get(u, binary=True))).convert("RGB")
            except Exception as e: print("download failed:", c["title"], e); continue
            im.thumbnail((2400, 2400)); path = f"{wd}/img/{n:02d}.jpg"; im.save(path, quality=90)
            s.setdefault("data", {})["image"] = path
            credits.append(dict(line=n, query=q, asked=qs, pick=pick, **{k: c[k] for k in ("title", "author", "license", "page")}))
            thumbs.append((n, q, im.copy())); done = True; time.sleep(5); break
        if not done:
            print(f"line {n}: no usable image for {qs} (scene will use graphics)")
            s.get("data", {}).pop("image", None)
    json.dump(script, open(f"{wd}/script.json", "w"), indent=1, ensure_ascii=False)
    json.dump(credits, open(f"{wd}/credits.json", "w"), indent=1, ensure_ascii=False)
    seen, lines = set(), []
    for c in credits:
        if c["title"] in seen: continue
        seen.add(c["title"]); lines.append(f"- {c['title']} by {c['author']} ({c['license']}), Wikimedia Commons")
    open(f"{wd}/credits.txt", "w").write(("Images:\n" + "\n".join(lines) + "\n") if lines else "")
    if thumbs:
        sheet = Image.new("RGB", (320 * min(4, len(thumbs)), 360 * ((len(thumbs) + 3) // 4)), (20, 20, 20)); d = ImageDraw.Draw(sheet)
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        for k, (n, q, im) in enumerate(thumbs):
            im.thumbnail((300, 300)); x, y = (k % 4) * 320 + 10, (k // 4) * 360 + 10
            sheet.paste(im, (x, y)); d.text((x, y + 310), f"line {n}: {q}"[:34], font=f, fill=(255, 220, 0))
        sheet.save(f"{wd}/img/contact.jpg")
    print(f"{len(credits)} images ready")

if __name__ == "__main__":
    main()
