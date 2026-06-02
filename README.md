# Network Backup Manager

Aplikasi manajemen backup konfigurasi perangkat jaringan berbasis web, dibangun dengan **FastAPI**, **HTMX**, dan **Netmiko**.

## Fitur

| Fitur | Keterangan |
|-------|------------|
| **Device Management** | Tambah/Edit/Hapus perangkat jaringan (Cisco, MikroTik, Juniper, Arista, dll.) dengan import massal via CSV |
| **Credential Management** | Manajemen SSH credential terenkripsi (Fernet AES-128) |
| **Command Templates** | Definisikan command backup per platform (misal `show running-config`) |
| **Automated Backup** | Jadwalkan backup otomatis menggunakan cron expression |
| **Manual Backup** | Trigger backup on-demand per device maupun per group |
| **Config Push** | Push konfigurasi ke device/group secara paralel, dengan opsi penjadwalan |
| **Backup History** | Lihat log, preview output, dan download file backup |
| **Group Download** | Download backup seluruh group sebagai file ZIP |
| **Dashboard** | Ringkasan status sistem dan aktivitas terbaru |

## Prasyarat

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (package manager)

## Instalasi

### 1. Clone repository

```bash
git clone https://github.com/chrisnadhe/management-backup.git
cd management-backup
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Setup environment

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

Buka `.env` dan isi `SECRET_KEY` dengan Fernet key yang baru digenerate:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> ⚠️ **Penting:** Jangan ubah `SECRET_KEY` setelah credential sudah tersimpan di database. Jika key hilang, semua credential tidak bisa didekripsi.

## Menjalankan Aplikasi

```bash
uv run uvicorn app.main:app --reload
```

Buka browser di: [http://localhost:8000](http://localhost:8000)

## Inisialisasi Pertama Kali

Saat aplikasi pertama kali dijalankan:

- **Database SQLite** (`network_backup.db`) dibuat otomatis di root project
- **Folder `backups/`** dibuat otomatis saat backup pertama dieksekusi

Tidak ada setup database manual yang diperlukan.

## Cara Penggunaan

1. **Credentials** → Tambahkan SSH credential (username/password/enable secret)
2. **Commands** → Definisikan command backup sesuai platform device
3. **Devices** → Daftarkan perangkat jaringan, assign credential dan group
4. **Backups** → Jalankan backup manual atau buat jadwal otomatis
5. **Push Config** → Push konfigurasi ke device/group

## Migrasi (Upgrade dari Versi Lama)

Jika Anda memiliki data credential yang tersimpan **plaintext** (sebelum enkripsi diterapkan), jalankan script migrasi **sekali**:

```bash
python scripts/migrate_credentials.py
```

Script ini akan mendeteksi dan mengenkripsi password yang belum terenkripsi secara otomatis.

## Struktur Project

```
management-backup/
├── app/
│   ├── config.py           # Konfigurasi via pydantic-settings (.env)
│   ├── database.py         # SQLite engine & session
│   ├── logging_config.py   # Setup Python logging
│   ├── main.py             # FastAPI app & lifespan
│   ├── models.py           # SQLModel table definitions
│   ├── security.py         # Fernet encrypt/decrypt credential
│   ├── templates.py        # Jinja2 templates setup
│   ├── routers/            # API route handlers
│   │   ├── backups.py
│   │   ├── commands.py
│   │   ├── credentials.py
│   │   ├── devices.py
│   │   ├── groups.py
│   │   ├── logs.py
│   │   ├── push.py
│   │   └── schedules.py
│   ├── services/           # Business logic
│   │   ├── base_service.py     # Shared network operation logic
│   │   ├── backup_service.py   # Backup via Netmiko
│   │   ├── push_service.py     # Config push via Netmiko
│   │   └── scheduler_service.py # APScheduler jobs
│   ├── static/             # CSS, JS, assets
│   └── templates/          # Jinja2 HTML templates
├── scripts/
│   └── migrate_credentials.py  # One-time migration script
├── backups/                # File backup & session log (auto-generated)
├── .env                    # Environment config (JANGAN commit!)
├── .env.example            # Template config untuk onboarding
└── pyproject.toml
```

## Stack Teknologi

- **Backend**: FastAPI, SQLModel, APScheduler
- **Network**: Netmiko
- **Frontend**: HTMX, Jinja2 Templates
- **Database**: SQLite
- **Security**: Cryptography (Fernet)
- **Config**: pydantic-settings

## License

MIT