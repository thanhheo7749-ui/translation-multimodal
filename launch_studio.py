"""Windows double-click launcher; key stays in the current process environment."""
import argparse
import getpass
import json
import os
from pathlib import Path
import runpy
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser


def available_port(start):
    for port in range(start, min(start + 20, 65536)):
        with socket.socket() as candidate:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                candidate.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                candidate.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError('Không tìm được cổng trống. Thử chạy với --port 8100.')


def open_when_ready(port, stop):
    url = f'http://localhost:{port}/live'
    for _ in range(60):
        if stop.is_set():
            return
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/translation-status', timeout=1) as response:
                config = json.loads(response.read())
            if config.get('provider') == os.environ['TRANSLATION_PROVIDER']:
                print(f'\nTrang dịch trực tiếp: {url}', flush=True)
                if not webbrowser.open(url):
                    print('Hãy mở địa chỉ trên trong trình duyệt.', flush=True)
                return
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        if stop.wait(.5):
            return
    print(f'Chưa xác nhận server sẵn sàng. Xem lỗi trên cửa sổ này; địa chỉ dự kiến: {url}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=('gemini', 'google-demo'), default='gemini')
    parser.add_argument('--model', default='gemini-3.5-flash-lite')
    parser.add_argument('--port', type=int, default=8003)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))
    print('KHỞI CHẠY WEBSITE THỬ DỊCH ANH–VIỆT', flush=True)
    print(f'Provider: {args.provider} | Model: {args.model if args.provider == "gemini" else "dịch văn bản demo"}', flush=True)
    if args.provider == 'gemini' and not os.getenv('GEMINI_API_KEY'):
        print('Dán API key rồi nhấn Enter. Khóa sẽ KHÔNG hiện ký tự khi nhập và không được lưu vào file.', flush=True)
        api_key = getpass.getpass('API key: ').strip()
        if not api_key:
            raise RuntimeError('Chưa nhập API key. Chạy lại và nhập khóa, hoặc dùng --provider google-demo.')
        os.environ['GEMINI_API_KEY'] = api_key
    os.environ['TRANSLATION_PROVIDER'] = args.provider
    os.environ['GEMINI_MODEL'] = args.model
    if args.provider == 'gemini':
        from backend.translation.live_service import LiveTranslationService
        from backend.translation.diagnostic_log import save_attempt
        print('Đang kiểm tra khóa và quyền truy cập model (tối đa khoảng 10 giây)…', flush=True)
        access = LiveTranslationService().check_access()
        save_attempt(access, args.model)
        print(f'Kiểm tra Gemini: {access.status} | {access.error_code or "model_access_ok"}', flush=True)
        print(access.message, flush=True)
        if access.diagnostic:
            print(json.dumps(access.diagnostic, ensure_ascii=False), flush=True)
        print('Kết quả an toàn đã lưu trong experiments/runtime_logs/translation_attempts.jsonl.', flush=True)
    port = available_port(args.port)
    os.environ['STUDIO_PORT'] = str(port)
    print(f'Website: http://localhost:{port}', flush=True)
    print('Giữ cửa sổ này mở. Nhấn Ctrl+C để dừng. Cấu hình key chưa có nghĩa API đã kết nối thành công.', flush=True)
    stop = threading.Event()
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(port, stop), daemon=True).start()
    try:
        runpy.run_module('backend.server', run_name='__main__')
    finally:
        stop.set()
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nĐã dừng server.')
    except (RuntimeError, OSError, ImportError, EOFError) as error:
        print(f'Không khởi chạy được: {error}', file=sys.stderr)
        raise SystemExit(1)
