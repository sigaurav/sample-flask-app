"""
Windows Credential Manager provider.

Retrieves secrets stored in the Windows Credential Manager via the
``keyring`` library.  Secrets are stored as generic credentials with
the service name equal to the secret name.

Usage (store a credential once):
    import keyring
    keyring.set_password("dremio_password", "dremio_password", "<your-password>")
    keyring.set_password("sqlserver_password", "sqlserver_password", "<your-password>")

Requires:
    pip install keyring
"""

import keyring

from app.security.credential_provider import CredentialProvider


class WindowsCredentialProvider(CredentialProvider):
    """Reads secrets from the Windows Credential Manager via keyring."""

    def get_secret(self, name: str) -> str:
        value = keyring.get_password(name, name)
        if value is None:
            raise KeyError(
                f"Secret '{name}' not found in Windows Credential Manager. "
                f"Store it with: keyring.set_password('{name}', '{name}', '<value>')"
            )
        return value
