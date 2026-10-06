"""Execute com: python main.py. Acesse pelo navegador."""

import argparse
import logging
import multiprocessing
import os
import sys
from pathlib import Path

from nicegui import ui

from flow.db import Database
from flow.runtime import default_data_dir, lock_instance
from flow.backup_restore import apply_pending_restore
from flow.service import Business
from flow.ui import register_pages


def main():
    parser = argparse.ArgumentParser(
        description='Fe Abbehusen Flow · gestão em Python'
    )

    parser.add_argument(
        '--demo',
        action='store_true',
        help='Usa uma base separada com dados fictícios'
    )

    parser.add_argument(
        '--data-dir',
        type=Path,
        default=default_data_dir()
    )

    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('PORT', 8080))
    )

    parser.add_argument(
        '--no-open',
        action='store_true',
        help='Não abre o navegador automaticamente'
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s'
    )

    instance_lock = lock_instance(args.data_dir)

    db_path = args.data_dir / (
        'demonstracao.sqlite3'
        if args.demo
        else 'flow.sqlite3'
    )

    apply_pending_restore(db_path)

    db = Database(db_path)
    business = Business(db)

    if args.demo:
        from flow.demo import seed
        seed(business)

    register_pages(
        business,
        demo=args.demo
    )

    ui.run(
        host='0.0.0.0',
        port=args.port,
        title='Fe Abbehusen Flow',
        favicon='💎',
        reload=False,
        show=not args.no_open,
        language='pt-BR'
    )


if __name__ in {'__main__', '__mp_main__'}:
    multiprocessing.freeze_support()

    try:
        main()

    except Exception:
        logging.exception(
            'Não foi possível iniciar o Fe Abbehusen Flow.'
        )

        if getattr(sys, 'frozen', False):
            input('Pressione Enter para fechar...')

        raise
