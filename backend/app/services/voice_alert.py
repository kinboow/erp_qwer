"""
服务器端语音告警：通过 Windows SAPI 播放 TTS 语音
在后台线程中执行，不阻塞 asyncio 事件循环
"""

import asyncio
import logging
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

_alert_lock = threading.Lock()


def _speak_sync(text: str, repeat: int = 3) -> None:
    """在当前线程同步播放 TTS 语音（仅 Windows）"""
    if sys.platform != "win32":
        logger.warning("[VoiceAlert] 语音告警仅支持 Windows，当前平台: %s", sys.platform)
        return

    with _alert_lock:
        for i in range(repeat):
            try:
                # 使用 PowerShell 调用 Windows SAPI 语音合成
                ps_script = (
                    f'Add-Type -AssemblyName System.Speech; '
                    f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                    f'$s.Rate = 2; '
                    f'$s.Speak("{text}"); '
                    f'$s.Dispose()'
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    timeout=15,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
            except Exception as exc:
                logger.warning("[VoiceAlert] 第 %d 次播放失败: %s", i + 1, exc)
                break


def speak_alert(text: str, repeat: int = 3) -> None:
    """在后台线程中播放语音告警，不阻塞调用方"""
    thread = threading.Thread(target=_speak_sync, args=(text, repeat), daemon=True)
    thread.start()


async def speak_alert_async(text: str, repeat: int = 3) -> None:
    """asyncio 友好的语音告警，在线程池中执行"""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _speak_sync, text, repeat)
