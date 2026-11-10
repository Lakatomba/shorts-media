"""render_v2 — edited-style faceless Short renderer (no stock footage needed).

Usage: python3 render_v2.py <workdir>
workdir needs:
  vo.wav     narration (any sample rate)
  seg.json   [{"text","start","end","visual","data":{...}}]   one entry per spoken line
  meta.json  {"palette": "noir|gold|blood|ice|toxic" (optional, else chosen from seed),
              "cover_text": "SOLD. TWICE.", "cover_accent": "TWICE", "seed": any int/str}
Outputs: short.mp4 (1080x1920, 30fps, H.264/AAC), thumbnail.jpg

VISUALS (pick a DIFFERENT one for consecutive lines; use 6+ different kinds per video):
  hook       data: big (str, e.g. "$150M"), sub (str)         big slam text + shockwave
  map        data: place (str), year (str), x (0-1), y (0-1)  stylised world grid, pin drop, ripples
  counter    data: value (num), prefix, suffix, label         number counts up fast
  newspaper  data: headline, paper (masthead), date           front page slams in + slow zoom
  document   data: title (e.g. CONFIDENTIAL), lines [str]     dossier + typewriter + stamp
  timeline   data: years [str], highlight (index)             animated timeline
  bars       data: items [{label, value}], unit               animated bar chart
  money      data: amount (str)                               falling banknotes + amount
  police     data: word (e.g. ARRESTED)                       red/blue lights + slam
  quote      data: quote (str), who (str)                     big quote card
  split      data: left, right, vs (str, default "VS")        two-panel comparison
  scene      data: kind (city|tower|vault|bank|ship|mountains|prison), label   parallax silhouette
  question   data: q (str)                                    big "?" + question (great for loop line)
  photo      data: image (path, set by prep_images.py), label   REAL photo, slow zoom/pan (framed card if low-res)
ANY other visual may also carry data.image: the photo becomes its darkened moving background (great on the hook).
"""
import json, math, os, random, subprocess, sys, hashlib
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

W, H, FPS = 1080, 1920, 30
F_BLACK = "/usr/share/fonts/opentype/inter/Inter-Black.otf"
F_XB = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
F_SERIF = "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrebonum-bold.otf"
F_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
_fc = {}
def font(sz, f=F_BLACK):
    k = (sz, f)
    if k not in _fc: _fc[k] = ImageFont.truetype(f, max(8, int(sz)))
    return _fc[k]

wd = sys.argv[1]
seg = json.load(open(f"{wd}/seg.json"))
meta = json.load(open(f"{wd}/meta.json"))
seed = int(hashlib.md5(str(meta.get("seed", meta.get("cover_text", "x"))).encode()).hexdigest()[:8], 16)
R = random.Random(seed)

PALETTES = {
    "noir":  dict(bg1=(10, 14, 22), bg2=(28, 36, 52), acc=(255, 196, 0), acc2=(230, 57, 70), txt=(245, 245, 240)),
    "gold":  dict(bg1=(18, 12, 6), bg2=(60, 40, 14), acc=(255, 190, 60), acc2=(255, 90, 40), txt=(255, 248, 230)),
    "blood": dict(bg1=(16, 4, 6), bg2=(70, 10, 18), acc=(255, 70, 70), acc2=(255, 210, 0), txt=(255, 240, 240)),
    "ice":   dict(bg1=(4, 14, 24), bg2=(12, 54, 80), acc=(0, 220, 255), acc2=(255, 80, 120), txt=(235, 250, 255)),
    "toxic": dict(bg1=(6, 14, 8), bg2=(20, 50, 24), acc=(140, 255, 60), acc2=(255, 60, 160), txt=(240, 255, 240)),
}
P = PALETTES.get(meta.get("palette") or R.choice(list(PALETTES)), PALETTES["noir"])
ACC, ACC2, TXT = P["acc"], P["acc2"], P["txt"]
CAP_STYLE = meta.get("caption_style") or R.choice(["pop", "box"])

vo, sr = sf.read(f"{wd}/vo.wav")
if vo.ndim > 1: vo = vo.mean(1)
DUR = len(vo) / sr + 0.5
NF = int(DUR * FPS)

# scene boundaries: each segment's scene lasts until next segment start
for i, s in enumerate(seg):
    s["s0"] = 0.0 if i == 0 else s["start"] - 0.05
    s["s1"] = seg[i + 1]["start"] - 0.05 if i + 1 < len(seg) else DUR
    s.setdefault("data", {})
    s.setdefault("visual", "scene")
TRANS = ["flash", "zoom", "whip", "glitch", "zoom", "whip"]
for i, s in enumerate(seg):
    s["trans"] = "none" if i == 0 else R.choice(TRANS)

# ---------------- backgrounds ----------------
yy, xx = np.mgrid[0:H, 0:W]
VIG = np.clip(1 - 0.85 * (((xx - W / 2) / (W / 1.25)) ** 2 + ((yy - H / 2) / (H / 1.35)) ** 2), 0.12, 1)[..., None]
def gradient(c1, c2, angle=0.0, radial=False):
    if radial:
        g = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.45) / H) ** 2) * 1.8
    else:
        g = (yy / H) * math.cos(angle) + (xx / W) * math.sin(angle)
    g = np.clip(g, 0, 1)[..., None]
    a = np.array(c1) * (1 - g) + np.array(c2) * g
    return Image.fromarray((a * VIG).astype(np.uint8))
BG_VARIANTS = [gradient(P["bg2"], P["bg1"], radial=True), gradient(P["bg1"], P["bg2"], 0.3),
               gradient(P["bg2"], P["bg1"], -0.4)]
