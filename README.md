# Phúc Thịnh ICT

## Run locally

The app runs on your computer; no deployment is needed. It uses Laragon's local
MySQL by default. Flask runs with Python; Apache/Nginx in Laragon is not
required. Set `DATABASE_URL` in `.env` if your MySQL credentials differ from
the defaults in [`.env.example`](./.env.example).

1. Open PowerShell in the project folder and activate the existing virtual
   environment:

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

   If you do not have a virtual environment yet, create one and install the
   Python dependencies:

   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. In Laragon, click **Start All** (or start only **MySQL** from its menu) and
   wait until it is running.
3. Open Laragon's **HeidiSQL**, connect to `127.0.0.1:3306` as `root` (the
   default Laragon password is empty), open
   [`thietbiphancung.sql`](./thietbiphancung.sql), and execute it. **This file
   drops and recreates tables**, so run it only against a local database you
   are willing to reset.
4. If you set a MySQL root password, put the matching `DATABASE_URL` in `.env`;
   the example for Laragon's default is in [`.env.example`](./.env.example).
5. Start the app:

   ```powershell
   python app.py
   ```

5. Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Press `Ctrl+C` in
   PowerShell to stop it.

The default server address is `127.0.0.1`, so the app is available only on
your own computer. Set `HOST` in `.env` only if you intentionally need a
different listening address.

## Optional: deploy Flask on Vercel with Supabase

Supabase provides PostgreSQL, not MySQL. This Flask application connects to
PostgreSQL using SQLAlchemy and Psycopg; the database credential stays on the
server and is never exposed to browser code.

1. In Supabase, open **SQL Editor** and run
   [`migrations/001_supabase_postgres.sql`](./migrations/001_supabase_postgres.sql).
   It creates the tables and enables RLS. It does not import data from an
   existing MySQL database.
2. In the Supabase **Connect** dialog, copy the **Transaction pooler** URI
   (port `6543`). Do not construct the pooler hostname or username manually.
3. Import this repository into Vercel. Flask is detected from the root
   [`app.py`](./app.py) and dependencies are installed from
   [`requirements.txt`](./requirements.txt).
4. Add these Vercel environment variables for Production:
   - `DATABASE_URL`: the Supabase transaction-pooler URI, including the actual
     project-specific host, username, and database password.
   - `SECRET_KEY`: a long, random value.
   - `FLASK_ENV=production`
   - `OTP_DELIVERY_MODE=live`, plus the SMTP or eSMS settings needed for OTP.

   Never use a Supabase `service_role` key in browser code. This application
   connects to PostgreSQL from Flask and does not need a Supabase API key.
5. Redeploy after setting the environment variables, then verify
   `GET /api/products` returns `200`. Vercel serves assets from `public/`; the
   app retains a local-only static-file route for development.

The existing MySQL schema and data in `thietbiphancung.sql` are not converted
automatically. Export and migrate existing data separately before switching
production traffic. For imported IDs, also advance the PostgreSQL identity
sequences to the maximum imported ID.

Vercel's filesystem is not persistent. Product image uploads are rejected in
Vercel deployments; use a publicly reachable image URL until persistent object
storage is configured. The bundled sample images remain available under
`public/image/`.

For local PostgreSQL development, set `DATABASE_URL` in `.env` to a PostgreSQL
connection string and apply the migration to that database.
