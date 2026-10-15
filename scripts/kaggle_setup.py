"""Explicit Kaggle fullstack setup helpers. Importing does no I/O or downloads."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile


def redact(text):
    for key in ('GEMINI_API_KEY', 'NGROK_AUTHTOKEN', 'HF_TOKEN', 'PGPASSWORD', 'DATABASE_URL'):
        value = os.environ.get(key)
        if value:
            text = text.replace(value, '[redacted]')
    return text


def checked(args, name, project, logs, timeout=2400, cwd=None):
    log = Path(logs) / (name + '.log')
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run([str(a) for a in args], cwd=cwd or project,
                                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        print(redact(log.read_text(errors='replace')[-10000:]))
        raise RuntimeError(f'{name} failed; inspect {log}')
    print(name, 'OK')


def safe_extract(archive, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as bundle:
        seen = set()
        for item in bundle.infolist():
            name = PurePosixPath(item.filename)
            target = (destination / item.filename).resolve()
            if (name.is_absolute() or '..' in name.parts or chr(92) in item.filename
                    or not target.is_relative_to(destination)
                    or stat.S_ISLNK(item.external_attr >> 16) or item.filename in seen):
                raise ValueError('Unsafe or duplicate ZIP entry')
            seen.add(item.filename)
        bundle.extractall(destination)


def verify_manifest(root, filename, key='sha256'):
    root = Path(root).resolve()
    manifest = json.loads((root / filename).read_text(encoding='utf-8'))
    hashes = manifest.get(key)
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError(f'Missing file hashes in {filename}')
    for name, expected in hashes.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Missing/invalid packaged file: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Package checksum mismatch: {name}')
    return manifest


def install_runtime(project, logs, enable_qwen=False, enable_gemini=True):
    project, logs = Path(project), Path(logs)
    venv = Path('/kaggle/working/tastly-venv')
    python = venv / 'bin/python'
    if not python.is_file():
        # Keep Kaggle's working CUDA torch; bypass its sometimes broken ensurepip.
        checked([sys.executable, '-m', 'venv', '--system-site-packages', '--without-pip', venv],
                'create-venv', project, logs)
    checked([sys.executable, '-m', 'pip', '--python', python, 'install', '--upgrade', 'pip'],
            'bootstrap-pip', project, logs)
    extras = 'ai1,ai3,db,backend' + (',gemini' if enable_gemini else '') + (',slm' if enable_qwen else '')
    checked([python, '-m', 'pip', 'install', '-e', f'.[{extras}]', 'ngrok', 'huggingface-hub'],
            'python-install', project, logs)
    checked([python, '-c', 'import numpy,pandas,pyarrow,sentence_transformers,catboost,psycopg,psycopg_pool,fastapi,uvicorn,httpx,ngrok; print("Required Python imports OK")'],
            'python-imports', project, logs)
    os.environ['PATH'] = os.environ.get('PATH', '') + ':/usr/bin:/usr/sbin:/bin:/sbin'
    required = ('pg_lsclusters', 'pg_ctlcluster', 'pg_createcluster', 'psql', 'runuser')
    if any(shutil.which(cmd) is None for cmd in required):
        checked(['apt-get', 'update', '-qq'], 'apt-update', project, logs)
        checked(['apt-get', 'install', '-y', 'postgresql', 'postgresql-client', 'postgresql-common'],
                'postgres-install', project, logs)
    if any(shutil.which(cmd) is None for cmd in required):
        raise RuntimeError('PostgreSQL tools missing after installation')
    # Official Node 22 release, with its published SHA256 checked before extraction.
    base = 'https://nodejs.org/download/release/latest-v22.x/'
    sums = urllib.request.urlopen(base + 'SHASUMS256.txt', timeout=60).read().decode()
    candidates = re.findall(r'^([0-9a-f]{64})\s+(node-v22[^ /]*-linux-x64.tar.xz)$', sums, re.M)
    if len(candidates) != 1:
        raise RuntimeError('Cannot identify official Node 22 Linux x64 release')
    digest, name = candidates[0]
    archive = Path('/kaggle/working') / name
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        urllib.request.urlretrieve(base + name, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError('Node archive checksum mismatch')
    node_root = archive.parent / name.removesuffix('.tar.xz')
    if not (node_root / 'bin/node').is_file():
        with tarfile.open(archive) as bundle:
            bundle.extractall(archive.parent, filter='data')
    os.environ['PATH'] = str(node_root / 'bin') + ':' + os.environ['PATH']
    checked(['node', '--version'], 'node-version', project, logs)
    frontend = project / 'src/frontend'
    checked(['npm', 'ci', '--no-audit', '--no-fund'], 'frontend-install', project, logs, cwd=frontend)
    if not (frontend / 'node_modules/next/dist/bin/next').is_file():
        raise RuntimeError('Next.js missing after npm ci')
    return python, frontend


def download_models(project, logs, python, enable_qwen=False):
    code = '''
import json, os
from pathlib import Path
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer
root=Path.cwd()
meta=json.loads((root/'data/embeddings/metadata.json').read_text())
encoder=meta['model']
path=snapshot_download(encoder, ignore_patterns=['*.onnx','*.h5','*.msgpack','*.ot','onnx/*','openvino/*'])
model=SentenceTransformer(path,device='cpu',local_files_only=True)
v=model.encode(['model readiness'],normalize_embeddings=True,convert_to_numpy=True)
assert v.shape[1]==meta['dishes']['dimension']
print('MiniLM downloaded and encode validated')
if os.environ.get('LOCAL_SLM_ENABLED')=='true':
    import torch
    assert torch.cuda.is_available(), 'Enable GPU or set ENABLE_QWEN=False'
    adapter=root/'models/ai2/ai2-qwen3-1.7b-lora-targeted-v3'
    assert (adapter/'adapter_config.json').is_file()
    assert (adapter/'adapter_model.safetensors').is_file()
    assert (adapter/'tokenizer_config.json').is_file()
    base=snapshot_download(os.environ['LOCAL_SLM_BASE_MODEL'],ignore_patterns=['*.gguf','*.onnx','*.h5','*.msgpack','*.ot'])
    os.environ['LOCAL_SLM_BASE_MODEL']=base
    from conversation.slm.qwen_lora import QwenLoRAProvider
    provider=QwenLoRAProvider(base, str(adapter))
    provider._load()
    print('Qwen NF4 base + LoRA GPU load validated:', provider.load_summary)
'''
    checked([python, '-c', code], 'model-download', project, logs, timeout=3600)
    os.environ['HF_HUB_OFFLINE'] = '1'


def validate_data(project, logs, python, expected_usage='synthetic_demo'):
    code = '''
import json, os
from pathlib import Path
from retrieval.retriever import Retriever
from ranking.model_ranker import CatBoostYetiRanker
root=Path.cwd()
engine=Retriever(root/'data/processed',root/'data/embeddings')
usage=engine.metadata.get('usage','source_backed')
assert usage==os.environ['EXPECTED_DATA_USAGE'], 'Wrong Dataset: attach the new ai1-demo-data package'
actual={'restaurants':len(engine.restaurants),'dishes':len(engine.dishes),'menus':len(engine.menus)}
assert actual['restaurants']==engine.metadata['restaurants']['rows']
assert actual['dishes']==engine.metadata['dishes']['rows']
assert actual['menus']==engine.metadata['menu_mapping']['rows']==len(engine.menu_map)
if usage=='synthetic_demo':
    card=json.loads((root/'data/processed/ai1_dataset_card.json').read_text())
    assert all(card[k]==v for k,v in actual.items()), 'Dataset card counts disagree'
    dishes=engine.dishes.set_index('dish_id')
    assigned=engine.menus.dish_id.map(dishes.demo_menu_cuisine)
    scenario=engine.menus.food_place_id.map(engine.restaurants.set_index('food_place_id').demo_menu_cuisine)
    assert assigned.eq(scenario).all(), 'Dish/restaurant cuisine mismatch'
CatBoostYetiRanker.from_file(root/'models/ranker/catboost_yetirank.cbm')
print('Data/profile/hash/ID/menu/cuisine/CatBoost validated:', actual, usage)
'''
    os.environ['EXPECTED_DATA_USAGE'] = expected_usage
    checked([python, '-c', code], 'artifact-validation', project, logs)


def configure_frontend(frontend, public_host=None):
    path = Path(frontend) / 'next.config.ts'
    text = path.read_text(encoding='utf-8')
    origins = [public_host] if public_host else ['*.ngrok-free.app', '*.ngrok-free.dev', '*.ngrok.app', '*.ngrok.dev', '*.ngrok.io']
    setting = 'allowedDevOrigins: ' + json.dumps(origins) + ','
    if 'allowedDevOrigins:' in text:
        text = re.sub(r'allowedDevOrigins\s*:\s*\[[^\]]*\]\s*,?', setting, text, count=1)
    else:
        marker = 'const nextConfig: NextConfig = {'
        if marker not in text:
            raise ValueError('Unknown Next config layout')
        text = text.replace(marker, marker + '\n  ' + setting, 1)
    if re.search(r'\bproxyTimeout\s*:', text):
        text = re.sub(r'\bproxyTimeout\s*:\s*\d+', 'proxyTimeout: 360000', text)
    elif re.search(r'\bexperimental\s*:\s*\{', text):
        text = re.sub(r'\bexperimental\s*:\s*\{', 'experimental: { proxyTimeout: 360000,', text, count=1)
    else:
        text = text.replace('const nextConfig: NextConfig = {', 'const nextConfig: NextConfig = {\n  experimental: { proxyTimeout: 360000 },', 1)
    path.write_text(text, encoding='utf-8')


def setup_database(project, logs, python):
    import secrets
    project = Path(project)
    lines = subprocess.check_output(['pg_lsclusters', '--no-header'], text=True).splitlines()
    if not lines:
        versions = sorted(Path('/usr/lib/postgresql').glob('*/bin/postgres'), key=lambda p: int(p.parents[1].name))
        if not versions:
            raise RuntimeError('PostgreSQL server missing')
        checked(['pg_createcluster', versions[-1].parents[1].name, 'main', '--start'], 'postgres-create', project, logs)
        lines = subprocess.check_output(['pg_lsclusters', '--no-header'], text=True).splitlines()
    if len(lines) != 1:
        raise RuntimeError('Expected one PostgreSQL cluster')
    version, cluster, port, status = lines[0].split()[:4]
    if status != 'online':
        checked(['pg_ctlcluster', version, cluster, 'start'], 'postgres-start', project, logs)
    # A new dataset gets its own database, so --if-empty cannot reuse stale menus.
    digest = hashlib.sha256((project / 'data/embeddings/metadata.json').read_bytes()).hexdigest()[:12]
    database = 'tastly_' + digest
    password = secrets.token_hex(24)
    sql = "SELECT 'CREATE ROLE tastly LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='tastly')\\gexec\n"
    sql += f"ALTER ROLE tastly WITH PASSWORD '{password}';\n"
    sql += f"SELECT 'CREATE DATABASE {database} OWNER tastly' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='{database}')\\gexec\n"
    result = subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-v', 'ON_ERROR_STOP=1'], input=sql, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Local database creation failed (credentials suppressed)')
    os.environ.update(DATABASE_URL=f'postgresql://tastly:{password}@127.0.0.1:{port}/{database}',
                      PGHOST='127.0.0.1', PGPORT=port, PGUSER='tastly', PGPASSWORD=password, PGDATABASE=database)
    for name in ('schema.sql', 'indexes.sql', 'procedures.sql'):
        checked(['psql', '-v', 'ON_ERROR_STOP=1', '-f', project / 'database' / name], 'db-' + name, project, logs)
    checked([python, 'scripts/seed_database.py', '--if-empty'], 'database-seed', project, logs)
    checked([python, '-c', '''
import os,json,psycopg
from pathlib import Path
card=json.loads(Path('data/processed/ai1_dataset_card.json').read_text())
with psycopg.connect(os.environ['DATABASE_URL']) as c:
    for table,key in [('restaurants','restaurants'),('dishes','dishes'),('menu_items','menus')]:
        count=c.execute('SELECT count(*) FROM '+table).fetchone()[0]
        assert count==card[key], 'Database count mismatch: '+table
        print(table,count)
'''], 'database-counts', project, logs)
    print('PostgreSQL seeded and counts checked:', database)
