"""Evernote external source adapter."""

from datetime import datetime
import logging
from uuid import UUID

from evernote.edam.notestore.ttypes import NoteFilter, NoteResultSpec, NotesMetadataResultSpec
from evernote.edam.type.ttypes import NoteSortOrder
from evernote_backup.cli_app_auth import get_auth_token, get_sync_client
from evernote_backup.evernote_client_sync import EvernoteClientSync
from evernote_backup.evernote_client_util import EvernoteAuthError

from assistant.adapters.content import DocumentContent
from assistant.adapters.secrets import Oauth1AuthProvider, Oauth1Credential
from assistant.adapters.source import ExternalSource, ExternalSourceInstanceConfig

logger = logging.getLogger(__name__)

def get_token() -> str:
    provider = Oauth1AuthProvider()
    token = get_auth_token(
        auth_user=None,
        auth_password=None,
        auth_oauth_port=10500,
        auth_oauth_host="localhost",
        backend="evernote",
        network_retry_count=1,
        use_system_ssl_ca=True,
        custom_api_data=None,
    )
    logger.info("Authenticated with Evernote")
    
    provider.store_credential(
        provider_type="evernote",
        provider_account="default",
        credential=Oauth1Credential(token=token),
    )
    return str(token)

def create_client() -> EvernoteClientSync:
    provider = Oauth1AuthProvider()
    cred = provider.get_credential(
        provider_type="evernote", 
        provider_account="default"
    )
    
    if not cred:
        token = get_token()
    else:
        token = cred.token

    try:
        client =get_sync_client(
            auth_token=token,
            backend="evernote",
            network_error_retry_count=1,
            use_system_ssl_ca=True,
            max_chunk_results=200,
            is_jwt_needed=False,
        )
    except Exception:
        token = get_token()
        client =get_sync_client(
            auth_token=token,
            backend="evernote",
            network_error_retry_count=1,
            use_system_ssl_ca=True,
            max_chunk_results=200,
            is_jwt_needed=False,
        )

    return client

class EvernoteSource(ExternalSource):
    """
    Evernote implementation of ExternalSource.

    
    """
    # TODO: Intercept permission denied errors

    def __init__(self, notebooks: list[str]) -> None:
        self._notebooks = notebooks
        self._client: EvernoteClientSync | None = None

    @classmethod
    def build(cls, config: ExternalSourceInstanceConfig) -> "EvernoteSource":
        """Build an EvernoteSource instance.

        Args:
            config: Instance configuration (provider config + DB query params).

        Returns:
            A configured EvernoteSource instance.
        """
        notebooks = config.query_params.get("notebooks")
        if notebooks is None or not isinstance(notebooks, list):
            raise ValueError("No notebooks specified in the provuider config")
        return cls(notebooks)

    def _get_client(self) -> EvernoteClientSync:
        if not self._client:        
            self._client = create_client()
            
        return self._client

    def get_document(self, external_id: str) -> DocumentContent:
        """Fetch a document by its external ID.

        Args:
            external_id: The ID of the document in the external source.

        Returns:
            DocumentContent containing the document data.
        """
        
        client = self._get_client()
        note = client.get_note_store().getNoteWithResultSpec(
            guid=external_id,
            resultSpec=NoteResultSpec(
                includeContent=True,
            )
        )

        return DocumentContent(
            uuid=UUID(note.guid),
            bytes=note.content.encode("utf-8") if note.content else b"",
        )

    def list_documents(self, since: datetime) -> list[str]:
        """List document IDs updated since a given datetime.

        Args:
            since: The earliest datetime to fetch documents from.

        Returns:
            List of external document IDs.
        """
        client = self._get_client()
        notebooks = {notebook.guid: notebook.name for notebook in client.get_note_store().listNotebooks()}
        names = set(notebooks.values())
        for notebook in self._notebooks:
            if notebook not in names:
                raise ValueError(f"Notebook {notebook} not found")
        
        relevant_notebooks = {
            notebook_id for notebook_id, name in notebooks.items() if name in self._notebooks
        }
        updated_ids = []

        for notebook_id in relevant_notebooks:
            logger.info(f"Fetching notes from notebook {notebook_id}")
            
            search_context: bytes | None = None
            end_reached = False
            offset = 0
        
            while not end_reached:
                notes = client.get_note_store().findNotesMetadata(
                    NoteFilter(
                        notebookGuid=notebook_id,
                        order=NoteSortOrder.UPDATED,
                        words=f"updated:{since.strftime('%Y%m%dT%H%M%S')}",
                        searchContextBytes=search_context,
                    ),
                    offset = offset,
                    maxNotes=100,
                    resultSpec=NotesMetadataResultSpec()
                )
                if len(notes.notes) == 0:
                    end_reached = True
                offset += len(notes.notes)
                search_context = notes.searchContextBytes
                updated_ids.extend([note.guid for note in notes.notes])
        
        return updated_ids

        