GRAIN = [Image.fromarray(np.random.default_rng(i).integers(0, 255, (H // 3, W // 3), dtype=np.uint8)).resize((W, H)) for i in range(5)]
SCAN = Image.new("L", (W, H), 0)
_d = ImageDraw.Draw(SCAN)
for y in range(0, H, 6): _d.line([0, y, W, y], fill=18)

def ease_out(x): x = min(1, max(0, x)); return 1 - (1 - x) ** 3
def ease_back(x):
    x = min(1, max(0, x)); c1 = 1.9; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
def rgba(c, a=255): return tuple(c[:3]) + (int(a),)
def text_c(d, xy, t, f, fill, sw=0, sf=(0, 0, 0), anchor="mm"):
    d.text(xy, t, font=f, fill=fill, stroke_width=sw, stroke_fill=sf, anchor=anchor)
def fit(d, t, maxw, sz, f=F_BLACK):
    while sz > 20 and d.textlength(t, font=font(sz, f)) > maxw: sz -= 4
    return font(sz, f)
def wrap(d, t, f, maxw):
    words, lines, cur = t.split(), [], ""
    for w in words:
        nt = (cur + " " + w).strip()
        if d.textlength(nt, font=f) <= maxw: cur = nt
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

# ---------------- silhouettes (cached) ----------------
_sil = {}
def silhouette(kind):
    if kind in _sil: return _sil[kind]
    L = Image.new("RGBA", (int(W * 1.3), H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    r = random.Random(kind); base = H * 0.80; LW = L.width
    dark = (4, 5, 8, 255)
    def skyline(base, hmin, hmax, col, win=True):
        x = -10
        while x < LW:
            bw = r.randint(70, 170); bh = r.randint(hmin, hmax)
            d.rectangle([x, base - bh, x + bw, base], fill=col)
            if win:
                for wy in range(int(base - bh + 24), int(base - 20), 40):
                    for wx in range(x + 14, x + bw - 14, 32):
                        if r.random() < 0.3: d.rectangle([wx, wy, wx + 12, wy + 18], fill=rgba(ACC, 120))
            x += bw + r.randint(4, 16)
    if kind in ("city", "tower", "bank", "prison"): skyline(base, 160, 520, (12, 14, 20, 240))
    cx = LW / 2
    if kind == "tower":
        h = H * 0.62; w = h * 0.42
        d.polygon([(cx - w / 2, base), (cx - w * .08, base - h * .62), (cx - w * .03, base - h * .95), (cx, base - h),
                   (cx + w * .03, base - h * .95), (cx + w * .08, base - h * .62), (cx + w / 2, base)], fill=dark)
        d.chord([cx - w * .28, base - h * .22, cx + w * .28, base + h * .12], 180, 360, fill=(0, 0, 0, 0))
        for fy, fw in ((.30, .33), (.62, .11)): d.rectangle([cx - w * fw, base - h * fy - 10, cx + w * fw, base - h * fy + 6], fill=dark)
    elif kind == "bank":
        bw, bh = 820, 620; x0 = cx - bw / 2
        d.polygon([(x0 - 40, base - bh), (cx, base - bh - 200), (x0 + bw + 40, base - bh)], fill=dark)
        d.rectangle([x0, base - bh, x0 + bw, base], fill=dark)
        for i in range(6):
            px = x0 + 50 + i * (bw - 100) / 5
            d.rectangle([px - 26, base - bh + 40, px + 26, base - 30], fill=(20, 22, 30, 255))
        text_c(d, (cx, base - bh - 70), "BANK", font(80, F_SERIF), rgba(ACC, 200))
    elif kind == "vault":
        rr = 420; cy = H * 0.50
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(30, 32, 40, 255), outline=rgba(ACC, 160), width=14)
        d.ellipse([cx - rr * .72, cy - rr * .72, cx + rr * .72, cy + rr * .72], outline=(70, 72, 84, 255), width=10)
        for a in range(0, 360, 30):
            x1 = cx + math.cos(math.radians(a)) * rr * .86; y1 = cy + math.sin(math.radians(a)) * rr * .86
            d.ellipse([x1 - 20, y1 - 20, x1 + 20, y1 + 20], fill=(60, 62, 72, 255))
        for a in (0, 120, 240):
            d.line([cx, cy, cx + math.cos(math.radians(a)) * rr * .55, cy + math.sin(math.radians(a)) * rr * .55], fill=rgba(ACC, 200), width=22)
        d.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill=rgba(ACC, 230))
    elif kind == "ship":
        d.polygon([(cx - 480, base - 120), (cx + 520, base - 120), (cx + 400, base + 20), (cx - 420, base + 20)], fill=dark)
        d.rectangle([cx - 220, base - 300, cx + 200, base - 120], fill=dark)
        d.rectangle([cx - 40, base - 460, cx + 40, base - 300], fill=dark)
        for i in range(8): d.ellipse([cx - 380 + i * 100, base - 80, cx - 356 + i * 100, base - 56], fill=rgba(ACC, 150))
    elif kind == "mountains":
        for k, col in ((0, (18, 20, 28, 255)), (1, dark)):
            pts = [(0, base)]; x = 0
            while x < LW:
                pts.append((x, base - r.randint(250, 700) * (1 - .3 * k))); x += r.randint(160, 320)
            pts.append((LW, base)); d.polygon(pts, fill=col)
    elif kind == "prison":
        d.rectangle([cx - 450, base - 560, cx + 450, base], fill=dark)
        for i in range(-3, 4):
            d.rectangle([cx + i * 110 - 30, base - 460, cx + i * 110 + 30, base - 360], fill=rgba(ACC, 90))
            for j in range(3): d.line([cx + i * 110 - 15 + j * 15, base - 460, cx + i * 110 - 15 + j * 15, base - 360], fill=dark, width=6)
        d.rectangle([cx + 380, base - 860, cx + 470, base - 560], fill=dark)
        d.polygon([(cx + 470, base - 840), (cx + 470, base - 800), (cx - 300, base - 1200), (cx - 300, base - 1080)], fill=(255, 255, 220, 30))
    d.rectangle([0, base, LW, H], fill=dark)
    fog = Image.new("RGBA", L.size, (0, 0, 0, 0)); fd = ImageDraw.Draw(fog)
    for i in range(5): fd.ellipse([-300, base - 300 + i * 70, LW + 300, base - 40 + i * 70], fill=(200, 210, 230, 26))
    L = Image.alpha_composite(L, fog.filter(ImageFilter.GaussianBlur(50)))
    _sil[kind] = L
    return L

# ---------------- templates ----------------
# each: draw(frame RGBA, d, lt (local time), sd (scene duration), data, i)
def t_hook(fr, d, lt, sd, a, i):
    big = str(a.get("big", "?")); sub = a.get("sub", "")
    # shockwave rings
    for k in range(3):
        p = (lt * 1.3 - k * .25)
        if 0 < p < 1:
            r_ = 100 + p * 900
            d.ellipse([W / 2 - r_, H * .45 - r_, W / 2 + r_, H * .45 + r_], outline=rgba(ACC, 200 * (1 - p)), width=int(18 * (1 - p)) + 2)
    sc = max(1, 2.6 - lt * 12)
    f = fit(d, big, W - 140, int(300 / max(1, len(big) / 6)))
    f = font(f.size * sc)
    text_c(d, (W / 2, H * .45), big, f, rgba(ACC), 14)
    if sub and lt > .35:
        al = ease_out((lt - .35) * 4)
        text_c(d, (W / 2, H * .45 + f.size * .75 + 30), sub.upper(), fit(d, sub.upper(), W - 160, 64, F_XB), rgba(TXT, 255 * al), 6)

def t_map(fr, d, lt, sd, a, i):
    # grid globe
    cx, cy, rr = W / 2, H * .36, 380
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 255, 255, 10), outline=rgba(ACC, 120), width=4)
    rot = lt * 25
    for k in range(-80, 81, 20):
        y = cy + math.sin(math.radians(k)) * rr; w_ = math.cos(math.radians(k)) * rr
        d.ellipse([cx - w_, y - 6, cx + w_, y + 6], outline=rgba(TXT, 40), width=2)
    for k in range(0, 180, 20):
        w_ = abs(math.cos(math.radians(k + rot))) * rr
        d.ellipse([cx - w_, cy - rr, cx + w_, cy + rr], outline=rgba(TXT, 40), width=2)
    r2 = random.Random(7)
    for _ in range(140):  # "land" dots
        ang = r2.uniform(0, 2 * math.pi); dist = math.sqrt(r2.random()) * rr * .95
        px, py = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=rgba(TXT, 70))
    px = cx + (float(a.get("x", .55)) - .5) * rr * 1.4; py = cy + (float(a.get("y", .4)) - .5) * rr * 1.4
    drop = ease_back(lt * 2.5); pyy = py - 300 * (1 - drop)
    for k in range(3):
        p = (lt * 1.2 - .3 - k * .3) % 1.2
        if 0 < p < 1 and lt > .3:
            r_ = 20 + p * 160; d.ellipse([px - r_, py - r_ * .45, px + r_, py + r_ * .45], outline=rgba(ACC2, 220 * (1 - p)), width=5)
    d.ellipse([px - 34, pyy - 110, px + 34, pyy - 42], fill=rgba(ACC2))
    d.polygon([(px - 30, pyy - 70), (px + 30, pyy - 70), (px, pyy)], fill=rgba(ACC2))
    d.ellipse([px - 13, pyy - 89, px + 13, pyy - 63], fill=(255, 255, 255, 255))
    if lt > .4:
        al = ease_out((lt - .4) * 4)
        place = a.get("place", "").upper(); year = a.get("year", "")
        f = fit(d, place, W - 160, 120)
        text_c(d, (W / 2, cy + rr + 90), place, f, rgba(TXT, 255 * al), 8)
        if year: text_c(d, (W / 2, cy + rr + 200), year, font(90, F_XB), rgba(ACC, 255 * al), 6)

def t_counter(fr, d, lt, sd, a, i):
    v = float(a.get("value", 100)); p = ease_out(lt / max(.6, min(1.4, sd * .6)))
    cur = v * p
    s = (f"{cur:,.0f}" if v >= 10 else f"{cur:.1f}")
    txt = f"{a.get('prefix', '')}{s}{a.get('suffix', '')}"
    f = fit(d, f"{a.get('prefix', '')}{v:,.0f}{a.get('suffix', '')}", W - 120, 230)
    jitter = (R.random() - .5) * 8 if p < 1 else 0
    text_c(d, (W / 2 + jitter, H * .42), txt, f, rgba(ACC if p >= 1 else TXT), 12)
    # ticking bar
    d.rounded_rectangle([140, H * .42 + 170, W - 140, H * .42 + 196], 13, fill=(255, 255, 255, 40))
    d.rounded_rectangle([140, H * .42 + 170, 140 + (W - 280) * p, H * .42 + 196], 13, fill=rgba(ACC))
    lab = a.get("label", "").upper()
    if lab: text_c(d, (W / 2, H * .42 - 190), lab, fit(d, lab, W - 160, 70, F_XB), rgba(TXT), 6)

_paper = {}
def t_newspaper(fr, d, lt, sd, a, i):
    key = (i, a.get("headline"))
    if key not in _paper:
        pw, ph = 900, 1100; P_ = Image.new("RGBA", (pw, ph), (236, 228, 208, 255)); pd = ImageDraw.Draw(P_)
        text_c(pd, (pw / 2, 90), a.get("paper", "THE DAILY GAZETTE").upper(), fit(pd, a.get("paper", "THE DAILY GAZETTE").upper(), pw - 80, 84, F_SERIF), (20, 20, 20, 255))
        pd.line([40, 150, pw - 40, 150], fill=(20, 20, 20, 255), width=5)
        pd.text((44, 162), a.get("date", "").upper(), font=font(30, F_SERIF), fill=(40, 40, 40, 255))
        pd.text((pw - 44, 162), "PRICE 5 CENTS", font=font(30, F_SERIF), fill=(40, 40, 40, 255), anchor="ra")
        pd.line([40, 206, pw - 40, 206], fill=(20, 20, 20, 255), width=3)
        hl = a.get("headline", "SHOCKING NEWS").upper(); hf = font(118, F_SERIF)
        lines = wrap(pd, hl, hf, pw - 90)
        while len(lines) > 3: hf = font(hf.size - 10, F_SERIF); lines = wrap(pd, hl, hf, pw - 90)
        y = 240
        for ln in lines: pd.text((pw / 2, y), ln, font=hf, fill=(15, 15, 15, 255), anchor="ma"); y += hf.size * 1.02
        y += 30; pd.rectangle([60, y, pw * .55, y + 300], fill=(60, 60, 60, 255))
        for col in range(2):
            for k in range(14):
                x0 = 60 if col == 0 else pw * .58
                if col == 0 and k < 9: continue
                yy_ = y + (k - (9 if col == 0 else 0)) * 30 + (310 if col == 0 else 0)
                pd.line([x0, yy_, x0 + (pw * .37 if col else pw * .5 - 20), yy_], fill=(120, 120, 120, 255), width=8)
        _paper[key] = P_.filter(ImageFilter.GaussianBlur(.6))
    P_ = _paper[key]
    spin = 1 - ease_out(lt * 3.2)
    sc = (.75 + .25 * ease_out(lt * 3.2)) * (1 + lt * .03)
    img = P_.resize((int(P_.width * sc), int(P_.height * sc))).rotate(-4 + spin * 200, expand=True, resample=Image.BICUBIC)
    fr.paste(img, (int(W / 2 - img.width / 2), int(H * .43 - img.height / 2)), img)

def t_document(fr, d, lt, sd, a, i):
    x0, y0, pw, ph = 110, H * .17, W - 220, H * .52
    slide = 1 - ease_out(lt * 3); y0 += slide * 600
    d.rounded_rectangle([x0 - 10, y0 - 50, x0 + 300, y0 + 20], 14, fill=(198, 160, 92, 255))
    d.rounded_rectangle([x0 - 10, y0, x0 + pw + 10, y0 + ph], 18, fill=(214, 176, 104, 255))
    d.rectangle([x0 + 30, y0 + 40, x0 + pw - 30, y0 + ph - 30], fill=(246, 242, 230, 255))
    title = a.get("title", "CONFIDENTIAL").upper()
    text_c(d, (W / 2, y0 + 110), title, fit(d, title, pw - 140, 74, F_MONO), (20, 20, 20, 255))
    d.line([x0 + 70, y0 + 160, x0 + pw - 70, y0 + 160], fill=(30, 30, 30, 255), width=4)
    lines = a.get("lines", []) or ["SUBJECT: UNKNOWN"]
    chars = int(max(0, lt - .3) * 38); y = y0 + 220; f = font(46, F_MONO)
    for ln in lines:
        ln = ln.upper(); show = ln[:max(0, chars)]; chars -= len(ln)
        wl = wrap(d, show, f, pw - 160) if show else []
        for w_ in wl: d.text((x0 + 80, y), w_, font=f, fill=(30, 30, 30, 255)); y += 62
        if chars <= 0: break
        y += 14
    if int(lt * 3) % 2 == 0 and chars <= 0: pass
    stamp_t = lt - (.3 + sum(len(l) for l in lines) / 38 + .15)
    if stamp_t > 0:
        sc = max(1, 2.2 - stamp_t * 10)
        st = Image.new("RGBA", (640, 200), (0, 0, 0, 0)); sd_ = ImageDraw.Draw(st)
        sd_.rounded_rectangle([8, 8, 632, 192], 20, outline=rgba(ACC2), width=14)
        text_c(sd_, (320, 102), a.get("stamp", "CLASSIFIED").upper(), fit(sd_, a.get("stamp", "CLASSIFIED").upper(), 580, 110), rgba(ACC2))
        st = st.rotate(14, expand=True, resample=Image.BICUBIC); st = st.resize((int(st.width * sc), int(st.height * sc)))
        fr.paste(st, (int(W / 2 - st.width / 2), int(y0 + ph * .62 - st.height / 2)), st)

def t_timeline(fr, d, lt, sd, a, i):
    ys = a.get("years", ["1900", "1950", "2000"]); hi = int(a.get("highlight", len(ys) - 1))
    n = len(ys); y = H * .45; x0, x1 = 120, W - 120
    p = ease_out(lt * 1.6)
    d.line([x0, y, x1, y], fill=(255, 255, 255, 60), width=10)
    d.line([x0, y, x0 + (x1 - x0) * p, y], fill=rgba(ACC), width=10)
    for k, yr in enumerate(ys):
        x = x0 + (x1 - x0) * (k / max(1, n - 1)); on = p >= k / max(1, n - 1) - .01
        r_ = 30 if k == hi else 18
        if on and k == hi: r_ += 8 * abs(math.sin(lt * 6))
        d.ellipse([x - r_, y - r_, x + r_, y + r_], fill=rgba(ACC if on else (90, 90, 90)), outline=(0, 0, 0, 255), width=4)
        f = font(96 if k == hi else 66, F_XB)
        text_c(d, (x, y + (-110 if k % 2 == 0 else 110)), yr, f, rgba(ACC if (k == hi and on) else TXT, 255 if on else 110), 6)
    lab = a.get("label", "").upper()
    if lab: text_c(d, (W / 2, H * .30), lab, fit(d, lab, W - 160, 76, F_XB), rgba(TXT), 6)

def t_bars(fr, d, lt, sd, a, i):
    items = a.get("items", [{"label": "A", "value": 1}, {"label": "B", "value": 3}])
    mx = max(float(it["value"]) for it in items) or 1; n = len(items)
    bw = min(220, (W - 200) / n - 40); base = H * .62; top = H * .24
    for k, it in enumerate(items):
        p = ease_out((lt - k * .15) * 2.2); hgt = (base - top) * float(it["value"]) / mx * p
        x = W / 2 + (k - (n - 1) / 2) * (bw + 50)
        col = ACC if float(it["value"]) == mx else (150, 150, 160)
        d.rounded_rectangle([x - bw / 2, base - hgt, x + bw / 2, base], 16, fill=rgba(col))
        text_c(d, (x, base + 60), str(it["label"]).upper(), fit(d, str(it["label"]).upper(), bw + 40, 48, F_XB), rgba(TXT), 4)
        if p > .2:
            text_c(d, (x, base - hgt - 50), f"{a.get('prefix', '')}{float(it['value']) * p:,.0f}{a.get('unit', '')}", fit(d, f"{a.get('prefix', '')}{float(it['value']):,.0f}{a.get('unit', '')}", bw + 60, 60, F_XB), rgba(TXT), 5)
    d.line([120, base, W - 120, base], fill=(255, 255, 255, 120), width=6)

def t_money(fr, d, lt, sd, a, i):
    r2 = random.Random(i)
    for k in range(26):
        x = r2.uniform(-100, W); sp = r2.uniform(500, 1100); y = -300 + ((lt * sp + r2.uniform(0, 2000)) % (H + 400))
        ang = math.sin(lt * 3 + k) * 35
        bill = Image.new("RGBA", (220, 100), (0, 0, 0, 0)); bd = ImageDraw.Draw(bill)
        bd.rounded_rectangle([0, 0, 219, 99], 10, fill=(72, 160, 96, 255), outline=(30, 80, 45, 255), width=5)
        bd.ellipse([80, 20, 140, 80], outline=(30, 80, 45, 255), width=5); text_c(bd, (110, 50), "$", font(40), (30, 80, 45, 255))
        bill = bill.rotate(ang, expand=True)
        fr.paste(bill, (int(x), int(y)), bill)
    amt = a.get("amount", "")
    if amt:
        sc = max(1, 1.8 - lt * 6)
        d2 = ImageDraw.Draw(fr, "RGBA")
        text_c(d2, (W / 2, H * .44), amt, font(fit(d2, amt, W - 140, 220).size * sc), rgba(ACC), 14)

def t_police(fr, d, lt, sd, a, i):
    on = int(lt * 7) % 2
    d.rectangle([0, 0, W, H], fill=(230, 20, 40, 70) if on else (20, 60, 255, 70))
    for k in range(2):
        cx = W * (.25 + .5 * k); col = (255, 40, 50) if k == on else (40, 90, 255)
        d.ellipse([cx - 260, -200, cx + 260, 260], fill=rgba(col, 110))
    word = a.get("word", "ARRESTED").upper()
    sc = max(1, 2.4 - lt * 10)
    f = fit(d, word, W - 140, 190); f = font(f.size * sc)
    tw = d.textlength(word, font=f)
    d.rectangle([W / 2 - tw / 2 - 40, H * .44 - f.size * .65, W / 2 + tw / 2 + 40, H * .44 + f.size * .65], fill=(0, 0, 0, 200))
    text_c(d, (W / 2, H * .44), word, f, (255, 255, 255, 255), 0)
    for k in range(-1, 2, 2):
        y = H * .44 + k * (f.size * .65 + 40)
        for x in range(-100, W + 100, 120):
            xo = (x + lt * 400 * k) % (W + 240) - 120
            d.polygon([(xo, y - 22), (xo + 60, y - 22), (xo + 30, y + 22), (xo - 30, y + 22)], fill=rgba((255, 210, 0), 230))

def t_quote(fr, d, lt, sd, a, i):
    q = a.get("quote", ""); who = a.get("who", "")
    text_c(d, (180, H * .26), "“", font(420, F_SERIF), rgba(ACC, 180))
    f = font(88, F_XB); lines = wrap(d, q, f, W - 220)
    while len(lines) > 5: f = font(f.size - 8, F_XB); lines = wrap(d, q, f, W - 220)
    y = H * .34; chars = int(lt * 45)
    for ln in lines:
        show = ln[:max(0, chars)]; chars -= len(ln) + 1
        d.text((110, y), show, font=f, fill=rgba(TXT), stroke_width=4, stroke_fill=(0, 0, 0)); y += f.size * 1.18
    if who and chars > 0: d.text((110, y + 30), "— " + who.upper(), font=font(52, F_XB), fill=rgba(ACC))

def t_split(fr, d, lt, sd, a, i):
    p = ease_out(lt * 3)
    d.polygon([(0, 0), (W * .58 * p, 0), (W * .42 * p, H), (0, H)], fill=rgba(ACC2, 150))
    d.polygon([(W, 0), (W - W * .42 * p, 0), (W - W * .58 * p, H), (W, H)], fill=rgba(ACC, 120))
    L, Rr = a.get("left", "").upper(), a.get("right", "").upper()
    for txt, (x, y0) in ((L, (W * .27, H * .27)), (Rr, (W * .73, H * .58))):
        f = font(100, F_BLACK); lines = wrap(d, txt, f, W * .44)
        while len(lines) > 3: f = font(f.size - 8); lines = wrap(d, txt, f, W * .44)
        y = y0
        for ln in lines: text_c(d, (x, y), ln, fit(d, ln, W * .44, f.size), rgba(TXT, 255 * p), 8); y += f.size * 1.1
    vs = a.get("vs", "VS"); sc = max(1, 2.5 - lt * 8)
    d.ellipse([W / 2 - 110 * sc, H * .44 - 110 * sc, W / 2 + 110 * sc, H * .44 + 110 * sc], fill=(0, 0, 0, 230), outline=rgba(TXT), width=8)
    text_c(d, (W / 2, H * .44), vs, font(96 * sc), rgba(TXT))

def t_scene(fr, d, lt, sd, a, i):
    L = silhouette(a.get("kind", "city"))
    off = int((L.width - W) * (.5 + .5 * math.sin(i)) * (1 - lt / max(sd, 1) * .4))
    _c = L.crop((off, 0, off + W, H)); fr.paste(_c, (0, 0), _c)
    lab = a.get("label", "").upper()
    if lab:
        al = ease_out(lt * 3); d2 = ImageDraw.Draw(fr, "RGBA")
        f = fit(d2, lab, W - 200, 96, F_XB); tw = d2.textlength(lab, font=f)
        d2.rectangle([W / 2 - tw / 2 - 30, H * .20 - 70, W / 2 + tw / 2 + 30, H * .20 + 70], fill=rgba((0, 0, 0), 170 * al))
        d2.rectangle([W / 2 - tw / 2 - 30, H * .20 + 62, W / 2 - tw / 2 - 30 + (tw + 60) * al, H * .20 + 70], fill=rgba(ACC))
        text_c(d2, (W / 2, H * .20), lab, f, rgba(TXT, 255 * al))

def t_question(fr, d, lt, sd, a, i):
    sc = 1 + .05 * math.sin(lt * 5)
    text_c(d, (W / 2, H * .36), "?", font(620 * sc), rgba(ACC, 230), 16)
    q = a.get("q", "").upper()
    if q:
        f = font(80, F_XB); lines = wrap(d, q, f, W - 180); y = H * .58
        for ln in lines: text_c(d, (W / 2, y), ln, f, rgba(TXT), 6); y += 96

_img = {}
BWc, BHc = int(W * 1.16), int(H * 1.16)
def load_img(path):
    if not path: return None
    if path in _img: return _img[path]
    try: im = Image.open(path).convert("RGB")
    except Exception: _img[path] = None; return None
    sc = max(BWc / im.width, BHc / im.height)
    cov = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.LANCZOS)
    l, t = (cov.width - BWc) // 2, (cov.height - BHc) // 2
    cov = cov.crop((l, t, l + BWc, t + BHc))
    full = sc <= 1.9 and im.height / im.width >= 1.05
    blur = cov.resize((BWc // 8, BHc // 8)).filter(ImageFilter.GaussianBlur(6)).resize((W, H))
    blur = Image.blend(blur, Image.new("RGB", (W, H), P["bg1"]), .55)
    k = min(940 / im.width, 1040 / im.height, 3.0)
    card = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    fr_ = Image.new("RGB", (card.width + 28, card.height + 28), (245, 242, 232)); fr_.paste(card, (14, 14))
    _img[path] = dict(cover=cov, dark=Image.blend(cov, Image.new("RGB", cov.size, (0, 0, 0)), .6), blur=blur, card=fr_, full=full)
    return _img[path]
def moving(src, lt, sd, i, zmax=.12):
    z = 1 + zmax * min(1, lt / max(sd, .1)); cw, ch = int(W * 1.16 / z), int(H * 1.16 / z)
    dx = (BWc - cw) * (.5 + .45 * (1 if i % 2 else -1) * min(1, lt / max(sd, .1))); dy = (BHc - ch) / 2
    return src.crop((int(dx), int(dy), int(dx) + cw, int(dy) + ch)).resize((W, H), Image.BILINEAR)
_shade = None
def t_photo(fr, d, lt, sd, a, i):
    global _shade
    info = load_img(a.get("image"))
    if not info: return t_scene(fr, d, lt, sd, a, i)
    if info["full"]:
        fr.paste(moving(info["cover"], lt, sd, i))
        if _shade is None:
            g = np.zeros((H, W, 4), dtype=np.uint8); yy_ = np.linspace(0, 1, H)
            g[..., 3] = (np.clip((yy_ - .55) / .45, 0, 1) * 200 + np.clip((.22 - yy_) / .22, 0, 1) * 150)[:, None]
            _shade = Image.fromarray(g)
        fr.paste(_shade, (0, 0), _shade)
    else:
        fr.paste(info["blur"])
        z = (1 + .07 * min(1, lt / max(sd, .1))) * (.9 + .1 * ease_back(lt * 5))
        c = info["card"]; c2 = c.resize((int(c.width * z), int(c.height * z)), Image.BILINEAR).convert("RGBA").rotate(-1.5 if i % 2 else 1.5, expand=True, resample=Image.BICUBIC)
        x, y = int(W / 2 - c2.width / 2), int(H * .44 - c2.height / 2)
        d2 = ImageDraw.Draw(fr, "RGBA"); d2.rectangle([x + 18, y + 22, x + c2.width + 18, y + c2.height + 22], fill=(0, 0, 0, 120))
        fr.paste(c2, (x, y), c2)
    lab = a.get("label", "").upper()
    if lab:
        al = ease_out(lt * 3); d2 = ImageDraw.Draw(fr, "RGBA")
        f = fit(d2, lab, W - 200, 88, F_XB); tw = d2.textlength(lab, font=f)
        d2.rectangle([W / 2 - tw / 2 - 30, H * .115 - 64, W / 2 + tw / 2 + 30, H * .115 + 64], fill=rgba(ACC, 255 * al))
        text_c(d2, (W / 2, H * .115), lab, f, (10, 10, 10, int(255 * al)))

TEMPL = dict(hook=t_hook, map=t_map, counter=t_counter, newspaper=t_newspaper, document=t_document, timeline=t_timeline,
             bars=t_bars, money=t_money, police=t_police, quote=t_quote, split=t_split, scene=t_scene, question=t_question, photo=t_photo)
SHAKE = {"hook", "police", "money"}

# ---------------- captions ----------------
def word_times(s):
    words = s["text"].replace("...", " ").replace("…", " ").split()
    tot = sum(len(w) + 2 for w in words) or 1; t = s["start"]; out = []
    for w in words:
        dt = (s["end"] - s["start"]) * (len(w) + 2) / tot; out.append((w, t, t + dt)); t += dt
    return out
chunks = []
for s in seg:
    ws = word_times(s); chunks += [ws[k:k + 3] for k in range(0, len(ws), 3)]

def draw_captions(fr, t):
    d = ImageDraw.Draw(fr)
    for c in chunks:
        if c[0][1] - .02 <= t < c[-1][2] + .05:
            line = " ".join(w for w, _, _ in c).upper()
            fsz = 112
            while d.textlength(line, font=font(fsz)) > W - 110: fsz -= 4
            fc = font(fsz); x = W / 2 - d.textlength(line, font=fc) / 2; y = int(H * .765)
            pop_in = ease_back((t - c[0][1]) * 6)
            for w, a0, a1 in c:
                wu = w.upper(); cur = a0 <= t < a1; ww = d.textlength(wu, font=fc)
                if CAP_STYLE == "box" and cur:
                    d.rounded_rectangle([x - 14, y - fsz * .62, x + ww + 14, y + fsz * .58], 18, fill=rgba(ACC2))
                    d.text((x + ww / 2, y), wu, font=fc, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0), anchor="mm")
                else:
                    sz = fsz * (1.12 if cur else 1) * (.85 + .15 * pop_in)
                    d.text((x + ww / 2, y), wu, font=font(sz), fill=ACC if cur else (255, 255, 255), stroke_width=11, stroke_fill=(0, 0, 0), anchor="mm")
                x += ww + d.textlength(" ", font=fc)
            break

# ---------------- render loop ----------------
ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                       "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "1.7M", "-bufsize", "3.4M", "-pix_fmt", "yuv420p", f"{wd}/video_only.mp4"],
                      stdin=subprocess.PIPE)
