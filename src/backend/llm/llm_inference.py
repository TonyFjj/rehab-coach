"""
LLM推理引擎
RK3588 上使用 RKLLM 加载 Qwen2.5 *.rkllm 模型；开发阶段提供模拟模式。
"""

import os
import time
import random
from typing import Optional

from llm.rkllm_backend import RKLLMBackend, default_rkllm_lib_path


def default_qwen_model_path(project_root: str) -> str:
    """默认 Qwen RKLLM 模型路径。"""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(project_root)), 'models', 'qwen2.5-1.5b-instruct.rkllm'),
        os.path.join(
            os.path.dirname(os.path.dirname(project_root)), 'models', 'qwen2.5-1.5b-instruct-w8a8_rk3588.rkllm'
        ),
    ]
    for path in candidates:
        resolved = os.path.abspath(path)
        if os.path.isfile(resolved):
            return resolved
    return os.path.abspath(candidates[0])


class LLMInference:
    """
    端侧 LLM 推理引擎

    支持：
    1. RKLLM 真实模式 — Qwen *.rkllm（RK3588 NPU）
    2. 模拟模式 — 预设回复，用于无模型时的开发调试
    """

    def __init__(
        self,
        model_path: str = None,
        simulate: bool = True,
        n_ctx: int = 2048,
        n_threads: int = 4,
        temperature: float = 0.7,
        max_tokens: int = 256,
        platform: str = 'rk3588',
        project_root: str = None,
    ):
        self.model_path = model_path
        self.simulate = simulate
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.platform = platform
        self.backend: Optional[RKLLMBackend] = None
        self._current_system_prompt = ''

        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            ))

        if not simulate:
            if not model_path:
                model_path = default_qwen_model_path(project_root)
            self.model_path = model_path
            self._load_rkllm(model_path, n_ctx, max_tokens, temperature)

    def _load_rkllm(
        self,
        model_path: str,
        n_ctx: int,
        max_tokens: int,
        temperature: float,
    ):
        try:
            project_root = os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            ))
            lib_path = default_rkllm_lib_path(project_root)
            print(f"[LLM] 正在加载 RKLLM 模型: {model_path}")
            start = time.time()
            self.backend = RKLLMBackend(
                model_path=model_path,
                lib_path=lib_path,
                platform=self.platform,
                max_context_len=n_ctx,
                max_new_tokens=max_tokens,
                temperature=temperature,
            )
            elapsed = time.time() - start
            print(f"[LLM] RKLLM 加载完成，耗时 {elapsed:.1f}s")
            self.simulate = False
        except Exception as e:
            print(f"[LLM] RKLLM 加载失败: {e}，切换到模拟模式")
            self.backend = None
            self.simulate = True

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        if self.simulate or self.backend is None:
            return self._simulate_generate(system_prompt, user_prompt)

        if system_prompt and system_prompt != self._current_system_prompt:
            self.backend.set_system_prompt(system_prompt)
            self._current_system_prompt = system_prompt

        try:
            start = time.time()
            text = self.backend.generate(user_prompt)
            elapsed = time.time() - start
            print(
                f"[LLM] 推理耗时: {elapsed:.2f}s, 输出: {len(text)} 字符"
            )
            return text or self._simulate_generate(system_prompt, user_prompt)
        except Exception as e:
            print(f"[LLM] 推理出错: {e}")
            return self._simulate_generate(system_prompt, user_prompt)

    def _simulate_generate(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        time.sleep(0.3)
        prompt_lower = user_prompt.lower()

        if '评估' in prompt_lower or '评分' in prompt_lower:
            responses = [
                "您的测试完成了！整体表现还不错。我们先从简单的动作开始练习，"
                "每天坚持，一定会越来越好的！",
                "测试结果出来了。有些方面做得很好，也有需要加强的地方。"
                "别担心，我会一步步带着您练的。",
                "您辛苦了！根据刚才的测试，我为您安排了适合的训练方案。"
                "咱们慢慢来，不着急。",
            ]
            return random.choice(responses)

        if '纠正' in prompt_lower or '问题' in prompt_lower or \
           '偏差' in prompt_lower:
            responses = [
                "动作很好，再稍微高一点就更完美了！",
                "注意一下姿势，慢慢来，不要着急。",
                "做得不错，控制住速度，匀速完成。",
                "稍微调整一下，放松肩膀，再试一次。",
            ]
            return random.choice(responses)

        if '鼓励' in prompt_lower or '做得好' in prompt_lower:
            responses = [
                "太棒了，继续保持！",
                "做得非常好，加油！",
                "很标准，就是这样！",
                "越做越好了，坚持住！",
                "漂亮！这个动作很到位！",
            ]
            return random.choice(responses)

        if '总结' in prompt_lower or '完成' in prompt_lower:
            responses = [
                "今天的训练完成了，您做得很好！明天继续加油，"
                "每天进步一点点。",
                "辛苦您了！今天的表现比上次有进步，继续坚持哦。",
                "今天的练习到这里，好好休息。期待明天见到更好的您！",
            ]
            return random.choice(responses)

        return "做得很好，继续保持这个节奏！"

    def is_ready(self) -> bool:
        if self.simulate:
            return True
        return self.backend is not None

    def release(self):
        if self.backend is not None:
            self.backend.release()
            self.backend = None

    def __del__(self):
        self.release()
