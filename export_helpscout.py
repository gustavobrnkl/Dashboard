"""Export Help Scout conversations from the last 30 days to a CSV file."""

import csv
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("HELP_SCOUT_APP_ID")
APP_SECRET = os.getenv("HELP_SCOUT_APP_SECRET")

TOKEN_URL = "https://api.helpscout.net/v2/oauth2/token"
CONVERSATIONS_URL = "https://api.helpscout.net/v2/conversations"
MAILBOXES_URL = "https://api.helpscout.net/v2/mailboxes"
OUTPUT_FILE = "helpscout_conversations_last_30_days.csv"
DAYS_BACK = 30

# Mailbox whose currently-open conversations must always be included, even if
# they were created outside the DAYS_BACK window (so a long-lived open case
# never silently drops off the export).
SUPPORT_MAILBOX_NAME = "BRNKL Support"
OPEN_STATUSES = "open"  # Help Scout's combined active+pending filter

FIELDNAMES = [
    "conversation_id",
    "conversation_number",
    "created_at",
    "closed_at",
    "modified_at",
    "status",
    "subject",
    "customer_name",
    "customer_email",
    "assignee",
    "mailbox",
    "tags",
]


def get_access_token():
    if not APP_ID or not APP_SECRET:
        print("Error: HELP_SCOUT_APP_ID and HELP_SCOUT_APP_SECRET must be set in .env")
        sys.exit(1)

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": APP_ID,
                "client_secret": APP_SECRET,
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error: authentication request failed ({e})")
        sys.exit(1)

    token = response.json().get("access_token")
    if not token:
        print("Error: authentication response did not contain an access token")
        sys.exit(1)

    print("Authentication successful")
    return token


def format_tags(tags):
    if not tags:
        return ""
    names = []
    for tag in tags:
        if isinstance(tag, dict):
            name = tag.get("tag") or tag.get("name")
        else:
            name = tag
        if name:
            names.append(str(name))
    return ", ".join(names)


def format_person_name(person):
    if not person or not isinstance(person, dict):
        return ""
    first = person.get("first") or ""
    last = person.get("last") or ""
    return f"{first} {last}".strip()


def extract_row(conversation, mailbox_names):
    primary_customer = conversation.get("primaryCustomer") or {}
    assignee = conversation.get("assignee") or {}
    mailbox_id = conversation.get("mailboxId", "")

    return {
        "conversation_id": conversation.get("id", ""),
        "conversation_number": conversation.get("number", ""),
        "created_at": conversation.get("createdAt", ""),
        "closed_at": conversation.get("closedAt") or "",
        "modified_at": conversation.get("userUpdatedAt") or conversation.get("modifiedAt", ""),
        "status": conversation.get("status", ""),
        "subject": conversation.get("subject") or "",
        "customer_name": format_person_name(primary_customer),
        "customer_email": primary_customer.get("email") or "",
        "assignee": format_person_name(assignee),
        "mailbox": mailbox_names.get(mailbox_id, mailbox_id),
        "tags": format_tags(conversation.get("tags")),
    }


def fetch_mailbox_names(token):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(MAILBOXES_URL, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error: failed to fetch mailboxes ({e})")
        sys.exit(1)

    mailboxes = response.json().get("_embedded", {}).get("mailboxes", [])
    return {mb.get("id"): mb.get("name") for mb in mailboxes}


def fetch_pages(token, params, label):
    headers = {"Authorization": f"Bearer {token}"}
    params = dict(params)
    conversations = []
    page = 1

    while True:
        params["page"] = page
        print(f"Fetching {label} - page {page}...")

        try:
            response = requests.get(CONVERSATIONS_URL, headers=headers, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error: request for {label} page {page} failed ({e})")
            sys.exit(1)

        data = response.json()
        batch = data.get("_embedded", {}).get("conversations", [])
        conversations.extend(batch)

        if not batch:
            break

        page_info = data.get("page") or {}
        total_pages = page_info.get("totalPages")
        has_next_link = "next" in (data.get("_links") or {})

        if total_pages is not None:
            if page >= total_pages:
                break
        elif not has_next_link:
            break

        page += 1

    return conversations


def fetch_last_30_days(token):
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=DAYS_BACK)
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "status": "all",
        "query": f"(createdAt:[{start_str} TO {end_str}])",
    }
    return fetch_pages(token, params, "last 30 days")


def fetch_all_open_support_conversations(token, mailbox_names):
    support_mailbox_id = next(
        (mb_id for mb_id, name in mailbox_names.items() if name == SUPPORT_MAILBOX_NAME), None
    )
    if support_mailbox_id is None:
        print(f"Warning: mailbox '{SUPPORT_MAILBOX_NAME}' not found; skipping open-backlog fetch")
        return []

    params = {"status": OPEN_STATUSES, "mailbox": support_mailbox_id}
    return fetch_pages(token, params, f"all open {SUPPORT_MAILBOX_NAME} conversations")


def merge_conversations(*conversation_lists):
    merged = {}
    for conversations in conversation_lists:
        for c in conversations:
            merged[c.get("id")] = c
    return list(merged.values())


def write_csv(conversations, mailbox_names):
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for conversation in conversations:
            writer.writerow(extract_row(conversation, mailbox_names))


def main():
    token = get_access_token()
    mailbox_names = fetch_mailbox_names(token)

    recent = fetch_last_30_days(token)
    open_backlog = fetch_all_open_support_conversations(token, mailbox_names)
    conversations = merge_conversations(recent, open_backlog)

    write_csv(conversations, mailbox_names)
    print(f"Exported {len(conversations)} conversations ({len(recent)} from last 30 days, "
          f"{len(open_backlog)} open {SUPPORT_MAILBOX_NAME} backlog, deduplicated)")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
