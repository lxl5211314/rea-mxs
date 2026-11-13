import queue,time,wave,numpy as np
import mvp
with wave.open("e2e_capture.wav","rb") as w:
    pcm=np.frombuffer(w.readframes(w.getnframes()),dtype="<i2").astype(np.float32)/32768.0
asr=mvp.Asr(); print("mode",asr.mode)
for end in (1.4,2.6,4.0,5.2,6.5):
    seg=pcm[:int(end*16000)]
    t=time.time(); txt=asr.transcribe(seg)
    print("%.1fs -> %.2fs is_q=%s | %s"%(end,time.time()-t,mvp.is_question(txt),txt))
