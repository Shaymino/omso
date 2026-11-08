"""
omso 命令行入口：基于 Typer 分发子命令。
当前提供 omso init 用于初始化本地数据库。
"""

from pathlib import Path
from .ingest import ingest_file
import typer

from .store import connect, get_db_path, init_db

app = typer.Typer(help="omso — 本地优先的个人 AI 记忆工具")

@app.callback()
def callback() -> None:
    """omso — 本地优先的个人 AI 记忆工具。"""
    
@app.command()
def init() -> None:
    """初始化本地数据库：建目录、建表、开启外键检查。"""
    conn = connect()
    try:
        init_db(conn)
    finally:
        conn.close()

    typer.echo(f"数据库路径: {get_db_path()}")
    typer.echo("初始化完成")

@app.command()
def ingest(path: Path) -> None:
    """导入一个粘贴文件到本地数据库。"""
    conn = connect()
    try:
        init_db(conn)
        conv, created = ingest_file(conn, path)
    finally:
        conn.close()

    if created:
        typer.echo(f"已保存: {conv.title or conv.id[:12]}")
    else:
        typer.echo("已存在，跳过")
    # 根据 created 打印两种结果


def main() -> None:
    app()