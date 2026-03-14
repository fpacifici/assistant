import json
from abc import ABC, abstractmethod
from typing import Generic, NamedTuple, TypeVar

import keyring

KEYRING_SERVICE = "assistant"


class SecretsStore(ABC):
    """
    A SecretStore abstract away multiple ways to store secrets in a mutable
    and secure way.

    Multiple implementations are needed depending whether Assistant works
    as a standalone app or as a cloud service.
    """

    @abstractmethod
    def get_secret(self, name: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def set_secret(self, name: str, secret: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_secret(self, name: str) -> None:
        raise NotImplementedError


class KeyRingSecretsStore(SecretsStore):
    """
    USes Keyring to store locally secrets using the OS specific implementation.
    """

    def get_secret(self, name: str) -> str | None:
        return keyring.get_password(KEYRING_SERVICE, name)

    def set_secret(self, name: str, secret: str) -> None:
        keyring.set_password(KEYRING_SERVICE, name, secret)

    def delete_secret(self, name: str) -> None:
        keyring.delete_password(KEYRING_SERVICE, name)


# TODO: Adds a secret store that reads and writes from DB encrypted with a KMS
# provided main key.

Credential = TypeVar("Credential")


class AuthProvider(ABC, Generic[Credential]):
    """
    An AuthProvider abstractgs multiple types of credentials storage.
    A Credential contains everything the client needs to authenticate with a
    provider. For example for an Oauth2 implementation, a Credential could
    contain a token and a refresh token plus metadata like expiration timestamp.
    """

    def __init__(self) -> None:
        self.secrets_store = KeyRingSecretsStore()

    @abstractmethod
    def get_credential(
        self, provider_type: str, provider_account: str
    ) -> Credential | None:
        raise NotImplementedError

    @abstractmethod
    def store_credential(
        self, provider_type: str, provider_account: str, credential: Credential
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_credential(self, provider_type: str, provider_account: str) -> None:
        raise NotImplementedError


class Oauth1Credential(NamedTuple):
    token: str
    # TODO: Add expiry date


class Oauth1AuthProvider(AuthProvider[Oauth1Credential]):
    def _get_key(self, provider_type: str, provider_account: str) -> str:
        return f"oauth1:{provider_type}:{provider_account}"

    def get_credential(
        self, provider_type: str, provider_account: str
    ) -> Oauth1Credential | None:
        secret = self.secrets_store.get_secret(
            self._get_key(provider_type, provider_account)
        )
        if not secret:
            return None
        parsed = json.loads(secret)
        return Oauth1Credential(parsed["token"])

    def store_credential(
        self, provider_type: str, provider_account: str, credential: Oauth1Credential
    ) -> None:
        key = self._get_key(provider_type, provider_account)
        serialized = json.dumps({"token": credential.token})
        self.secrets_store.set_secret(key, serialized)

    def delete_credential(self, provider_type: str, provider_account: str) -> None:
        self.secrets_store.delete_secret(self._get_key(provider_type, provider_account))
