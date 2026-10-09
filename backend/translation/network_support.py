"""Verified TLS and credential-free transport diagnostics."""
import socket
import ssl


def verified_ssl_context():
    context = ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        pass
    else:
        # Supplement system roots; retain certificate and hostname verification.
        context.load_verify_locations(cafile=certifi.where())
    return context


def classify_network_error(error):
    reason = getattr(error, 'reason', error)
    details = {'exception_type': type(reason).__name__}
    for name in ('errno', 'winerror', 'verify_code'):
        value = getattr(reason, name, None)
        if isinstance(value, int):
            details[name] = value
    if isinstance(reason, ssl.SSLCertVerificationError):
        code = 'tls_certificate_error'
        message = 'Không xác minh được chứng chỉ HTTPS. Chạy diagnose_network.cmd để kiểm tra CA/chứng chỉ; không tắt xác minh TLS.'
    elif isinstance(reason, ssl.SSLError):
        code = 'tls_error'
        message = 'Lỗi bắt tay TLS với Gemini. Chạy diagnose_network.cmd để phân biệt lỗi chứng chỉ và kết nối.'
    elif isinstance(reason, socket.gaierror):
        code = 'dns_error'
        message = 'Không phân giải được địa chỉ Google API. Chạy diagnose_network.cmd để kiểm tra DNS.'
    elif isinstance(reason, TimeoutError) or getattr(reason, 'winerror', None) == 10060:
        code = 'network_timeout'
        message = 'Kết nối hoặc phản hồi Gemini quá thời gian chờ. Chạy diagnose_network.cmd để kiểm tra kết nối HTTPS tới Google API.'
    elif getattr(reason, 'winerror', None) == 10013 or getattr(reason, 'errno', None) == 13:
        code = 'network_blocked'
        message = 'Kết nối bị từ chối quyền truy cập socket. Chạy diagnose_network.cmd từ File Explorer để kiểm tra trong môi trường của bạn.'
    elif isinstance(reason, ConnectionRefusedError) or getattr(reason, 'winerror', None) == 10061:
        code = 'connection_refused'
        message = 'Kết nối bị từ chối. Kiểm tra kết nối mạng/proxy bằng diagnose_network.cmd.'
    elif isinstance(reason, ConnectionResetError) or getattr(reason, 'winerror', None) == 10054:
        code = 'connection_reset'
        message = 'Kết nối HTTPS bị đóng giữa chừng. Chạy diagnose_network.cmd để kiểm tra đường kết nối.'
    else:
        code = 'network_error'
        message = 'Không kết nối được provider. Chạy diagnose_network.cmd; chi tiết an toàn được hiển thị bên dưới.'
    return code, message, details