events = []  # (time, kind) for sound design
cur = -1
for n in range(NF):
    t = n / FPS
    i = next((k for k, s in enumerate(seg) if s["s0"] <= t < s["s1"]), len(seg) - 1)
    s = seg[i]; lt = t - s["s0"]; sd = s["s1"] - s["s0"]
    if i != cur:
        cur = i; events.append((t, s["trans"], s["visual"]))
    bg = BG_VARIANTS[i % len(BG_VARIANTS)]
    z = 1.0 + .06 * (lt / max(sd, .1))  # slow push-in
    base = bg.resize((int(W * z), int(H * z))).crop((int(W * (z - 1) / 2), int(H * (z - 1) / 2), int(W * (z - 1) / 2) + W, int(H * (z - 1) / 2) + H))
    _bi = load_img(s["data"].get("image")) if s["visual"] != "photo" else None
    if _bi: base = moving(_bi["dark"], lt, sd, i, .10)
    d = ImageDraw.Draw(base, "RGBA")
    TEMPL.get(s["visual"], t_scene)(base, d, lt, sd, s["data"], i)
    fr = base
    # transitions
    tr = s["trans"]
    if lt < .22 and tr != "none":
        k = 1 - lt / .22
        if tr == "flash": fr = Image.blend(fr, Image.new("RGB", (W, H), (255, 255, 255)), .85 * k)
        elif tr == "zoom":
            zz = 1 + .35 * k; fr = fr.resize((int(W * zz), int(H * zz))).crop((int(W * (zz - 1) / 2), int(H * (zz - 1) / 2), int(W * (zz - 1) / 2) + W, int(H * (zz - 1) / 2) + H))
        elif tr == "whip":
            sm = fr.resize((max(1, int(W / (1 + 30 * k))), H)).resize((W, H)); off = int(W * .5 * k)
            fr = ImageChops.offset(sm, off, 0)
        elif tr == "glitch":
            r_, g_, b_ = fr.split(); o = int(40 * k) + 6
            fr = Image.merge("RGB", (ImageChops.offset(r_, o, 0), g_, ImageChops.offset(b_, -o, 0)))
            if int(lt * 60) % 2: fr = ImageChops.offset(fr, 0, int(30 * k))
    # shake
    if s["visual"] in SHAKE and lt < .45:
        a_ = (1 - lt / .45) * 22; fr = ImageChops.offset(fr, int(R.uniform(-a_, a_)), int(R.uniform(-a_, a_)))
    # grade: grain + scanlines
    fr = Image.blend(fr, Image.merge("RGB", [GRAIN[n % 5]] * 3), .05)
    fr = ImageChops.subtract(fr, Image.merge("RGB", [SCAN] * 3))
    fr = fr.convert("RGBA")
    draw_captions(fr, t)
    dd = ImageDraw.Draw(fr)
    dd.rectangle([0, 0, W * (t / DUR), 10], fill=rgba(ACC))  # progress bar
    ff.stdin.write(fr.convert("RGB").tobytes())
