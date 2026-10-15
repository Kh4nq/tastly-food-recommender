"""Run this file's contents in a Kaggle cell immediately before section 5."""
import re
from scripts.kaggle_setup import setup_database

schema_path = PROJECT / 'database/schema.sql'
sql = schema_path.read_text(encoding='utf-8')
nutrients = ('fat', 'fiber', 'sugar', 'protein')
for name in nutrients:
    sql = re.sub(rf'\b{name}\s+INTEGER\s+NOT NULL\b',
                 f'{name} DOUBLE PRECISION', sql)
if 'ALTER COLUMN fat DROP NOT NULL' not in sql:
    changes = []
    for name in nutrients:
        changes += [
            f'ALTER COLUMN {name} TYPE DOUBLE PRECISION USING {name}::double precision',
            f'ALTER COLUMN {name} DROP NOT NULL',
        ]
    migration = 'ALTER TABLE dishes\n    ' + ',\n    '.join(changes) + ';\n'
    assert sql.count('COMMIT;') == 1, 'Unexpected schema transaction layout'
    sql = sql.replace('COMMIT;', migration + '\nCOMMIT;')
schema_path.write_text(sql, encoding='utf-8')
setup_database(PROJECT, LOGS, PYTHON)
