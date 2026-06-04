"""
Abstract credential provider.

All concrete implementations must override ``get_secret`` so that
passwords are retrieved from a secure store and never hard-coded
in configuration files or source code.
"""

from abc import ABC, abstractmethod


class CredentialProvider(ABC):
    """Retrieve secrets by name from a secure backing store."""

    @abstractmethod
    def get_secret(self, name: str) -> str:
        """
        Return the secret value for *name*.

        Args:
            name: Logical secret name (e.g., 'dremio_password').

        Returns:
            The secret string.

        Raises:
            KeyError: If the secret is not found in the store.
        """
