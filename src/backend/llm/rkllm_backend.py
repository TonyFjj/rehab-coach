"""
RKLLM 推理后端（RK3588 NPU）
通过 ctypes 调用 librkllmrt.so，加载 Qwen *.rkllm 模型。
"""

import ctypes
import os
import threading
from typing import Optional


# ctypes 结构体与枚举（与 rkllm.h / flask_server 对齐）
LLMCallState = ctypes.c_int
LLMCallState.RKLLM_RUN_NORMAL = 0
LLMCallState.RKLLM_RUN_WAITING = 1
LLMCallState.RKLLM_RUN_FINISH = 2
LLMCallState.RKLLM_RUN_ERROR = 3

RKLLMInputType = ctypes.c_int
RKLLMInputType.RKLLM_INPUT_PROMPT = 0

RKLLMInferMode = ctypes.c_int
RKLLMInferMode.RKLLM_INFER_GENERATE = 0


class RKLLMExtendParam(ctypes.Structure):
    _fields_ = [
        ("base_domain_id", ctypes.c_int32),
        ("embed_flash", ctypes.c_int8),
        ("enabled_cpus_num", ctypes.c_int8),
        ("enabled_cpus_mask", ctypes.c_uint32),
        ("n_batch", ctypes.c_uint8),
        ("use_cross_attn", ctypes.c_int8),
        ("reserved", ctypes.c_uint8 * 104),
    ]


class RKLLMParam(ctypes.Structure):
    _fields_ = [
        ("model_path", ctypes.c_char_p),
        ("max_context_len", ctypes.c_int32),
        ("max_new_tokens", ctypes.c_int32),
        ("top_k", ctypes.c_int32),
        ("n_keep", ctypes.c_int32),
        ("top_p", ctypes.c_float),
        ("temperature", ctypes.c_float),
        ("repeat_penalty", ctypes.c_float),
        ("frequency_penalty", ctypes.c_float),
        ("presence_penalty", ctypes.c_float),
        ("mirostat", ctypes.c_int32),
        ("mirostat_tau", ctypes.c_float),
        ("mirostat_eta", ctypes.c_float),
        ("skip_special_token", ctypes.c_bool),
        ("is_async", ctypes.c_bool),
        ("img_start", ctypes.c_char_p),
        ("img_end", ctypes.c_char_p),
        ("img_content", ctypes.c_char_p),
        ("extend_param", RKLLMExtendParam),
    ]


class RKLLMInputUnion(ctypes.Union):
    _fields_ = [("prompt_input", ctypes.c_char_p)]


class RKLLMInput(ctypes.Structure):
    _fields_ = [
        ("role", ctypes.c_char_p),
        ("enable_thinking", ctypes.c_bool),
        ("input_type", RKLLMInputType),
        ("input_data", RKLLMInputUnion),
    ]


class RKLLMInferParam(ctypes.Structure):
    _fields_ = [
        ("mode", RKLLMInferMode),
        ("lora_params", ctypes.c_void_p),
        ("prompt_cache_params", ctypes.c_void_p),
        ("keep_history", ctypes.c_int),
    ]


class RKLLMResultLastHiddenLayer(ctypes.Structure):
    _fields_ = [
        ("hidden_states", ctypes.POINTER(ctypes.c_float)),
        ("embd_size", ctypes.c_int),
        ("num_tokens", ctypes.c_int),
    ]


class RKLLMResultLogits(ctypes.Structure):
    _fields_ = [
        ("logits", ctypes.POINTER(ctypes.c_float)),
        ("vocab_size", ctypes.c_int),
        ("num_tokens", ctypes.c_int),
    ]


class RKLLMPerfStat(ctypes.Structure):
    _fields_ = [
        ("prefill_time_ms", ctypes.c_float),
        ("prefill_tokens", ctypes.c_int),
        ("generate_time_ms", ctypes.c_float),
        ("generate_tokens", ctypes.c_int),
        ("memory_usage_mb", ctypes.c_float),
    ]


class RKLLMResult(ctypes.Structure):
    _fields_ = [
        ("text", ctypes.c_char_p),
        ("token_id", ctypes.c_int32),
        ("last_hidden_layer", RKLLMResultLastHiddenLayer),
        ("logits", RKLLMResultLogits),
        ("perf", RKLLMPerfStat),
    ]


def default_rkllm_lib_path(project_root: str) -> str:
    """优先项目 third_party/，其次 rkllm_demo 部署目录。"""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(project_root)), 'third_party', 'librkllmrt.so'),
        os.path.join(
            os.path.dirname(os.path.dirname(project_root)),
            'rkllm_demo', 'deploy', 'lib', 'librkllmrt.so'
        ),
        '/home/elf/Desktop/rkllm_demo/deploy/lib/librkllmrt.so',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[0]


