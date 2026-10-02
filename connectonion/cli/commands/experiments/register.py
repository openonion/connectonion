"""Register the implemented experiments in co's normal discovery tree."""

from .business import confluence_app, hubspot_app, jira_app, stripe_app, zendesk_app
from .google import gdocs_app, gforms_app, gsheets_app, gslides_app
from .media import dropbox_app, figma_app, shopify_app
from .microsoft import excel_app, onedrive_app, sharepoint_app, todo_app
from .native import dingtalk_app, github_app
from .notes import airtable_app, notion_app
from .tasks import asana_app, todoist_app, trello_app

APPS = {
    "gdocs": gdocs_app,
    "gsheets": gsheets_app,
    "gslides": gslides_app,
    "gforms": gforms_app,
    "onedrive": onedrive_app,
    "sharepoint": sharepoint_app,
    "excel": excel_app,
    "todo": todo_app,
    "notion": notion_app,
    "airtable": airtable_app,
    "todoist": todoist_app,
    "trello": trello_app,
    "asana": asana_app,
    "hubspot": hubspot_app,
    "stripe": stripe_app,
    "jira": jira_app,
    "confluence": confluence_app,
    "zendesk": zendesk_app,
    "dropbox": dropbox_app,
    "figma": figma_app,
    "shopify": shopify_app,
    "github": github_app,
    "dingtalk": dingtalk_app,
}


def register(app):
    from ..command_tips import NEXT

    for name, experiment in APPS.items():
        app.add_typer(experiment, name=name, rich_help_panel="Experimental integrations")
        NEXT[f"co {name} *"] = f"co {name} --help"
