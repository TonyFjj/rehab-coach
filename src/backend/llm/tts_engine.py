"""
TTS语音合成引擎
将文本转为语音播报，支持离线模式

支持后端：
1. sherpa-onnx — RK3588 部署用（VITS 模型，中文自然）
2. pyttsx3 — 开发调试用（效果一般，但简单）
3. PaddleSpeech — 备选部署用
4. simulate — 纯打印模式（无需任何TTS库）
"""

import threading
import queue
import time
import os
import re
import hashlib
import subprocess
from typing import List, Optional

import numpy as np

from .tts_text import (
    JOINT_NAMES_ZH,
    sanitize_for_tts,
    collect_standard_phrases,
    collect_training_phrases,
)


def detect_usb_alsa_device() -> Optional[str]:
    """扫描 aplay -l，返回第一个 USB 声卡的 plughw 设备名。"""
    try:
        out = subprocess.check_output(
            ['aplay', '-l'],
            text=True,
            stderr=subprocess.STDOUT,
        )
        for line in out.splitlines():
            lower = line.lower()
            if 'card' in lower and 'usb' in lower:
                m = re.search(r'card\s+(\d+):', line, re.I)
                if m:
                    return f'plughw:{m.group(1)},0'
    except (OSError, subprocess.CalledProcessError):
        pass
    return None


def detect_alsa_device(config_device: Optional[str] = None) -> Optional[str]:
    """
    选择播放设备。
    config_device: 来自配置文件（None 表示 default/未指定）。
    环境变量 REHAB_ALSA_DEVICE 仍可覆盖配置文件。
    """
    env = os.environ.get('REHAB_ALSA_DEVICE', '').strip()
    if env:
        return env

    if config_device:
        return config_device

    return detect_usb_alsa_device()


