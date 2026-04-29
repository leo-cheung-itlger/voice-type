import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import ServerConfig
from server.asr_engine import ASREngine
from common.logger import setup_logger

logger = setup_logger("test_asr")

def test_asr_engine():
    print("=" * 60)
    print("ASR Engine 测试 - Qwen3-ASR-1.7B")
    print("=" * 60)

    config = ServerConfig()
    print(f"\n配置信息:")
    print(f"  模型: {config.model}")
    print(f"  模型路径: {config.model_dir}")
    print(f"  GPU: {config.gpu}")
    print(f"  GPU后端: {config.gpu_backend}")

    if not os.path.isdir(config.model_dir):
        print(f"\n❌ 错误: 模型目录不存在: {config.model_dir}")
        return False

    print(f"\n✅ 模型目录存在，包含文件:")
    for f in os.listdir(config.model_dir)[:10]:
        filepath = os.path.join(config.model_dir, f)
        size_mb = os.path.getsize(filepath) / (1024*1024)
        print(f"  - {f} ({size_mb:.1f} MB)")

    print("\n正在初始化 ASR 引擎...")
    start_time = time.time()

    engine = ASREngine(
        model=config.model,
        model_dir=config.model_dir,
        gpu=config.gpu,
        gpu_backend=config.gpu_backend
    )

    success = engine.initialize()
    elapsed = time.time() - start_time

    if success:
        print(f"\n✅ ASR 引擎初始化成功!")
        print(f"   后端: {engine.backend}")
        print(f"   耗时: {elapsed:.2f}s")
        return True
    else:
        print(f"\n❌ ASR 引擎初始化失败 (耗时: {elapsed:.2f}s)")
        return False

if __name__ == "__main__":
    try:
        success = test_asr_engine()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
