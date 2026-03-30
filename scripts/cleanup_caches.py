#!/usr/bin/env python3
"""Eliminar caches locales seguros: __pycache__, *.pyc, .DS_Store.
No toca bases de datos ni node_modules ni .venv.
Ejecutar desde la raíz del proyecto:
  python scripts/cleanup_caches.py
"""
import os
import shutil

root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
removed = 0
for dirpath, dirnames, filenames in os.walk(root):
    # evitar borrar dentro de .git o .venv o backend/db
    if '.git' in dirpath.split(os.sep) or '.venv' in dirpath.split(os.sep):
        continue

    if '__pycache__' in dirnames:
        p = os.path.join(dirpath, '__pycache__')
        try:
            shutil.rmtree(p)
            print('Removed', p)
            removed += 1
        except Exception as e:
            print('Failed to remove', p, e)

    for f in list(filenames):
        if f.endswith('.pyc') or f == '.DS_Store':
            p = os.path.join(dirpath, f)
            try:
                os.remove(p)
                print('Removed', p)
                removed += 1
            except Exception as e:
                print('Failed to remove', p, e)

print('Total removed items:', removed)