ff.stdin.close(); ff.wait()

# ---------------- sound design ----------------
N = int(DUR * sr); tt = np.arange(N) / sr; rng = np.random.default_rng(seed % 1000)
bpm = R.choice([84, 90, 96, 100]); beat = 60 / bpm
root = R.choice([41.2, 43.65, 46.25, 49.0])  # E1 F1 F#1 G1
prog = R.choice([[0, 8, 3, 10], [0, 5, 8, 7], [0, 3, 8, 5]])
music = np.zeros(N)
bar = beat * 4
for bi in range(int(DUR / bar) + 1):
    f0 = root * 2 ** (prog[bi % 4] / 12); a0 = int(bi * bar * sr); a1 = min(N, int((bi + 1) * bar * sr))
    if a0 >= N: break
    x = tt[a0:a1] - bi * bar
    env = np.minimum(1, x * 4) * np.exp(-x * .35)
    music[a0:a1] += (np.sin(2 * np.pi * f0 * 2 * x) * .5 + np.sin(2 * np.pi * f0 * 3 * x) * .18 + np.sin(2 * np.pi * f0 * 4.0 * x + np.sin(x * 3)) * .1) * env * .5
    music[a0:a1] += np.sin(2 * np.pi * f0 * x) * .5 * np.exp(-x * 1.2)
