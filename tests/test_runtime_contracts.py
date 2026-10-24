import asyncio
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from common import activity as leases
from common.model_catalog import QWEN_LANGUAGES, model_installed, validate_model
from common.model_download import _download
from common.transcription import TranscriptionManager
from config.settings import AppConfig, ServerConfig, load_app_config, save_app_config, save_server_config, update_app_config


class ConfigurationTests(unittest.TestCase):
    def test_unicode_sherpa_vocabulary_uses_ascii_relative_filename(self):
        from server.asr_engine import _create_sherpa_recognizer
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "中文词表.txt"
            source.write_text("你好 1", encoding="utf-8")
            seen = []
            def factory(**kwargs):
                path = Path(kwargs["tokens"])
                self.assertTrue(str(path).isascii())
                self.assertFalse(path.is_absolute())
                self.assertEqual(path.read_bytes(), source.read_bytes())
                seen.append(path)
                return "loaded"
            with patch("server.asr_engine.os.name", "nt"):
                self.assertEqual(_create_sherpa_recognizer(factory, tokens=str(source)), "loaded")
            self.assertFalse(seen[0].exists())

    def test_history_keeps_persisted_metadata_beyond_page_limit(self):
        from common.history import HistoryManager
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(json.dumps({"entries": [{"task_id": str(i), "text": "x"} for i in range(1001)]}), encoding="utf-8")
            history = HistoryManager(str(path))
            history.add_entry("new", "new", .1)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["entries"]), 1002)
            self.assertEqual(len(history.get_entries(limit=9999)), 1000)

    def test_health_keeps_process_reference_when_stop_clears_global(self):
        import api.api_server as api
        process = MagicMock(pid=123)
        process.poll.return_value = None
        for role in ("server", "client"):
            def stopped(_):
                setattr(api, role + "_process", None)
                return []
            with patch.object(api, role + "_process", process), patch.object(api.ProcessManager, "_processes_by_role", side_effect=stopped), patch.object(api.ProcessManager, "_port_open", return_value=False):
                result = getattr(api.ProcessManager, "check_" + role + "_health")()
                self.assertEqual(result["pid"], 123)

    def test_new_and_legacy_compute_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            self.assertEqual(load_app_config(str(path)).server.compute_mode, "auto")
            for values, expected in [({"gpu": False}, "cpu"),
                                     ({"gpu": True, "gpu_required": True, "allow_cpu_fallback": False}, "cuda"),
                                     ({"gpu": True, "gpu_required": False, "allow_cpu_fallback": True}, "auto")]:
                path.write_text(json.dumps({"server": values}), encoding="utf-8")
                config = load_app_config(str(path)).server
                self.assertEqual(config.compute_mode, expected)
                self.assertEqual(config.language, "zh")
        self.assertEqual(QWEN_LANGUAGES["zh"], "Chinese")
        self.assertIsNone(QWEN_LANGUAGES["auto"])

    def test_unsupported_combinations_and_missing_weights(self):
        with self.assertRaises(ValueError):
            validate_model("qwen3-asr-1.7b-gguf-vulkan")
        with self.assertRaises(ValueError):
            validate_model("paraformer", "yue")
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(model_installed("sensevoice", directory))
            for name in ("model.int8.onnx", "tokens.txt"):
                (Path(directory) / name).touch()
            self.assertFalse(model_installed("sensevoice", directory))

    def test_recording_blocks_switch_and_stale_leases_are_removed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(leases, "DATA_DIR", directory):
            token = leases.acquire("recording")
            with self.assertRaises(RuntimeError):
                leases.acquire("switch")
            leases.release(token)
            with leases.activity("switch"):
                with self.assertRaises(RuntimeError):
                    leases.acquire("recording")
            self.assertEqual(leases.activities(), [])

    def test_task_snapshots_language_without_rewriting_old_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text(json.dumps({"tasks": {"old": {"task_id": "old", "status": "completed"}}}), encoding="utf-8")
            manager = TranscriptionManager(str(path))
            payload = {"input_files": ["example.wav"], "model": "sensevoice", "language": "yue", "compute_mode": "cpu"}
            task = manager.create_task(payload)
            payload["language"] = "en"
            self.assertEqual(manager.get_task(task["task_id"])["language"], "yue")
            self.assertNotIn("language", manager.get_task("old"))

    def test_download_resume_and_checksum(self):
        class Response(io.BytesIO):
            status = 206
            headers = {"Content-Length": "3"}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            target.with_name("model.partial").write_bytes(b"abc")
            with patch("common.model_download.urlopen", return_value=Response(b"def")) as request:
                _download("https://example.test/model", target, {}, hashlib.sha256(b"abcdef").hexdigest())
                self.assertEqual(request.call_args.args[0].get_header("Range"), "bytes=3-")
            self.assertEqual(target.read_bytes(), b"abcdef")


