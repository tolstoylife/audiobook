#!/usr/bin/env python3
"""Voice audition: the 3 ch02 problem sentences in each British voice (male + female).
Output: audition_<voice>.wav  (one per voice, 3 sentences + 0.45s gaps).
Per-sentence WAVs are cached in wav_aud/, so re-running only synthesizes new voices."""
import subprocess, os

VOICES = ["bm_george", "bm_fable", "bm_lewis", "bm_daniel",
          "bf_alice", "bf_emma", "bf_isabella", "bf_lily"]
GAP = 0.45
SR = 24000
SENTS = [
    # the "the satisfaction" spot
    "All productive labor, in the final analysis, consists in working up land, or materials drawn from land, into such forms as fit them for the satisfaction of human wants and desires.",
    # the rushed "while taunting him" clause
    "There is a deeper and more insidious form, a more cursed form yet before us, to abolish, in this industrial slavery that makes a man a virtual slave, while taunting him and mocking him in the name of freedom.",
    # the "the working classes" spot
    'Did you ever think, says Henry George in another part of the same speech, of the utter absurdity and strangeness of the fact that all over the civilized world the working classes are the poor classes?',
]

def run(cmd): subprocess.run(cmd, check=True, capture_output=True, text=True)
os.makedirs("wav_aud", exist_ok=True)
sil = f"wav_aud/_sil.wav"
run(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono","-t",str(GAP),"-c:a","pcm_s16le",sil])

for v in VOICES:
    concat = open(f"wav_aud/{v}.txt","w")
    for i, s in enumerate(SENTS):
        wav = f"wav_aud/{v}_s{i}.wav"
        if not os.path.exists(wav):
            tmp = f"wav_aud/{v}_s{i}.in.txt"; open(tmp,"w").write(s+"\n")
            print(f">> {v} sentence {i+1}/3")
            run(["kokoro-tts-tool","infinite","--input",tmp,"--output",wav,"--voice",v,"--no-markdown"])
            norm = wav+".n.wav"
            run(["ffmpeg","-y","-i",wav,"-ar",str(SR),"-ac","1","-c:a","pcm_s16le",norm]); os.replace(norm,wav)
        concat.write(f"file '{os.path.abspath(wav)}'\n")
        if i < len(SENTS)-1: concat.write(f"file '{os.path.abspath(sil)}'\n")
    concat.close()
    out = f"audition_{v}.wav"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",f"wav_aud/{v}.txt","-c","copy",out])
    print(f">> {out}")
print(">> done")
