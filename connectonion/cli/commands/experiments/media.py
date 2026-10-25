"""Read-first Dropbox, Figma and Shopify experiments."""

from typing import Optional

import typer

from .api import ExperimentError, emit, group, hosted, key, request, segment

dropbox_app = group(
    "dropbox",
    "Dropbox: list folders and inspect file metadata.",
    "save a valid DROPBOX_TOKEN with co env set --secret; token refresh is manual in this experiment",
    "list",
)
figma_app = group(
    "figma",
    "Figma: read files, components and comments.",
    "save FIGMA_TOKEN with co env set --secret; use a file key from its URL",
    "read <file-key>",
)
shopify_app = group(
    "shopify",
    "Shopify: read products and order status.",
    "save SHOPIFY_URL (https://store.myshopify.com) and SHOPIFY_TOKEN; token needs product/order read scopes",
    "products",
)


@dropbox_app.command("list", epilog='Example: co dropbox list --path "/Reports"')
def folder(
    path: str = typer.Option("", help="Dropbox folder path; empty means root"),
    cursor: Optional[str] = typer.Option(None, help="cursor from a previous response with has_more"),
):
    """Read one folder page; use cursor while has_more is true. Read-only."""
    endpoint = "list_folder/continue" if cursor else "list_folder"
    body = {"cursor": cursor} if cursor else {"path": path, "limit": 100}
    emit(
        request("https://api.dropboxapi.com/2/files/" + endpoint, token=key("DROPBOX_TOKEN"), method="POST", body=body)
    )


@dropbox_app.command("info", epilog='Example: co dropbox info "/Reports/report.pdf"')
def info(path: str = typer.Argument(..., help="Dropbox file path or id: identifier")):
    """Read file/folder metadata; does not download bytes. Read-only."""
    emit(
        request(
            "https://api.dropboxapi.com/2/files/get_metadata",
            token=key("DROPBOX_TOKEN"),
            method="POST",
            body={"path": path},
        )
    )


@figma_app.command("read", epilog="Example: co figma read <file-key> --depth 2")
def file_read(
    file: str = typer.Argument(..., help="File key from the Figma URL"),
    depth: int = typer.Option(2, min=1, max=20, help="Document tree depth; keep output small"),
):
    """Read a Figma file tree to the requested depth. Read-only."""
    emit(
        request(
            f"https://api.figma.com/v1/files/{segment(file)}",
            headers={"X-Figma-Token": key("FIGMA_TOKEN")},
            params={"depth": depth},
        )
    )


@figma_app.command("comments", epilog="Example: co figma comments <file-key>")
def comments(file: str = typer.Argument(..., help="Figma file key")):
    """Read comments on a Figma file. Read-only."""
    emit(
        request(
            f"https://api.figma.com/v1/files/{segment(file)}/comments", headers={"X-Figma-Token": key("FIGMA_TOKEN")}
        )
    )


@figma_app.command("components", epilog="Example: co figma components <file-key>")
def components(file: str = typer.Argument(..., help="Figma file key")):
    """Read published components belonging to a file. Read-only."""
    emit(
        request(
            f"https://api.figma.com/v1/files/{segment(file)}/components", headers={"X-Figma-Token": key("FIGMA_TOKEN")}
        )
    )


def shopify(query: str, variables: dict):
    result = request(
        hosted("SHOPIFY_URL", "myshopify.com") + "/admin/api/2026-07/graphql.json",
        headers={"X-Shopify-Access-Token": key("SHOPIFY_TOKEN")},
        method="POST",
        body={"query": query, "variables": variables},
    )
    if result.get("errors"):
        raise ExperimentError("Shopify rejected the GraphQL query. Check app scopes and API access.")
    return result


@shopify_app.command("products", epilog="Example: co shopify products --limit 10")
def products(
    limit: int = typer.Option(20, min=1, max=100, help="Page size"),
    after: Optional[str] = typer.Option(None, help="pageInfo.endCursor when hasNextPage is true"),
):
    """Read product IDs, titles and status with cursor paging. Read-only."""
    query = """query($first: Int!, $after: String) { products(first: $first, after: $after) {
      nodes { id title handle status } pageInfo { hasNextPage endCursor } } }"""
    emit(shopify(query, {"first": limit, "after": after}))


@shopify_app.command("orders", epilog="Example: co shopify orders --limit 10")
def orders(
    limit: int = typer.Option(20, min=1, max=100, help="Page size"),
    after: Optional[str] = typer.Option(None, help="pageInfo.endCursor when hasNextPage is true"),
):
    """Read recent order IDs and fulfilment/financial status, subject to app access. Read-only."""
    query = """query($first: Int!, $after: String) { orders(first: $first, after: $after) {
      nodes { id name displayFinancialStatus displayFulfillmentStatus }
      pageInfo { hasNextPage endCursor } } }"""
    emit(shopify(query, {"first": limit, "after": after}))
