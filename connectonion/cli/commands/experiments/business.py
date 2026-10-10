"""Small CRM, billing, issue-tracker and support API experiments."""

from typing import Optional

import httpx
import typer

from .api import emit, group, hosted, json_file, key, mutation, request, segment, text_file

hubspot_app = group(
    "hubspot",
    "HubSpot: contacts, deals and contact creation.",
    "save HUBSPOT_TOKEN with co env set --secret",
    "contacts",
)
stripe_app = group(
    "stripe",
    "Stripe: read customers, invoices and subscriptions.",
    "save STRIPE_API_KEY with co env set --secret; a restricted read key is enough",
    "invoices",
)
jira_app = group(
    "jira",
    "Jira Cloud: search/read issues, transitions and comments.",
    "save ATLASSIAN_URL, ATLASSIAN_EMAIL and ATLASSIAN_TOKEN; use an unscoped API token for the site URL",
    'search "assignee = currentUser()"',
)
confluence_app = group(
    "confluence",
    "Confluence Cloud: spaces, pages, read and create.",
    "save ATLASSIAN_URL, ATLASSIAN_EMAIL and ATLASSIAN_TOKEN",
    "spaces",
)
zendesk_app = group(
    "zendesk", "Zendesk: ticket pages, read and reply.", "save ZENDESK_URL, ZENDESK_EMAIL and ZENDESK_TOKEN", "tickets"
)


def hubspot(path: str, **kwargs):
    return request("https://api.hubapi.com/" + path, token=key("HUBSPOT_TOKEN"), **kwargs)


def atlassian(path: str, **kwargs):
    return request(
        hosted("ATLASSIAN_URL", "atlassian.net") + path,
        auth=httpx.BasicAuth(key("ATLASSIAN_EMAIL"), key("ATLASSIAN_TOKEN")),
        **kwargs,
    )


def zendesk(path: str, **kwargs):
    return request(
        hosted("ZENDESK_URL", "zendesk.com") + "/api/v2/" + path,
        auth=httpx.BasicAuth(key("ZENDESK_EMAIL") + "/token", key("ZENDESK_TOKEN")),
        **kwargs,
    )


@hubspot_app.command("contacts", epilog="Example: co hubspot contacts")
def contacts(after: Optional[str] = typer.Option(None, help="paging.next.after from the previous response")):
    """Read one page of CRM contacts, including paging data. Read-only."""
    emit(
        hubspot(
            "crm/v3/objects/contacts",
            params={"limit": 100, "after": after, "properties": "email,firstname,lastname,company"},
        )
    )


@hubspot_app.command("contact", epilog="Example: co hubspot contact <contact-id>")
def contact(identifier: str = typer.Argument(..., help="HubSpot contact ID")):
    """Read a contact by ID. Read-only."""
    emit(hubspot(f"crm/v3/objects/contacts/{segment(identifier)}"))


@hubspot_app.command("deals", epilog="Example: co hubspot deals")
def deals(after: Optional[str] = typer.Option(None, help="paging.next.after from the previous response")):
    """Read one page of deals, including paging data. Read-only."""
    emit(
        hubspot(
            "crm/v3/objects/deals",
            params={"limit": 100, "after": after, "properties": "dealname,dealstage,amount,closedate"},
        )
    )


@hubspot_app.command("create", epilog="Example: co hubspot create --input-file contact.json --yes")
def contact_create(
    input_file: str = typer.Option(..., help="Contact JSON body with properties; - reads stdin"),
    yes: bool = typer.Option(False, help="Create a contact; otherwise preview"),
):
    """Creates a contact using HubSpot's official JSON body only with --yes."""
    body = json_file(input_file)
    if mutation(yes, "Create HubSpot contact", body):
        emit(hubspot("crm/v3/objects/contacts", method="POST", body=body))


def register_stripe_list(kind: str):
    @stripe_app.command(kind, epilog=f"Example: co stripe {kind} --limit 10")
    def listing(
        limit: int = typer.Option(20, min=1, max=100, help="Page size"),
        after: Optional[str] = typer.Option(None, help="Last object ID from the previous page; starting_after"),
    ):
        """Read a Stripe object page; use has_more and after to continue. Read-only."""
        emit(
            request(
                "https://api.stripe.com/v1/" + kind,
                token=key("STRIPE_API_KEY"),
                params={"limit": limit, "starting_after": after},
            )
        )


for _kind in ("customers", "invoices", "subscriptions"):
    register_stripe_list(_kind)


@jira_app.command("search", epilog='Example: co jira search "assignee = currentUser()"')
def issue_search(
    jql: str = typer.Argument(..., help="Jira query language expression"),
    page_token: Optional[str] = typer.Option(None, help="nextPageToken from the previous response"),
):
    """Read one page of matching Jira issues using the enhanced JQL endpoint. Read-only."""
    emit(
        atlassian(
            "/rest/api/3/search/jql",
            params={
                "jql": jql,
                "maxResults": 100,
                "nextPageToken": page_token,
                "fields": "summary,status,assignee,updated",
            },
        )
    )


@jira_app.command("read", epilog="Example: co jira read ENG-123")
def issue_read(issue: str = typer.Argument(..., help="Issue key or ID")):
    """Read issue fields by key or ID. Read-only."""
    emit(atlassian(f"/rest/api/3/issue/{segment(issue)}"))


