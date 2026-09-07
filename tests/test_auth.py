"""Tests for API Key authentication."""
import hashlib

from apps.api.app.core.auth import generate_api_key, hash_api_key


def test_generate_api_key():
    """Test API key generation."""
    key, key_hash, key_prefix = generate_api_key()

    # Key should start with df_
    assert key.startswith("df_")

    # Key hash should be SHA256 (64 chars)
    assert len(key_hash) == 64

    # Key prefix should be first 8 chars
    assert key_prefix == key[:8]


def test_hash_api_key():
    """Test API key hashing."""
    key = "df_test123456789"
    hashed = hash_api_key(key)

    # Should be SHA256
    expected = hashlib.sha256(key.encode()).hexdigest()
    assert hashed == expected
    assert len(hashed) == 64


def test_api_key_uniqueness():
    """Test that generated API keys are unique."""
    keys = set()
    for _ in range(100):
        key, _, _ = generate_api_key()
        assert key not in keys
        keys.add(key)


def test_api_key_format():
    """Test API key format consistency."""
    for _ in range(10):
        key, key_hash, key_prefix = generate_api_key()

        # Key format
        assert key.startswith("df_")
        assert len(key) > 10

        # Prefix should match
        assert key.startswith(key_prefix)

        # Hash should be consistent
        assert hash_api_key(key) == key_hash
