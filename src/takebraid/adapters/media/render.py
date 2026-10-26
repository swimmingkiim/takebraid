"""Bounded, argument-list preview execution and decoded output verification."""

import math
import subprocess
import tempfile
import time
from fractions import Fraction
from pathlib import Path

from takebraid.adapters.media.frames import decode_frames
from takebraid.adapters.media.probe import ProbeError, probe_media
from takebraid.domain.timeline import SAMPLE_RATE, ClipLayout, ManualTimeline


def run_media(command: list[str], *, deadline: float, cwd: Path | None = None) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProbeError("Preview rendering timed out")
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                timeout=remaining,
                cwd=cwd,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProbeError("FFmpeg not found; install FFmpeg and add it to PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProbeError("Preview rendering timed out; raise --timeout") from exc
        errors.seek(0)
        diagnostic = errors.read(4000).strip()
        if result.returncode or diagnostic:
            raise ProbeError(f"FFmpeg preview failed: {diagnostic or result.returncode}")


def ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        raise ProbeError("Cannot read FFmpeg version; check installation") from exc


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def video_filter(clip: ClipLayout, timeline: ManualTimeline) -> str:
    fps = timeline.frame_rate
    # Normalize non-square pixels and rotation already applied by FFmpeg to a 640x360 box.
    scale = (
        "scale=w='max(2,trunc(iw*sar*min(1,min(640/(iw*sar),360/ih))/2)*2)':"
        "h='max(2,trunc(ih*min(1,min(640/(iw*sar),360/ih))/2)*2)',setsar=1"
    )
    return (
        f"trim=start_frame={clip.start_frame}:end_frame={clip.end_frame},setpts=PTS-STARTPTS,"
        f"fps=fps={fps.numerator}/{fps.denominator}:round=up:start_time=0,"
        f"tpad=stop_mode=clone:stop={clip.frame_count},trim=end_frame={clip.frame_count},"
        f"{scale},settb=expr={fps.denominator}/{fps.numerator},setpts=N"
    )


def audio_filter(clip: ClipLayout) -> str:
    start = _ceil(clip.source.time_base.seconds(clip.source.in_pts) * SAMPLE_RATE)
    end = _ceil(clip.source.time_base.seconds(clip.source.out_pts) * SAMPLE_RATE)
    return (
        f"aresample={SAMPLE_RATE},asettb=1/{SAMPLE_RATE},atrim=start_pts={start}:end_pts={end},"
        f"asetpts=PTS-({start}),aresample={SAMPLE_RATE}:async=1:first_pts=0,"
        f"aformat=sample_fmts=s16:sample_rates={SAMPLE_RATE}:channel_layouts=stereo,"
        f"apad=whole_len={clip.sample_count},atrim=end_sample={clip.sample_count},asetpts=N/SR/TB"
    )


def render_preview(
    source: Path,
    timeline: ManualTimeline,
    clips: tuple[ClipLayout, ...],
    directory: Path,
    *,
    timeout: float,
) -> Path:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ProbeError("Render timeout must be positive and finite")
    deadline = time.monotonic() + timeout
    fps = f"{timeline.frame_rate.numerator}/{timeline.frame_rate.denominator}"
    encoding = [
        "-c:v",
        "mpeg4",
        "-q:v",
        "3",
        "-pix_fmt",
        "yuv420p",
        "-r",
        fps,
        "-enc_time_base:v",
        f"{timeline.frame_rate.denominator}/{timeline.frame_rate.numerator}",
        "-fps_mode",
        "cfr",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-metadata:s:v:0",
        "rotate=0",
    ]
    names = []
    for index, clip in enumerate(clips):
        name = f"clip-{index:04d}.mov"
        names.append(name)
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-copyts",
            "-protocol_whitelist",
            "file",
            "-i",
            str(source),
            "-map",
            f"0:{timeline.stream_index}",
            "-vf",
            video_filter(clip, timeline),
        ]
        if timeline.audio_policy == "source":
            command += [
                "-map",
                f"0:{timeline.audio_stream_index}",
                "-af",
                audio_filter(clip),
                "-c:a",
                "pcm_s16le",
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                "2",
            ]
        else:
            command += ["-an"]
        run_media(command + encoding + [str(directory / name)], deadline=deadline)
    playlist = directory / "concat.txt"
    playlist.write_text("".join(f"file '{name}'\n" for name in names), encoding="utf-8")
    output = directory / "preview.mov"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-n",
        "-protocol_whitelist",
        "file",
        "-f",
        "concat",
        "-safe",
        "1",
        "-i",
        playlist.name,
        "-map",
        "0:v:0",
        "-vf",
        f"settb=expr={timeline.frame_rate.denominator}/{timeline.frame_rate.numerator},setpts=N",
    ]
    if timeline.audio_policy == "source":
        command += ["-map", "0:a:0", "-af", "asetpts=N/SR/TB", "-c:a", "pcm_s16le"]
    else:
        command += ["-an"]
    run_media(command + encoding + [output.name], deadline=deadline, cwd=directory)
    return output


