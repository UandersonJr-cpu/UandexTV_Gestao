import os
from datetime import date, timedelta
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "troque-esta-chave-antes-de-publicar"
)


# ============================================================
# CONEXÃO COM POSTGRESQL
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não foi configurada. "
        "Configure a variável DATABASE_URL no Render."
    )


def db():
    if "db" not in g:
        g.db = psycopg2.connect(DATABASE_URL)
        g.db.autocommit = False

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)

    if conn is not None:
        if error:
            conn.rollback()
        conn.close()


# ============================================================
# CRIAÇÃO DAS TABELAS
# ============================================================

def init_db():
    conn = db()

    with conn.cursor() as cursor:

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                app_name TEXT DEFAULT '',
                device TEXT DEFAULT '',
                username TEXT DEFAULT '',
                monthly_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                expires_on TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Ativo',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                client_id INTEGER NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                paid_on TEXT NOT NULL,
                method TEXT DEFAULT 'Pix',
                paid_until TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                FOREIGN KEY(client_id)
                    REFERENCES clients(id)
                    ON DELETE CASCADE
            );
        """)

        # Cria o administrador no primeiro acesso
        cursor.execute(
            "SELECT id FROM users WHERE username = %s",
            ("admin",)
        )

        existing = cursor.fetchone()

        if not existing:
            cursor.execute(
                """
                INSERT INTO users(username, password_hash)
                VALUES (%s, %s)
                """,
                (
                    "admin",
                    generate_password_hash("MudeEstaSenha123!")
                )
            )

    conn.commit()


@app.before_request
def ensure_db():
    init_db()


# ============================================================
# LOGIN
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = db()

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute(
                "SELECT * FROM users WHERE username = %s",
                (username,)
            )

            user = cursor.fetchone()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("dashboard"))

        flash(
            "Usuário ou senha incorretos.",
            "error"
        )

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ============================================================
# ALTERAR SENHA
# ============================================================

@app.route("/alterar-senha", methods=["GET", "POST"])
@login_required
def change_password():

    if request.method == "POST":

        current = request.form.get(
            "current_password",
            ""
        )

        new = request.form.get(
            "new_password",
            ""
        )

        confirm = request.form.get(
            "confirm_password",
            ""
        )

        conn = db()

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute(
                "SELECT * FROM users WHERE id = %s",
                (session["user_id"],)
            )

            user = cursor.fetchone()

        if not check_password_hash(
            user["password_hash"],
            current
        ):

            flash(
                "A senha atual não confere.",
                "error"
            )

        elif len(new) < 10:

            flash(
                "Use uma senha com pelo menos 10 caracteres.",
                "error"
            )

        elif new != confirm:

            flash(
                "A confirmação da senha não confere.",
                "error"
            )

        else:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    UPDATE users
                    SET password_hash = %s
                    WHERE id = %s
                    """,
                    (
                        generate_password_hash(new),
                        session["user_id"]
                    )
                )

            conn.commit()

            flash(
                "Senha alterada com sucesso.",
                "success"
            )

            return redirect(url_for("dashboard"))

    return render_template(
        "change_password.html"
    )


# ============================================================
# ATUALIZAR STATUS DOS CLIENTES
# ============================================================

