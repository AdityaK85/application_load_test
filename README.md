# CCTV Alerts API (Django + DRF + JWT + ASGI)

## Setup
```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

## Run (ASGI)
```bash
uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --reload
```
(Alternative: `pip install daphne && daphne config.asgi:application -p 8000`)

## APIs
| Method | URL | Auth | Purpose |
|---|---|---|---|
| POST | /api/auth/register/ | no | create user (optional, remove if not needed) |
| POST | /api/auth/login/ | no | returns `access` (1 hour) + `refresh` (1 day) |
| POST | /api/auth/refresh/ | no | new access token using `refresh` |
| POST | /api/alerts/ | Bearer | send image + alert data (saved to DB) |
| GET  | /api/alerts/ | Bearer | list alerts, filters `?camera_no=1&alert_name=person` |

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login/ -d username=admin -d password=admin123
```

### Send alert (multipart)
```bash
curl -X POST http://localhost:8000/api/alerts/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F image=@frame.jpg \
  -F alert_names=person -F alert_names=vehicle \
  -F camera_no=CAM-1 \
  -F alert_time=2026-10-24T10:30:00Z
```
`alert_names` also accepts `person,vehicle` or `["person","vehicle"]`.

## Table: alerts_alert
| Column | Description |
|---|---|
| image | uploaded image path (media/alerts/YYYY/MM/DD/) |
| alert_names | list, e.g. ["person","vehicle"] |
| camera_no | camera number |
| alert_time | when the alert happened |
| created_date | when row was saved (auto) |
