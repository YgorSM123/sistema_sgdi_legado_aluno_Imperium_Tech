import glob
import os
import shutil
import sqlite3
from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEGACY_DB_PATH = os.path.join(BASE_DIR, "demandas_store.db")
DB_PATH = os.path.join(BASE_DIR, "demandas_store_runtime.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32)

DEFAULT_USERS = (
    "Joao Silva",
    "Maria Santos",
    "Pedro Costa",
    "Ana Lima",
    "Carla Souza",
)


def _sqlite_file_is_usable(db_path):
    if not os.path.exists(db_path):
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def _bootstrap_database_file():
    if _sqlite_file_is_usable(DB_PATH):
        return

    candidates = []
    if _sqlite_file_is_usable(LEGACY_DB_PATH):
        candidates.append(LEGACY_DB_PATH)

    backup_paths = sorted(
        glob.glob(os.path.join(BASE_DIR, "demandas_store.db.backup-*")),
        reverse=True,
    )
    candidates.extend(path for path in backup_paths if _sqlite_file_is_usable(path))

    if candidates:
        shutil.copyfile(candidates[0], DB_PATH)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = MEMORY")
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


def _demandas_have_user_foreign_key(conn):
    if not _table_exists(conn, "demandas"):
        return False
    foreign_keys = conn.execute("PRAGMA foreign_key_list(demandas)").fetchall()
    return any(
        fk[2] == "usuarios" and fk[3] == "solicitante_id" and fk[4] == "id"
        for fk in foreign_keys
    )


def _column_exists(conn, table_name, column_name):
    if not _table_exists(conn, table_name):
        return False
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column[1] == column_name for column in columns)


def _seed_default_users(conn):
    conn.executemany(
        "INSERT OR IGNORE INTO usuarios (nome) VALUES (?)",
        [(name,) for name in DEFAULT_USERS],
    )


def _list_users(conn):
    return conn.execute("SELECT id, nome FROM usuarios ORDER BY nome").fetchall()


def _parse_solicitante_id(raw_value):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _normalizar_prioridade(prioridade, default="media"):
    prioridade = (prioridade or default).strip().lower()
    if prioridade not in PRIORIDADES_VALIDAS:
        return default
    return prioridade


def _schema_needs_migration(conn):
    return not (
        _column_is_primary_key(conn, "usuarios", "id")
        and _column_exists(conn, "usuarios", "nome")
        and _column_is_primary_key(conn, "demandas", "id")
        and _column_exists(conn, "demandas", "solicitante_id")
        and _demandas_have_user_foreign_key(conn)
        and _column_is_primary_key(conn, "comentarios", "id")
        and _comments_have_foreign_key(conn)
    )


def _collect_usuarios_rows(conn):
    if not _table_exists(conn, "usuarios"):
        return []
    return conn.execute("SELECT id, nome FROM usuarios ORDER BY id").fetchall()


def _collect_demandas_rows(conn):
    if not _table_exists(conn, "demandas"):
        return []

    select_columns = ["id", "titulo", "descricao"]
    if _column_exists(conn, "demandas", "solicitante_id"):
        select_columns.append("solicitante_id")
    if _column_exists(conn, "demandas", "solicitante"):
        select_columns.append("solicitante")
    select_columns.append("data_criacao")
    if _column_exists(conn, "demandas", "prioridade"):
        select_columns.append("prioridade")
    if _column_exists(conn, "demandas", "status"):
        select_columns.append("status")

    sql = f"SELECT {', '.join(select_columns)} FROM demandas ORDER BY id"
    return conn.execute(sql).fetchall()


