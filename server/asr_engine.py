import os
import tempfile
from typing import Optional

from common.logger import setup_logger
from common.model_catalog import QWEN_LANGUAGES, validate_model, model_installed

logger = setup_logger("asr_engine")


def _create_sherpa_recognizer(factory, **kwargs):
    """sherpa 1.13 opens tokens with a narrow Windows path; ONNX uses wide paths."""
    tokens = kwargs["tokens"]
    if os.name != "nt" or tokens.isascii():
        return factory(**kwargs)
    # An ASCII relative filename works even when the working directory is Chinese.
    # Only the small vocabulary is copied, and it is read during construction.
    temporary = tempfile.NamedTemporaryFile(prefix="voicetype_tokens_", suffix=".txt", dir=".", delete=False)
    try:
        with temporary, open(tokens, "rb") as source:
            temporary.write(source.read())
        kwargs["tokens"] = os.path.basename(temporary.name)
        return factory(**kwargs)
    finally:
        os.unlink(temporary.name)


class ASREngine:
    def __init__(
        self,
        model: str,
        model_dir: str,
        gpu: bool = True,
        gpu_backend: str = "cuda",
        gpu_required: bool = True,
        allow_cpu_fallback: bool = False,
        language: str = "zh",
        cpu_threads: int = 4,
    ):
        self._model = model
        self._model_dir = model_dir
        self._gpu = gpu
        self._gpu_backend = gpu_backend
        self._gpu_required = gpu_required
        self._allow_cpu_fallback = allow_cpu_fallback
        self._recognizer = None
        self._qwen_model = None
        self._backend = None
        self._acceleration = "not-initialized"
        self._using_gpu = False
        self._last_error = ""
        self.language = language
        self.cpu_threads = cpu_threads

    def initialize(self) -> bool:
        try:
            validate_model(self._model, self.language)
            if not model_installed(self._model, self._model_dir):
                return self._fail("模型文件不完整，请下载或导入与引擎匹配的模型")
            if self._gpu_required and self._model in ("sensevoice", "paraformer"):
                return self._fail("该模型使用 CPU，请把运行方式改为自动选择或 CPU")
            if self._model in ("qwen3-asr-1.7b", "qwen3-asr-0.6b"):
                return self._init_qwen3_asr()
            elif self._model == "qwen3-asr-1.7b-gguf-vulkan":
                return self._init_qwen3_asr_gguf_vulkan()
            elif self._model in ("sensevoice", "paraformer"):
                return self._init_sherpa_onnx()
            elif self._model == "funasr-nano":
                return self._init_sherpa_onnx()
            else:
                logger.error(f"Unknown model: {self._model}")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize ASR engine: {e}")
            self._last_error = str(e)
            import traceback
            traceback.print_exc()
            return False

    def _fail(self, message: str) -> bool:
        self._last_error = message
        logger.error(message)
        return False

    def _init_qwen3_asr(self) -> bool:
        try:
            import os as _os
            _os.environ["TRANSFORMERS_OFFLINE"] = "1"
            _os.environ["HF_HUB_OFFLINE"] = "1"
            _os.environ["HF_DATASETS_CACHE"] = self._model_dir

            from qwen_asr import Qwen3ASRModel

            model_name_map = {
                "qwen3-asr-1.7b": "Qwen/Qwen3-ASR-1.7B",
                "qwen3-asr-0.6b": "Qwen/Qwen3-ASR-0.6B",
            }
            model_name = model_name_map.get(self._model, "Qwen/Qwen3-ASR-0.6B")
            if self._model_dir and os.path.isdir(self._model_dir):
                model_name = self._model_dir

            logger.info(f"Loading Qwen3-ASR from local path: {model_name}")
            import torch
            use_cuda = self._gpu and torch.cuda.is_available()
            if self._gpu and not use_cuda:
                return self._fail("NVIDIA CUDA 不可用，请安装 GPU 运行组件或选择 CPU 模型")
            self._qwen_model = Qwen3ASRModel.from_pretrained(
                model_name, dtype=torch.float16 if use_cuda else torch.float32,
                device_map="cuda:0" if use_cuda else "cpu", max_inference_batch_size=1,
            )
            if self._gpu:
                try:
                    import torch

                    if torch.cuda.is_available():
                        moved = self._move_qwen_model_to_cuda()
                        if not moved:
                            message = "CUDA is available but qwen-asr model could not be moved to CUDA"
                            if self._gpu_required and not self._allow_cpu_fallback:
                                return self._fail(message)
                            logger.warning(f"{message}; using CPU fallback")
                            self._acceleration = "pytorch-cpu"
                        else:
                            try:
                                torch.cuda.synchronize()
                            except Exception:
                                pass
                            logger.info(f"Qwen3-ASR moved to CUDA device: {torch.cuda.get_device_name(0)}")
                            self._acceleration = "pytorch-cuda"
                            self._using_gpu = True
                    else:
                        message = "CUDA requested but current PyTorch is CPU-only or CUDA is unavailable"
                        if self._gpu_required and not self._allow_cpu_fallback:
                            return self._fail(message)
                        logger.warning(f"{message}; using CPU fallback")
                        self._acceleration = "pytorch-cpu"
                except Exception as e:
                    message = f"CUDA availability check failed: {e}"
                    if self._gpu_required and not self._allow_cpu_fallback:
                        return self._fail(message)
                    logger.warning(f"{message}; using CPU fallback")
                    self._acceleration = "pytorch-cpu"
            else:
                self._acceleration = "pytorch-cpu"
                if self._gpu_required and not self._allow_cpu_fallback:
                    return self._fail("GPU is required but Qwen model does not expose a CUDA move method")
            self._backend = "qwen-asr"
            logger.info(f"Qwen3-ASR model loaded: {model_name} (gpu={self._gpu})")
            return True

        except ImportError:
            return self._fail("缺少 Qwen GPU 运行组件，请安装组件或使用 SenseVoice CPU 模型")
        except Exception as e:
            logger.error(f"Failed to init Qwen3-ASR: {e}")
            self._last_error = str(e)
            return False

    def _move_qwen_model_to_cuda(self) -> bool:
        inner_model = getattr(self._qwen_model, "model", None)
        if inner_model is None or not hasattr(inner_model, "to"):
            return False
        inner_model = inner_model.to("cuda")
        self._qwen_model.model = inner_model
        try:
            first_param = next(inner_model.parameters())
            self._qwen_model.device = first_param.device
            self._qwen_model.dtype = first_param.dtype
        except Exception:
            self._qwen_model.device = getattr(inner_model, "device", "cuda")
            self._qwen_model.dtype = getattr(inner_model, "dtype", None)
        return True

    def _init_qwen3_asr_gguf_vulkan(self) -> bool:
        if not os.path.isdir(self._model_dir):
            return self._fail(f"Qwen3-ASR-GGUF model dir not found: {self._model_dir}")
        gguf_files = [f for f in os.listdir(self._model_dir) if f.lower().endswith(".gguf")]
        if not gguf_files:
            return self._fail(f"No Qwen3-ASR GGUF files found in {self._model_dir}")
        return self._fail("Qwen3-ASR-GGUF Vulkan backend is detected but not implemented in VoiceType yet")

    def _init_sherpa_onnx(self) -> bool:
        import sherpa_onnx

        provider = "cpu"
        if self._gpu and self._model not in ("sensevoice", "paraformer"):
            if self._gpu_backend == "cuda":
                provider = "cuda"
            elif self._gpu_backend == "vulkan":
                provider = "vulkan"
            elif self._gpu_backend == "dml":
                provider = "dml"

        if self._gpu_required and self._gpu and provider == "cpu" and not self._allow_cpu_fallback:
            return self._fail("GPU is required but no non-CPU sherpa-onnx provider was selected")
        if provider != "cpu" and not self._sherpa_provider_available(provider):
            message = f"sherpa-onnx provider '{provider}' is not available in the current Python environment"
            if self._gpu_required and not self._allow_cpu_fallback:
                return self._fail(message)
            logger.warning(f"{message}; using CPU fallback")
            provider = "cpu"

        model_dir = self._model_dir
        if not os.path.isdir(model_dir):
            logger.error(f"Model dir not found: {model_dir}")
            return False

        tokens_file = os.path.join(model_dir, "tokens.txt")
        if not os.path.exists(tokens_file):
            logger.error(f"tokens.txt not found in {model_dir}")
            return False

        if self._model == "sensevoice":
            model_file = os.path.join(model_dir, "model.int8.onnx")
            if not os.path.exists(model_file):
                model_file = self._find_onnx(model_dir)
            if not model_file:
                logger.error(f"No ONNX model found in {model_dir}")
                return False

            try:
                self._recognizer = _create_sherpa_recognizer(sherpa_onnx.OfflineRecognizer.from_sense_voice,
                    model=model_file,
                    tokens=tokens_file,
                    num_threads=self.cpu_threads,
                    provider=provider,
                    language=self.language,
                    use_itn=True,
                )
            except Exception as e:
                if self._gpu_required and provider != "cpu" and not self._allow_cpu_fallback:
                    return self._fail(f"sherpa-onnx provider '{provider}' failed while GPU is required: {e}")
                raise

        elif self._model == "paraformer":
            model_file = os.path.join(model_dir, "model.int8.onnx")
            if not os.path.exists(model_file):
                model_file = self._find_onnx(model_dir)
            if not model_file:
                logger.error(f"No ONNX model found in {model_dir}")
                return False

            try:
                self._recognizer = _create_sherpa_recognizer(sherpa_onnx.OfflineRecognizer.from_paraformer,
                    paraformer=model_file,
                    tokens=tokens_file,
                    num_threads=self.cpu_threads,
                    provider=provider,
                )
            except Exception as e:
                if self._gpu_required and provider != "cpu" and not self._allow_cpu_fallback:
                    return self._fail(f"sherpa-onnx provider '{provider}' failed while GPU is required: {e}")
                raise

        elif self._model == "funasr-nano":
            gguf_files = [f for f in os.listdir(model_dir) if f.endswith(".gguf")]
            if not gguf_files:
                logger.error(f"No GGUF files found in {model_dir}")
                return False

            encoder_file = None
            decoder_file = None
            for f in gguf_files:
                full_path = os.path.join(model_dir, f)
                if "encoder" in f.lower():
                    encoder_file = full_path
                elif "decoder" in f.lower():
                    decoder_file = full_path

            if not encoder_file or not decoder_file:
                if len(gguf_files) >= 2:
                    encoder_file = os.path.join(model_dir, gguf_files[0])
                    decoder_file = os.path.join(model_dir, gguf_files[1])
                else:
                    logger.error(f"Need encoder+decoder GGUF files in {model_dir}")
                    return False

            config = sherpa_onnx.OfflineRecognizerConfig(
                model_config=sherpa_onnx.OfflineModelConfig(
                    tokens=tokens_file,
                    num_threads=4,
                    provider=provider,
                    whisper_encoder=encoder_file,
                    whisper_decoder=decoder_file,
                ),
            )
        else:
            logger.error(f"Unknown sherpa-onnx model: {self._model}")
            return False

        if self._recognizer is None:
            try:
                self._recognizer = sherpa_onnx.OfflineRecognizer(config)
            except Exception as e:
                if self._gpu_required and provider != "cpu" and not self._allow_cpu_fallback:
                    return self._fail(f"sherpa-onnx provider '{provider}' failed while GPU is required: {e}")
                raise
        self._backend = "sherpa-onnx"
        self._acceleration = f"sherpa-onnx-{provider}"
        self._using_gpu = provider != "cpu"
        logger.info(f"Sherpa-ONNX model loaded: {self._model} (provider={provider})")
        return True

    def _sherpa_provider_available(self, provider: str) -> bool:
        if provider == "cpu":
            return True
        try:
            import onnxruntime as ort

            providers = set(ort.get_available_providers())
        except Exception:
            providers = set()
        provider_map = {
            "cuda": "CUDAExecutionProvider",
            "dml": "DmlExecutionProvider",
        }
        expected = provider_map.get(provider)
        if expected:
            return expected in providers
        return False

    def _find_onnx(self, model_dir: str) -> Optional[str]:
        for f in os.listdir(model_dir):
            if f.endswith(".onnx") and "int8" in f:
                return os.path.join(model_dir, f)
        for f in os.listdir(model_dir):
            if f.endswith(".onnx"):
                return os.path.join(model_dir, f)
        return None

    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[str]:
        self._last_error = ""
        if self._backend == "qwen-asr" and self._qwen_model:
            return self._recognize_qwen(audio_data, sample_rate)
        elif self._backend == "sherpa-onnx" and self._recognizer:
            return self._recognize_sherpa(audio_data, sample_rate)
        else:
            logger.error("ASR engine not initialized")
            return None

    def _recognize_qwen(self, audio_data: bytes, sample_rate: int) -> Optional[str]:
        try:
            import numpy as np

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()

            try:
                import wave
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                with wave.open(tmp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio_array.tobytes())

                self._last_error = ""
                results = self._qwen_model.transcribe(audio=tmp_path, language=QWEN_LANGUAGES[self.language])
                if results and len(results) > 0:
                    text = results[0].text.strip()
                    logger.info(f"Qwen3-ASR result: {text}")
                    return text if text else None
                return None
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        except Exception as e:
            logger.error(f"Qwen3-ASR recognition failed: {e}")
            self._last_error = str(e)
            return None

    def _recognize_sherpa(self, audio_data: bytes, sample_rate: int) -> Optional[str]:
        try:
            import numpy as np

            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, audio_array)
            self._recognizer.decode_stream(stream)
            result = stream.result.text.strip()

            logger.info(f"Sherpa-ONNX result: {result}")
            return result if result else None

        except Exception as e:
            logger.error(f"Sherpa-ONNX recognition failed: {e}")
            self._last_error = str(e)
            return None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def backend(self) -> Optional[str]:
        return self._backend

    @property
    def acceleration(self) -> str:
        return self._acceleration

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu

    @property
    def last_error(self) -> str:
        return self._last_error
