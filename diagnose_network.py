"""Probe DNS and HTTPS without reading or sending an API key."""
import json
from pathlib import Path
import socket
import ssl
import sys
import urllib.error
import urllib.request

from backend.translation.network_support import classify_network_error, verified_ssl_context


def probe(url, context):
    try:
        with urllib.request.urlopen(url, timeout=8, context=context) as response:
            return {'transport':'ok', 'http_status':response.status}
    except urllib.error.HTTPError as error:
        # An HTTP error is positive evidence DNS/TCP/TLS reached the remote service.
        return {'transport':'ok', 'http_status':error.code, 'note':'HTTP response reached; this is an unauthenticated probe.'}
    except (urllib.error.URLError,OSError) as error:
        code, message, details=classify_network_error(error)
        return {'transport':'error','error_code':code,'message':message,'details':details}


def main():
    print('KIỂM TRA KẾT NỐI — KHÔNG ĐỌC HOẶC GỬI API KEY', flush=True)
    report={'python_version':sys.version.split()[0], 'openssl_version':ssl.OPENSSL_VERSION,
            'proxy_detected':bool(urllib.request.getproxies()), 'probes':{}}
    try:
        socket.getaddrinfo('generativelanguage.googleapis.com',443,type=socket.SOCK_STREAM)
        report['google_api_dns']='ok'
    except OSError as error:
        code,_,details=classify_network_error(error)
        report['google_api_dns']={'error_code':code,'details':details}
    contexts=[('system_ca',ssl.create_default_context()),('system_plus_certifi',verified_ssl_context())]
    for label,context in contexts:
        print(f'Đang thử HTTPS Google API với {label}…',flush=True)
        result=probe('https://generativelanguage.googleapis.com/v1beta/models',context)
        report['probes'][label]=result
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    print('Đang thử HTTPS Google thông thường…',flush=True)
    report['probes']['google_web']=probe('https://www.google.com/generate_204',contexts[-1][1])
    print(json.dumps(report['probes']['google_web'],ensure_ascii=False,indent=2),flush=True)
    destination=Path(__file__).resolve().parent/'experiments/runtime_logs/network_diagnostic.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'\nBáo cáo không chứa khóa: {destination}',flush=True)
    return report


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
