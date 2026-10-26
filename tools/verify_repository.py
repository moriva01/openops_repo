"""Check local documentation links, Python syntax and private-file boundaries."""
import ast
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
errors = []
files = [p for p in root.rglob('*') if p.is_file() and not any(part in ('.git','__pycache__','dist') for part in p.relative_to(root).parts)]
for path in files:
    relative = path.relative_to(root)
    if path.name == '.env' or '.local' in relative.parts or path.suffix in ('.sqlite3','.key','.pem'):
        errors.append('Private/runtime file in repository: ' + str(relative))
    if path.suffix == '.py':
        ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(relative))
    if path.suffix == '.md':
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8-sig')):
            target = target.strip('<>').split('#',1)[0]
            if not target or '://' in target or target.startswith('mailto:'):
                continue
            if not (path.parent / target).exists():
                errors.append('Missing documentation target: ' + str(relative) + ' -> ' + target)
if errors:
    raise SystemExit('\n'.join(errors))
print('PASS: Python syntax, Markdown local links and private-file boundaries; files checked:',len(files))
