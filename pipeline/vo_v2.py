"""vo_v2 — narration with free Kokoro TTS.
Usage: python3 vo_v2.py <workdir> [voice] [speed]
workdir/script.json = [{"text": "...", "visual": "map", "data": {...}}, ...]  (one entry per spoken line)
Needs /tmp/kokoro.onnx and /tmp/voices.bin (see README). Writes vo.wav + seg.json (script + start/end times).
"""
import json, sys
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
wd = sys.argv[1]; voice = sys.argv[2] if len(sys.argv) > 2 else "am_onyx"; speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.22
script = json.load(open(f"{wd}/script.json"))
k = Kokoro("/tmp/kokoro.onnx", "/tmp/voices.bin")
out, t, sr = [], 0.0, 24000
for i, s in enumerate(script):
    a, sr = k.create(s["text"], voice=voice, speed=speed, lang="en-us")
    gap = 0.35 if s["text"].rstrip().endswith(("...", "?")) else 0.12
    s["start"], s["end"] = round(t, 2), round(t + len(a) / sr, 2)
    out += [a, np.zeros(int(gap * sr), dtype=a.dtype)]; t += len(a) / sr + gap
sf.write(f"{wd}/vo.wav", np.concatenate(out), sr)
json.dump(script, open(f"{wd}/seg.json", "w"), indent=1)
print("voiceover", round(t, 2), "s")