class RKLLMBackend:
    """线程安全的 RKLLM 单次推理封装。"""

    def __init__(
        self,
        model_path: str,
        lib_path: str = None,
        platform: str = 'rk3588',
        max_context_len: int = 2048,
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ):
        self.model_path = model_path
        self._lock = threading.Lock()
        self._output_chunks = []
        self._state = -1

        lib_path = lib_path or default_rkllm_lib_path(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if not os.path.isfile(lib_path):
            raise FileNotFoundError(f"未找到 librkllmrt.so: {lib_path}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"未找到 RKLLM 模型: {model_path}")

        self._lib = ctypes.CDLL(lib_path)
        self._handle = ctypes.c_void_p()

        callback_type = ctypes.CFUNCTYPE(
            ctypes.c_int,
            ctypes.POINTER(RKLLMResult),
            ctypes.c_void_p,
            ctypes.c_int,
        )
        self._callback = callback_type(self._callback_impl)

        param = RKLLMParam()
        param.model_path = model_path.encode('utf-8')
        param.max_context_len = max_context_len
        param.max_new_tokens = max_new_tokens
        param.skip_special_token = True
        param.n_keep = -1
        param.top_k = 1
        param.top_p = top_p
        param.temperature = temperature
        param.repeat_penalty = 1.1
        param.frequency_penalty = 0.0
        param.presence_penalty = 0.0
        param.mirostat = 0
        param.is_async = False
        param.img_start = b""
        param.img_end = b""
        param.img_content = b""
        param.extend_param.base_domain_id = 0
        param.extend_param.embed_flash = 1
        param.extend_param.n_batch = 1
        param.extend_param.use_cross_attn = 0
        param.extend_param.enabled_cpus_num = 4
        if platform.lower() in ('rk3576', 'rk3588'):
            param.extend_param.enabled_cpus_mask = (
                (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7)
            )
        else:
            param.extend_param.enabled_cpus_mask = (
                (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3)
            )

        init_fn = self._lib.rkllm_init
        init_fn.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(RKLLMParam),
            callback_type,
        ]
        init_fn.restype = ctypes.c_int
        ret = init_fn(
            ctypes.byref(self._handle),
            ctypes.byref(param),
            self._callback,
        )
        if ret != 0:
            raise RuntimeError(f"rkllm_init 失败，返回码 {ret}")

        self._run = self._lib.rkllm_run
        self._run.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(RKLLMInput),
            ctypes.POINTER(RKLLMInferParam),
            ctypes.c_void_p,
        ]
        self._run.restype = ctypes.c_int

        self._set_chat_template = self._lib.rkllm_set_chat_template
        self._set_chat_template.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        self._set_chat_template.restype = ctypes.c_int

        self._destroy = self._lib.rkllm_destroy
        self._destroy.argtypes = [ctypes.c_void_p]
        self._destroy.restype = ctypes.c_int

        self._infer_params = RKLLMInferParam()
        ctypes.memset(ctypes.byref(self._infer_params), 0, ctypes.sizeof(
            RKLLMInferParam
        ))
        self._infer_params.mode = RKLLMInferMode.RKLLM_INFER_GENERATE
        self._infer_params.keep_history = 0

        self._system_prompt = ''
        print(f"[LLM] RKLLM 模型已加载: {model_path}")

    def _callback_impl(self, result, userdata, state):
        self._state = state
        if state == LLMCallState.RKLLM_RUN_NORMAL:
            if result.contents.text:
                self._output_chunks.append(
                    result.contents.text.decode('utf-8', errors='replace')
                )
        return 0

    def set_system_prompt(self, system_prompt: str):
        """设置 Qwen chat 模板中的 system 段。"""
        im_end = "<|" + "im_end" + "|>"
        self._system_prompt = system_prompt or ''
        sys_tmpl = (
            f"<|im_start|>system\n{self._system_prompt}{im_end}"
        )
        prefix = "<|im_start|>user\n"
        postfix = f"\n{im_end}\n<|im_start|>assistant\n"
        self._set_chat_template(
            self._handle,
            sys_tmpl.encode('utf-8'),
            prefix.encode('utf-8'),
            postfix.encode('utf-8'),
        )

    def generate(self, user_prompt: str) -> str:
        with self._lock:
            self._output_chunks = []
            self._state = -1

            rkllm_input = RKLLMInput()
            rkllm_input.role = b"user"
            rkllm_input.enable_thinking = False
            rkllm_input.input_type = RKLLMInputType.RKLLM_INPUT_PROMPT
            rkllm_input.input_data.prompt_input = user_prompt.encode('utf-8')

            ret = self._run(
                self._handle,
                ctypes.byref(rkllm_input),
                ctypes.byref(self._infer_params),
                None,
            )
            if ret != 0:
                raise RuntimeError(f"rkllm_run 失败，返回码 {ret}")
            if self._state == LLMCallState.RKLLM_RUN_ERROR:
                raise RuntimeError("RKLLM 推理出错")

            return ''.join(self._output_chunks).strip()

    def release(self):
        if self._handle.value:
            self._destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass
