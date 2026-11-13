"""手机端联动（局域网）：手机浏览器看答案、遥控小窗，不需要装 App。

电脑起一个 HTTP 服务，打印带 6 位配对码的地址：
    http://192.168.x.x:8765/?t=123456
手机和电脑同一个 Wi-Fi，浏览器打开即可。只有电脑 → 手机的内容同步；
手机 → 电脑只有遥控指令（截图/隐藏/翻题/透明度/缩放/退出）。
"""
from __future__ import annotations

import json
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>协同</title><style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:#0d0f12;color:#e8eaed;font:16px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding-bottom:150px}
header{position:sticky;top:0;background:#12151a;padding:10px 14px;border-bottom:1px solid #222831;z-index:9}
#st{color:#8b94a3;font-size:13px}
#st b{color:#6ee7a8;font-weight:600}
main{padding:12px 14px}
.card{background:#141821;border:1px solid #232a35;border-radius:12px;padding:12px 14px;margin-bottom:12px}
.q{color:#8f9bad;font-size:13px;margin-bottom:6px;white-space:pre-wrap}
.a{white-space:pre-wrap;font-size:17px}
.a code{background:#1d2430;padding:1px 4px;border-radius:4px;font-size:14px}
footer{position:fixed;left:0;right:0;bottom:0;background:#12151a;border-top:1px solid #222831;padding:8px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;z-index:9}
button{background:#1b212b;color:#dfe4ec;border:1px solid #2a323f;border-radius:10px;padding:12px 4px;font-size:14px}
button:active{background:#2a3441}
button.warn{color:#ffb4a8;border-color:#4a2c2c}
#tip{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);background:#000c;padding:14px 20px;border-radius:10px;display:none;z-index:99}
</style></head><body>
<header><div id="st">连接中…</div></header>
<main id="list"><div class="card"><div class="a">等待电脑推送…</div></div></main>
<footer>
<button onclick="cmd('shot')">截图出答案</button>
<button onclick="cmd('pin')">钉住</button>
<button onclick="cmd('prev')">上一题</button>
<button onclick="cmd('next')">下一题</button>
<button onclick="cmd('opacity_down')">变淡</button>
<button onclick="cmd('opacity_up')">变亮</button>
<button onclick="cmd('hide')">隐藏电脑</button>
<button onclick="cmd('show')">显示电脑</button>
<button onclick="cmd('scroll_up')">向上</button>
<button onclick="cmd('scroll_down')">向下</button>
<button onclick="cmd('scale_up')">放大</button>
<button onclick="cmd('scale_down')">缩小</button>
<button onclick="cmd('shot_window')">窗口截图</button>
<button onclick="cmd('shot_long')">长截图</button>
<button class="warn" onclick="cmd('exit')">结束本场</button>
<button onclick="cmd('cancel')">取消作答</button>
</footer><div id="tip"></div>
<script>
const T=new URLSearchParams(location.search).get('t');
let lastSig='';
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function render(d){
  if(d.sig===lastSig)return; lastSig=d.sig;
  document.getElementById('st').innerHTML='<b>'+(d.mode||'面试中')+'</b> · '+esc(d.status||'');
  const list=document.getElementById('list');
  const items=(d.items||[]).slice(-8).reverse();
  list.innerHTML=items.length?items.map(it=>'<div class="card"><div class="q">'+esc(it.q)+'</div><div class="a">'+esc(it.a)+'</div></div>').join(''):'<div class="card"><div class="a">等待电脑推送…</div></div>';
}
async function poll(){
  try{
    const r=await fetch('/api/state?t='+T+'&_='+Date.now());
    if(r.status===403){document.getElementById('st').textContent='配对码错误，请重新扫码';return}
    render(await r.json());
  }catch(e){document.getElementById('st').textContent='已断开，重连中…'}
  setTimeout(poll,800);
}
async function cmd(c){
  const tip=document.getElementById('tip');
  try{await fetch('/api/cmd?t='+T,{method:'POST',body:JSON.stringify({cmd:c})});}
  catch(e){}
  tip.textContent=c; tip.style.display='block'; setTimeout(()=>tip.style.display='none',500);
}
poll();
</script></body></html>"""


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class MobilePad:
    def __init__(self, on_cmd, port: int = 8765, token: str | None = None, log=print) -> None:
        self.on_cmd = on_cmd
        self.port = port
        self.token = token or f"{secrets.randbelow(900000) + 100000}"
        self.log = log
        self.lock = threading.Lock()
        self.items: list[dict] = []
        self.status = "等待桌面端开始"
        self.mode = "面试中"
        self.sig = ""
        self.srv = None

    # ---- 电脑 → 手机
    def update(self, question: str | None = None, answer: str | None = None,
               status: str | None = None, mode: str | None = None) -> None:
        with self.lock:
            if status is not None:
                self.status = status
            if mode is not None:
                self.mode = mode
            if question is not None:
                self.items.append({"q": question, "a": answer or ""})
            elif answer is not None and self.items:
                self.items[-1]["a"] = answer
            self.sig = f"{len(self.items)}:{len(self.items[-1]['a']) if self.items else 0}:{self.status}"

    def snapshot(self) -> dict:
        with self.lock:
            return {"items": [dict(x) for x in self.items[-12:]], "status": self.status,
                    "mode": self.mode, "sig": self.sig}

    # ---- 启停
    def start(self) -> str:
        pad = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # 静默，别刷屏
                pass

            def _ok(self, body: bytes, ctype="application/json; charset=utf-8"):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _auth(self, qs) -> bool:
                t = (qs.get("t") or [""])[0]
                return secrets.compare_digest(t, pad.token)

            def do_GET(self):
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if not self._auth(qs):
                    self.send_response(403)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if u.path == "/api/state":
                    self._ok(json.dumps(pad.snapshot(), ensure_ascii=False).encode())
                elif u.path in ("/", "/index.html"):
                    self._ok(PAGE.encode(), "text/html; charset=utf-8")
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

            def do_POST(self):
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if not self._auth(qs):
                    self.send_response(403)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    cmd = json.loads(raw.decode() or "{}").get("cmd", "")
                except Exception:
                    cmd = ""
                if u.path == "/api/cmd" and re.fullmatch(r"[a-z_]+", cmd or ""):
                    try:
                        pad.on_cmd(cmd)
                    except Exception as e:
                        pad.log(f"[mobile] 指令 {cmd} 失败 {type(e).__name__}: {e}")
                    self._ok(b'{"ok":true}')
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

        try:
            self.srv = ThreadingHTTPServer(("0.0.0.0", self.port), H)
        except OSError as e:
            self.log(f"[mobile] 端口 {self.port} 起不来（{e}），手机联动关闭")
            return ""
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        url = f"http://{lan_ip()}:{self.port}/?t={self.token}"
        self.log(f"[mobile] 手机打开：{url}")
        self._qr(url)
        return url

    def _qr(self, url: str) -> None:
        try:
            import qrcode  # type: ignore

            q = qrcode.QRCode(border=1)
            q.add_data(url)
            q.make()
            q.print_ascii(invert=True)
        except Exception:
            self.log("[mobile] （装 qrcode 可在终端直接出二维码）")

    def stop(self) -> None:
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()
            self.srv = None