def update_expiry_status():

    today = date.today()

    conn = db()

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:

        cursor.execute(
            """
            SELECT id, expires_on, status
            FROM clients
            """
        )

        rows = cursor.fetchall()

        for row in rows:

            if row["status"] == "Cancelado":
                continue

            try:

                expiry = date.fromisoformat(
                    row["expires_on"]
                )

            except (ValueError, TypeError):

                continue

            if expiry < today:

                new_status = "Vencido"

            elif expiry <= today + timedelta(days=3):

                new_status = "Vence em breve"

            else:

                new_status = "Em dia"

            cursor.execute(
                """
                UPDATE clients
                SET status = %s
                WHERE id = %s
                """,
                (
                    new_status,
                    row["id"]
                )
            )

    conn.commit()


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@login_required
def dashboard():

    update_expiry_status()

    conn = db()

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:

        cursor.execute("""
            SELECT COUNT(*) AS n
            FROM clients
            WHERE status != 'Cancelado'
        """)

        total = cursor.fetchone()["n"]

        cursor.execute("""
            SELECT COUNT(*) AS n
            FROM clients
            WHERE status = 'Vencido'
        """)

        overdue = cursor.fetchone()["n"]

        cursor.execute("""
            SELECT COUNT(*) AS n
            FROM clients
            WHERE status = 'Vence em breve'
        """)

        due_soon = cursor.fetchone()["n"]

        cursor.execute("""
            SELECT COALESCE(SUM(monthly_price), 0) AS total
            FROM clients
            WHERE status IN ('Em dia', 'Vence em breve')
        """)

        monthly = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE SUBSTRING(paid_on, 1, 7) = %s
        """, (
            date.today().strftime("%Y-%m"),
        ))

        payments_month = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT
                p.*,
                c.name AS client_name
            FROM payments p
            JOIN clients c
                ON c.id = p.client_id
            ORDER BY p.paid_on DESC, p.id DESC
            LIMIT 8
        """)

        recent = cursor.fetchall()

        cursor.execute("""
            SELECT *
            FROM clients
            WHERE status IN ('Vencido', 'Vence em breve')
            ORDER BY expires_on ASC
            LIMIT 8
        """)

        expiring = cursor.fetchall()

    return render_template(
        "dashboard.html",
        total=total,
        overdue=overdue,
        due_soon=due_soon,
        monthly=monthly,
        payments_month=payments_month,
        recent=recent,
        expiring=expiring
    )


# ============================================================
# CLIENTES
# ============================================================

