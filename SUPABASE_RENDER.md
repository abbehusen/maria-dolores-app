# Supabase + Render

O aplicativo usa SQLite por padrão. Quando a variável de ambiente `DATABASE_URL` existe, ele usa PostgreSQL (por exemplo, Supabase) automaticamente.

## 1. Conexão

No Supabase, copie uma connection string PostgreSQL compatível com conexões de servidor. Não versione a senha no GitHub.

No Render, crie a variável de ambiente:

- `DATABASE_URL` = connection string do Supabase

O `main.py` detecta a variável e não usa restauração/lock do SQLite.

## 2. Migrar o banco local

No computador que contém `data/flow.sqlite3`:

```powershell
$env:DATABASE_URL="postgresql://..."
pip install -r requirements.txt
python scripts/migrate_sqlite_to_postgres.py data/flow.sqlite3
```

O importador recusa um destino já preenchido. `--force` apaga os dados Flow do destino e deve ser usado somente de forma deliberada.

## 3. Deploy

Render:

- Build command: `pip install -r requirements.txt`
- Start command: `python main.py --no-open`

Após adicionar `DATABASE_URL`, faça novo deploy/restart. O schema PostgreSQL v8 é criado automaticamente se ainda não existir.

## 4. Backups

- SQLite local: backup/restauração `.sqlite3` continua igual.
- PostgreSQL online: o botão de backup gera snapshot JSON, incluindo XML de NF-e em base64. A restauração `.sqlite3` fica desabilitada na interface online para evitar substituir um banco remoto por engano.
- O Supabase deve continuar sendo a fonte persistente de dados do ambiente online.
