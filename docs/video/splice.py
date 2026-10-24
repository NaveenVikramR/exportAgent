"""Replace some clips and rebuild the full MP4 and segments.json from the clips in order.

    python splice.py <ffmpeg> <new-clips-dir> [<key> ...]

Copies <new-clips-dir>/<key>.mp4 over clips/<key>.mp4 for each key, then joins every clip in
segments.json order into exportagent-demo.mp4 and rewrites the segment start/end times
from the clips' real durations. Titles come from the new take's segments.json when given.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ffmpeg, new_dir, keys = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
segments = json.loads((HERE / "segments.json").read_text())
new_titles = {}
if (new_dir.parent / "segments.json").exists():
    new_titles = {s["key"]: s["title"] for s in json.loads((new_dir.parent / "segments.json").read_text())}
for key in keys:
    shutil.copyfile(new_dir / f"{key}.mp4", HERE / "clips" / f"{key}.mp4")


def duration(path: Path) -> float:
    out = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


lst = HERE / "clips.txt"
lst.write_text("".join(f"file '{(HERE / 'clips' / (s['key'] + '.mp4')).as_posix()}'\n" for s in segments))
subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
                "-movflags", "+faststart", str(HERE / "exportagent-demo.mp4")], check=True)
lst.unlink()

t = 0.0
for seg in segments:
    seg["title"] = new_titles.get(seg["key"], seg["title"])
    seg["start"] = round(t, 2)
    t += duration(HERE / "clips" / f"{seg['key']}.mp4")
    seg["end"] = round(t, 2)
    print(f"{seg['start']:7.2f}-{seg['end']:7.2f}  {seg['key']}")
(HERE / "segments.json").write_text(json.dumps(segments, indent=1))
print(f"total {t:.1f} s")
