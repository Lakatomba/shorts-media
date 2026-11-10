# Shorts pipeline v2
1. pip install --break-system-packages -q kokoro-onnx soundfile
2. curl -sL -o /tmp/kokoro.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
   curl -sL -o /tmp/voices.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
3. Write <wd>/script.json (see example_script.json and the VISUALS list at the top of render_v2.py) and <wd>/meta.json
3b. python3 prep_images.py <wd>  -> real photos from Wikimedia Commons (needs those domains allowed)
4. python3 vo_v2.py <wd>     -> vo.wav, seg.json
5. python3 render_v2.py <wd> -> short.mp4, thumbnail.jpg
