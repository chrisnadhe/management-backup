"""
Script migrasi untuk mengenkripsi credential yang sudah ada di database.
Jalankan SATU KALI setelah menambahkan SECRET_KEY ke .env

Usage:
    python scripts/migrate_credentials.py
"""
import sys
import os

# Tambah root project ke path agar bisa import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from app.database import engine
from app.models import Credential
from app.security import encrypt_password, is_encrypted


def migrate():
    print("=" * 60)
    print("Migrasi Enkripsi Credential")
    print("=" * 60)

    with Session(engine) as session:
        credentials = session.exec(select(Credential)).all()

        if not credentials:
            print("Tidak ada credential ditemukan di database.")
            return

        migrated = 0
        skipped = 0

        for cred in credentials:
            changed = False

            # Enkripsi password jika belum terenkripsi
            if cred.password and not is_encrypted(cred.password):
                cred.password = encrypt_password(cred.password)
                changed = True

            # Enkripsi secret jika ada dan belum terenkripsi
            if cred.secret and not is_encrypted(cred.secret):
                cred.secret = encrypt_password(cred.secret)
                changed = True

            if changed:
                session.add(cred)
                migrated += 1
                print(f"  [OK] Migrated: {cred.name}")
            else:
                skipped += 1
                print(f"  [--] Skipped (sudah terenkripsi): {cred.name}")

        session.commit()

    print()
    print(f"Selesai! Migrated: {migrated}, Skipped: {skipped}")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
