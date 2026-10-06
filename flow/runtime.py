"""Diretórios persistentes e exclusão de segunda instância."""
import os
import sys
from pathlib import Path


def default_data_dir():
    if getattr(sys, 'frozen', False):
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'FeAbbehusenFlow' / 'data'
    return Path(__file__).resolve().parent.parent / 'data'


def lock_instance(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / 'app.lock').open('a+b')
    handle.seek(0)
    handle.write(b'0')
    handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('O app já está aberto usando esta pasta de dados. Feche a outra instância primeiro.')
    return handle
