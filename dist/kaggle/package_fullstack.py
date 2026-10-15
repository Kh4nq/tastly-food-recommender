"""Build a code/model Dataset bundle, without private runtime data."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
GIT = ['git', '-c', f'safe.directory={ROOT.as_posix()}']
OUT = ROOT / 'dist/kaggle/mlai-fullstack-code.zip'
tracked = subprocess.check_output([*GIT, 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
allowed = ('src/', 'scripts/', 'database/', 'docs/', 'tests/')
top = {'pyproject.toml', 'README.md', 'CONTRIBUTING.md', 'AGENTS.md', 'compose.yaml'}
files = {p for p in tracked if p.startswith(allowed) or p in top}
files.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'models').rglob('*') if p.is_file())
files = sorted(p for p in files if not any(part in {'__pycache__', 'node_modules', '.next', '.git', '.venv'} or part.startswith('.env') for part in Path(p).parts) and not p.endswith(('.pyc', '.gitkeep')))
for name in files:
    path = ROOT / name
    if path.is_symlink():
        raise ValueError(f'Symlink not allowed: {name}')
    if path.read_bytes()[:80].startswith(b'version https://git-lfs.github.com/spec/v1'):
        raise ValueError(f'Unresolved LFS pointer: {name}')
manifest = {
    'commit': subprocess.check_output([*GIT, 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'branch': subprocess.check_output([*GIT, 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
    'working_tree_modified': bool(subprocess.check_output([*GIT, 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
    'sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files},
    'excluded': ['data/', '.env files', 'credentials', 'build caches', 'sealed benchmarks'],
}
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as bundle:
    for name in files:
        bundle.write(ROOT / name, name)
    bundle.writestr('kaggle_manifest.json', json.dumps(manifest, indent=2))
with zipfile.ZipFile(OUT) as bundle:
    assert bundle.testzip() is None
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256(bundle.read(name)).hexdigest() == digest, name
print(f'{OUT}\n{len(files)} files; {OUT.stat().st_size / 1024**2:.1f} MiB; commit {manifest["commit"]}')
