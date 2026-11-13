import os,subprocess,sys,time
WAV=r"C:\Program Files\msx-client\resources\self-test-interviewer.wav"
env=dict(os.environ); env["PYTHONIOENCODING"]="utf-8"
p=subprocess.Popen([sys.executable,"mvp.py","--no-ui"],cwd=r"E:\aaa_msx\clone",env=env,
    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",bufsize=1)
time.sleep(9)
print(">>> PLAY",flush=True)
subprocess.run(["python","-c",f"import winsound;winsound.PlaySound(r'{WAV}', winsound.SND_FILENAME)"],check=False)
time.sleep(16)
p.terminate()
try: out,_=p.communicate(timeout=5)
except subprocess.TimeoutExpired:
    p.kill(); out,_=p.communicate()
print("----- mvp -----",flush=True)
print(out,flush=True)
