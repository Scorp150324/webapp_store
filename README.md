# Phúc Thịnh ICT

## Deploy Flask on Vercel with Supabase

Supabase provides PostgreSQL, not MySQL. This Flask application now connects to
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

For local development, set `DATABASE_URL` in `.env` to a PostgreSQL connection
string and apply the same migration to that database. The default local URL
targets `postgres` on `localhost:5432`.
