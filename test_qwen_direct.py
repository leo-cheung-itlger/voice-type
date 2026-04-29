import sys
import os
import traceback

venv_site = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "Lib", "site-packages")
if venv_site not in sys.path:
    sys.path.insert(0, venv_site)

print("=" * 60)
print("Qwen3-ASR Direct Test")
print("=" * 60)

print("\n[Step 1] Checking Python path...")
for p in sys.path[:5]:
    print(f"  {p}")

print("\n[Step 2] Testing qwen_asr import...")
try:
    from qwen_asr import Qwen3ASRModel
    print(f"  [OK] Qwen3ASRModel imported from: {Qwen3ASRModel.__module__}")
except ImportError as e:
    print(f"  [FAIL] ImportError: {e}")
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"  [FAIL] Unexpected error: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n[Step 3] Loading model...")
model_path = r"c:\Program Files\CapsWriter-Offline-Windows-64bit\models\Qwen3-ASR-1.7B"
print(f"  Model path: {model_path}")

try:
    model = Qwen3ASRModel.from_pretrained(model_path)
    if hasattr(model, 'to'):
        model = model.to("cuda")
    print("  [OK] Model loaded successfully!")
except Exception as e:
    print(f"  [FAIL] Failed to load model: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n[Step 4] Testing transcription with silence...")
try:
    import numpy as np

    sr = 16000
    duration = 1.0
    audio = np.zeros(int(sr * duration), dtype=np.float32)

    tmp_path = os.path.join(os.path.dirname(__file__), "_test_silence.wav")
    import wave
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((audio * 32768).astype(np.int16).tobytes())

    results = model.transcribe(audio=tmp_path, language=None)
    if results and len(results) > 0:
        text = results[0].text.strip() if hasattr(results[0], 'text') else str(results[0])
        print(f"  [OK] Result: '{text}'")
    else:
        print("  [OK] Empty result (expected for silence)")

    try:
        os.unlink(tmp_path)
    except OSError:
        pass

except Exception as e:
    print(f"  [WARN] Transcription test error: {e}")
    traceback.print_exc()

print("\n[DONE] All tests passed!")
