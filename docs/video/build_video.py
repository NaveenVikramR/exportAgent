"""Turn record_demo.py's frames and timeline into the MP4 and one clip per segment.

    python build_video.py <footage-dir> <ffmpeg-exe>

Writes <footage-dir>/exportagent-demo.mp4 (H.264, 1920x1080, 30 fps) and clips/NN_name.mp4.
Screencast frames arrive only when the page changes, so each frame is held until the next one.
"""
import json
import subprocess
import sys
from pathlib import Path

root, ffmpeg = Path(sys.argv[1]), sys.argv[2]
timeline = json.loads((root / "timeline.json").read_text())
frames, segments = timeline["frames"], timeline["segments"]
end = next(s["start"] for s in segments if s["key"] == "end")

# The frame on screen at t=0 is the last one captured before it.
start_index = max((i for i, f in enumerate(frames) if f["t"] <= 0), default=0)
shown = frames[start_index:]
lines = []
for i, frame in enumerate(shown):
    t = max(frame["t"], 0.0)
    nxt = min(shown[i + 1]["t"], end) if i + 1 < len(shown) else end
    if t >= end:
        break
    lines += [f"file '{(root / frame['file']).as_posix()}'", f"duration {max(nxt - t, 0.001):.3f}"]
lines.append(lines[-2])  # concat demuxer: repeat the last file so its duration counts
(root / "frames.txt").write_text("\n".join(lines) + "\n")

video = root / "exportagent-demo.mp4"
subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(root / "frames.txt"),
                "-vf", "scale=1920:1080:flags=lanczos,fps=30", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)], check=True)

clips = root / "clips"
clips.mkdir(exist_ok=True)
for seg, nxt in zip(segments, segments[1:]):
    out = clips / f"{seg['key']}.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{seg['start']:.3f}", "-to", f"{nxt['start']:.3f}",
                    "-i", str(video), "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(out)], check=True)

summary = [{"key": s["key"], "title": s["title"], "start": s["start"], "end": n["start"]} for s, n in zip(segments, segments[1:])]
(root / "segments.json").write_text(json.dumps(summary, indent=1))
for s in summary:
    print(f"{s['start']:7.2f}-{s['end']:7.2f}  {s['key']}: {s['title']}")
print(f"total {end:.1f} s -> {video}")
