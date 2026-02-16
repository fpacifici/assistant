"""CLI script to load a note by notebook name."""

import argparse
import logging
import sys
from evernote_backup.cli_app_auth import (
    get_auth_token,
    get_sync_client,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point for the load_note CLI script.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Load a note by notebook name",
    )
    parser.add_argument(
        "notebook_name",
        type=str,
        help="Name of the notebook",
    )

    args = parser.parse_args()

    notebook_name = args.notebook_name

    try:
        with open("auth_token.txt", "r") as f:
            auth_token = f.read()
    
    except FileNotFoundError:
        auth_token = get_auth_token(
            auth_user=None,
            auth_password=None,
            auth_oauth_port=10500,
            auth_oauth_host="localhost",
            backend="evernote",
            network_retry_count=1,
            use_system_ssl_ca=True,
            custom_api_data=None,
        )

        with open("auth_token.txt", "w") as f:
            f.write(auth_token)
    
    logger.info("Authenticated with Evernote")

    client = get_sync_client(
        auth_token=auth_token,
        backend="evernote",
        network_error_retry_count=1,
        use_system_ssl_ca=True,
        max_chunk_results=200,
        is_jwt_needed=False,
    )

    notebooks = client.note_store.listNotebooks()
    print([notebook.name for notebook in notebooks])

    return 0
    

if __name__ == "__main__":
    sys.exit(main())
