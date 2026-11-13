r"""把默认输出设备（耳机）音量调到指定值，并解除静音。

pycaw 的 AudioUtilities.GetAllDevices() 在本机会崩，但 GetSpeakers() 可用。

  python setvol.py          # 设为 0.75
  python setvol.py 0.5
  python setvol.py --show
"""
from __future__ import annotations

import ctypes
import sys

from comtypes import CLSCTX_ALL
from pycaw.pycaw import IAudioEndpointVolume
from pycaw.utils import AudioUtilities


def main() -> int:
    show = "--show" in sys.argv
    target = 0.75
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            target = float(a)

    sp = AudioUtilities.GetSpeakers()
    iface = sp._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    vol = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))
    print(f"device: {sp.FriendlyName}")
    print(f"before: mute={vol.GetMute()} volume={vol.GetMasterVolumeLevelScalar():.3f}")
    if not show:
        vol.SetMute(0, None)
        vol.SetMasterVolumeLevelScalar(target, None)
        print(f"after : mute={vol.GetMute()} volume={vol.GetMasterVolumeLevelScalar():.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
