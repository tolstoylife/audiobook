#!/usr/bin/env python3
"""
Build a chaptered, paragraph-paced M4B of "A Great Iniquity".
Synthesizes each paragraph separately so pauses land where the text wants them.
Resumable: re-running skips paragraphs whose WAV already exists.

Run from the folder containing chapters/:   python3 build_audiobook.py [voice]
Requires: kokoro-tts-tool, ffmpeg, ffprobe.
"""
import subprocess, os, re, sys

VOICE    = sys.argv[1] if len(sys.argv) > 1 else "bm_george"
PARA_GAP = 0.5    # seconds of silence between paragraphs  (tweak to taste)
CHAP_GAP = 1.4    # seconds of silence between sections
BITRATE  = "128k"
SR       = 24000  # Kokoro's native sample rate
OUT      = "a_great_iniquity.m4b"
# Mastering: rumble cut, gentle de-ess, even loudness (audiobook standard)
MASTER   = "highpass=f=70,deesser=i=0.4,loudnorm=I=-19:TP=-2:LRA=7"

FILES  = [f"chapters/ch{i:02d}.txt" for i in range(10)]
TITLES = ["Introduction","Part I","Part II","Part III","Part IV",
          "Part V","Part VI","Part VII","Part VIII","Part IX"]

os.makedirs("wav", exist_ok=True)

def run(cmd, quiet=True):
    subprocess.run(cmd, check=True,
                   capture_output=quiet, text=True)

def dur(path):
    out = subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","csv=p=0", path], text=True)
    return float(out.strip())

def make_silence(path, seconds):
    if not os.path.exists(path):
        run(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono",
             "-t",str(seconds),"-c:a","pcm_s16le", path])

make_silence("wav/_sil_para.wav", PARA_GAP)
make_silence("wav/_sil_chap.wav", CHAP_GAP)

concat = open("concat.txt","w")
meta   = open("meta.txt","w")
meta.write(";FFMETADATA1\ntitle=A Great Iniquity\nartist=Leo Tolstoy\n"
           "album=A Great Iniquity\ngenre=Audiobook\ndate=1905\n\n")

cum = 0.0
def add(path):
    global cum
    concat.write(f"file '{os.path.abspath(path)}'\n")
    cum += dur(path)

for i, f in enumerate(FILES):
    paras = [p.strip() for p in re.split(r"\n\s*\n", open(f).read()) if p.strip()]
    if i > 0:
        add("wav/_sil_chap.wav")
    chap_start = cum
    for j, p in enumerate(paras):
        if j > 0:
            add("wav/_sil_para.wav")
        wav = f"wav/ch{i:02d}_p{j:02d}.wav"
        if not os.path.exists(wav):
            tmp = f"wav/ch{i:02d}_p{j:02d}.txt"
            open(tmp,"w").write(p + "\n")
            print(f">> {TITLES[i]}  para {j+1}/{len(paras)} -> {wav}")
            run(["kokoro-tts-tool","infinite","--input",tmp,
                 "--output",wav,"--voice",VOICE,"--no-markdown"], quiet=False)
            # normalize to canonical format so concat is seamless
            norm = wav + ".norm.wav"
            run(["ffmpeg","-y","-i",wav,"-ar",str(SR),"-ac","1",
                 "-c:a","pcm_s16le", norm])
            os.replace(norm, wav)
        add(wav)
    meta.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(chap_start*1000)}\n"
               f"END={int(cum*1000)}\ntitle={TITLES[i]}\n\n")

concat.close(); meta.close()

print(f">> Muxing + mastering -> {OUT}")
run(["ffmpeg","-y","-f","concat","-safe","0","-i","concat.txt","-i","meta.txt",
     "-map_metadata","1","-af",MASTER,"-ar","44100",
     "-c:a","aac","-b:a",BITRATE,"-f","mp4", OUT])
print(f">> Done: {OUT}  ({cum/60:.1f} min)")
print(">> Cleanup with:  rm -rf wav concat.txt meta.txt")
