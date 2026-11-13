import wave,numpy as np,time
import mvp
with wave.open("e2e_capture.wav","rb") as w:
    pcm=np.frombuffer(w.readframes(w.getnframes()),dtype="<i2").astype(np.float32)/32768.0
asr=mvp.Asr()
for end in (4.0,5.2,5.6):
    for pad in (0.0,0.3,0.5):
        seg=np.concatenate([pcm[:int(end*16000)], np.zeros(int(pad*16000),dtype=np.float32)])
        txt=asr.transcribe(seg)
        print("end=%.1f pad=%.1f -> %s"%(end,pad,txt))
