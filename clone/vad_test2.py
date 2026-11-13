import queue,time,wave,numpy as np
import mvp
with wave.open("e2e_capture.wav","rb") as w:
    pcm=np.frombuffer(w.readframes(w.getnframes()),dtype="<i2").astype(np.float32)/32768.0
inq=queue.Queue(); outq=queue.Queue()
v=mvp.VadSegmenter(inq,outq); v.start()
for i in range(0,len(pcm)-1600,1600):
    inq.put(pcm[i:i+1600]); time.sleep(0.01)
time.sleep(1.0); v.running=False
items=[]
while not outq.empty(): items.append(outq.get())
print("emits:",[(k,round(len(p)/16000,2)) for k,p in items])
