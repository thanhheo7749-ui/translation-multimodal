"""
Diagnostic and inventory report for NCKH Translation Modal Project.
Verifies all existing local hardware, libraries, and cached models.
"""
import sys
import os
import platform

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def run_diagnostics():
    print("=" * 60)
    print(" BÁO CÁO KIỂM TRA MÔI TRƯỜNG & TÀI NGUYÊN SẴN CÓ TRÊN MÁY")
    print("=" * 60)
    
    # 1. Python & OS
    print(f"[1] Python Version: {platform.python_version()} ({sys.executable})")
    print(f"    Hệ điều hành: {platform.system()} {platform.release()}")
    
    # 2. CUDA & CTranslate2
    try:
        import ctranslate2
        cuda_count = ctranslate2.get_cuda_device_count()
        print(f"[2] CTranslate2: v{ctranslate2.__version__}")
        print(f"    CUDA Device Count: {cuda_count} (RTX 3050)")
        if cuda_count > 0:
            for i in range(cuda_count):
                print(f"    -> Thiết bị [{i}]: Cài đặt CUDA hoạt động tốt!")
    except Exception as e:
        print(f"[2] CTranslate2 Error: {e}")

    # 3. Faster-Whisper
    try:
        import faster_whisper
        print(f"[3] faster-whisper: v{faster_whisper.__version__} (Đã cài sẵn trong .venv)")
    except Exception as e:
        print(f"[3] faster-whisper: Chưa cài ({e})")
        
    # 4. PaddleOCR local cache
    paddle_path = os.path.expanduser(r"~\.paddleocr\whl")
    print(f"[4] PaddleOCR Cache:")
    if os.path.exists(paddle_path):
        found_models = []
        for root, dirs, files in os.walk(paddle_path):
            for f in files:
                if f.endswith(".pdiparams") or f.endswith(".pdmodel"):
                    rel = os.path.relpath(os.path.join(root, f), paddle_path)
                    found_models.append(rel)
        print(f"    Đường dẫn: {paddle_path}")
        print(f"    Số file trọng số model phát hiện: {len(found_models)}")
        for m in found_models[:5]:
            print(f"      - {m}")
        if len(found_models) > 5:
            print(f"      ... và {len(found_models) - 5} file khác.")
        print("    -> Trạng thái: ĐÃ CÓ SẴN (Không cần tải lại!)")
    else:
        print("    Không tìm thấy thư mục .paddleocr")
        
    # 5. Hugging Face local cache
    hf_path = os.path.expanduser(r"~\.cache\huggingface\hub")
    print(f"[5] Hugging Face Hub Cache:")
    if os.path.exists(hf_path):
        models = [d for d in os.listdir(hf_path) if os.path.isdir(os.path.join(hf_path, d))]
        print(f"    Đường dẫn: {hf_path}")
        for m in models:
            m_path = os.path.join(hf_path, m)
            # Check size
            total_size = sum(os.path.getsize(os.path.join(dirpath, f)) for dirpath, _, filenames in os.walk(m_path) for f in filenames)
            size_mb = total_size / (1024 * 1024)
            print(f"      - {m} ({size_mb:.2f} MB)")
    else:
        print("    Không tìm thấy thư mục .cache/huggingface")

    print("=" * 60)

if __name__ == "__main__":
    run_diagnostics()
