"""Read a Gemini key from stdin, probe access without logging credentials."""
import argparse
import getpass
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='gemini-3.8-flash')
    parser.add_argument('--serve-port', type=int)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9._-]+',args.model):
        parser.error('Invalid model name')
    print('Waiting for key on stdin (not echoed)', flush=True)
    key = (getpass.getpass('API key (hidden): ') if sys.stdin.isatty() else sys.stdin.readline()).strip()
    if not key:
        print(json.dumps({'status':'error','error_code':'missing_key'})); return 2
    req = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+args.model,headers={'x-goog-api-key':key})
    try:
        with urllib.request.urlopen(req,timeout=10) as response:
            model=json.loads(response.read().decode())
        available=model.get('name')=='models/'+args.model and 'generateContent' in model.get('supportedGenerationMethods',[])
        print(json.dumps({'status':'ok','model':args.model,'model_available':available}),flush=True)
    except urllib.error.HTTPError as error:
        print(json.dumps({'status':'error','error_code':'http_'+str(error.code),'key_validated':False}),flush=True)
        return 1
    except (urllib.error.URLError,TimeoutError) as error:
        reason=getattr(error,'reason',error)
        print(json.dumps({'status':'error','error_code':'network_blocked' if getattr(reason,'winerror',None)==10013 else 'network_error','key_validated':False}),flush=True)
        available=None
    if available is False:
        return 1
    if args.serve_port:
        root=Path(__file__).resolve().parents[1]; logs=root/'experiments/runtime_logs'
        logs.mkdir(exist_ok=True)
        env={name.upper():value for name,value in os.environ.items()}
        env.update(GEMINI_API_KEY=key,GEMINI_MODEL=args.model,TRANSLATION_PROVIDER='gemini',STUDIO_PORT=str(args.serve_port))
        with (logs/f'gemini_{args.serve_port}.stdout.log').open('ab') as out,(logs/f'gemini_{args.serve_port}.stderr.log').open('ab') as err:
            child=subprocess.Popen([sys.executable,'-u','-m','backend.server'],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW,close_fds=True)
        print(json.dumps({'server_pid':child.pid,'port':args.serve_port,'model':args.model,'key_storage':'child process environment only','network_verified':available is not None}),flush=True)
    return 0 if available is not None else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
