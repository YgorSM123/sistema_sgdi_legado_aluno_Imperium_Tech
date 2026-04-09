import os
import sqlite3
from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "demandas_store.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_is_primary_key(conn, table_name, column_name):
    if not _table_exists(conn, table_name):
        return False
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column[1] == column_name and column[5] == 1 for column in columns)


def _comments_have_foreign_key(conn):
    if not _table_exists(conn, "comentarios"):
        return False
    foreign_keys = conn.execute("PRAGMA foreign_key_list(comentarios)").fetchall()
    return any(
        fk[2] == "demandas" and fk[3] == "demanda_id" and fk[4] == "id"
        for fk in foreign_keys
    )


def _column_exists(conn, table_name, column_name):
    if not _table_exists(conn, table_name):
        return False
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column[1] == column_name for column in columns)


def _schema_needs_migration(conn):
    return not (
        _column_is_primary_key(conn, "demandas", "id")
        and _column_is_primary_key(conn, "comentarios", "id")
        and _comments_have_foreign_key(conn)
    )


def ensure_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA foreign_keys = ON")

        needs_priority = not _column_exists(conn, "demandas", "prioridade")
        needs_status = not _column_exists(conn, "demandas", "status")

        if not _schema_needs_migration(conn):
            changed = False
            if needs_priority:
                conn.execute(
                    "ALTER TABLE demandas ADD COLUMN prioridade TEXT NOT NULL DEFAULT 'media'"
                )
                changed = True
            if needs_status:
                conn.execute(
                    "ALTER TABLE demandas ADD COLUMN status TEXT NOT NULL DEFAULT 'Aberta'"
                )
                changed = True
            if changed:
                conn.commit()
            return

        demandas_rows = []
        comentarios_rows = []
        if _table_exists(conn, "demandas"):
            demandas_rows = conn.execute(
                "SELECT id, titulo, descricao, solicitante, data_criacao FROM demandas ORDER BY id"
            ).fetchall()
        if _table_exists(conn, "comentarios"):
            comentarios_rows = conn.execute(
                "SELECT id, demanda_id, comentario, autor, data FROM comentarios ORDER BY id"
            ).fetchall()

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE IF EXISTS comentarios")
        conn.execute("DROP TABLE IF EXISTS demandas")

        conn.execute(
            """
            CREATE TABLE demandas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                descricao TEXT NOT NULL,
                solicitante TEXT NOT NULL,
                data_criacao TEXT NOT NULL,
                prioridade TEXT NOT NULL DEFAULT 'media',
                status TEXT NOT NULL DEFAULT 'Aberta'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE comentarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demanda_id INTEGER NOT NULL,
                comentario TEXT NOT NULL,
                autor TEXT NOT NULL,
                data TEXT NOT NULL,
                FOREIGN KEY (demanda_id) REFERENCES demandas(id) ON DELETE CASCADE
            )
            """
        )

        if demandas_rows:
            conn.executemany(
                """
                INSERT INTO demandas (id, titulo, descricao, solicitante, data_criacao)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["id"],
                        row["titulo"],
                        row["descricao"],
                        row["solicitante"],
                        row["data_criacao"],
                    )
                    for row in demandas_rows
                ],
            )

        valid_demand_ids = {row["id"] for row in demandas_rows}
        valid_comments = [
            (
                row["id"],
                row["demanda_id"],
                row["comentario"],
                row["autor"],
                row["data"],
            )
            for row in comentarios_rows
            if row["demanda_id"] in valid_demand_ids
        ]
        if valid_comments:
            conn.executemany(
                """
                INSERT INTO comentarios (id, demanda_id, comentario, autor, data)
                VALUES (?, ?, ?, ?, ?)
                """,
                valid_comments,
            )

        conn.commit()


ensure_database()

PRIORIDADES_VALIDAS = frozenset(("alta", "media", "baixa"))


@app.route('/')
def index():
    return render_index()


def render_index():
    tab = request.args.get('tab', 'abertas')
    if tab not in ('abertas', 'finalizadas'):
        tab = 'abertas'

    q = (request.args.get('q') or '').strip()
    prioridade_filtro = (request.args.get("prioridade") or "").strip().lower()
    if prioridade_filtro not in PRIORIDADES_VALIDAS:
        prioridade_filtro = ""
    status = 'Finalizada' if tab == 'finalizadas' else 'Aberta'

    conn = get_db()
    cursor = conn.cursor()

    abertas_count = cursor.execute(
        "SELECT COUNT(*) FROM demandas WHERE status = 'Aberta'"
    ).fetchone()[0]
    finalizadas_count = cursor.execute(
        "SELECT COUNT(*) FROM demandas WHERE status = 'Finalizada'"
    ).fetchone()[0]

    sql = 'SELECT * FROM demandas WHERE status = ?'
    params = [status]

    if prioridade_filtro:
        sql += " AND prioridade = ?"
        params.append(prioridade_filtro)

    if q:
        sql += ' AND (titulo LIKE ? OR descricao LIKE ? OR solicitante LIKE ?)'
        like = f'%{q}%'
        params.extend([like, like, like])

    sql += ' ORDER BY id DESC'
    demandas = cursor.execute(sql, params).fetchall()
    conn.close()
    return render_template(
        'index.html',
        demandas=demandas,
        active_tab=tab,
        search_query=q,
        prioridade_filtro=prioridade_filtro,
        abertas_count=abertas_count,
        finalizadas_count=finalizadas_count,
    )


@app.route('/nova_demanda', methods=['GET', 'POST'])
def nova_demanda():
    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante = request.form['solicitante']
        prioridade = request.form.get('prioridade', 'media')
        data_criacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO demandas (titulo, descricao, solicitante, data_criacao, prioridade, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (titulo, descricao, solicitante, data_criacao, prioridade, 'Aberta'),
        )
        conn.commit()
        conn.close()

        flash('Salvo!')
        return redirect('/')

    return render_template('nova_demanda.html')


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    conn = get_db()
    cursor = conn.cursor()

    demanda = cursor.execute(
        'SELECT * FROM demandas WHERE id = ?',
        (id,),
    ).fetchone()

    if demanda is None:
        conn.close()
        abort(404)

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante = request.form['solicitante']
        prioridade = request.form.get('prioridade', demanda['prioridade'] or 'media')

        cursor.execute(
            """
            UPDATE demandas
            SET titulo = ?, descricao = ?, solicitante = ?, prioridade = ?
            WHERE id = ?
            """,
            (titulo, descricao, solicitante, prioridade, id),
        )
        conn.commit()
        conn.close()
        return redirect('/')

    conn.close()
    return render_template('editar.html', demanda=demanda)


@app.route('/deletar/<int:id>', methods=['POST'])
def deletar(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM demandas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Deletado!')
    return redirect('/')


@app.route('/finalizar/<int:id>', methods=['POST'])
def finalizar(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE demandas
        SET status = 'Finalizada'
        WHERE id = ?
        """,
        (id,),
    )
    conn.commit()
    conn.close()
    flash('Demanda finalizada!')
    return redirect('/')


