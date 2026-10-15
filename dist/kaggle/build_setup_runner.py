"""Generate a clean setup notebook from the user's runner, with no saved outputs."""
import json
from pathlib import Path
import textwrap

HERE=Path(__file__).resolve().parent
cells=[]
def add(kind,source):
    source=textwrap.dedent(source).strip()+'\n'
    cell={'cell_type':kind,'id':f'setup-{len(cells):02d}','metadata':{},'source':source.splitlines(True)}
    if kind=='code':
        compile(source,f'cell-{len(cells)}','exec')
        cell.update(execution_count=None,outputs=[])
    cells.append(cell)

add('markdown','''
# Tastly — setup và thử web trên Kaggle
Upload/attach **hai Dataset đầu vào mới**:
1. `mlai-fullstack-code.zip` (code, frontend, CatBoost, LoRA adapter).
2. `ai1-demo-data.zip` (processed + embeddings của demo có ràng buộc).

Bật **Internet**, **GPU T4/P100** nếu `ENABLE_QWEN=True`. Secrets:
`NGROK_AUTHTOKEN`; thêm `GEMINI_API_KEY` và `GEMINI_MODEL` nếu bật Gemini.
Notebook tự giải nén, kiểm tra SHA256, cài Python/Node/PostgreSQL/npm,
tải MiniLM và Qwen base, kiểm tra model/data, nạp database rồi chạy web.
Không cần chạy setup.ps1, không cần restart kernel. Các bước dùng venv riêng;
GPU torch sẵn có của Kaggle được dùng lại nếu tương thích.

Chạy các mục **1 → 8**; mục 9 chỉ chẩn đoán, mục 10 dùng để dừng.
Dataset đang chạy là **giả lập cho demo**, không phải menu/tiện ích xác minh.
Không upload `.env`, token hoặc thư mục backup. Notebook không tự lấy được
ZIP mới đang nằm trên máy bạn: cần upload hai ZIP trên một lần trước khi chạy.
''')
add('markdown','## 1. Nạp code và dataset demo mới')
add('code',r'''
from pathlib import Path, PurePosixPath
import os, sys, json, tempfile, zipfile, shutil, stat, signal
INPUT=Path('/kaggle/input')
# Để None để tự tìm; chỉ điền đường dẫn cụ thể khi attach nhiều bản.
CODE_ARCHIVE=None
DATA_ARCHIVE=None
for process in globals().get('SERVERS',{}).values():
    if process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try: process.wait(timeout=15)
        except Exception: os.killpg(process.pid,signal.SIGKILL); process.wait()
SERVERS={}
bundles=[Path(CODE_ARCHIVE)] if CODE_ARCHIVE else list(INPUT.rglob('mlai-fullstack-code.zip'))
extracted=[p.parent for p in INPUT.rglob('kaggle_manifest.json') if (p.parent/'scripts/kaggle_setup.py').is_file()]
PROJECT=Path(tempfile.mkdtemp(prefix='tastly-',dir='/kaggle/working'))
if len(bundles)==1:
    with zipfile.ZipFile(bundles[0]) as z:
        seen=set()
        for item in z.infolist():
            name=PurePosixPath(item.filename); target=(PROJECT/item.filename).resolve()
            if name.is_absolute() or '..' in name.parts or chr(92) in item.filename or not target.is_relative_to(PROJECT.resolve()) or stat.S_ISLNK(item.external_attr >> 16) or item.filename in seen:
                raise ValueError('Unsafe ZIP entry')
            seen.add(item.filename)
        z.extractall(PROJECT)
elif not bundles and len(extracted)==1:
    shutil.copytree(extracted[0],PROJECT,dirs_exist_ok=True)
else:
    raise RuntimeError('Attach exactly one updated mlai-fullstack-code.zip Dataset')
if not (PROJECT/'scripts/kaggle_setup.py').is_file():
    raise RuntimeError('Code ZIP is old: upload the rebuilt fullstack ZIP with kaggle_setup.py')
os.chdir(PROJECT)
sys.path.insert(0,str(PROJECT))
for module in ('scripts.kaggle_setup','scripts'):
    sys.modules.pop(module,None)
from scripts.kaggle_setup import safe_extract,verify_manifest
code_manifest=verify_manifest(PROJECT,'kaggle_manifest.json')
print('Code commit:',code_manifest['commit'],'Local changes:',code_manifest['working_tree_modified'])
bundles=[Path(DATA_ARCHIVE)] if DATA_ARCHIVE else list(INPUT.rglob('ai1-demo-data.zip'))
data_roots=[p.parent.parent for p in INPUT.rglob('ai1_profile_manifest.json')
            if p.parent.name=='processed' and (p.parent.parent/'embeddings/metadata.json').is_file()
            and json.loads(p.read_text()).get('usage')=='synthetic_demo']
if len(bundles)==1:
    stage=Path(tempfile.mkdtemp(prefix='demo-data-',dir='/kaggle/working'))
    safe_extract(bundles[0],stage)
    data_manifest=verify_manifest(stage,'dataset_manifest.json')
    assert data_manifest.get('usage')=='synthetic_demo'
    DATA_ROOT=stage
elif not bundles and len(data_roots)==1:
    DATA_ROOT=data_roots[0]
    if (DATA_ROOT/'dataset_manifest.json').is_file(): verify_manifest(DATA_ROOT,'dataset_manifest.json')
else:
    raise RuntimeError('Attach exactly one NEW ai1-demo-data.zip or extracted synthetic_demo Dataset; old source-backed data will not be used')
for folder in ('processed','embeddings'):
    shutil.copytree(DATA_ROOT/folder,PROJECT/'data'/folder,dirs_exist_ok=True)
assert json.loads((PROJECT/'data/processed/ai1_profile_manifest.json').read_text()).get('usage')=='synthetic_demo'
print('Project:',PROJECT,'Dataset:',DATA_ROOT)
''')
add('markdown','''
## 2. Cấu hình AI và Secrets
`ENABLE_QWEN=True` tải Qwen base và kiểm tra LoRA trên GPU.
Đổi False nếu muốn thử web bằng Gemini trước. Có thể tắt cả hai để thử form/rule offline;
chế độ đó không đại diện đầy đủ khả năng chat. Không ghi key trực tiếp vào cell.
''')
add('code','''
from kaggle_secrets import UserSecretsClient
import subprocess,time,hashlib,urllib.request,urllib.error,re
from scripts.kaggle_setup import checked as run_checked,redact
ENABLE_QWEN=True
ENABLE_GEMINI=True
CHECK_GEMINI=False  # True gọi API một lần; False để chat gọi khi bạn thử.
secrets=UserSecretsClient()
if ENABLE_GEMINI:
    os.environ['GEMINI_API_KEY']=secrets.get_secret('GEMINI_API_KEY')
    os.environ['GEMINI_MODEL']=secrets.get_secret('GEMINI_MODEL').strip()
    assert os.environ['GEMINI_MODEL'], 'GEMINI_MODEL must be your accessible model name'
os.environ.update(LLM_PROVIDER='gemini' if ENABLE_GEMINI else 'none',
    LOCAL_SLM_ENABLED=str(ENABLE_QWEN).lower(),LOCAL_SLM_BACKEND='qwen_lora',
    LOCAL_SLM_BASE_MODEL='Qwen/Qwen3-1.7B',
    LOCAL_SLM_ADAPTER_PATH=str(PROJECT/'models/ai2/ai2-qwen3-1.7b-lora-targeted-v3'),
    HF_HOME='/kaggle/working/tastly-hf',HF_HUB_OFFLINE='0',
    AI1_EMBEDDING_DEVICE='cpu',BACKEND_AI_TIMEOUT_S='300',BACKEND_AI_QUEUE_TIMEOUT_S='300',
    BACKEND_AI_CONCURRENCY='1',BACKEND_WARMUP='true',BACKEND_COOKIE_SECURE='true',
    BACKEND_URL='http://127.0.0.1:8000',NEXT_TELEMETRY_DISABLED='1',CONVERSATION_LOG_ENABLED='false')
LOGS=PROJECT/'kaggle-logs';LOGS.mkdir(exist_ok=True)
def checked(args,name,cwd=PROJECT,timeout=2400):
    return run_checked(args,name,PROJECT,LOGS,timeout,cwd)
print('Qwen:',ENABLE_QWEN,'Gemini:',ENABLE_GEMINI,'Logs:',LOGS)
''')
add('markdown','## 3. Cài đầy đủ môi trường Python, Node, PostgreSQL và frontend')
add('code','''
from scripts.kaggle_setup import install_runtime,configure_frontend
PYTHON,FRONTEND=install_runtime(PROJECT,LOGS,ENABLE_QWEN,ENABLE_GEMINI)
configure_frontend(FRONTEND)
print('Python:',PYTHON,'Frontend:',FRONTEND)
''')
add('markdown','''
## 4. Tải và kiểm tra model/data trước khi chạy server
MiniLM tải vào cache; Qwen base tải nếu bật Qwen, adapter và CatBoost lấy từ code ZIP.
Mục này kiểm tra encode thật, load Qwen NF4/LoRA trên GPU, hash/ID/mapping,
cuisine món–quán và số dòng từ metadata demo — không dùng số dòng dataset cũ.
''')
add('code','''
from scripts.kaggle_setup import download_models,validate_data
download_models(PROJECT,LOGS,PYTHON,ENABLE_QWEN)
validate_data(PROJECT,LOGS,PYTHON,expected_usage='synthetic_demo')
print(redact((LOGS/'artifact-validation.log').read_text()))
if ENABLE_GEMINI and CHECK_GEMINI:
    checked([str(PYTHON),'-c',"import os; from google import genai; r=genai.Client(api_key=os.environ['GEMINI_API_KEY']).models.generate_content(model=os.environ['GEMINI_MODEL'],contents='Reply with OK'); print(r.text)"],'gemini-check',timeout=120)
    print(redact((LOGS/'gemini-check.log').read_text()))
''')
add('markdown','## 5. Tạo database theo phiên bản dataset và seed đủ dữ liệu')
add('code','''
from scripts.kaggle_setup import setup_database
setup_database(PROJECT,LOGS,PYTHON)
''')
add('markdown','## 6. Định nghĩa process manager rồi chạy backend và frontend')
add('code','''
def stop(name):
    process=SERVERS.get(name)
    if process and process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
def launch(name,args,cwd):
    stop(name)
    with (LOGS/(name+'.log')).open('w') as log:
        SERVERS[name]=subprocess.Popen(args,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
def wait_http(name,url,timeout=360):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if SERVERS[name].poll() is not None: break
        try:
            with urllib.request.urlopen(url,timeout=10) as response:
                if response.status==200: print(name,'ready');return
        except (OSError,urllib.error.URLError): time.sleep(2)
    print(redact((LOGS/(name+'.log')).read_text(errors='replace')[-12000:]))
    raise RuntimeError(name+' failed; check logs')
launch('backend',[str(PYTHON),'-m','uvicorn','backend.main:create_production_app','--factory','--host','127.0.0.1','--port','8000'],PROJECT)
wait_http('backend','http://127.0.0.1:8000/ready')
FRONTEND_ARGS=['node',str(FRONTEND/'node_modules/next/dist/bin/next'),'dev','--webpack','--hostname','127.0.0.1','--port','3000']
launch('frontend',FRONTEND_ARGS,FRONTEND)
wait_http('frontend','http://127.0.0.1:3000')
''')
add('markdown','## 7. Kiểm tra tìm món qua frontend → backend → database trước khi mở web')
add('code','''
import http.cookiejar
def search_probe(opener,base,food):
    headers={'Content-Type':'application/json','ngrok-skip-browser-warning':'true'}
    request=urllib.request.Request(base+'/api/search',data=json.dumps({'form':{'food':food},'top_k':3}).encode(),headers=headers,method='POST')
    try:
        with opener.open(request,timeout=360) as response: payload=json.load(response)
    except urllib.error.HTTPError as exc:
        print(redact(exc.read().decode(errors='replace')[:5000]));raise
    assert payload['results'], 'No results: '+food
    for result in payload['results']: print(result['restaurant_name'],result['dish_name'],result['price_vnd'])
    return payload
browser=urllib.request.build_opener()
search_probe(browser,'http://127.0.0.1:3000','phở')
search_probe(browser,'http://127.0.0.1:3000','sushi')
print('Local web/API/data pipeline OK; HTTPS session cookie is tested next')
''')
add('markdown','''
## 8. Mở ngrok, cập nhật origin rồi kiểm tra HTTPS/session
Secret `NGROK_AUTHTOKEN` lấy từ dashboard ngrok. Link chỉ sống trong phiên Kaggle.
Notebook chỉ đưa frontend port 3000 lên Internet.
''')
add('code',r'''
os.environ['NGROK_AUTHTOKEN']=secrets.get_secret('NGROK_AUTHTOKEN')
tunnel_script=PROJECT/'kaggle_tunnel.py'
tunnel_script.write_text(chr(10).join(['import ngrok,time', "listener=ngrok.forward('127.0.0.1:3000',authtoken_from_env=True)", 'print(listener.url(),flush=True)', 'while True: time.sleep(30)'])+chr(10))
launch('tunnel',[str(PYTHON),str(tunnel_script)],PROJECT)
deadline=time.monotonic()+60;PUBLIC_URL=None
while time.monotonic()<deadline:
    text=(LOGS/'tunnel.log').read_text(errors='replace')
    urls=re.findall(r'(?m)^(https://[a-zA-Z0-9.-]+)/?$',text)
    if urls: PUBLIC_URL=urls[0];break
    if SERVERS['tunnel'].poll() is not None: break
    time.sleep(1)
if not PUBLIC_URL: raise RuntimeError('Tunnel failed; check token and tunnel.log')
from urllib.parse import urlparse
configure_frontend(FRONTEND,urlparse(PUBLIC_URL).hostname)
launch('frontend',FRONTEND_ARGS,FRONTEND)
wait_http('frontend','http://127.0.0.1:3000')
https_browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
first=search_probe(https_browser,PUBLIC_URL,'phở')
second=search_probe(https_browser,PUBLIC_URL,'phở')
assert first['session_id']==second['session_id'],'Secure session cookie failed'
reset=urllib.request.Request(PUBLIC_URL+'/api/session',headers={'ngrok-skip-browser-warning':'true'},method='DELETE')
with https_browser.open(reset,timeout=60) as response: assert response.status==204
third=search_probe(https_browser,PUBLIC_URL,'sushi')
assert not third['state']['food'] or 'phở' not in third['state']['food'],'Session reset failed'
from IPython.display import display,Markdown
display(Markdown(f'**Mở Tastly:** [{PUBLIC_URL}]({PUBLIC_URL})'))
print('HTTPS search, session cookie and reset OK')
''')
add('markdown','## 9. Xem log khi cần')
add('code',"for name in ('backend','frontend','tunnel'):\n    file=LOGS/(name+'.log')\n    if file.exists(): print(name,redact(file.read_text(errors='replace')[-8000:]))")
add('markdown','## 10. Dừng sau khi thử — không chạy mục này ngay khi vừa mở web')
add('code',"STOP_SERVERS=False  # Chuyển True và chạy lại cell này khi thử xong.\nif STOP_SERVERS:\n    for name in list(SERVERS):\n        stop(name)\n        print(name,'stopped')\nelse:\n    print('Web tiếp tục chạy. Đặt STOP_SERVERS=True để dừng.')")
notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}},'cells':cells}
for name in ('mlai-runner.ipynb','mlai-fullstack-web-kaggle.ipynb'):
    path=HERE/name;path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8');print(path)
