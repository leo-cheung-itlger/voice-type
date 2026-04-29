import os
import tempfile
from typing import Optional

from common.logger import setup_logger

logger = setup_logger("asr_engine")


class ASREngine:
    def __init__(self, model: str, model_dir: str, gpu: bool = True, gpu_backend: str = "cuda"):
        self._model = model
        self._model_dir = model_dir
        self._gpu = gpu
        self._gpu_backend = gpu_backend
        self._recognizer = None
        self._qwen_model = None
        self._backend = None

    def initialize(self) -> bool:
        try:
            if self._model in ("qwen3-asr-1.7b", "qwen3-asr-0.6b"):
                return self._init_qwen3_asr()
            elif self._model in ("sensevoice", "paraformer"):
                return self._init_sherpa_onnx()
            elif self._model == "funasr-nano":
                return self._init_sherpa_onnx()
            else:
                logger.error(f"Unknown model: {self._model}")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize ASR engine: {e}")
            import traceback
            traceback.print_exc()
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
            self._qwen_model = Qwen3ASRModel.from_pretrained(model_name)
            if self._gpu and hasattr(self._qwen_model, 'to'):
                self._qwen_model = self._qwen_model.to("cuda")
            self._backend = "qwen-asr"
            logger.info(f"Qwen3-ASR model loaded: {model_name} (gpu={self._gpu})")
            return True

        except ImportError:
            logger.warning("qwen-asr package not found, trying sherpa-onnx fallback")
            return self._init_sherpa_onnx()
        except Exception as e:
            logger.error(f"Failed to init Qwen3-ASR: {e}")
            return False

    def _init_sherpa_onnx(self) -> bool:
        import sherpa_onnx

        provider = "cpu"
        if self._gpu:
            if self._gpu_backend == "cuda":
                provider = "cuda"
            elif self._gpu_backend == "vulkan":
                provider = "vulkan"
            elif self._gpu_backend == "dml":
                provider = "dml"

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

            config = sherpa_onnx.OfflineRecognizerConfig(
                model_config=sherpa_onnx.OfflineModelConfig(
                    sense_voice=sherpa_onnx.OfflineSenseVoiceModelConfig(
                        model=model_file,
                        language="auto",
                    ),
                    tokens=tokens_file,
                    num_threads=4,
                    provider=provider,
                ),
            )

        elif self._model == "paraformer":
            model_file = os.path.join(model_dir, "model.int8.onnx")
            if not os.path.exists(model_file):
                model_file = self._find_onnx(model_dir)
            if not model_file:
                logger.error(f"No ONNX model found in {model_dir}")
                return False

            config = sherpa_onnx.OfflineRecognizerConfig(
                model_config=sherpa_onnx.OfflineModelConfig(
                    paraformer=sherpa_onnx.OfflineParaformerModelConfig(
                        model=model_file,
                    ),
                    tokens=tokens_file,
                    num_threads=4,
                    provider=provider,
                ),
            )

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

        self._recognizer = sherpa_onnx.OfflineRecognizer(config)
        self._backend = "sherpa-onnx"
        logger.info(f"Sherpa-ONNX model loaded: {self._model} (provider={provider})")
        return True

    def _find_onnx(self, model_dir: str) -> Optional[str]:
        for f in os.listdir(model_dir):
            if f.endswith(".onnx") and "int8" in f:
                return os.path.join(model_dir, f)
        for f in os.listdir(model_dir):
            if f.endswith(".onnx"):
                return os.path.join(model_dir, f)
        return None

    def recognize(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[str]:
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

                results = self._qwen_model.transcribe(audio=tmp_path, language=None)
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
            return None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def backend(self) -> Optional[str]:
        return self._backend
