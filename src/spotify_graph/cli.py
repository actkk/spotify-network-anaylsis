from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from urllib.parse import urlsplit

import typer
from selenium.webdriver.remote.webdriver import WebDriver

from spotify_graph.config import PROJECT_ROOT, Settings, get_settings
from spotify_graph.analysis.graph_builder import build_display_graph, export_graphml
from spotify_graph.analysis.loops import find_triangles
from spotify_graph.crawlers.auth import SpotifyWebAuthenticator
from spotify_graph.crawlers.cookies import load_cookies, save_cookies
from spotify_graph.crawlers.crawler import SpotifyGraphCrawler
from spotify_graph.crawlers.webdriver import build_chrome_driver
from spotify_graph.storage.repository import GraphRepository
from spotify_graph.storage.json_store import JsonGraphStore
from spotify_graph.storage.run_recorder import RunRecorder
from spotify_graph.logging import configure_logging, get_logger

app = typer.Typer(add_completion=False)
LOGGER = get_logger(__name__)


@contextmanager
def managed_driver(*, headless: bool, settings: Settings) -> Iterator[WebDriver]:
    driver = build_chrome_driver(headless=headless, settings=settings)
    try:
        yield driver
    finally:
        driver.quit()


def normalize_profile_identifier(identifier: str) -> str:
    if identifier.startswith("http"):
        trimmed = identifier.rstrip("/")
        return trimmed.split("/")[-1]
    return identifier


def root_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return url


def authenticate_session(
    driver: WebDriver,
    settings: Settings,
    *,
    manual_login: bool,
    use_cookies: bool,
    cookie_path: Optional[Path],
    save_cookies_flag: bool,
) -> None:
    authenticator = SpotifyWebAuthenticator(driver, settings=settings)
    authenticated = False

    if use_cookies and cookie_path:
        loaded = load_cookies(driver, cookie_path, base_domain=root_url(settings.spotify_base_url))
        if loaded:
            result = authenticator.confirm_login()
            if result.success:
                typer.secho("Authenticated via stored cookies", fg=typer.colors.GREEN)
                authenticated = True
            else:
                typer.secho(
                    f"Cookie-based authentication failed: {result.error}",
                    err=True,
                    fg=typer.colors.YELLOW,
                )

    if not authenticated:
        result = authenticator.login(manual=manual_login)
        if not result.success:
            typer.secho(f"Login failed: {result.error}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1)
        authenticated = True
        typer.secho("Authenticated via credential login", fg=typer.colors.GREEN)

    if authenticated and cookie_path and save_cookies_flag:
        domains = {
            root_url(settings.spotify_base_url),
            root_url(settings.spotify_login_url),
        }
        save_cookies(driver, cookie_path, domains=domains)


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9_-]", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-") or "profile"


def write_run_results(
    *,
    repository: GraphRepository,
    run_recorder: RunRecorder,
    root_profile_id: str,
    run_timestamp: datetime,
) -> Path:
    results_root = PROJECT_ROOT / "data" / "results"
    results_root.mkdir(parents=True, exist_ok=True)

    root_profile = repository.find_profile(root_profile_id)
    display_name = (root_profile.display_name if root_profile else None) or root_profile_id
    slug = _slugify(display_name)
    run_dir = results_root / f"{run_timestamp.strftime('%Y%m%d-%H%M%S')}_{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)

    profiles_payload = {
        pid: repository.profiles[pid].model_dump(mode="json")
        for pid in sorted(run_recorder.profile_ids)
        if pid in repository.profiles
    }

    edges_payload = [edge.model_dump(mode="json") for edge in run_recorder.edges]

    with (run_dir / "profiles.json").open("w", encoding="utf-8") as fp:
        json.dump(profiles_payload, fp, indent=2, ensure_ascii=False)

    with (run_dir / "edges.json").open("w", encoding="utf-8") as fp:
        json.dump(edges_payload, fp, indent=2, ensure_ascii=False)

    metadata = {
        "root_profile_id": root_profile_id,
        "display_name": display_name,
        "profile_count": len(profiles_payload),
        "edge_count": len(edges_payload),
        "generated_at": run_timestamp.isoformat() + "Z",
    }
    with (run_dir / "metadata.json").open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2, ensure_ascii=False)

    return run_dir


