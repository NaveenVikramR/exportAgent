"""Voice samples for the narration: the first line in a few Kokoro voices.

    python tts_samples.py <kokoro-model-dir>

Kokoro-82M (Apache-2.0) through kokoro-onnx, run locally. Writes voice-samples/<voice>.wav.
"""
import sys
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
MODEL_DIR = Path(sys.argv[1])
LINE = "This is ExportAgent, an AI export desk for apparel and textile exporters."
VOICES = {
    "af_heart": "US English, female",
    "am_michael": "US English, male",
    "bm_george": "UK English, male",
}

kokoro = Kokoro(str(MODEL_DIR / "kokoro-v1.0.onnx"), str(MODEL_DIR / "voices-v1.0.bin"))
out = HERE / "voice-samples"
out.mkdir(exist_ok=True)
for voice, label in VOICES.items():
    lang = "en-gb" if voice.startswith("b") else "en-us"
    samples, rate = kokoro.create(LINE, voice=voice, speed=1.0, lang=lang)
    path = out / f"{voice}.wav"
    sf.write(path, samples, rate)
    print(f"{path.name}: {label}, {len(samples) / rate:.1f} s")
