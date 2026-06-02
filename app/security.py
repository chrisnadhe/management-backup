"""
Modul keamanan untuk enkripsi/dekripsi credential.
Menggunakan Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Key disimpan di .env, TIDAK di database.
"""
from cryptography.fernet import Fernet
from app.config import settings

_fernet = Fernet(settings.secret_key.encode())


def encrypt_password(plain_text: str) -> str:
    """Enkripsi string plaintext, kembalikan string terenkripsi."""
    if not plain_text:
        return plain_text
    return _fernet.encrypt(plain_text.encode()).decode()


def decrypt_password(encrypted_text: str) -> str:
    """Dekripsi string terenkripsi, kembalikan plaintext."""
    if not encrypted_text:
        return encrypted_text
    try:
        return _fernet.decrypt(encrypted_text.encode()).decode()
    except Exception:
        # Jika gagal decrypt (misal: data lama yang belum terenkripsi),
        # kembalikan nilai aslinya agar tidak break koneksi yang sudah ada.
        return encrypted_text


def is_encrypted(value: str) -> bool:
    """Cek apakah string sudah terenkripsi (digunakan untuk migrasi)."""
    try:
        _fernet.decrypt(value.encode())
        return True
    except Exception:
        return False
