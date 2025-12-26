# QR Yoklama (Pro) — Dynamic QR + WebSocket + Neon + Render

Bu repo; ders/seminer/eğitim gibi ortamlarda **dinamik QR anahtarı** (link paylaşımını pratikte bitiren) ve **canlı hoca paneli** (WebSocket) ile çalışan, **Neon PostgreSQL + Render** uyumlu yoklama sistemidir.

## Özellikler
- ✅ **Dinamik QR anahtarı (k):** kısa süreli anahtar; link paylaşımına dayanıklı
- ✅ **Tek cihaz – tek öğrenci kuralı:** aynı device_id ile aynı oturumda farklı öğrenci check-in yapamaz
- ✅ **Gerçek zamanlı hoca paneli:** WebSocket ile tablo otomatik güncellenir
- ✅ Oturum süresi, manuel kapama, geç kalma kuralı
- ✅ Oturum bazlı rapor + **CSV export**
- ✅ Ders bazlı özet istatistik (Stats)
- ✅ UTC veritabanı + **Europe/Istanbul gösterim**
- ✅ Render deploy + Neon DB uyumlu

## Tech Stack
- FastAPI + Jinja2 templates
- WebSocket (FastAPI)
- PostgreSQL (Neon)
- SQLAlchemy 2.x (async) + Alembic
- JWT (HttpOnly cookie) auth
- qrcode (QR görseli üretimi)

## Kurulum (Local)
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# mac/linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

# DB migrations
alembic upgrade head

# Seed kullanıcılar
python -m app.scripts.seed

# Run
uvicorn app.main:app --reload
```

Uygulama: http://127.0.0.1:8000

## Varsayılan kullanıcılar (seed)
- Teacher: `teacher1` / `Teacher123!`
- Student: `student1` / `Student123!`
- Student: `student2` / `Student123!`

> Prod ortamda seed kullanma. Şifreleri değiştir, yeni kullanıcıları panelden ekle (geliştirilebilir) veya kendi script'inle oluştur.

## Render Deploy (Özet)
1) Neon'da Postgres oluştur, connection string al: `postgresql://...`
2) Render'da repo'yu bağla (Web Service)
3) Render env vars:
- `DATABASE_URL` = Neon connection string
- `SECRET_KEY` = uzun random (en az 32 char)
- `APP_BASE_URL` = Render URL (örn. https://xxx.onrender.com)
- `TZ` = Europe/Istanbul
- `MIGRATE_ON_START` = `1` (ilk deploy için önerilir)
4) Deploy sonrası MIGRATE_ON_START'ı kapatabilirsin (0)

Detaylar aşağıda.

## Önemli Notlar
- DB'de timestamp'ler UTC tutulur, ekranda Istanbul saatine çevrilir.
- QR anahtar süresi varsayılan 20 sn (ENV ile değişir).
- Oturum kodu ve anahtarlar kriptografik random üretilir.

---
