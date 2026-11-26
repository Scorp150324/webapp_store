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
   [`thietbiphancung.sql`](./thietbiphancung.sql), and execute it. The dump
   contains the schema, indexes, and sample data (100 rows per table).
   **Importing it drops and recreates tables**, so use only a local database
   you are willing to reset.
4. If you set a MySQL root password, put the matching `DATABASE_URL` in `.env`;
   the example for Laragon's default is in [`.env.example`](./.env.example).
5. To top up any missing sample rows and ensure product-search indexes without
   deleting existing data, optionally run:

   ```powershell
   python -m scripts.seed_sample_data
   ```

   This is local-MySQL-only and safe to rerun. Product search matches from the
   beginning of the name, SKU, barcode, or specifications so the B-tree
   indexes can be used.
6. Start the app:

   ```powershell
   python app.py
   ```

7. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) on the computer running
   the app. To test from a phone or another device on the same Wi-Fi, find the
   computer's IPv4 address with `ipconfig`, then open
   `http://<computer-ipv4>:5000` on that device. Press `Ctrl+C` in PowerShell
   to stop the app.

The development server listens on all network interfaces by default so local
devices can connect. If Windows Firewall prompts you, allow Python on your
private network. Set `HOST=127.0.0.1` in `.env` to restrict access to the
computer itself.