def add(arr, at, sig, gain=1.0):
    i0 = int(at * sr)
    if i0 >= N: return
    L = min(len(sig), N - i0); arr[i0:i0 + L] += sig[:L] * gain
kick = np.sin(2 * np.pi * (50 + 120 * np.exp(-np.arange(int(.35 * sr)) / sr * 30)) * np.arange(int(.35 * sr)) / sr) * np.exp(-np.arange(int(.35 * sr)) / sr * 9)
def tone(f0, f1, L, decay):  # clean pitched blip, NO noise (noise = audible "shhh")
    n_ = int(L * sr); x = np.arange(n_) / sr
    ph = 2 * np.pi * np.cumsum(np.linspace(f0, f1, n_)) / sr
    return np.sin(ph) * np.exp(-x * decay) * np.minimum(1, x * 400)
k_ = 0.0; step = 0
while k_ < DUR - .3:
    if step % 4 in (0, 2) or (step % 8 == 7): add(music, k_, kick, .9)
    k_ += beat; step += 1
sfx = np.zeros(N)
def boom(L=1.0):
    n_ = int(L * sr); x = np.arange(n_) / sr
    return np.sin(2 * np.pi * (36 + 70 * np.exp(-x * 9)) * x) * np.exp(-x * 3.5)
for (t0, tr, vis) in events:
    if tr != "none": add(sfx, t0, tone(320, 160, .12, 30), .35)          # soft tonal "pop" on cuts
    if vis in ("hook", "police", "money") or tr == "flash": add(sfx, t0, boom(), .9)
    if vis == "counter":
        for k in range(14): add(sfx, t0 + k * .07, tone(1800, 1800, .03, 160), .25)
    if vis in ("document", "quote"):
        for k in range(24): add(sfx, t0 + .3 + k * .09, tone(1100, 900, .025, 200), .18)
