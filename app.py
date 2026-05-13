import csv
import glob
import io
import os
import shutil
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, Response, abort, flash, redirect, render_template, request

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

COMPANY_NAME = "Imperium Tech"
SLA_DAYS = 7
STATUS_VALIDOS = frozenset(("Aberta", "Finalizada"))
PERIODOS_DASHBOARD = {
    "7d": {"label": "7 dias", "days": 7},
    "1m": {"label": "1 mes", "days": 30},
    "3m": {"label": "3 meses", "days": 90},
    "6m": {"label": "6 meses", "days": 180},
}


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


def _parse_datetime(value):
    if not value:
        return None

    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return None


def _normalizar_periodo(periodo):
    periodo = (periodo or "7d").strip().lower()
    if periodo not in PERIODOS_DASHBOARD:
        return "7d"
    return periodo


def _periodo_range(periodo, now):
    period_config = PERIODOS_DASHBOARD[periodo]
    return now.date() - timedelta(days=period_config["days"]), now.date()


def _normalizar_status_filtro(status):
    status = (status or "").strip().lower()
    if status in ("aberta", "abertas"):
        return "aberta"
    if status in ("finalizada", "finalizadas", "concluida", "concluidas"):
        return "finalizada"
    if status in ("atrasada", "atrasadas"):
        return "atrasada"
    return ""


