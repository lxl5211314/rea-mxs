"""动作捕捉：扶眼镜 / 双击眨眼 触发截图。

对齐 https://mianshixia.cn/docs/gesture-capture 的行为：
- 扶眼镜：食指尖停在鼻梁约 0.5s 触发；超过 5s 当托脸不触发；移开重新计时。
- 眨眼两次：两下间隔 <= 0.5s、整串 <= 1.5s、前 1 秒内无其他眨眼、只算双眼同时闭合。
- 触发后 3.5s 冷却；本机识别，画面不上传，不落盘。
- 正式使用无提示音无弹窗；进度通过回调给 UI 显示。

依赖：opencv-contrib-python + mediapipe(tasks) + 两个 .task 模型。
环境变量：
  GESTURE=1|0            总开关（默认 0）
  GESTURE_MODE=glasses|blink
  GESTURE_CAM=0          摄像头序号
  GESTURE_HOLD=0.5       扶眼镜保持秒数
  GESTURE_COOLDOWN=3.5
  GESTURE_MODELS=<dir>   默认 E:\\aaa_msx\\models
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

# mediapipe/TFLite 会往 stderr 打一堆 W0000，控制台会误以为出错了
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

# 必须在主线程导入：在 Qt 运行后由子线程首次 import cv2 会死锁（实测 import 卡住）；
# VideoCapture 本身放子线程没问题，但要用 CAP_DSHOW（MSMF 在本机 Qt 进程里会卡在 read）。
import cv2  # noqa: E402
import mediapipe as mp  # noqa: E402
from mediapipe.tasks import python as mp_py  # noqa: E402
from mediapipe.tasks.python import vision  # noqa: E402

MODELS = os.getenv("GESTURE_MODELS") or os.getenv("MSX_MODELS_DIR", r"E:\aaa_msx\models")

# mediapipe FaceMesh 索引
NOSE_BRIDGE = 168
# 左眼（图像左侧）
L_UP, L_LOW, L_OUT, L_IN = 159, 145, 33, 133
# 右眼
R_UP, R_LOW, R_OUT, R_IN = 386, 374, 263, 362


def _dist(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _ear(up, low, out, inn) -> float:
    w = _dist(out, inn)
    if w < 1e-6:
        return 1.0
    return _dist(up, low) / w


class GestureWatcher(threading.Thread):
    """后台线程：开摄像头 -> 逐帧推理 -> 命中就回调 on_trigger()。"""

    def __init__(
        self,
        on_trigger: Callable[[str], None],
        on_progress: Callable[[float, str], None] | None = None,
        log: Callable[[str], None] = print,
        mode: str | None = None,
        cam: int | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.on_trigger = on_trigger
        self.on_progress = on_progress or (lambda p, t: None)
        self.log = log
        self.mode = (mode or os.getenv("GESTURE_MODE", "glasses")).strip().lower()
        self.cam_index = int(os.getenv("GESTURE_CAM", "0")) if cam is None else cam
        self.hold = float(os.getenv("GESTURE_HOLD", "0.5"))
        self.cooldown = float(os.getenv("GESTURE_COOLDOWN", "3.5"))
        self._stop = threading.Event()
        self.error: str | None = None
        self.count = 0

    # ---- 生命周期
    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            self._run()
        except Exception as e:  # 摄像头被占用/模型缺失都不该炸掉主程序
            self.error = f"{type(e).__name__}: {e}"
            self.log(f"[gesture] 停止: {self.error}")

    # ---- 主循环
    def _run(self) -> None:
        t_imp = time.time()
        self.log("[gesture] 初始化…")
        if os.getenv("GESTURE_DEBUG"):
            import faulthandler

            faulthandler.dump_traceback_later(12, repeat=False)

        face_path = os.path.join(MODELS, "face_landmarker.task")
        hand_path = os.path.join(MODELS, "hand_landmarker.task")
        if not os.path.exists(face_path):
            raise FileNotFoundError(face_path)
        if self.mode == "glasses" and not os.path.exists(hand_path):
            raise FileNotFoundError(hand_path)

        base = mp_py.BaseOptions(model_asset_path=face_path)
        self.log("[gesture] 加载人脸模型…")
        face = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=base,
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )
        hand = None
        if self.mode == "glasses":
            self.log("[gesture] 加载手势模型…")
            hand = vision.HandLandmarker.create_from_options(
                vision.HandLandmarkerOptions(
                    base_options=mp_py.BaseOptions(model_asset_path=hand_path),
                    running_mode=vision.RunningMode.VIDEO,
                    num_hands=1,
                    min_hand_detection_confidence=0.5,
                    min_hand_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            )

        import ctypes

        # Qt 主线程已把进程的 COM 初始化过；子线程这里显式 MTA，
        # 否则 DirectShow 打开摄像头会在 read() 处无限阻塞。
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        except Exception:
            pass
        cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        self.log(f"[gesture] 摄像头 opened={cap.isOpened()}")
        if not cap.isOpened():
            raise RuntimeError(f"摄像头 {self.cam_index} 打不开（可能被会议软件占用）")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.log(f"[gesture] 已启动：{self.mode}｜摄像头 {self.cam_index}｜{MODELS}")

        t_start = time.time()
        last_ts = -1
        # 扶眼镜
        near_since: float | None = None
        last_prog = -1.0
        # 眨眼
        baseline = 0.30
        eyes_closed = False
        blink_times: list[float] = []
        last_blink = 0.0
        last_trigger = 0.0

        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                frame = cv2.flip(frame, 1)  # 镜像，符合用户直觉
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                now = time.time()
                ts = int((now - t_start) * 1000)
                if ts <= last_ts:
                    ts = last_ts + 1
                last_ts = ts

                fres = face.detect_for_video(mp_img, ts)
                lms = fres.face_landmarks[0] if fres.face_landmarks else None

                if lms and self.mode == "blink":
                    ear = (
                        _ear(lms[L_UP], lms[L_LOW], lms[L_OUT], lms[L_IN])
                        + _ear(lms[R_UP], lms[R_LOW], lms[R_OUT], lms[R_IN])
                    ) / 2
                    # 自适应基线：睁眼时缓慢学习
                    if not eyes_closed and ear > baseline * 0.8:
                        baseline = baseline * 0.98 + ear * 0.02
                    th = max(0.06, baseline * 0.55)
                    if not eyes_closed and ear < th:
                        eyes_closed = True
                        blink_times.append(now)
                        last_blink = now
                        # 只保留最近 2 次
                        blink_times = blink_times[-4:]
                        if len(blink_times) >= 2:
                            gap = blink_times[-1] - blink_times[-2]
                            span = blink_times[-1] - blink_times[0]
                            prev_gap = blink_times[-2] - blink_times[-3] if len(blink_times) >= 3 else 99
                            if (
                                0.05 <= gap <= 0.5
                                and span <= 1.5
                                and prev_gap >= 1.0
                                and now - last_trigger > self.cooldown
                            ):
                                last_trigger = now
                                blink_times.clear()
                                self._fire("blink")
                                self.on_progress(0.0, "")
                    elif eyes_closed and ear > th * 1.4:
                        eyes_closed = False

                elif lms and self.mode == "glasses":
                    hres = hand.detect_for_video(mp_img, ts)
                    tip = None
                    if hres.hand_landmarks:
                        tip = hres.hand_landmarks[0][8]  # 食指指尖
                    nose = lms[NOSE_BRIDGE]
                    if tip is not None and _dist(tip, nose) < 0.09:
                        if near_since is None:
                            near_since = now
                        held = now - near_since
                        prog = min(1.0, held / self.hold)
                        if prog - last_prog >= 0.2:
                            last_prog = prog
                            self.on_progress(prog, f"扶眼镜 {held:.1f}/{self.hold:.1f}s")
                        if held >= self.hold and now - last_trigger > self.cooldown:
                            last_trigger = now
                            near_since = None
                            last_prog = -1.0
                            self.on_progress(1.0, "")
                            self._fire("glasses")
                        elif held > 5.0:
                            # 托脸：不触发
                            near_since = None
                            last_prog = -1.0
                            self.on_progress(0.0, "")
                    else:
                        if near_since is not None:
                            near_since = None
                            last_prog = -1.0
                            self.on_progress(0.0, "")

                if not lms and self.mode == "glasses" and near_since is not None:
                    near_since = None
                    self.on_progress(0.0, "")
        finally:
            cap.release()
            try:
                face.close()
                if hand is not None:
                    hand.close()
            except Exception:
                pass
            self.log("[gesture] 已停止")

    def _fire(self, kind: str) -> None:
        self.count += 1
        self.log(f"[gesture] 触发 {kind}（第 {self.count} 次）")
        try:
            self.on_trigger(kind)
        except Exception as e:
            self.log(f"[gesture] 回调失败: {type(e).__name__}: {e}")