def verify_preview(output: Path, timeline: ManualTimeline, clips: tuple[ClipLayout, ...]) -> dict:
    metadata = probe_media(output)
    videos = [s for s in metadata.streams if s.kind == "video"]
    audio = [s for s in metadata.streams if s.kind == "audio"]
    if len(videos) != 1 or len(audio) != (1 if timeline.audio_policy == "source" else 0):
        raise ProbeError("Rendered stream layout disagrees with timeline")
    video = videos[0]
    if (
        not video.width
        or not video.height
        or video.width > 640
        or video.height > 360
        or video.width % 2
        or video.height % 2
        or video.rotation_degrees not in (None, 0)
    ):
        raise ProbeError("Rendered geometry/rotation is invalid")
    frames = decode_frames(output, video.index, max_frames=1000000)
    count = sum(clip.frame_count for clip in clips)
    if len(frames) != count:
        raise ProbeError("Rendered frame count disagrees with timeline")
    for index, frame in enumerate(frames):
        if (
            frame.pts is None
            or video.time_base.seconds(frame.pts) != Fraction(index, 1) / timeline.frame_rate
        ):
            raise ProbeError("Rendered presentation clock disagrees with timeline")
    last = frames[-1]
    if (
        last.duration is None
        or video.time_base.seconds(last.pts + last.duration)
        != Fraction(count, 1) / timeline.frame_rate
    ):
        raise ProbeError("Rendered final presentation end disagrees with timeline")
    samples = 0
    if audio:
        stream = audio[0]
        if stream.sample_rate != SAMPLE_RATE or stream.codec != "pcm_s16le" or stream.channels != 2:
            raise ProbeError("Rendered audio format disagrees with timeline")
        with (
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as handle,
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors,
        ):
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file",
                    "-select_streams",
                    str(stream.index),
                    "-show_frames",
                    "-show_entries",
                    "frame=pts,nb_samples:frame_side_data=",
                    "-of",
                    "compact=p=0:nk=0",
                    str(output),
                ],
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=errors,
                timeout=300,
                check=False,
            )
            errors.seek(0)
            if result.returncode or errors.read(4000).strip():
                raise ProbeError("Cannot verify rendered audio samples")
            handle.seek(0)
            for line in handle:
                fields = dict(part.split("=", 1) for part in line.strip().split("|") if "=" in part)
                pts, size = int(fields["pts"]), int(fields["nb_samples"])
                if size <= 0 or stream.time_base.seconds(pts) != Fraction(samples, SAMPLE_RATE):
                    raise ProbeError("Rendered audio has a gap or overlap")
                samples += size
        if samples != sum(clip.sample_count for clip in clips):
            raise ProbeError("Rendered sample count disagrees with timeline")
    return {
        "schema_version": "0.1",
        "video_frames": count,
        "audio_samples": samples,
        "duration_seconds": Fraction(count, 1) / timeline.frame_rate,
        "width": video.width,
        "height": video.height,
        "verification": "decoded_counts_and_clocks",
    }
