"""Configuration from Azure KeyVaults."""

import time
from dataclasses import dataclass
from typing import Any, Dict, ItemsView, KeysView, Optional, Union, ValuesView, cast

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient

from .. import Configuration


@dataclass
class Cache:
    """Cache class."""

    value: str
    ts: float


class AzureKeyVaultConfiguration(Configuration):
    """
    Azure Configuration class.

    The Azure Configuration class takes Azure KeyVault credentials and
    behaves like a drop-in replacement for the regular Configuration class.

    The following limitations apply to the Azure KeyVault Configurations:
        - keys must conform to the pattern '^[0-9a-zA-Z-]+$'. In particular,
          there is no support for levels and nested values as there are no
          natural key separators for the pattern above.
        - values must be strings.
    """

    def __init__(
        self,
        az_client_id: str,
        az_client_secret: str,
        az_tenant_id: str,
        az_vault_name: str,
        cache_expiration: int = 5 * 60,
    ) -> None:
        """
        Constructor.

        :param az_client_id:
        :param az_client_secret:
        :param az_tenant_id:
        :param az_vault_name:
        :param cache_expiration:
        """
        credentials = ClientSecretCredential(
            client_id=az_client_id,
            client_secret=az_client_secret,
            tenant_id=az_tenant_id,
        )
        vault_url = "https://{az_vault_name}.vault.azure.net/".format(
            az_vault_name=az_vault_name
        )
        self._kv_client = SecretClient(vault_url=vault_url, credential=credentials)
        self._cache_expiration = cache_expiration
        self._cache: Dict[str, Cache] = {}

    def _get_secret(self, key: str) -> Optional[str]:
        key = key.replace("_", "-")  # Normalize for Azure KeyVault
        now = time.time()
        from_cache = self._cache.get(key)
        if from_cache and from_cache.ts + self._cache_expiration > now:
            return from_cache.value
        try:
            secret = self._kv_client.get_secret(key)
            self._cache[key] = Cache(value=secret.value, ts=now)
            return cast(str, secret.value)
        except ResourceNotFoundError:
            if key in self._cache:
                del self._cache[key]
            return None

    def __getitem__(self, item: str) -> Any:  # noqa: D105
        secret = self._get_secret(item)
        if secret is None:
            raise KeyError(item)
        else:
            return secret

    def __getattr__(self, item: str) -> Any:  # noqa: D105
        secret = self._get_secret(item)
        if secret is None:
            raise KeyError(item)
        else:
            return secret

    def get(self, key: str, default: Any = None) -> Union[dict, Any]:
        """
        Get the configuration values corresponding to :attr:`key`.

        :param key: key to retrieve
        :param default: default value in case the key is missing
        :return: the value found or a default
        """
        secret = self._get_secret(key)
        if secret is None:
            return default
        else:
            return secret

    def keys(
        self, levels: Optional[int] = None
    ) -> Union["Configuration", Any, KeysView[str]]:
        """Return a set-like object providing a view on the configuration keys."""
        assert not levels  # Azure Key Vaults don't support separators
        return cast(
            KeysView[str],
            (k.name for k in self._kv_client.list_properties_of_secrets()),
        )

    def values(
        self, levels: Optional[int] = None
    ) -> Union["Configuration", Any, ValuesView[Any]]:
        """Return a set-like object providing a view on the configuration values."""
        assert not levels  # Azure Key Vaults don't support separators
        return cast(
            ValuesView[str],
            (
                self._get_secret(k.name)
                for k in self._kv_client.list_properties_of_secrets()
            ),
        )

    def items(
        self, levels: Optional[int] = None
    ) -> Union["Configuration", Any, ItemsView[str, Any]]:
        """Return a set-like object providing a view on the configuration items."""
        assert not levels  # Azure Key Vaults don't support separators
        return cast(
            ItemsView[str, Any],
            (
                (k.name, self._get_secret(k.name))
                for k in self._kv_client.list_properties_of_secrets()
            ),
        )

    def __repr__(self) -> str:  # noqa: D105
        return "<AzureKeyVaultConfiguration: %r>" % self._kv_client.vault_url