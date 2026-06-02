# Network Backup Manager

Aplikasi manajemen backup konfigurasi perangkat jaringan berbasis web, dibangun dengan **FastAPI**, **HTMX**, dan **Netmiko**.

## Fitur Utama

| Fitur | Keterangan |
|-------|------------|
| **Device Management** | Tambah/Edit/Hapus perangkat jaringan (Cisco, MikroTik, Juniper, Arista, dll.) dengan import massal via CSV |
| **Credential Management** | Manajemen SSH credential terenkripsi (Fernet AES-128) |
| **Command Templates** | Definisikan command backup per platform (misal `show running-config`) |
| **Automated Backup** | Jadwalkan backup otomatis menggunakan cron expression |
| **Manual & Bulk Backup** | Trigger backup on-demand per device, multi-select (bulk), maupun per group |
| **Config Push** | Push konfigurasi ke device/group secara paralel, dengan opsi penjadwalan. Dilengkapi dengan **Confirmation Modal** untuk keamanan eksekusi. |
| **Backup History & Viewer** | Lihat log, preview syntax-highlighted output, dan download file backup |
| **Backup Diff Viewer** | Bandingkan perbedaan dua versi file backup secara *side-by-side* (highlight insert, delete, replace) |
| **Group Download** | Download backup seluruh group sebagai file ZIP |
| **Device Test Connection** | Uji koneksi SSH ke device (deteksi online, offline, atau auth error) secara realtime |
| **Backup Retention** | Pembersihan backup lama otomatis dengan konfigurasi berbasis umur (hari) dan/atau jumlah (N terbaru) |
| **User Management (RBAC)** | Autentikasi aman berbasis sesi dengan role `admin` (akses penuh) dan `user` (read-only untuk device/credential/user) |
| **Settings Dashboard** | Ringkasan dan kontrol konfigurasi aplikasi, termasuk performa Netmiko dan Threading |

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

Buka `.env` dan konfigurasikan `SECRET_KEY` serta `SESSION_SECRET_KEY`:

```bash
# Generate Fernet key (untuk enkripsi password SSH):
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate Session key (untuk cookie autentikasi):
python -c "import secrets; print(secrets.token_hex(32))"
```

> ⚠️ **Penting:** Jangan ubah `SECRET_KEY` setelah credential sudah tersimpan di database. Jika key hilang, semua credential tidak bisa didekripsi.

## Menjalankan Aplikasi

```bash
uv run uvicorn app.main:app --reload
```

Buka browser di: [http://localhost:8000](http://localhost:8000)

## Inisialisasi Pertama Kali (First Run)

Saat aplikasi pertama kali dijalankan:

1. **Database SQLite** (`network_backup.db`) dibuat otomatis di root project dengan mode `WAL` untuk performa *concurrent*.
2. Anda akan otomatis diarahkan ke halaman `/setup` untuk membuat **Akun Administrator** pertama.
3. Setelah setup selesai, login dengan akun yang dibuat.
4. **Folder `backups/`** dibuat otomatis saat backup pertama dieksekusi.

Tidak ada setup database manual yang diperlukan.

## Cara Penggunaan

1. **Credentials** → Tambahkan SSH credential (username/password/enable secret)
2. **Commands** → Definisikan command backup sesuai platform device
3. **Devices** → Daftarkan perangkat jaringan, assign credential dan group. Gunakan fitur *Test Connection* untuk memvalidasi.
4. **Backups** → Jalankan backup manual (single/bulk) atau buat jadwal otomatis. Anda bisa membandingkan hasilnya dengan *Diff Viewer*.
5. **Push Config** → Push konfigurasi ke device/group. Selalu tinjau *preview* sebelum mengetik konfirmasi.
6. **Users (Admin Only)** → Kelola akun akses dan berikan *role* yang sesuai.

## Migrasi (Upgrade dari Versi Lama)

Jika Anda memiliki data credential yang tersimpan **plaintext** (sebelum enkripsi diterapkan), jalankan script migrasi **sekali**:

```bash
python scripts/migrate_credentials.py
```

## Struktur Project

```
management-backup/
├── app/
│   ├── config.py           # Konfigurasi via pydantic-settings (.env)
│   ├── database.py         # SQLite engine (WAL mode) & session
│   ├── auth.py             # Session cookie auth, bcrypt hashing
│   ├── models.py           # SQLModel table definitions (Device, User, dll)
│   ├── security.py         # Fernet encrypt/decrypt credential
│   ├── main.py             # FastAPI app, middleware auth, & lifespan
│   ├── routers/            # API route handlers
│   │   ├── auth.py, users.py, settings.py
│   │   ├── backups.py, push.py, devices.py, ...
│   ├── services/           # Business logic
│   │   ├── backup_service.py      # Backup via Netmiko
│   │   ├── push_service.py        # Config push via Netmiko
│   │   ├── scheduler_service.py   # APScheduler (Non-blocking ThreadPool)
│   │   ├── retention_service.py   # Pembersihan backup usang
│   │   └── connectivity_service.py# Uji koneksi SSH
│   ├── static/             # CSS, JS, assets
│   └── templates/          # Jinja2 HTML templates
├── scripts/
│   └── migrate_credentials.py
├── backups/                # Folder penyimpanan file backup & log
├── .env                    # Environment config (JANGAN commit!)
├── .env.example            # Template config
└── pyproject.toml
```

## Stack Teknologi

- **Backend**: FastAPI, SQLModel, APScheduler, Passlib (bcrypt), itsdangerous
- **Network**: Netmiko
- **Frontend**: HTMX, Jinja2 Templates, Tailwind CSS (Glassmorphism UI)
- **Database**: SQLite (WAL Mode)
- **Security**: Cryptography (Fernet)

## License

MIT