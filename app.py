import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "uandex_tv.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-antes-de-publicar")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        app_name TEXT DEFAULT '',
        device TEXT DEFAULT '',
        username TEXT DEFAULT '',
        monthly_price REAL NOT NULL DEFAULT 0,
        expires_on TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Ativo',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        paid_on TEXT NOT NULL,
        method TEXT DEFAULT 'Pix',
        paid_until TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
    );
    """)
    # A first-run admin account; change the password immediately after logging in.
    existing = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not existing:
        conn.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)",
                     ("admin", generate_password_hash("MudeEstaSenha123!")))
    conn.commit()
    conn.close()

@app.before_request
def ensure_db():
    init_db()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def update_expiry_status():
    today = date.today()
    rows = db().execute("SELECT id, expires_on, status FROM clients").fetchall()
    for row in rows:
        if row["status"] == "Cancelado":
            continue
        try:
            expiry = date.fromisoformat(row["expires_on"])
        except (ValueError, TypeError):
            continue
        new_status = "Vencido" if expiry < today else ("Vence em breve" if expiry <= today + timedelta(days=3) else "Em dia")
        db().execute("UPDATE clients SET status=? WHERE id=?", (new_status, row["id"]))
    db().commit()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Usuário ou senha incorretos.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/alterar-senha", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        user = db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not check_password_hash(user["password_hash"], current):
            flash("A senha atual não confere.", "error")
        elif len(new) < 10:
            flash("Use uma senha com pelo menos 10 caracteres.", "error")
        elif new != confirm:
            flash("A confirmação da senha não confere.", "error")
        else:
            db().execute("UPDATE users SET password_hash=? WHERE id=?",
                         (generate_password_hash(new), session["user_id"]))
            db().commit()
            flash("Senha alterada com sucesso.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html")

@app.route("/")
@login_required
def dashboard():
    update_expiry_status()
    conn = db()
    total = conn.execute("SELECT COUNT(*) n FROM clients WHERE status != 'Cancelado'").fetchone()["n"]
    overdue = conn.execute("SELECT COUNT(*) n FROM clients WHERE status='Vencido'").fetchone()["n"]
    due_soon = conn.execute("SELECT COUNT(*) n FROM clients WHERE status='Vence em breve'").fetchone()["n"]
    monthly = conn.execute("SELECT COALESCE(SUM(monthly_price),0) total FROM clients WHERE status IN ('Em dia','Vence em breve')").fetchone()["total"]
    payments_month = conn.execute("""SELECT COALESCE(SUM(amount),0) total FROM payments
        WHERE substr(paid_on,1,7)=?""", (date.today().strftime("%Y-%m"),)).fetchone()["total"]
    recent = conn.execute("""SELECT p.*, c.name client_name FROM payments p
        JOIN clients c ON c.id=p.client_id ORDER BY p.paid_on DESC, p.id DESC LIMIT 8""").fetchall()
    expiring = conn.execute("""SELECT * FROM clients WHERE status IN ('Vencido','Vence em breve')
        ORDER BY expires_on ASC LIMIT 8""").fetchall()
    return render_template("dashboard.html", total=total, overdue=overdue, due_soon=due_soon,
                           monthly=monthly, payments_month=payments_month, recent=recent, expiring=expiring)

@app.route("/clientes")
@login_required
def clients():
    update_expiry_status()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    sql = "SELECT * FROM clients WHERE 1=1"
    args = []
    if q:
        sql += " AND (name LIKE ? OR phone LIKE ? OR username LIKE ?)"
        args += [f"%{q}%"] * 3
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY name COLLATE NOCASE"
    rows = db().execute(sql, args).fetchall()
    return render_template("clients.html", clients=rows, q=q, status=status)

@app.route("/clientes/novo", methods=["GET", "POST"])
@app.route("/clientes/<int:client_id>/editar", methods=["GET", "POST"])
@login_required
def client_form(client_id=None):
    conn = db()
    item = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone() if client_id else None
    if client_id and not item:
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("clients"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Informe o nome do cliente.", "error")
            return render_template("client_form.html", item=item)
        data = (
            name, request.form.get("phone", "").strip(), request.form.get("app_name", "").strip(),
            request.form.get("device", "").strip(), request.form.get("username", "").strip(),
            float(request.form.get("monthly_price") or 0), request.form.get("expires_on", ""),
            request.form.get("status", "Ativo"), request.form.get("notes", "").strip()
        )
        if client_id:
            conn.execute("""UPDATE clients SET name=?, phone=?, app_name=?, device=?, username=?,
                monthly_price=?, expires_on=?, status=?, notes=? WHERE id=?""", data + (client_id,))
            flash("Cadastro atualizado.", "success")
        else:
            conn.execute("""INSERT INTO clients(name, phone, app_name, device, username,
                monthly_price, expires_on, status, notes) VALUES (?,?,?,?,?,?,?,?,?)""", data)
            flash("Cliente cadastrado.", "success")
        conn.commit()
        return redirect(url_for("clients"))
    return render_template("client_form.html", item=item)

@app.route("/clientes/<int:client_id>/excluir", methods=["POST"])
@login_required
def delete_client(client_id):
    db().execute("DELETE FROM clients WHERE id=?", (client_id,))
    db().commit()
    flash("Cliente e histórico de pagamentos removidos.", "success")
    return redirect(url_for("clients"))

@app.route("/pagamentos")
@login_required
def payments():
    rows = db().execute("""SELECT p.*, c.name client_name FROM payments p
        JOIN clients c ON c.id=p.client_id ORDER BY p.paid_on DESC, p.id DESC""").fetchall()
    clients_list = db().execute("SELECT id, name FROM clients ORDER BY name COLLATE NOCASE").fetchall()
    total = db().execute("SELECT COALESCE(SUM(amount),0) total FROM payments WHERE substr(paid_on,1,7)=?",
                         (date.today().strftime("%Y-%m"),)).fetchone()["total"]
    return render_template("payments.html", payments=rows, clients=clients_list, total=total, today=date.today().isoformat())

@app.route("/pagamentos/novo", methods=["POST"])
@login_required
def add_payment():
    try:
        client_id = int(request.form["client_id"])
        amount = float(request.form["amount"])
        paid_on = request.form.get("paid_on") or date.today().isoformat()
    except (ValueError, KeyError):
        flash("Confira cliente, valor e data do pagamento.", "error")
        return redirect(url_for("payments"))
    paid_until = request.form.get("paid_until", "")
    method = request.form.get("method", "Pix")
    notes = request.form.get("notes", "").strip()
    conn = db()
    client = conn.execute("SELECT id FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client or amount < 0:
        flash("Cliente ou valor inválido.", "error")
        return redirect(url_for("payments"))
    conn.execute("""INSERT INTO payments(client_id, amount, paid_on, method, paid_until, notes)
        VALUES (?,?,?,?,?,?)""", (client_id, amount, paid_on, method, paid_until, notes))
    if paid_until:
        conn.execute("UPDATE clients SET expires_on=?, status='Ativo' WHERE id=?", (paid_until, client_id))
    conn.commit()
    flash("Pagamento registrado.", "success")
    return redirect(url_for("payments"))

@app.route("/pagamentos/<int:payment_id>/excluir", methods=["POST"])
@login_required
def delete_payment(payment_id):
    db().execute("DELETE FROM payments WHERE id=?", (payment_id,))
    db().commit()
    flash("Registro de pagamento removido.", "success")
    return redirect(url_for("payments"))

if __name__ == "__main__":
    init_db()
    app.run(debug=False)
