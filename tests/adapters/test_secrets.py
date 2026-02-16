"""Tests for adapters secrets module."""

import json
from unittest.mock import patch

from assistant.adapters.secrets import (
    KEYRING_SERVICE,
    Oauth1AuthProvider,
    Oauth1Credential,
)

def test_oauth1_auth_provider_get_store_get_delete() -> None:
    """Test Oauth1AuthProvider: get non-existent, store, get, delete."""
    provider = Oauth1AuthProvider()
    provider_type = "evernote"
    provider_account = "test_user"
    credential = Oauth1Credential(token="oauth1_token_123")
    key = f"oauth1:{provider_type}:{provider_account}"
    serialized = json.dumps({"token": credential.token})

    with patch("assistant.adapters.secrets.keyring") as mock_keyring:
        mock_keyring.get_password.return_value = None
        assert provider.get_credential(provider_type, provider_account) is None
        mock_keyring.get_password.assert_called_with(KEYRING_SERVICE, key)

        # Store credential
        mock_keyring.reset_mock()
        provider.store_credential(provider_type, provider_account, credential)
        mock_keyring.set_password.assert_called_once_with(KEYRING_SERVICE, key, serialized)

        # Get: returns stored credential
        mock_keyring.reset_mock()
        mock_keyring.get_password.return_value = serialized
        retrieved = provider.get_credential(provider_type, provider_account)
        assert retrieved is not None
        assert retrieved.token == credential.token
        mock_keyring.get_password.assert_called_once_with(KEYRING_SERVICE, key)

        # Delete
        mock_keyring.reset_mock()
        provider.delete_credential(provider_type, provider_account)
        mock_keyring.delete_password.assert_called_once_with(KEYRING_SERVICE, key)