def _parse_int_filter(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return ""
    return parsed if parsed > 0 else ""


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
    if _column_exists(conn, "demandas", "data_finalizacao"):
        select_columns.append("data_finalizacao")

    sql = f"SELECT {', '.join(select_columns)} FROM demandas ORDER BY id"
    return conn.execute(sql).fetchall()


def ensure_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA foreign_keys = ON")

        needs_priority = not _column_exists(conn, "demandas", "prioridade")
        needs_status = not _column_exists(conn, "demandas", "status")
        needs_finished_at = not _column_exists(conn, "demandas", "data_finalizacao")

        if not _schema_needs_migration(conn):
            if needs_priority:
                conn.execute(
                    "ALTER TABLE demandas ADD COLUMN prioridade TEXT NOT NULL DEFAULT 'media'"
                )
            if needs_status:
                conn.execute(
                    "ALTER TABLE demandas ADD COLUMN status TEXT NOT NULL DEFAULT 'Aberta'"
                )
            if needs_finished_at:
                conn.execute("ALTER TABLE demandas ADD COLUMN data_finalizacao TEXT")
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
                data_finalizacao TEXT,
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
                    row["data_finalizacao"] if "data_finalizacao" in row.keys() else None,
                )
            )

        if demandas_migradas:
            conn.executemany(
                """
                INSERT INTO demandas (
                    id, titulo, descricao, solicitante_id, data_criacao, prioridade, status, data_finalizacao
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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


def _fetch_dashboard_rows(conn):
    return conn.execute(
        """
        SELECT
            d.id,
            d.titulo,
            d.descricao,
            d.data_criacao,
            d.data_finalizacao,
            d.prioridade,
            d.status,
            d.solicitante_id,
            u.nome AS solicitante
        FROM demandas d
        JOIN usuarios u ON u.id = d.solicitante_id
        ORDER BY d.data_criacao DESC, d.id DESC
        """
    ).fetchall()


def _dashboard_filters(args, now):
    periodo = _normalizar_periodo(args.get("periodo"))
    inicio, fim = _periodo_range(periodo, now)
    return {
        "periodo": periodo,
        "periodo_label": PERIODOS_DASHBOARD[periodo]["label"],
        "inicio": inicio,
        "fim": fim,
        "responsavel": _parse_int_filter(args.get("responsavel")),
        "prioridade": _normalizar_prioridade(args.get("prioridade"), default=""),
        "status": _normalizar_status_filtro(args.get("status")),
    }


def _is_overdue(created_at, status, now):
    if status != "Aberta" or created_at is None:
        return False
    return created_at.date() < (now.date() - timedelta(days=SLA_DAYS))


def _filter_dashboard_rows(rows, filters, now):
    filtered = []
    for row in rows:
        created_at = _parse_datetime(row["data_criacao"])
        finished_at = _parse_datetime(row["data_finalizacao"])
        overdue = _is_overdue(created_at, row["status"], now)

        if filters["inicio"] and (created_at is None or created_at.date() < filters["inicio"]):
            continue
        if filters["fim"] and (created_at is None or created_at.date() > filters["fim"]):
            continue
        if filters["responsavel"] and row["solicitante_id"] != filters["responsavel"]:
            continue
        if filters["prioridade"] and row["prioridade"] != filters["prioridade"]:
            continue
        if filters["status"] == "aberta" and row["status"] != "Aberta":
            continue
        if filters["status"] == "finalizada" and row["status"] != "Finalizada":
            continue
        if filters["status"] == "atrasada" and not overdue:
            continue

        resolution_days = None
        if row["status"] == "Finalizada" and created_at and finished_at:
            resolution_days = max((finished_at - created_at).days, 0)

        filtered.append(
            {
                "id": row["id"],
                "titulo": row["titulo"],
                "descricao": row["descricao"],
                "data_criacao": row["data_criacao"],
                "data_finalizacao": row["data_finalizacao"],
                "prioridade": row["prioridade"],
                "status": row["status"],
                "solicitante_id": row["solicitante_id"],
                "solicitante": row["solicitante"],
                "created_at": created_at,
                "finished_at": finished_at,
                "atrasada": overdue,
                "idade_dias": max((now - created_at).days, 0) if created_at else 0,
                "tempo_resolucao": resolution_days,
            }
        )
    return filtered


def _percent(value, total):
    if total <= 0:
        return 0
    return round((value / total) * 100)


def _filters_label(filters, usuarios):
    user_names = {usuario["id"]: usuario["nome"] for usuario in usuarios}
    parts = []
    parts.append(f"Periodo: {filters['periodo_label']}")
    parts.append(f"Responsavel: {user_names.get(filters['responsavel'], 'Todos')}")
    parts.append(f"Prioridade: {filters['prioridade'].title() if filters['prioridade'] else 'Todas'}")
    parts.append(f"Status: {filters['status'].title() if filters['status'] else 'Todos'}")
    return " | ".join(parts)


def _build_dashboard_context(args):
    now = datetime.now()
    conn = get_db()
    usuarios = _list_users(conn)
    rows = _fetch_dashboard_rows(conn)
    conn.close()

    filters = _dashboard_filters(args, now)
    demandas = _filter_dashboard_rows(rows, filters, now)
    total = len(demandas)
    abertas = sum(1 for demanda in demandas if demanda["status"] == "Aberta")
    concluidas = sum(1 for demanda in demandas if demanda["status"] == "Finalizada")
    atrasadas = sum(1 for demanda in demandas if demanda["atrasada"])
    criticas_atrasadas = [
        demanda
        for demanda in demandas
        if demanda["prioridade"] == "alta" and demanda["atrasada"]
    ]
    criticas_atrasadas.sort(
        key=lambda demanda: (
            -demanda["idade_dias"],
            demanda["titulo"],
        )
    )

    por_status = [
        {"label": "Abertas", "value": abertas, "percent": _percent(abertas, total), "class": "open"},
        {"label": "Concluidas", "value": concluidas, "percent": _percent(concluidas, total), "class": "done"},
        {"label": "Atrasadas", "value": atrasadas, "percent": _percent(atrasadas, total), "class": "late"},
    ]
    por_prioridade = []
    for prioridade in ("alta", "media", "baixa"):
        value = sum(1 for demanda in demandas if demanda["prioridade"] == prioridade)
        por_prioridade.append(
            {
                "label": prioridade.title(),
                "value": value,
                "percent": _percent(value, total),
                "class": prioridade,
            }
        )

    abertas_por_responsavel = []
    max_open = 1
    for usuario in usuarios:
        value = sum(
            1
            for demanda in demandas
            if demanda["solicitante_id"] == usuario["id"] and demanda["status"] == "Aberta"
        )
        max_open = max(max_open, value)
        abertas_por_responsavel.append({"nome": usuario["nome"], "value": value})
    for item in abertas_por_responsavel:
        item["percent"] = _percent(item["value"], max_open)

    resolved_days = [
        demanda["tempo_resolucao"]
        for demanda in demandas
        if demanda["tempo_resolucao"] is not None
    ]
    tempo_medio = round(sum(resolved_days) / len(resolved_days), 1) if resolved_days else 0

    temporal = {}
    for demanda in demandas:
        if demanda["created_at"] is None:
            continue
        key = demanda["created_at"].strftime("%Y-%m")
        temporal[key] = temporal.get(key, 0) + 1
    evolucao_temporal = [
        {"label": key, "value": value}
        for key, value in sorted(temporal.items())
    ]
    temporal_max = max([item["value"] for item in evolucao_temporal] or [1])
    for item in evolucao_temporal:
        item["percent"] = _percent(item["value"], temporal_max)

    filters_label = _filters_label(filters, usuarios)
    generated_at = now.strftime("%d/%m/%Y %H:%M")

    return {
        "company_name": COMPANY_NAME,
        "generated_at": generated_at,
        "filters": filters,
        "periodos": PERIODOS_DASHBOARD,
        "filters_label": filters_label,
        "usuarios": usuarios,
        "demandas": demandas,
        "kpis": {
            "total": total,
            "abertas": abertas,
            "concluidas": concluidas,
            "atrasadas": atrasadas,
            "criticas": len(criticas_atrasadas),
            "tempo_medio": tempo_medio,
        },
        "por_status": por_status,
        "por_prioridade": por_prioridade,
        "abertas_por_responsavel": abertas_por_responsavel,
        "evolucao_temporal": evolucao_temporal,
        "criticas_atrasadas": criticas_atrasadas,
        "criticas": criticas_atrasadas[:8],
        "sla_days": SLA_DAYS,
    }


def _csv_dashboard_response(context):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([COMPANY_NAME])
    writer.writerow(["Relatorio gerado em", context["generated_at"]])
    writer.writerow(["Filtros aplicados", context["filters_label"]])
    writer.writerow(["Escopo", "Somente demandas criticas atrasadas"])
    writer.writerow([])
    writer.writerow(["ID", "Titulo", "Solicitante", "Prioridade", "Status", "Dias em aberto", "Criada em"])
    for demanda in context["criticas_atrasadas"]:
        writer.writerow(
            [
                demanda["id"],
                demanda["titulo"],
                demanda["solicitante"],
                demanda["prioridade"],
                demanda["status"],
                demanda["idade_dias"],
                demanda["data_criacao"],
            ]
        )
    payload = "\ufeff" + output.getvalue()
    return Response(
        payload,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=dashboard_sgdi.csv"},
    )


def _escape_pdf_text(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_from_lines(lines):
    page_width = 595.28
    page_height = 841.89
    margin = 54
    line_height = 15
    pages = []
    page_lines = []
    y = page_height - margin
    for line in lines:
        if y < margin:
            pages.append(page_lines)
            page_lines = []
            y = page_height - margin
        page_lines.append((line, y))
        y -= line_height
    pages.append(page_lines)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [] /Count 0 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    page_ids = []
    for page_index, page in enumerate(pages, start=1):
        content = []
        for line, y in page:
            font = "F2" if line.startswith("# ") else "F1"
            size = 13 if font == "F2" else 10
            text = line[2:] if line.startswith("# ") else line
            content.append(
                f"BT /{font} {size} Tf 1 0 0 1 {margin:.2f} {y:.2f} Tm ({_escape_pdf_text(text)}) Tj ET"
            )
        content.append(
            f"BT /F1 9 Tf 1 0 0 1 {page_width - margin - 30:.2f} 26.00 Tm ({page_index}) Tj ET"
        )
        stream = "\n".join(content).encode("latin-1", "replace")
        content_id = len(objects) + 1
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = len(objects) + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width:.2f} {page_height:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _pdf_dashboard_response(context):
    lines = [
        f"# {COMPANY_NAME} - Dashboard SGDI",
        f"Relatorio gerado em: {context['generated_at']}",
        f"Filtros aplicados: {context['filters_label']}",
        "",
        "# Indicadores",
        f"Demandas criticas atrasadas: {context['kpis']['criticas']}",
        f"Regra: prioridade alta e fora do SLA de {SLA_DAYS} dias",
        "",
        "# Demandas criticas atrasadas",
    ]
    if context["criticas_atrasadas"]:
        for demanda in context["criticas_atrasadas"]:
            lines.append(
                f"#{demanda['id']} - {demanda['titulo']} | {demanda['solicitante']} | "
                f"{demanda['prioridade']} | {demanda['status']} | {demanda['idade_dias']} dias em aberto"
            )
    else:
        lines.append("Nenhuma demanda critica atrasada nos filtros atuais.")

    pdf = _pdf_from_lines(lines)
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=dashboard_sgdi.pdf"},
    )


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', **_build_dashboard_context(request.args))


@app.route('/dashboard/export')
def dashboard_export():
    context = _build_dashboard_context(request.args)
    formato = (request.args.get("formato") or "csv").strip().lower()
    if formato == "pdf":
        return _pdf_dashboard_response(context)
    return _csv_dashboard_response(context)


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
        SET status = 'Finalizada',
            data_finalizacao = ?
        WHERE id = ?
        """,
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id),
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
