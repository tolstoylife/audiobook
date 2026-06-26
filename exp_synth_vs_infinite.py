#!/usr/bin/env python3
"""Throwaway A/B: does the long-sentence pitch artifact come from the `infinite`
command, or from Kokoro itself? Synthesize two problem sentences both ways.

Output exp_synth_vs_infinite.wav plays, in order:
  A  (current method: infinite)   <gap>   A  (alternative: synthesize)
  <longer gap>
  B  (current method: infinite)   <gap>   B  (alternative: synthesize)

If the 2nd of each pair has a cleaner ENDING (last word falls naturally, no
mid-phrase pause), the fix is switching the build from `infinite` to `synthesize`.
If both sound the same, it's a Kokoro limit, not the tool.
"""
import subprocess, os

VOICE = "bm_daniel"; SR = 24000
SENTS = {
    "A": "Men are compelled to compete with each other for the wages of an employer, because they have been robbed of the natural opportunities of employing themselves.",
    "B": "In the Old Testament we are told that when the Israelites journeyed through the desert they were hungered, and that God sent manna down out of the heavens.",
}
os.makedirs("exp", exist_ok=True)
def run(cmd, **kw): subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
def norm(w):
    n = w + ".n.wav"; run(["ffmpeg","-y","-i",w,"-ar",str(SR),"-ac","1","-c:a","pcm_s16le",n]); os.replace(n,w)
def sil(path, sec):
    run(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono","-t",str(sec),"-c:a","pcm_s16le",path])

sil("exp/_g.wav", 0.7); sil("exp/_gg.wav", 1.4)
order = []
for k, s in SENTS.items():
    inf = f"exp/{k}_inf.wav"; syn = f"exp/{k}_syn.wav"
    run(["kokoro-tts-tool","infinite","--stdin","--output",inf,"--voice",VOICE,"--no-markdown"], input=s+"\n")
    run(["kokoro-tts-tool","synthesize","--stdin","--output",syn,"--voice",VOICE], input=s+"\n")
    norm(inf); norm(syn)
    order += [inf, "exp/_g.wav", syn, "exp/_gg.wav"]
order = order[:-1]  # drop trailing long gap

with open("exp/concat.txt","w") as f:
    for w in order: f.write(f"file '{os.path.abspath(w)}'\n")
run(["ffmpeg","-y","-f","concat","-safe","0","-i","exp/concat.txt","-c","copy","exp_synth_vs_infinite.wav"])
print(">> exp_synth_vs_infinite.wav  (A-infinite, A-synthesize, B-infinite, B-synthesize)")