class TTSEngine:
    """
    离线TTS引擎

    特性：
    - 异步播报：不阻塞主线程
    - 优先级队列：安全警报优先播报
    - Sherpa-ONNX VITS 为 RK3588 首选后端
    - 模拟模式：不安装任何TTS库也能跑通流程
    """

    PRIORITY_CRITICAL = 0
    PRIORITY_HIGH = 1
    PRIORITY_NORMAL = 2
    PRIORITY_LOW = 3

    # 同类播报最短间隔（秒）；block=True 的引导语不受限
    MIN_INTERVAL = {
        PRIORITY_CRITICAL: 8.0,
        PRIORITY_HIGH: 10.0,
        PRIORITY_NORMAL: 10.0,
        PRIORITY_LOW: 15.0,
    }

    def __init__(
        self,
        backend: str = 'auto',
        rate: int = 160,
        volume: float = 0.9,
        output_dir: str = './tts_cache',
        simulate: bool = False,
        model_dir: str = None,
        alsa_device: str = None,
    ):
        self.rate = rate
        self.volume = volume
        self.output_dir = output_dir
        self.simulate = simulate

        self._queue = queue.PriorityQueue()
        self._counter = 0
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._is_speaking = False
        self._synth_lock = threading.Lock()
        self._alsa_device = detect_alsa_device(alsa_device)
        self._prebuilt_dir = os.path.join(output_dir, 'prebuilt')
        self._cache_index: dict[str, str] = {}
        self._precache_lock = threading.Lock()
        self._last_spoken_at = 0.0
        self._throttle_log_at = 0.0
        self._playback_lock = threading.Lock()

        self._pyttsx3_engine = None
        self._paddle_tts = None
        self._sherpa_tts = None
        if model_dir:
            self._sherpa_model_dir = model_dir
        else:
            self._sherpa_model_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'tts_models', 'vits-melo-tts-zh_en',
            )
        self.backend = 'simulate' if simulate else backend

        if not simulate:
            self.backend = self._resolve_backend(backend)

        if self.backend == 'pyttsx3':
            self._init_pyttsx3()
        elif self.backend == 'sherpa-onnx':
            self._init_sherpa_onnx()
        elif self.backend == 'paddlespeech':
            self._init_paddlespeech()

        os.makedirs(self._prebuilt_dir, exist_ok=True)
        self._load_cache_index()
        self.precache_many(collect_standard_phrases(), background=True)

        print(f"[TTS] 后端: {self.backend}")
        if self._alsa_device:
            print(f"[TTS] 音频输出: {self._alsa_device}")
        else:
            print("[TTS] 音频输出: 系统默认 (可在 config/camera_config*.yaml 的 audio.device 配置)")

    def _resolve_backend(self, requested: str) -> str:
        if requested == 'sherpa-onnx':
            if self._check_sherpa_onnx():
                return 'sherpa-onnx'
            print("[TTS] Sherpa-ONNX不可用，回退到pyttsx3")

        if requested == 'paddlespeech':
            if self._check_paddlespeech():
                return 'paddlespeech'
            print("[TTS] PaddleSpeech不可用，回退到pyttsx3")

        if requested in ('pyttsx3', 'auto'):
            if requested == 'auto' and self._check_sherpa_onnx():
                return 'sherpa-onnx'
            if self._check_pyttsx3():
                return 'pyttsx3'

        if requested == 'auto' and self._check_paddlespeech():
            return 'paddlespeech'

        print("[TTS] 无可用TTS后端，使用模拟模式")
        return 'simulate'

    def _check_pyttsx3(self) -> bool:
        try:
            import pyttsx3
            return True
        except ImportError:
            return False

    def _check_sherpa_onnx(self) -> bool:
        try:
            import sherpa_onnx
            return os.path.exists(os.path.join(
                self._sherpa_model_dir, 'model.onnx'))
        except ImportError:
            return False

    def _check_paddlespeech(self) -> bool:
        try:
            from paddlespeech.cli.tts import TTSExecutor
            return True
        except ImportError:
            return False

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_engine.setProperty('rate', self.rate)
            self._pyttsx3_engine.setProperty('volume', self.volume)
            print("[TTS] pyttsx3 初始化成功")
        except Exception as e:
            print(f"[TTS] pyttsx3 初始化失败: {e}")
            self.backend = 'simulate'

    def _init_sherpa_onnx(self):
        try:
            import sherpa_onnx

            model_dir = self._sherpa_model_dir
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=os.path.join(model_dir, 'model.onnx'),
                        lexicon=os.path.join(model_dir, 'lexicon.txt'),
                        tokens=os.path.join(model_dir, 'tokens.txt'),
                        dict_dir=os.path.join(model_dir, 'dict'),
                    ),
                    num_threads=2,
                ),
            )
            self._sherpa_tts = sherpa_onnx.OfflineTts(tts_config)
            os.makedirs(self.output_dir, exist_ok=True)
            print(
                f"[TTS] Sherpa-ONNX VITS 初始化成功 "
                f"({model_dir})"
            )
        except Exception as e:
            print(f"[TTS] Sherpa-ONNX 初始化失败: {e}")
            self.backend = 'simulate'

    def _init_paddlespeech(self):
        try:
            from paddlespeech.cli.tts import TTSExecutor
            self._paddle_tts = TTSExecutor()
            os.makedirs(self.output_dir, exist_ok=True)
            print("[TTS] PaddleSpeech 初始化成功")
        except Exception as e:
            print(f"[TTS] PaddleSpeech 初始化失败: {e}")
            self.backend = 'simulate'

    def _cache_key(self, text: str) -> str:
        normalized = sanitize_for_tts(text)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:16]

    def _cache_path(self, text: str) -> str:
        return os.path.join(self._prebuilt_dir, f'{self._cache_key(text)}.wav')

    def _load_cache_index(self):
        if not os.path.isdir(self._prebuilt_dir):
            return
        for name in os.listdir(self._prebuilt_dir):
            if name.endswith('.wav'):
                self._cache_index[name[:-4]] = os.path.join(
                    self._prebuilt_dir, name
                )

    def has_cached(self, text: str) -> bool:
        key = self._cache_key(text)
        path = self._cache_index.get(key) or self._cache_path(text)
        return os.path.isfile(path)

    def precache(self, text: str) -> bool:
        """预合成单句并写入缓存，成功返回 True。"""
        if not text or not text.strip():
            return False
        normalized = sanitize_for_tts(text)
        if not normalized:
            return False

        key = self._cache_key(text)
        path = self._cache_path(text)
        if os.path.isfile(path):
            with self._precache_lock:
                self._cache_index[key] = path
            return True

        with self._precache_lock:
            if os.path.isfile(path):
                self._cache_index[key] = path
                return True
            ok = self._synthesize_to_file(normalized, path)
            if ok:
                self._cache_index[key] = path
            return ok

    def precache_many(
        self,
        texts: List[str],
        background: bool = False,
    ):
        unique = []
        seen = set()
        for text in texts:
            if not text or not text.strip():
                continue
            key = self._cache_key(text)
            if key in seen:
                continue
            seen.add(key)
            if self.has_cached(text):
                continue
            unique.append(text)

        if not unique:
            return

        def _worker():
            for text in unique:
                self.precache(text)

        if background:
            threading.Thread(
                target=_worker,
                daemon=True,
                name='TTS-Precache',
            ).start()
        else:
            _worker()

    def precache_training_session(
        self,
        level_name: str,
        actions: List[dict],
        background: bool = False,
    ):
        phrases = collect_training_phrases(level_name, actions)
        self.precache_many(phrases, background=background)

    def precache_assessment(self, background: bool = False):
        """预生成评估短播报语音。"""
        try:
            from assessment_plan import assessment_tts_phrases
            self.precache_many(assessment_tts_phrases(), background=background)
        except ImportError:
            pass

    def ensure_assessment_cached(self) -> int:
        """同步补齐缺失的评估语音缓存，返回新合成条数。"""
        try:
            from assessment_plan import assessment_tts_phrases
        except ImportError:
            return 0
        missing = [
            p for p in assessment_tts_phrases()
            if p and not self.has_cached(p)
        ]
        if missing:
            print(f'[TTS] 预生成评估语音 {len(missing)} 条…')
            self.precache_many(missing, background=False)
        return len(missing)

    def _should_throttle(self, priority: int, block: bool) -> bool:
        if block:
            return False
        now = time.time()
        gap = self.MIN_INTERVAL.get(priority, 15.0)
        if now - self._last_spoken_at < gap:
            if now - self._throttle_log_at > 30.0:
                print(
                    f"[TTS] 播报节流中（距上次 "
                    f"{now - self._last_spoken_at:.0f}s，"
                    f"需间隔 {gap:.0f}s）"
                )
                self._throttle_log_at = now
            return True
        if (
            priority > self.PRIORITY_CRITICAL
            and (self._is_speaking or self._queue.qsize() > 0)
        ):
            return True
        return False

    def speak(
        self,
        text: str,
        priority: int = PRIORITY_NORMAL,
        block: bool = False,
        use_cache: bool = True,
    ):
        if not text or not text.strip():
            return

        if block:
            self.speak_and_wait(text, use_cache=use_cache)
            return

        if self._should_throttle(priority, block):
            return

        self._counter += 1
        self._queue.put((priority, self._counter, text, use_cache))
        if not self._running:
            self.start_worker()

    def speak_and_wait(self, text: str, use_cache: bool = True):
        if not text or not text.strip():
            return
        self._counter += 1
        self._queue.put((self.PRIORITY_HIGH, self._counter, text, use_cache))
        if not self._running:
            self.start_worker()
        self.wait_until_idle(timeout=180.0)

    def wait_until_idle(self, timeout: float = 180.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._queue.empty() and not self._is_speaking:
                return True
            time.sleep(0.05)
        return False

    def speak_correction(self, text: str):
        self.speak(text, priority=self.PRIORITY_HIGH)

    def speak_encouragement(self, text: str):
        self.speak(text, priority=self.PRIORITY_NORMAL)

    def speak_alert(self, text: str):
        self._clear_queue()
        self.speak(text, priority=self.PRIORITY_CRITICAL)

    def speak_info(self, text: str):
        self.speak(text, priority=self.PRIORITY_LOW)

    def set_volume(self, volume: float):
        """设置播报音量 0.0–1.0"""
        self.volume = max(0.0, min(1.0, float(volume)))

    def set_rate(self, rate: int):
        """设置语速（字/分钟基准，默认 160）"""
        self.rate = max(80, min(320, int(rate)))
        if self._pyttsx3_engine:
            try:
                self._pyttsx3_engine.setProperty('rate', self.rate)
            except Exception:
                pass

    def get_volume(self) -> float:
        return self.volume

    def get_rate(self) -> int:
        return self.rate

    def start_worker(self):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="TTS-Worker",
        )
        self._worker_thread.start()

    def stop_worker(self):
        self._running = False
        self._queue.put((-1, -1, None, True))
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=15)

    def _worker_loop(self):
        while self._running:
            try:
                priority, counter, text, use_cache = self._queue.get(timeout=1.0)
                if text is None:
                    break
                self._do_speak(text, use_cache=use_cache)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[TTS] 工作线程异常: {e}")

    def _synthesize_to_file(self, text: str, output_path: str) -> bool:
        if self.backend == 'simulate':
            return False
        try:
            if self.backend == 'sherpa-onnx' and self._sherpa_tts is not None:
                with self._synth_lock:
                    speed = max(0.5, min(2.0, self.rate / 160.0))
                    audio = self._sherpa_tts.generate(text, sid=0, speed=speed)
                    if len(audio.samples) == 0:
                        return False
                    import soundfile as sf
                    sf.write(
                        output_path,
                        np.array(audio.samples),
                        audio.sample_rate,
                    )
                return True
            if self.backend == 'paddlespeech' and self._paddle_tts is not None:
                self._paddle_tts(
                    text=text,
                    output=output_path,
                    am='fastspeech2_mix',
                    voc='hifigan_csmsc',
                    lang='mix',
                    spk_id=0,
                )
                return os.path.isfile(output_path)
            if self.backend == 'pyttsx3' and self._pyttsx3_engine:
                self._pyttsx3_engine.save_to_file(text, output_path)
                self._pyttsx3_engine.runAndWait()
                return os.path.isfile(output_path)
        except Exception as e:
            print(f"[TTS] 预合成失败: {e}")
        return False

    def _do_speak(self, text: str, use_cache: bool = True):
        text = sanitize_for_tts(text)
        if not text:
            return
        self._is_speaking = True
        print(f"[TTS] 播报: {text}")
        try:
            cache_path = self._cache_path(text)
            indexed = self._cache_index.get(self._cache_key(text))
            wav_path = indexed if indexed and os.path.isfile(indexed) else None
            if not wav_path and use_cache and os.path.isfile(cache_path):
                wav_path = cache_path

            if wav_path:
                self._play_audio(wav_path)
                return

            if self.backend == 'pyttsx3':
                self._speak_pyttsx3(text)
            elif self.backend == 'sherpa-onnx':
                self._speak_sherpa_onnx(text, save_cache=use_cache)
            elif self.backend == 'paddlespeech':
                self._speak_paddlespeech(text, save_cache=use_cache)
            else:
                self._speak_simulate(text)
        except Exception as e:
            print(f"[TTS] 播报异常: {e}")
        finally:
            self._is_speaking = False
            self._last_spoken_at = time.time()

    def _speak_pyttsx3(self, text: str):
        if self._pyttsx3_engine:
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()

    def _speak_sherpa_onnx(self, text: str, save_cache: bool = True):
        if self._sherpa_tts is None:
            self._speak_simulate(text)
            return
        cache_path = self._cache_path(text)
        with self._synth_lock:
            try:
                speed = max(0.5, min(2.0, self.rate / 160.0))
                audio = self._sherpa_tts.generate(text, sid=0, speed=speed)
                if len(audio.samples) == 0:
                    print("[TTS] Sherpa 合成结果为空")
                    self._speak_simulate(text)
                    return

                output_path = cache_path if save_cache else os.path.join(
                    self.output_dir, f"tts_{int(time.time() * 1000)}.wav"
                )
                import soundfile as sf
                sf.write(
                    output_path,
                    np.array(audio.samples),
                    audio.sample_rate,
                )
                if save_cache:
                    self._cache_index[self._cache_key(text)] = output_path
                self._play_audio(output_path)
                if not save_cache:
                    self._cleanup_cache()
            except Exception as e:
                print(f"[TTS] Sherpa-ONNX 合成失败: {e}")
                self._speak_simulate(text)

    def _speak_paddlespeech(self, text: str, save_cache: bool = True):
        if self._paddle_tts is None:
            self._speak_simulate(text)
            return
        try:
            output_path = self._cache_path(text) if save_cache else os.path.join(
                self.output_dir, f"tts_{int(time.time() * 1000)}.wav"
            )
            self._paddle_tts(
                text=text,
                output=output_path,
                am='fastspeech2_mix',
                voc='hifigan_csmsc',
                lang='mix',
                spk_id=0,
            )
            if save_cache:
                self._cache_index[self._cache_key(text)] = output_path
            self._play_audio(output_path)
            if not save_cache:
                self._cleanup_cache()
        except Exception as e:
            print(f"[TTS] PaddleSpeech 合成失败: {e}")
            self._speak_simulate(text)

    def _speak_simulate(self, text: str):
        char_count = len(text)
        estimated_time = min(char_count / 5.0, 5.0)
        time.sleep(estimated_time)

    def _play_audio(self, filepath: str):
        import platform
        import tempfile
        system = platform.system()
        play_path = filepath
        temp_path = None
        with self._playback_lock:
            try:
                if self.volume < 0.995:
                    try:
                        import soundfile as sf
                        data, sr = sf.read(filepath)
                        scaled = np.clip(data * self.volume, -1.0, 1.0)
                        fd, temp_path = tempfile.mkstemp(suffix='.wav')
                        os.close(fd)
                        sf.write(temp_path, scaled, sr)
                        play_path = temp_path
                    except Exception as e:
                        print(f"[TTS] 音量缩放失败，使用原音量: {e}")
                if system == 'Linux':
                    cmd = ['aplay', '-q']
                    if self._alsa_device:
                        cmd.extend(['-D', self._alsa_device])
                    cmd.append(play_path)
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if result.returncode != 0:
                        print(
                            f"[TTS] aplay 失败 (code={result.returncode}): "
                            f"{result.stderr.strip() or result.stdout.strip()}"
                        )
                elif system == 'Darwin':
                    subprocess.run(['afplay', play_path], check=True, timeout=120)
                elif system == 'Windows':
                    import winsound
                    winsound.PlaySound(play_path, winsound.SND_FILENAME)
            except subprocess.TimeoutExpired:
                print(f"[TTS] 音频播放超时: {play_path}")
            except Exception as e:
                print(f"[TTS] 音频播放失败: {e}")
            finally:
                if temp_path and os.path.isfile(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

    def _clear_queue(self):
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def _cleanup_cache(self, keep: int = 30):
        if not os.path.exists(self.output_dir):
            return
        files = sorted([
            os.path.join(self.output_dir, f)
            for f in os.listdir(self.output_dir)
            if f.endswith('.wav') and not f.startswith('prebuilt')
        ])
        while len(files) > keep:
            try:
                os.remove(files.pop(0))
            except OSError:
                pass

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def __del__(self):
        self.stop_worker()
