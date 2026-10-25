"""Make the narrated demo video: Kokoro TTS voiceover, loudness-normalised, mixed onto the footage.

    python voiceover_tts.py <kokoro-model-dir> <ffmpeg>

Reads the narration lines from narration.py and the segment times from segments.json.
Writes audio/NN_<segment>.wav (one per line), audio/voiceover.wav (normalised),
exportagent-final.mp4, exportagent-final-captioned.mp4, and rewrites exportagent-demo.srt
with the real start and end of every spoken line.

Voice: Kokoro-82M (Apache-2.0) via kokoro-onnx, voice bm_george (UK English, male).
Pronunciation fixes go into the phonemes only; subtitles keep the normal spelling.
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
MODEL_DIR, FFMPEG = Path(sys.argv[1]), sys.argv[2]
VOICE, LANG = "bm_george", "en-gb"
BASE_SPEED, MIN_SPEED, MAX_SPEED = 1.0, 0.9, 1.1
GAP = 0.25          # minimum pause before the next line starts (seconds)
TARGET_LUFS = -16.0

# Words read differently from their spelling: (text spelling for TTS, phonemes espeak gives, phonemes we want)
TEXT_FOR_TTS = {
    "NW-45120": "N W four five one two oh",
    "$0.0094": "zero point nine four cents",   # a hundredth of a dollar: "under one cent: 0.94 cents"
}
PHONEME_FIXES = {
    "Nemotron": ("nˈɛmətɹˌɒn", "nˈiːmətɹˌɒn"),     # NEE-mo-tron
    "Nebius": ("nˈiːbɪəs", "nˈɛbiəs"),             # NEB-ee-us
    "Tiruppur": ("tˈɜːɹəpˌʊə", "tɪɹˈuːpʊə"),        # ti-ROO-poor
    "Tavily": ("tˈeɪvili", "təvˈɪli"),             # tuh-VILL-ee
}


def narration() -> list[tuple[str, float, float, str]]:
    """The NARRATION list from narration.py, read without running that script."""
    tree = ast.parse((HERE / "narration.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "NARRATION")
    return ast.literal_eval(node.value)


def phonemes_for(kokoro: Kokoro, text: str) -> str:
    for spelled, spoken in TEXT_FOR_TTS.items():
        text = text.replace(spelled, spoken)
    ph = kokoro.tokenizer.phonemize(text, LANG)
    for word, (default, wanted) in PHONEME_FIXES.items():
        if word in text:
            assert default in ph, f"{word}: expected {default!r} in {ph!r}"
            ph = ph.replace(default, wanted)
    return ph


def video_duration(path: Path) -> float:
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def stamp(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    kokoro = Kokoro(str(MODEL_DIR / "kokoro-v1.0.onnx"), str(MODEL_DIR / "voices-v1.0.bin"))
    segments = {s["key"]: s for s in json.loads((HERE / "segments.json").read_text())}
    lines = narration()
    video = HERE / "exportagent-demo.mp4"
    total = video_duration(video)
    audio_dir = HERE / "audio"
    audio_dir.mkdir(exist_ok=True)

    # Per segment: one speed for all its lines, the lowest from 1.0 up to 1.1 at which every line
    # fits. A line starts at its planned time, or just after the line before it if that one runs
    # on; the last line must end before the segment does. No line ever overlaps another.
    placed, rate = [], 24000
    order = list(dict.fromkeys(key for key, *_ in lines))
    for key in order:
        seg = segments[key]
        mine = [(i, line) for i, line in enumerate(lines) if line[0] == key]
        phonemes = [phonemes_for(kokoro, text) for _, (_, _, _, text) in mine]
        for speed in [round(BASE_SPEED + 0.02 * k, 2) for k in range(int((MAX_SPEED - BASE_SPEED) / 0.02) + 1)]:
            rendered, cursor, rows = [], -1.0, []
            for (i, (_, offset, _length, text)), ph in zip(mine, phonemes):
                samples, rate = kokoro.create(ph, voice=VOICE, speed=speed, lang=LANG, is_phonemes=True)
                start = max(seg["start"] + offset, cursor + GAP)
                duration = len(samples) / rate
                cursor = start + duration
                rendered.append(samples)
                rows.append({"n": i + 1, "key": key, "text": text, "planned": round(seg["start"] + offset, 3),
                             "start": round(start, 3), "end": round(cursor, 3), "duration": round(duration, 2),
                             "speed": speed, "segment_end": seg["end"]})
            if cursor <= seg["end"] - 0.1:
                break
        else:
            raise SystemExit(f"Segment {key} does not fit even at speed {MAX_SPEED}: shorten one of its lines.")
        for row, samples in zip(rows, rendered):
            sf.write(audio_dir / f"{row['n']:02d}_{key}.wav", samples, rate)
        placed += rows

    track = np.zeros(int(total * rate) + rate, dtype=np.float32)
    for p, (i, _line) in zip(placed, enumerate(lines)):
        samples, _ = sf.read(audio_dir / f"{i + 1:02d}_{p['key']}.wav", dtype="float32")
        at = int(p["start"] * rate)
        track[at:at + len(samples)] += samples
    track = track[: int(total * rate)]
    raw = audio_dir / "voiceover-raw.wav"
    sf.write(raw, track, rate)

    # Two-pass loudness normalisation to -16 LUFS integrated, true peak below -1.5 dBTP.
    measure = subprocess.run([FFMPEG, "-hide_banner", "-i", str(raw), "-af",
                              f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
    m = json.loads(measure[measure.rindex("{"):measure.rindex("}") + 1])
    norm = audio_dir / "voiceover.wav"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(raw), "-af",
                    f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                    f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
                    "linear=true", "-ar", "48000", str(norm)], check=True)

    final = HERE / "exportagent-final.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-i", str(norm), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart",
                    str(final)], check=True)

    srt = []
    for p in placed:
        srt += [str(p["n"]), f"{stamp(p['start'])} --> {stamp(p['end'])}", p["text"], ""]
    srt_path = HERE / "exportagent-demo.srt"
    srt_path.write_text("\n".join(srt), encoding="utf-8")

    # libass scales to a 288-line canvas: FontSize 11 is about 41 px at 1080p, MarginV 7 about 26 px.
    style = ("FontName=Arial,FontSize=11,PrimaryColour=&H00FFFFFF,OutlineColour=&H40000000,BackColour=&H40000000,"
             "BorderStyle=4,Outline=1,Shadow=0,MarginV=7,MarginL=40,MarginR=40,Alignment=2")
    captioned = HERE / "exportagent-final-captioned.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(final), "-vf",
                    f"subtitles=exportagent-demo.srt:force_style='{style}'", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(captioned)],
                   check=True, cwd=HERE)

    (audio_dir / "placement.json").write_text(json.dumps(placed, indent=1))
    write_voiceover_md(placed, segments)
    for p in placed:
        moved = f"  (planned {stamp(p['planned'])[3:]})" if p["start"] - p["planned"] > 0.05 else ""
        print(f"{p['n']:2d} {stamp(p['start'])[3:]}-{stamp(p['end'])[3:]} {p['duration']:5.2f}s speed {p['speed']:.2f}  "
              f"{p['key']} ends {p['segment_end'] - p['end']:4.1f}s before the segment{moved}")
    print(f"video {total:.2f} s; loudness before {m['input_i']} LUFS, peak {m['input_tp']} dBTP")


def write_voiceover_md(placed: list[dict], segments: dict) -> None:
    """voiceover.md with the times the lines are actually spoken in the final video."""
    clock = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"  # noqa: E731
    md = ["# Demo video: voiceover script", "",
          f"Voice: Kokoro TTS (Apache-2.0), `{VOICE}` (UK English, male), run locally with kokoro-onnx. "
          "Generated by `voiceover_tts.py`; times are when each line is spoken in `exportagent-final.mp4`.",
          "Subtitles with the same text and timings: `exportagent-demo.srt`. Silent footage: `exportagent-demo.mp4`, "
          "with one clip per segment in `clips/`.", "",
          "Pronounced (TTS input only, never in the subtitles): Nemotron NEE-mo-tron, Nebius NEB-ee-us, "
          "Tiruppur ti-ROO-poor, Tavily tuh-VILL-ee; NW-45120 read as \"N W four five one two oh\", "
          "$0.0094 as \"zero point nine four cents\".", ""]
    for key, seg in segments.items():
        rows = [p for p in placed if p["key"] == key]
        speed = f" · speed {rows[0]['speed']:.2f}" if rows else ""
        md += [f"## {clock(seg['start'])}–{clock(seg['end'])} · {seg['title']}", f"Clip: `clips/{key}.mp4`{speed}", ""]
        md += [f"- **{clock(p['start'])}** {p['text']}" for p in rows]
        md.append("")
    (HERE / "voiceover.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()
