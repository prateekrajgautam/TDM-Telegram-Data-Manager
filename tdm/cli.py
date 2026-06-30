"""
cli.py
------
Entry point. Defines the `tdm` command group with Typer, matching the
CLI surface sketched in section 22 of the planning doc.

Run via: python -m tdm.cli <command>   (or `tdm <command>` once installed)
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from . import auth, download, verify as verify_mod, exporter
from .config import load_config, save_config
from .database import Database
from .logger import setup_logging, log_summary
from .ui import make_progress, print_stats

app = typer.Typer(help="Telegram Data Manager - a yt-dlp/rclone-style tool for Telegram data.")
console = Console()


def _run(coro):
    """Run an async function from a sync Typer command."""
    return asyncio.run(coro)


@app.command()
def login():
    """Authenticate with Telegram and store a local session."""
    cfg = load_config()
    setup_logging(cfg.log_folder)

    async def _go():
        client = await auth.get_client(cfg)
        me = await client.get_me()
        console.print(f"[green]Logged in as {me.first_name} (@{me.username})[/green]")
        await client.disconnect()

    _run(_go())


@app.command()
def logout():
    """Log out and remove the local session file."""
    cfg = load_config()

    async def _go():
        await auth.logout(cfg)
        console.print("[yellow]Logged out and session removed.[/yellow]")

    _run(_go())


@app.command()
def chats(search: str = typer.Option(None, help="Filter chats by name substring")):
    """List your chats (groups, channels, private chats)."""
    cfg = load_config()

    async def _go():
        client = await auth.get_client(cfg)
        table = Table(title="Telegram Chats")
        table.add_column("Index")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Unread")

        idx = 0
        async for dialog in client.iter_dialogs():
            if search and search.lower() not in (dialog.name or "").lower():
                continue
            chat_type = "channel" if dialog.is_channel else "group" if dialog.is_group else "private"
            table.add_row(str(idx), str(dialog.id), dialog.name or "-", chat_type, str(dialog.unread_count))
            idx += 1
        console.print(table)
        await client.disconnect()

    _run(_go())


@app.command()
def backup(
    chat_id: int = typer.Argument(..., help="Chat ID to back up"),
    limit: int = typer.Option(None, help="Max number of messages to scan (default: all)"),
):
    """Index a chat's media and download all pending items (resumable)."""
    cfg = load_config()
    logger = setup_logging(cfg.log_folder)
    db = Database(cfg.db_path)

    async def _go():
        client = await auth.get_client(cfg)

        console.print(f"Indexing chat {chat_id}...")
        queued = await download.index_chat(client, db, chat_id, limit=limit)
        console.print(f"Queued {queued} new media items.")

        progress = make_progress()
        with progress:
            task = progress.add_task("Downloading", total=len(db.pending_items(chat_id)))

            def on_progress(row, status):
                progress.update(task, advance=1 if status in ("downloaded", "skipped", "failed") else 0,
                                 description=f"Downloading [{status}] {row['file_name'] or row['media_type']}")

            results = await download.download_pending(client, db, cfg, chat_id=chat_id, progress_cb=on_progress)

        console.print(results)
        log_summary(cfg.log_folder, f"backup chat_id={chat_id} results={results}")
        print_stats(db.stats())
        await client.disconnect()

    try:
        _run(_go())
    finally:
        db.close()


@app.command()
def retry():
    """Retry all failed items across all chats."""
    cfg = load_config()
    setup_logging(cfg.log_folder)
    db = Database(cfg.db_path)

    async def _go():
        client = await auth.get_client(cfg)
        progress = make_progress()
        with progress:
            task = progress.add_task("Retrying", total=len(db.pending_items()))

            def on_progress(row, status):
                progress.update(task, advance=1 if status in ("downloaded", "skipped", "failed") else 0)

            results = await download.download_pending(client, db, cfg, progress_cb=on_progress)
        console.print(results)
        await client.disconnect()

    try:
        _run(_go())
    finally:
        db.close()


@app.command()
def verify():
    """Verify downloaded files (existence, size, hash)."""
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        report = verify_mod.verify_all(db)
        console.print(report)
    finally:
        db.close()


@app.command(name="export")
def export_cmd(
    fmt: str = typer.Argument(..., help="csv or json"),
    out: str = typer.Option(None, help="Output file path"),
):
    """Export metadata to CSV or JSON."""
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        if fmt == "csv":
            out_path = out or "export.csv"
            n = exporter.export_csv(db, out_path)
        elif fmt == "json":
            out_path = out or "export.json"
            n = exporter.export_json(db, out_path)
        else:
            console.print(f"[red]Unknown format: {fmt}[/red] (use csv or json)")
            raise typer.Exit(1)
        console.print(f"Exported {n} rows to {out_path}")
    finally:
        db.close()


@app.command()
def config(
    api_id: int = typer.Option(None, help="Telegram API ID from my.telegram.org"),
    api_hash: str = typer.Option(None, help="Telegram API hash from my.telegram.org"),
    download_folder: str = typer.Option(None),
    workers: int = typer.Option(None),
):
    """View or update config.json."""
    cfg = load_config()
    if api_id is not None:
        cfg.api_id = api_id
    if api_hash is not None:
        cfg.api_hash = api_hash
    if download_folder is not None:
        cfg.download_folder = download_folder
    if workers is not None:
        cfg.workers = workers
    save_config(cfg)
    console.print(cfg.model_dump())


if __name__ == "__main__":
    app()
