import os
import sys
import threading
import traceback
from datetime import datetime

import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item

import main
from settings import load_settings, SettingsError


def _base_dir() -> str:
    # 兼容源码运行 / PyInstaller：让日志和 settings*.json 都在 exe 同目录
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


LOG_FILE = os.path.join(_base_dir(), "tray.log")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def popup_error(title: str, message: str):
    """Windows 弹窗提醒（不依赖 tkinter 主循环）"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)  # MB_ICONERROR
    except Exception:
        log(f"popup_error failed: {title} {message}")


def _interval_seconds() -> int:
    try:
        cfg = load_settings()
        hours = float(cfg.get("runtime", {}).get("interval_hours", 6))
        if hours <= 0:
            hours = 6
        return int(hours * 60 * 60)
    except SettingsError as e:
        # 配置不完整：先用 6 小时，且弹窗提示一次
        popup_error("配置错误", str(e))
        return 6 * 60 * 60
    except Exception:
        return 6 * 60 * 60


def run_once():
    """跑一次全流程：调用 main.run()"""
    try:
        log("Run start")
        main.run()
        log("Run success")
    except SettingsError as e:
        log("Run FAILED (SettingsError):\n" + str(e))
        popup_error("配置错误", str(e))
    except Exception as e:
        err = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        log("Run FAILED:\n" + err)
        popup_error("Live48 定时任务异常", err)


def worker_loop(stop_event: threading.Event):
    """后台循环：启动先跑一次，然后按 interval_hours 定时执行"""
    run_once()
    interval = _interval_seconds()

    while not stop_event.wait(interval):
        run_once()
        # 每轮结束后重新读取 interval，方便你修改 settings.json 后生效
        interval = _interval_seconds()


def create_image():
    """生成一个简单托盘图标（你也可以换成 .ico 文件）"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=(30, 144, 255, 255))
    d.text((20, 22), "48", fill=(255, 255, 255, 255))
    return img


def open_log():
    if os.path.exists(LOG_FILE):
        os.startfile(LOG_FILE)
    else:
        popup_error("提示", "暂无日志文件")


def on_run_now(icon, _):
    threading.Thread(target=run_once, daemon=True).start()


def on_exit(icon, _):
    icon.stop()


def main_tray():
    stop_event = threading.Event()

    t = threading.Thread(target=worker_loop, args=(stop_event,), daemon=True)
    t.start()

    menu = pystray.Menu(
        item("立即执行一次", lambda icon, _: on_run_now(icon, _)),
        item("打开日志", lambda icon, _: open_log()),
        item("退出", lambda icon, _: on_exit(icon, _)),
    )

    icon = pystray.Icon(
        "idol_show_auto_recorder",
        create_image(),
        "IdolShowAutoRecorder",
        menu
    )

    icon.run()
    stop_event.set()


if __name__ == "__main__":
    main_tray()