class RecoveryTests(unittest.TestCase):
    def test_server_save_preserves_runtime_settings_saved_during_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "config.json")
            save_app_config(AppConfig(), path)
            candidate = load_app_config(path).server
            candidate.language = "en"
            update_app_config({"client": {"shortcut_key": "f9"}}, path)
            saved = save_server_config(candidate, path)
            self.assertEqual(saved.client.shortcut_key, "f9")
            self.assertEqual(saved.server.language, "en")

    def test_start_cannot_bypass_busy_lifecycle(self):
        from api import api_server as api
        from fastapi import HTTPException
        with api._lifecycle_lock:
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(api.api_start_all())
        self.assertEqual(caught.exception.status_code, 409)

    def test_cpu_package_does_not_report_qwen_as_compatible(self):
        from api import api_server as api
        config = AppConfig()
        config.server.compute_mode = "cpu"
        with patch.object(api, "load_app_config", return_value=config), \
             patch.object(api, "_torch_status", return_value={"available": False, "cuda_available": False}), \
             patch.object(api, "runtime_state", return_value={}):
            qwen = next(row for row in api._model_entries() if row["id"] == "qwen3-asr-0.6b")
            self.assertFalse(qwen["compatible"])

    def test_failed_apply_restores_previous_config(self):
        from api import api_server as api
        from fastapi import HTTPException
        prior = AppConfig()
        prior.server.model = "sensevoice"
        manager = MagicMock()
        manager.check_client_health.return_value = {"running": True}
        with patch.object(api, "load_app_config", return_value=prior), \
             patch.object(api, "save_server_config") as save, \
             patch.object(api, "ProcessManager", manager), \
             patch.object(api, "model_installed", return_value=True), \
             patch.object(api, "runtime_state", return_value={"loaded": True}), \
             patch.object(api, "activity", return_value=contextlib.nullcontext()), \
             patch.object(api, "_start_and_wait", side_effect=[RuntimeError("simulated CUDA out of memory"), {"loaded": True}]):
            with self.assertRaises(HTTPException) as caught:
                api._apply_recognition(api.RecognitionApplyRequest(model="qwen3-asr-0.6b", language="en", compute_mode="auto"))
            self.assertIn("已恢复", caught.exception.detail)
            self.assertEqual(save.call_args.args[0].model, "sensevoice")
            self.assertEqual(save.call_args.args[0].language, "zh")

    def test_auto_falls_back_but_strict_gpu_does_not(self):
        from server import asr_server as server

        class Finished(Exception):
            pass

        class Serve:
            async def __aenter__(self):
                raise Finished()
            async def __aexit__(self, *args):
                pass

        for mode in ("auto", "cuda"):
            failed = MagicMock()
            failed.initialize.return_value = False
            failed.last_error = "simulated incompatible CUDA driver"
            cpu = MagicMock()
            cpu.initialize.return_value = True
            cpu.model_name = "sensevoice"
            cpu.language = "zh"
            cpu.using_gpu = False
            config = ServerConfig(model="qwen3-asr-0.6b", compute_mode=mode)
            with patch.object(server, "ASREngine", side_effect=[failed, cpu]) as factory, \
                 patch.object(server, "model_installed", return_value=True), \
                 patch.object(server, "write_runtime_state") as write, \
                 patch.object(server.websockets, "serve", return_value=Serve()):
                runner = server.ASRServer(config)
                if mode == "auto":
                    with self.assertRaises(Finished):
                        asyncio.run(runner.start())
                    self.assertEqual(factory.call_count, 2)
                    self.assertEqual(write.call_args.kwargs["active_model"], "sensevoice")
                    self.assertEqual(write.call_args.kwargs["actual_device"], "cpu")
                else:
                    asyncio.run(runner.start())
                    self.assertEqual(factory.call_count, 1)
                    self.assertFalse(write.call_args.kwargs["loaded"])


if __name__ == "__main__":
    unittest.main()