@app.route("/clientes")
@login_required
def clients():

    update_expiry_status()

    q = request.args.get(
        "q",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()

    sql = """
        SELECT *
        FROM clients
        WHERE 1 = 1
    """

    args = []

    if q:

        sql += """
            AND (
                name ILIKE %s
                OR phone ILIKE %s
                OR username ILIKE %s
            )
        """

        search = f"%{q}%"

        args += [
            search,
            search,
            search
        ]

    if status:

        sql += """
            AND status = %s
        """

        args.append(status)

    sql += """
        ORDER BY LOWER(name)
    """

    conn = db()

    with conn.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:

        cursor.execute(
            sql,
            args
        )

        rows = cursor.fetchall()

    return render_template(
        "clients.html",
        clients=rows,
        q=q,
        status=status
    )


# ============================================================
# NOVO / EDITAR CLIENTE
# ============================================================

@app.route(
    "/clientes/novo",
    methods=["GET", "POST"]
)
@app.route(
    "/clientes/<int:client_id>/editar",
    methods=["GET", "POST"]
)
@login_required
def client_form(client_id=None):

    conn = db()

    item = None

    if client_id:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                SELECT *
                FROM clients
                WHERE id = %s
                """,
                (client_id,)
            )

            item = cursor.fetchone()

    if client_id and not item:

        flash(
            "Cliente não encontrado.",
            "error"
        )

        return redirect(
            url_for("clients")
        )

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        if not name:

            flash(
                "Informe o nome do cliente.",
                "error"
            )

            return render_template(
                "client_form.html",
                item=item
            )

        try:

            monthly_price = float(
                request.form.get(
                    "monthly_price"
                ) or 0
            )

        except ValueError:

            monthly_price = 0

        data = (
            name,
            request.form.get(
                "phone",
                ""
            ).strip(),

            request.form.get(
                "app_name",
                ""
            ).strip(),

            request.form.get(
                "device",
                ""
            ).strip(),

            request.form.get(
                "username",
                ""
            ).strip(),

            monthly_price,

            request.form.get(
                "expires_on",
                ""
            ),

            request.form.get(
                "status",
                "Ativo"
            ),

            request.form.get(
                "notes",
                ""
            ).strip()
        )

        with conn.cursor() as cursor:

            if client_id:

                cursor.execute(
                    """
                    UPDATE clients
                    SET
                        name = %s,
                        phone = %s,
                        app_name = %s,
                        device = %s,
                        username = %s,
                        monthly_price = %s,
                        expires_on = %s,
                        status = %s,
                        notes = %s
                    WHERE id = %s
                    """,
                    data + (client_id,)
                )

                message = "Cadastro atualizado."

            else:

                cursor.execute(
                    """
                    INSERT INTO clients (
                        name,
                        phone,
                        app_name,
                        device,
                        username,
                        monthly_price,
                        expires_on,
                        status,
                        notes
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    data
                )

                message = "Cliente cadastrado."

        conn.commit()

        flash(
            message,
            "success"
        )

        return redirect(
            url_for("clients")
        )

    return render_template(
        "client_form.html",
        item=item
    )


# ============================================================
# EXCLUIR CLIENTE
# ============================================================

@app.route(
    "/clientes/<int:client_id>/excluir",
    methods=["POST"]
)
@login_required
def delete_client(client_id):

    conn = db()

    with conn.cursor() as cursor:

        cursor.execute(
            """
            DELETE FROM clients
            WHERE id = %s
            """,
            (client_id,)
        )

    conn.commit()

    flash(
        "Cliente e histórico de pagamentos removidos.",
        "success"
    )

    return redirect(
        url_for("clients")
    )


# ============================================================
# PAGAMENTOS
# ============================================================

@app.route("/pagamentos")
@login_required
def payments():

    conn = db()

    with conn.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:

        cursor.execute("""
            SELECT
                p.*,
                c.name AS client_name
            FROM payments p
            JOIN clients c
                ON c.id = p.client_id
            ORDER BY p.paid_on DESC, p.id DESC
        """)

        rows = cursor.fetchall()

        cursor.execute("""
            SELECT
                id,
                name
            FROM clients
            ORDER BY LOWER(name)
        """)

        clients_list = cursor.fetchall()

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE SUBSTRING(paid_on, 1, 7) = %s
        """, (
            date.today().strftime("%Y-%m"),
        ))

        total = cursor.fetchone()["total"]

    return render_template(
        "payments.html",
        payments=rows,
        clients=clients_list,
        total=total,
        today=date.today().isoformat()
    )


# ============================================================
# NOVO PAGAMENTO
# ============================================================

@app.route(
    "/pagamentos/novo",
    methods=["POST"]
)
@login_required
def add_payment():

    try:

        client_id = int(
            request.form["client_id"]
        )

        amount = float(
            request.form["amount"]
        )

        paid_on = (
            request.form.get("paid_on")
            or date.today().isoformat()
        )

    except (ValueError, KeyError):

        flash(
            "Confira cliente, valor e data do pagamento.",
            "error"
        )

        return redirect(
            url_for("payments")
        )

    paid_until = request.form.get(
        "paid_until",
        ""
    )

    method = request.form.get(
        "method",
        "Pix"
    )

    notes = request.form.get(
        "notes",
        ""
    ).strip()

    conn = db()

    with conn.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:

        cursor.execute(
            """
            SELECT id
            FROM clients
            WHERE id = %s
            """,
            (client_id,)
        )

        client = cursor.fetchone()

    if not client or amount < 0:

        flash(
            "Cliente ou valor inválido.",
            "error"
        )

        return redirect(
            url_for("payments")
        )

    with conn.cursor() as cursor:

        cursor.execute(
            """
            INSERT INTO payments (
                client_id,
                amount,
                paid_on,
                method,
                paid_until,
                notes
            )
            VALUES (
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                client_id,
                amount,
                paid_on,
                method,
                paid_until,
                notes
            )
        )

        if paid_until:

            cursor.execute(
                """
                UPDATE clients
                SET
                    expires_on = %s,
                    status = 'Ativo'
                WHERE id = %s
                """,
                (
                    paid_until,
                    client_id
                )
            )

    conn.commit()

    flash(
        "Pagamento registrado.",
        "success"
    )

    return redirect(
        url_for("payments")
    )


# ============================================================
# EXCLUIR PAGAMENTO
# ============================================================

@app.route(
    "/pagamentos/<int:payment_id>/excluir",
    methods=["POST"]
)
@login_required
def delete_payment(payment_id):

    conn = db()

    with conn.cursor() as cursor:

        cursor.execute(
            """
            DELETE FROM payments
            WHERE id = %s
            """,
            (payment_id,)
        )

    conn.commit()

    flash(
        "Registro de pagamento removido.",
        "success"
    )

    return redirect(
        url_for("payments")
    )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":

    with app.app_context():
        init_db()

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