# duck music under voice
v_env = np.zeros(N); L = min(len(vo), N); v_env[:L] = np.abs(vo[:L])
v_env = np.convolve(v_env, np.ones(int(.15 * sr)) / int(.15 * sr), "same")
duck = 1 - .45 * np.clip(v_env / (v_env.max() + 1e-9) * 3, 0, 1)
mix = music / (np.abs(music).max() + 1e-9) * .22 * duck + sfx / (np.abs(sfx).max() + 1e-9) * .35
mix[:L] += vo[:L] * .95
mix = np.tanh(mix * 1.1) / np.tanh(1.1)
sf.write(f"{wd}/mix.wav", mix.astype(np.float32), sr)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/video_only.mp4", "-i", f"{wd}/mix.wav", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", f"{wd}/short.mp4"], check=True)

# ---------------- thumbnail ----------------
_ti = next((load_img(s["data"].get("image")) for s in seg if s["data"].get("image")), None)
th = (_ti["cover"].crop(((BWc - W) // 2, (BHc - H) // 2, (BWc - W) // 2 + W, (BHc - H) // 2 + H)) if _ti else BG_VARIANTS[0].copy()); d = ImageDraw.Draw(th, "RGBA")
first = seg[0]
TEMPL.get(first["visual"], t_scene)(th, d, 5.0, 6.0, first["data"], 0) if first["visual"] not in ("hook",) else None
d.rectangle([0, 0, W, H], fill=(0, 0, 0, 110))
for k in range(3):
    r_ = 300 + k * 260; d.ellipse([W / 2 - r_, H * .45 - r_, W / 2 + r_, H * .45 + r_], outline=rgba(ACC, 90 - k * 25), width=14)
words = meta.get("cover_text", "WATCH THIS").split(); y = H * .45 - (len(words) - 1) * 150
for w in words:
    f = fit(d, w, W - 100, 280)
    col = ACC2 if w.strip(".!?,").upper() == meta.get("cover_accent", "").upper() else (255, 255, 255)
    text_c(d, (W / 2, y), w, f, rgba(col), 18); y += f.size * 1.05
th.convert("RGB").save(f"{wd}/thumbnail.jpg", quality=92)
print("done", round(DUR, 1), "s, palette", [k for k, v in PALETTES.items() if v is P][0], "captions", CAP_STYLE)