@app.route('/buscar')
def buscar():
    return render_index()


# @app.route('/admin')
# def admin():
#     return 'Área administrativa'

@app.route('/detalhes/<int:id>')
def detalhes(id):
    conn = get_db()
    cursor = conn.cursor()
    demanda = cursor.execute(
        'SELECT * FROM demandas WHERE id = ?',
        (id,),
    ).fetchone()

    if demanda is None:
        conn.close()
        abort(404)

    comentarios = cursor.execute(
        'SELECT * FROM comentarios WHERE demanda_id = ? ORDER BY id',
        (id,),
    ).fetchall()
    conn.close()

    return render_template('detalhes.html', demanda=demanda, comentarios=comentarios)


@app.route('/adicionar_comentario/<int:demanda_id>', methods=['POST'])
def adicionar_comentario(demanda_id):
    comentario = request.form['comentario']
    autor = request.form['autor']

    conn = get_db()
    cursor = conn.cursor()
    demanda = cursor.execute(
        'SELECT id FROM demandas WHERE id = ?',
        (demanda_id,),
    ).fetchone()

    if demanda is None:
        conn.close()
        abort(404)

    cursor.execute(
        """
        INSERT INTO comentarios (demanda_id, comentario, autor, data)
        VALUES (?, ?, ?, ?)
        """,
        (
            demanda_id,
            comentario,
            autor,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()

    return redirect(f'/detalhes/{demanda_id}')


def calcular_prazo(data_inicio):
    return "30 dias"


if __name__ == '__main__':
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host='0.0.0.0')