@jira_app.command("transitions", epilog="Example: co jira transitions ENG-123")
def transitions(issue: str = typer.Argument(..., help="Issue key or ID")):
    """Read available workflow transitions and their IDs. Read-only."""
    emit(atlassian(f"/rest/api/3/issue/{segment(issue)}/transitions"))


@jira_app.command("transition", epilog="Example: co jira transition ENG-123 <transition-id> --yes")
def transition(
    issue: str = typer.Argument(..., help="Issue key or ID"),
    transition_id: str = typer.Argument(..., help="ID from transitions"),
    yes: bool = typer.Option(False, help="Change workflow state; otherwise preview"),
):
    """Changes an issue's workflow state only with --yes."""
    body = {"transition": {"id": transition_id}}
    if mutation(yes, "Transition Jira issue", body):
        emit(atlassian(f"/rest/api/3/issue/{segment(issue)}/transitions", method="POST", body=body))


@jira_app.command("comment", epilog="Example: co jira comment ENG-123 --input-file reply.txt --yes")
def comment(
    issue: str = typer.Argument(..., help="Issue key or ID"),
    input_file: str = typer.Option(..., help="UTF-8 comment file; - reads stdin"),
    yes: bool = typer.Option(False, help="Post a comment; otherwise preview"),
):
    """Creates an issue comment as plain text in Atlassian Document Format only with --yes."""
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text_file(input_file)}]}],
        }
    }
    if mutation(yes, "Comment on Jira issue", body):
        emit(atlassian(f"/rest/api/3/issue/{segment(issue)}/comment", method="POST", body=body))


@confluence_app.command("spaces", epilog="Example: co confluence spaces")
def spaces(cursor: Optional[str] = typer.Option(None, help="cursor from the previous _links.next URL")):
    """Read a page of Confluence spaces. Read-only."""
    emit(atlassian("/wiki/api/v2/spaces", params={"limit": 100, "cursor": cursor}))


@confluence_app.command("pages", epilog="Example: co confluence pages <space-id>")
def pages(
    space: str = typer.Argument(..., help="Space ID from spaces"),
    cursor: Optional[str] = typer.Option(None, help="cursor from the previous _links.next URL"),
):
    """Read a page of space pages. Read-only."""
    emit(atlassian(f"/wiki/api/v2/spaces/{segment(space)}/pages", params={"limit": 100, "cursor": cursor}))


@confluence_app.command("read", epilog="Example: co confluence read <page-id>")
def page_read(page: str = typer.Argument(..., help="Page ID from pages")):
    """Read a page including its storage-format HTML body. Read-only."""
    emit(atlassian(f"/wiki/api/v2/pages/{segment(page)}", params={"body-format": "storage"}))


@confluence_app.command(
    "create", epilog='Example: co confluence create <space-id> "Report" --input-file report.html --yes'
)
def page_create(
    space: str = typer.Argument(..., help="Space ID"),
    title: str = typer.Argument(..., help="Page title"),
    input_file: str = typer.Option(..., help="Confluence storage-format HTML file; - reads stdin"),
    yes: bool = typer.Option(False, help="Publish a page; otherwise preview"),
):
    """Publishes a Confluence page in the space only with --yes."""
    body = {
        "spaceId": space,
        "status": "current",
        "title": title,
        "body": {"representation": "storage", "value": text_file(input_file)},
    }
    if mutation(yes, "Create Confluence page", body):
        emit(atlassian("/wiki/api/v2/pages", method="POST", body=body))


@zendesk_app.command("tickets", epilog="Example: co zendesk tickets")
def tickets(after: Optional[str] = typer.Option(None, help="meta.after_cursor from the previous page")):
    """Read a page of tickets using cursor pagination. Read-only."""
    emit(zendesk("tickets.json", params={"page[size]": 100, "page[after]": after}))


@zendesk_app.command("read", epilog="Example: co zendesk read <ticket-id>")
def ticket_read(ticket: str = typer.Argument(..., help="Ticket ID")):
    """Read a support ticket by ID. Read-only."""
    emit(zendesk(f"tickets/{segment(ticket)}.json"))


@zendesk_app.command("comments", epilog="Example: co zendesk comments <ticket-id>")
def ticket_comments(
    ticket: str = typer.Argument(..., help="Ticket ID"),
    after: Optional[str] = typer.Option(None, help="meta.after_cursor from the previous page"),
):
    """Read a page of ticket comments. Read-only."""
    emit(zendesk(f"tickets/{segment(ticket)}/comments.json", params={"page[size]": 100, "page[after]": after}))


@zendesk_app.command("reply", epilog="Example: co zendesk reply <ticket-id> --input-file reply.txt --yes")
def ticket_reply(
    ticket: str = typer.Argument(..., help="Ticket ID"),
    input_file: str = typer.Option(..., help="UTF-8 reply file; - reads stdin"),
    public: bool = typer.Option(False, help="Make the reply public; default is an internal note"),
    yes: bool = typer.Option(False, help="Post the reply; otherwise preview"),
):
    """Creates an internal ticket note, or Sends a public reply with --public, only with --yes."""
    body = {"ticket": {"comment": {"body": text_file(input_file), "public": public}}}
    if mutation(yes, "Reply to Zendesk ticket", body):
        emit(zendesk(f"tickets/{segment(ticket)}.json", method="PUT", body=body))
