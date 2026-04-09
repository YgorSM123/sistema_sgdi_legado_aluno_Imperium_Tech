import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "demandas_store.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = OFF")
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA foreign_keys = ON")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS demandas (
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

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS comentarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            demanda_id INTEGER NOT NULL,
            comentario TEXT NOT NULL,
            autor TEXT NOT NULL,
            data TEXT NOT NULL,
            FOREIGN KEY (demanda_id) REFERENCES demandas(id) ON DELETE CASCADE
        )
        """
    )

    if cursor.execute("SELECT COUNT(*) FROM demandas").fetchone()[0] == 0:
        cursor.executemany(
            """
            INSERT INTO demandas (id, titulo, descricao, solicitante, data_criacao, prioridade, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "Corrigir bug no login", "Usuarios nao conseguem fazer login", "Joao Silva", "2024-01-15 10:30:00", "alta", "Aberta"),
                (2, "Implementar relatorio de vendas", "Precisamos de um relatorio mensal", "Maria Santos", "2024-01-16 14:20:00", "media", "Aberta"),
                (3, "Melhorar performance", "Sistema esta lento", "Pedro Costa", "2024-01-17 09:15:00", "alta", "Aberta"),
                (5, "Adicionar filtros", "Usuarios querem filtrar demandas", "Ana Lima", "2024-01-18 11:00:00", "baixa", "Aberta"),
            ],
        )

    if cursor.execute("SELECT COUNT(*) FROM comentarios").fetchone()[0] == 0:
        cursor.executemany(
            """
            INSERT INTO comentarios (id, demanda_id, comentario, autor, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "Vou investigar esse bug", "Tech Team", "2024-01-15 11:00:00"),
                (2, 1, "Bug corrigido na branch develop", "Desenvolvedor", "2024-01-15 16:30:00"),
            ],
        )

    conn.commit()
    conn.close()

    print("Banco de dados criado com sucesso!")


if __name__ == "__main__":
    main()