@app.command()
def login_test(
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode."),
    manual_login: bool = typer.Option(False, help="Wait for manual login instead of auto-filling credentials."),
    use_cookies: bool = typer.Option(False, "--use-cookies/--no-use-cookies", help="Attempt to authenticate using stored cookies before logging in."),
    cookie_file: Optional[Path] = typer.Option(None, help="Path to a cookie JSON file."),
    save_cookies_flag: bool = typer.Option(True, "--save-cookies/--no-save-cookies", help="Persist cookies after successful authentication."),
) -> None:
    """Verify that credentials from .env can authenticate against Spotify."""
    configure_logging()
    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"Failed to load settings: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    with managed_driver(headless=headless, settings=settings) as driver:
        authenticate_session(
            driver,
            settings,
            manual_login=manual_login,
            use_cookies=use_cookies,
            cookie_path=cookie_file,
            save_cookies_flag=save_cookies_flag,
        )
        typer.secho("Login check completed", fg=typer.colors.GREEN)


@app.command()
def scrape(
    profile: str = typer.Argument(..., help="Spotify profile ID or URL to crawl."),
    depth: int = typer.Option(1, min=1, help="Maximum graph depth to crawl."),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode."),
    manual_login: bool = typer.Option(False, help="Wait for manual login instead of auto-filling credentials."),
    use_cookies: bool = typer.Option(False, "--use-cookies/--no-use-cookies", help="Attempt to authenticate using stored cookies before logging in."),
    cookie_file: Optional[Path] = typer.Option(Path("data/cookies.json"), help="Path to a cookie JSON file."),
    save_cookies_flag: bool = typer.Option(True, "--save-cookies/--no-save-cookies", help="Persist cookies after successful authentication."),
) -> None:
    """Placeholder scrape command. Real crawling logic is implemented later."""
    configure_logging()
    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"Failed to load settings: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if depth > settings.crawl_max_depth:
        typer.secho(
            f"Requested depth {depth} exceeds configured max {settings.crawl_max_depth}; temporarily raising limit.",
            err=True,
            fg=typer.colors.YELLOW,
        )
        try:
            settings = settings.model_copy(update={"crawl_max_depth": depth})
        except AttributeError:
            settings.crawl_max_depth = depth  # type: ignore[attr-defined]

    normalized_profile = normalize_profile_identifier(profile)

    repository = GraphRepository()

    run_timestamp = datetime.utcnow()
    run_recorder = RunRecorder()
    repository = GraphRepository(store=JsonGraphStore(timestamp=run_timestamp))

    with managed_driver(headless=headless, settings=settings) as driver:
        authenticate_session(
            driver,
            settings,
            manual_login=manual_login,
            use_cookies=use_cookies,
            cookie_path=cookie_file,
            save_cookies_flag=save_cookies_flag,
        )

        crawler = SpotifyGraphCrawler(
            driver,
            repository=repository,
            settings=settings,
            run_recorder=run_recorder,
        )
        typer.secho(
            f"Authenticated successfully. Starting crawl for '{normalized_profile}' up to depth {depth}.",
            fg=typer.colors.GREEN,
        )
        crawler.crawl(normalized_profile, max_depth=depth)
    repository.persist()
    repository.archive_snapshot()

    run_dir = write_run_results(
        repository=repository,
        run_recorder=run_recorder,
        root_profile_id=normalized_profile,
        run_timestamp=run_timestamp,
    )
    typer.secho(
        f"Crawl finished. Run data saved under {run_dir} and master cache updated.",
        fg=typer.colors.BLUE,
    )


@app.command()
def export_graph(
    output: Path = typer.Option(Path("data/graph.graphml"), help="Destination path for GraphML export."),
    exclude_private: bool = typer.Option(False, "--exclude-private/--include-private", help="Exclude private profiles from the graph."),
) -> None:
    """Build a NetworkX graph keyed by display names and export as GraphML."""
    configure_logging()
    graph = build_display_graph(include_private=not exclude_private)
    export_graphml(graph, output)
    typer.secho(
        f"Graph exported with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges to {output}",
        fg=typer.colors.GREEN,
    )


@app.command()
def analyze_loops(
    exclude_private: bool = typer.Option(False, "--exclude-private/--include-private", help="Exclude private profiles from analysis."),
) -> None:
    """List friend-of-friend loops (triangles) by display name."""
    configure_logging()
    triangles = find_triangles(include_private=not exclude_private)
    if not triangles:
        typer.secho("No loops detected in current data set.", fg=typer.colors.BLUE)
        return

    typer.secho(f"Found {len(triangles)} loops:", fg=typer.colors.GREEN)
    for trio in triangles:
        typer.echo(" -> ".join(trio))


def main() -> None:
    app(prog_name="spotify-graph")


if __name__ == "__main__":
    main()
