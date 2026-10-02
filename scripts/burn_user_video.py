import os
import re
import subprocess
import sys
import time

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_srt(srt_path):
    with open(srt_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\d+\n|\Z)')
    matches = pattern.findall(text)
    def to_sec(t_str):
        h, m, s_ms = t_str.split(':')
        s, ms = s_ms.split(',')
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
    items = []
    for m in matches:
        items.append({
            'start': to_sec(m[1]),
            'end': to_sec(m[2]),
            'text': m[3].strip().replace('\r', '')
        })
    return items

def split_long_item(item, max_chars=50, min_dur_split=4.5):
    start = item['start']
    end = item['end']
    dur = end - start
    text = item['text'].replace('\n', ' ').strip()
    if len(text) <= max_chars or dur < min_dur_split:
        return [item]

    parts = re.split(r'([,;:.?!]+)', text)
    clauses = []
    curr = ''
    for p in parts:
        curr += p
        if re.search(r'[,;:.?!]$', curr.strip()) and len(curr.strip()) >= 18:
            clauses.append(curr.strip())
            curr = ''
    if curr.strip():
        clauses.append(curr.strip())

    if len(clauses) <= 1:
        words = text.split()
        clauses = []
        c = []
        for w in words:
            c.append(w)
            if len(' '.join(c)) >= max_chars:
                clauses.append(' '.join(c))
                c = []
        if c:
            clauses.append(' '.join(c))

    total_len = sum(len(c) for c in clauses)
    if total_len == 0:
        return [item]

    res = []
    curr_time = start
    for idx, c in enumerate(clauses):
        portion = len(c) / total_len
        c_dur = dur * portion
        c_end = curr_time + c_dur if idx < len(clauses)-1 else end
        clean_text = c.strip().rstrip(',')
        if clean_text:
            res.append({'start': round(curr_time, 2), 'end': round(c_end, 2), 'text': clean_text})
        curr_time = c_end
    return res

def sec_to_ass(sec):
    total_cs = int(round(sec * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_box_ass(items, ass_path, video_w=640, video_h=480, font_size=18, margin_v=12):
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {video_w}",
        f"PlayResY: {video_h}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial,{font_size},&H0000E5FF&,&H000000FF&,&H40000000&,&H40000000&,1,0,0,0,100,100,0,0,3,4.5,0,2,20,20,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    # Khử trùng thời gian để không chồng lấn
    for i in range(len(items) - 1):
        if items[i]["end"] > items[i + 1]["start"]:
            items[i]["end"] = max(items[i]["start"] + 0.1, round(items[i + 1]["start"] - 0.02, 2))

    for it in items:
        st = sec_to_ass(it['start'])
        et = sec_to_ass(it['end'])
        txt = it['text'].replace('\n', ' ').strip()
        txt_padded = f"\\h {txt} \\h"
        lines.append(f"Dialogue: 0,{st},{et},Default,,0,0,0,,{txt_padded}")

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Generated ASS with {len(items)} dialogues at {ass_path}")

def main():
    video_dir = r"C:\Users\boycu\Downloads\Video"
    srt_file = os.path.join(video_dir, "sOns2lUoleQ.vi.srt")
    video_file = os.path.join(video_dir, "京沪高速铁路桥上CRTSⅡ板式无砟轨道施工技术指南 RMVB格式 🇨🇳.mp4")
    out_video = os.path.join(video_dir, "京沪高速铁路桥上CRTSⅡ_PhuDe_TiengViet_480p_Chuan.mp4")
    ass_file = os.path.join(video_dir, "temp_subtitles_box.ass")

    print("Reading and processing SRT...")
    raw_items = parse_srt(srt_file)
    print(f"Raw items: {len(raw_items)}")

    final_items = []
    for it in raw_items:
        final_items.extend(split_long_item(it))
    print(f"Final processed subtitle items: {len(final_items)}")

    # Chuẩn 480p: 640x480 (tránh bị YouTube/Player nhận nhầm thành 360p do chiều rộng 600)
    generate_box_ass(final_items, ass_file, video_w=640, video_h=480, font_size=18, margin_v=12)

    ffmpeg = r"d:\code\KathSldeToVideo\.venv\Scripts\ffmpeg.exe"
    esc_ass = ass_file.replace("\\", "/").replace(":", "\\:")

    # Check encoder
    test_nvenc = subprocess.run([ffmpeg, "-f", "lavfi", "-i", "nullsrc=s=640x480:d=1", "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
    vcodec = "h264_nvenc" if test_nvenc.returncode == 0 else "libx264"
    print(f"Using video encoder: {vcodec}")

    cmd = [
        ffmpeg, "-y",
        "-i", video_file,
        "-vf", f"scale=640:480:flags=lanczos,subtitles='{esc_ass}'",
        "-c:v", vcodec,
        "-pix_fmt", "yuv420p",
    ]
    if vcodec == "h264_nvenc":
        # Chất lượng cao: cq 15, bitrate 2.5 Mbps, preset p7
        cmd.extend(["-preset", "p7", "-cq", "15", "-b:v", "2500k", "-maxrate", "4000k"])
    else:
        cmd.extend(["-preset", "slow", "-crf", "16"])
    cmd.extend(["-c:a", "copy", out_video])

    print("Running FFmpeg render...")
    print("Command:", " ".join(cmd))
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    dur_match = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    total_dur = 1943.13

    for line in proc.stdout:
        m = dur_match.search(line)
        if m:
            cur = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
            pct = min(100, int((cur / total_dur) * 100))
            sys.stdout.write(f"\rEncoding progress: {pct}% [{cur:.1f}s / {total_dur:.1f}s]")
            sys.stdout.flush()

    proc.wait()
    t1 = time.time()
    print(f"\nFinished in {t1 - t0:.1f} seconds. Exit code: {proc.returncode}")
    if proc.returncode == 0 and os.path.exists(out_video):
        size_mb = os.path.getsize(out_video) / (1024 * 1024)
        print(f"Success! Output video created: {out_video} ({size_mb:.1f} MB)")
    else:
        print("Error: FFmpeg failed!")

if __name__ == "__main__":
    main()
