"""Phase 7: Production Integration Tests."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from apps.api.app.services.secrets import (
    EnvironmentSecretsProvider,
    SecretsProvider,
    get_secrets_provider,
    set_secrets_provider,
)
from apps.api.app.services.connectors.base import ConnectorConfig


class TestSecretsProvider:
    """Test the secrets provider abstraction."""

    def test_environment_provider_returns_env_var(self):
        provider = EnvironmentSecretsProvider()
        with patch.dict("os.environ", {"TEST_SECRET": "hello"}):
            import asyncio
            result = asyncio.run(provider.get_secret("TEST_SECRET"))
            assert result == "hello"

    def test_environment_provider_returns_none_for_missing(self):
        provider = EnvironmentSecretsProvider()
        import asyncio
        result = asyncio.run(provider.get_secret("NONEXISTENT_KEY_12345"))
        assert result is None

    def test_default_provider_is_environment(self):
        provider = get_secrets_provider()
        assert isinstance(provider, EnvironmentSecretsProvider)

    def test_set_provider(self):
        mock_provider = MagicMock(spec=SecretsProvider)
        set_secrets_provider(mock_provider)
        assert get_secrets_provider() is mock_provider
        # Reset
        set_secrets_provider(EnvironmentSecretsProvider())


class TestConnectorConfigSecrets:
    """Test ConnectorConfig secret resolution."""

    def test_direct_password(self):
        config = ConnectorConfig(password="mypassword")
        import asyncio
        result = asyncio.run(config.resolve_password())
        assert result == "mypassword"

    def test_secret_ref_resolves(self):
        config = ConnectorConfig(password_secret_ref="TEST_DB_PASSWORD")
        with patch.dict("os.environ", {"TEST_DB_PASSWORD": "secret123"}):
            import asyncio
            result = asyncio.run(config.resolve_password())
            assert result == "secret123"

    def test_secret_ref_not_found_raises(self):
        config = ConnectorConfig(password_secret_ref="NONEXISTENT_999")
        import asyncio
        with pytest.raises(ValueError, match="not found"):
            asyncio.run(config.resolve_password())

    def test_secret_ref_takes_precedence(self):
        config = ConnectorConfig(
            password="direct_password",
            password_secret_ref="TEST_PRECEDENCE",
        )
        with patch.dict("os.environ", {"TEST_PRECEDENCE": "from_secret"}):
            import asyncio
            result = asyncio.run(config.resolve_password())
            assert result == "from_secret"


class TestAPIKeyModel:
    """Test the updated APIKey model has org_id."""

    def test_apikey_has_org_id_column(self):
        from apps.api.app.db.models import APIKey
        assert hasattr(APIKey, "org_id")


class TestAuthImports:
    """Test auth and main imports work."""

    def test_main_imports(self):
        from apps.api.app.main import app
        assert app is not None

    def test_utils_imports(self):
        from apps.api.app.api.utils import incident_to_dict, set_incident_status
        assert callable(incident_to_dict)
        assert callable(set_incident_status)

    def test_secrets_imports(self):
        from apps.api.app.services.secrets import (
            SecretsProvider,
            EnvironmentSecretsProvider,
            get_secrets_provider,
        )
        assert issubclass(EnvironmentSecretsProvider, SecretsProvider)