def ensure_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA foreign_keys = ON")

        needs_priority = not _column_exists(conn, "demandas", "prioridade")
        needs_status = not _column_exists(conn, "demandas", "status")

        if not _schema_needs_migration(conn):
            if needs_priority:
                conn.execute(
                    "ALTER TABLE demandas ADD COLUMN prioridade TEXT NOT NULL DEFAULT 'media'"
                )
            if needs_status:
                conn.execute(
                    "ALTER TABLE demandas ADD COLUMN status TEXT NOT NULL DEFAULT 'Aberta'"
                )
            _seed_default_users(conn)
            conn.commit()
            return

        usuarios_rows = _collect_usuarios_rows(conn)
        demandas_rows = _collect_demandas_rows(conn)
        comentarios_rows = []
        if _table_exists(conn, "comentarios"):
            comentarios_rows = conn.execute(
                "SELECT id, demanda_id, comentario, autor, data FROM comentarios ORDER BY id"
            ).fetchall()

        legacy_names = set(DEFAULT_USERS)
        legacy_names.update(
            row["nome"].strip()
            for row in usuarios_rows
            if row["nome"] and row["nome"].strip()
        )
        legacy_names.update(
            row["solicitante"].strip()
            for row in demandas_rows
            if "solicitante" in row.keys() and row["solicitante"] and row["solicitante"].strip()
        )

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE IF EXISTS comentarios")
        conn.execute("DROP TABLE IF EXISTS demandas")
        conn.execute("DROP TABLE IF EXISTS usuarios")

        conn.execute(
            """
            CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE demandas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                descricao TEXT NOT NULL,
                solicitante_id INTEGER NOT NULL,
                data_criacao TEXT NOT NULL,
                prioridade TEXT NOT NULL DEFAULT 'media',
                status TEXT NOT NULL DEFAULT 'Aberta',
                FOREIGN KEY (solicitante_id) REFERENCES usuarios(id)
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

        if usuarios_rows:
            conn.executemany(
                "INSERT INTO usuarios (id, nome) VALUES (?, ?)",
                [
                    (row["id"], row["nome"])
                    for row in usuarios_rows
                    if row["nome"] and row["nome"].strip()
                ],
            )

        _seed_default_users(conn)
        conn.executemany(
            "INSERT OR IGNORE INTO usuarios (nome) VALUES (?)",
            [(name,) for name in sorted(legacy_names)],
        )

        usuarios_migrados = conn.execute("SELECT id, nome FROM usuarios ORDER BY id").fetchall()
        usuarios_por_nome = {
            row["nome"].strip().casefold(): row["id"]
            for row in usuarios_migrados
            if row["nome"] and row["nome"].strip()
        }
        usuarios_ids = {row["id"] for row in usuarios_migrados}
        fallback_user_id = usuarios_migrados[0]["id"] if usuarios_migrados else None

        demandas_migradas = []
        for row in demandas_rows:
            solicitante_id = None
            if "solicitante_id" in row.keys() and row["solicitante_id"] in usuarios_ids:
                solicitante_id = row["solicitante_id"]
            elif "solicitante" in row.keys() and row["solicitante"]:
                solicitante_id = usuarios_por_nome.get(row["solicitante"].strip().casefold())

            demandas_migradas.append(
                (
                    row["id"],
                    row["titulo"],
                    row["descricao"],
                    solicitante_id or fallback_user_id,
                    row["data_criacao"],
                    row["prioridade"] if "prioridade" in row.keys() and row["prioridade"] else "media",
                    row["status"] if "status" in row.keys() and row["status"] else "Aberta",
                )
            )

        if demandas_migradas:
            conn.executemany(
                """
                INSERT INTO demandas (
                    id, titulo, descricao, solicitante_id, data_criacao, prioridade, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                demandas_migradas,
            )

        valid_demand_ids = {row[0] for row in demandas_migradas}
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


_bootstrap_database_file()
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
    prioridade_filtro = _normalizar_prioridade(
        request.args.get("prioridade"),
        default="",
    )
    status = 'Finalizada' if tab == 'finalizadas' else 'Aberta'

    conn = get_db()
    cursor = conn.cursor()

    abertas_count = cursor.execute(
        "SELECT COUNT(*) FROM demandas WHERE status = 'Aberta'"
    ).fetchone()[0]
    finalizadas_count = cursor.execute(
        "SELECT COUNT(*) FROM demandas WHERE status = 'Finalizada'"
    ).fetchone()[0]

    sql = """
        SELECT
            d.id,
            d.titulo,
            d.descricao,
            u.nome AS solicitante,
            d.data_criacao,
            d.prioridade,
            d.status,
            d.solicitante_id
        FROM demandas d
        JOIN usuarios u ON u.id = d.solicitante_id
        WHERE d.status = ?
    """
    params = [status]

    if prioridade_filtro:
        sql += " AND d.prioridade = ?"
        params.append(prioridade_filtro)

    if q:
        sql += " AND (d.titulo LIKE ? OR d.descricao LIKE ? OR u.nome LIKE ?)"
        like = f'%{q}%'
        params.extend([like, like, like])

    sql += ' ORDER BY d.id DESC'
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
    conn = get_db()
    cursor = conn.cursor()
    usuarios = _list_users(conn)

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante_id = _parse_solicitante_id(request.form.get('solicitante_id'))
        prioridade = _normalizar_prioridade(request.form.get('prioridade'))
        data_criacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        usuario = None
        if solicitante_id is not None:
            usuario = cursor.execute(
                "SELECT id FROM usuarios WHERE id = ?",
                (solicitante_id,),
            ).fetchone()

        if usuario is None:
            conn.close()
            flash('Selecione um solicitante valido.')
            return render_template(
                'nova_demanda.html',
                usuarios=usuarios,
                form_data=request.form,
                selected_solicitante_id=solicitante_id,
            )

        cursor.execute(
            """
            INSERT INTO demandas (
                titulo, descricao, solicitante_id, data_criacao, prioridade, status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (titulo, descricao, solicitante_id, data_criacao, prioridade, 'Aberta'),
        )
        conn.commit()
        conn.close()

        flash('Salvo!')
        return redirect('/')

    conn.close()
    return render_template(
        'nova_demanda.html',
        usuarios=usuarios,
        form_data=None,
        selected_solicitante_id=None,
    )


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    conn = get_db()
    cursor = conn.cursor()

    demanda = cursor.execute(
        """
        SELECT
            d.id,
            d.titulo,
            d.descricao,
            u.nome AS solicitante,
            d.data_criacao,
            d.prioridade,
            d.status,
            d.solicitante_id
        FROM demandas d
        JOIN usuarios u ON u.id = d.solicitante_id
        WHERE d.id = ?
        """,
        (id,),
    ).fetchone()
    usuarios = _list_users(conn)

    if demanda is None:
        conn.close()
        abort(404)

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante_id = _parse_solicitante_id(request.form.get('solicitante_id'))
        prioridade = _normalizar_prioridade(
            request.form.get('prioridade'),
            default=demanda['prioridade'] or 'media',
        )

        usuario = None
        if solicitante_id is not None:
            usuario = cursor.execute(
                "SELECT id FROM usuarios WHERE id = ?",
                (solicitante_id,),
            ).fetchone()

        if usuario is None:
            conn.close()
            flash('Selecione um solicitante valido.')
            return render_template(
                'editar.html',
                demanda=demanda,
                usuarios=usuarios,
                form_data=request.form,
                selected_solicitante_id=solicitante_id,
            )

        cursor.execute(
            """
            UPDATE demandas
            SET titulo = ?, descricao = ?, solicitante_id = ?, prioridade = ?
            WHERE id = ?
            """,
            (titulo, descricao, solicitante_id, prioridade, id),
        )
        conn.commit()
        conn.close()
        return redirect('/')

    conn.close()
    return render_template(
        'editar.html',
        demanda=demanda,
        usuarios=usuarios,
        form_data=None,
        selected_solicitante_id=demanda['solicitante_id'],
    )


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
        """
        SELECT
            d.id,
            d.titulo,
            d.descricao,
            u.nome AS solicitante,
            d.data_criacao,
            d.prioridade,
            d.status,
            d.solicitante_id
        FROM demandas d
        JOIN usuarios u ON u.id = d.solicitante_id
        WHERE d.id = ?
        """,
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
