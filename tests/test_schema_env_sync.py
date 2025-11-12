"""
Test suite for environment variable synchronization in Pydantic models.

Tests the EnvSyncMixin functionality that automatically syncs field values
to environment variables based on field metadata (json_schema_extra).
"""

import os
import pytest
from typing import Optional
from pydantic import Field

from src.proxy.schema import (
    EnvSyncMixin,
    GeneralSettings,
    LiteLLMSettings,
    RedisCacheParams,
    sync_field_to_env,
    sync_model_fields_to_env,
)


class TestEnvSyncBasic:
    """Test basic field-to-environment variable synchronization."""
    
    def test_general_settings_database_url_sync(self):
        """Test that GeneralSettings.database_url syncs to DATABASE_URL env var."""
        # Clear any existing DATABASE_URL
        os.environ.pop('DATABASE_URL', None)
        
        # Create instance with database_url
        settings = GeneralSettings(
            master_key="sk-test-key",
            database_url="postgresql://user:pass@localhost:5432/litellm"
        )
        
        # Verify env var was set
        assert os.environ.get('DATABASE_URL') == "postgresql://user:pass@localhost:5432/litellm"
    
    def test_litellm_settings_database_url_sync(self):
        """Test that LiteLLMSettings.database_url syncs to DATABASE_URL env var."""
        os.environ.pop('DATABASE_URL', None)
        
        settings = LiteLLMSettings(
            database_url="postgresql://admin:secret@db.example.com:5432/proxy"
        )
        
        assert os.environ.get('DATABASE_URL') == "postgresql://admin:secret@db.example.com:5432/proxy"
    
    def test_redis_cache_params_sync(self):
        """Test that RedisCacheParams syncs host, port, password to env vars."""
        # Clear any existing Redis env vars
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
        os.environ.pop('REDIS_PASSWORD', None)
        
        # Create instance
        redis_params = RedisCacheParams(
            host="redis.example.com",
            port=6380,
            password="redis_secret"
        )
        
        # Verify all three env vars were set
        assert os.environ.get('REDIS_HOST') == "redis.example.com"
        assert os.environ.get('REDIS_PORT') == "6380"  # int converted to string
        assert os.environ.get('REDIS_PASSWORD') == "redis_secret"
    
    def test_redis_default_values_sync(self):
        """Test that Redis default values (host=localhost, port=6379) are synced."""
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
        
        redis_params = RedisCacheParams()
        
        assert os.environ.get('REDIS_HOST') == "localhost"
        assert os.environ.get('REDIS_PORT') == "6379"


class TestEnvSyncWithEnvVarReferences:
    """Test that os.environ/VAR references are resolved before syncing."""
    
    def test_database_url_with_env_reference(self):
        """Test that DATABASE_URL with os.environ/VAR reference is resolved."""
        # Set up source env var
        os.environ['DB_CONNECTION'] = "postgresql://user:pass@localhost:5432/db"
        os.environ.pop('DATABASE_URL', None)
        
        # Create settings with env var reference
        settings = GeneralSettings(
            master_key="sk-test-key",
            database_url="os.environ/DB_CONNECTION"
        )
        
        # Verify DATABASE_URL was set to resolved value
        assert os.environ.get('DATABASE_URL') == "postgresql://user:pass@localhost:5432/db"
        
        # Cleanup
        os.environ.pop('DB_CONNECTION', None)
    
    def test_redis_password_with_env_reference(self):
        """Test that Redis password with os.environ/VAR reference is resolved."""
        os.environ['REDIS_SECRET'] = "super_secret_password"
        os.environ.pop('REDIS_PASSWORD', None)
        
        redis_params = RedisCacheParams(
            password="os.environ/REDIS_SECRET"
        )
        
        assert os.environ.get('REDIS_PASSWORD') == "super_secret_password"
        
        # Cleanup
        os.environ.pop('REDIS_SECRET', None)


class TestEnvSyncNoneValues:
    """Test that None values don't set environment variables."""
    
    def test_none_database_url_does_not_set_env(self):
        """Test that None database_url doesn't overwrite DATABASE_URL."""
        # Set initial value
        os.environ['DATABASE_URL'] = "existing_value"
        
        # Create settings with None database_url
        settings = GeneralSettings(master_key="sk-test-key", database_url=None)
        
        # Verify env var was NOT overwritten
        assert os.environ.get('DATABASE_URL') == "existing_value"
        
        # Cleanup
        os.environ.pop('DATABASE_URL', None)
    
    def test_none_redis_password_does_not_set_env(self):
        """Test that None Redis password doesn't set REDIS_PASSWORD."""
        os.environ.pop('REDIS_PASSWORD', None)
        
        redis_params = RedisCacheParams(password=None)
        
        # Verify env var was NOT set
        assert 'REDIS_PASSWORD' not in os.environ
    
    def test_optional_field_defaults_to_none(self):
        """Test that optional fields defaulting to None don't set env vars."""
        os.environ.pop('DATABASE_URL', None)
        
        # Create settings without providing database_url (defaults to None)
        settings = GeneralSettings(master_key="sk-test-key")
        
        # Verify DATABASE_URL was not set
        assert 'DATABASE_URL' not in os.environ


class TestEnvSyncHelperFunctions:
    """Test the helper functions directly."""
    
    def test_sync_field_to_env_basic(self):
        """Test sync_field_to_env with a simple string value."""
        os.environ.pop('TEST_VAR', None)
        
        sync_field_to_env('test_field', 'test_value', 'TEST_VAR')
        
        assert os.environ.get('TEST_VAR') == 'test_value'
        os.environ.pop('TEST_VAR', None)
    
    def test_sync_field_to_env_with_int(self):
        """Test sync_field_to_env converts int to string."""
        os.environ.pop('TEST_PORT', None)
        
        sync_field_to_env('port', 8080, 'TEST_PORT')
        
        assert os.environ.get('TEST_PORT') == '8080'
        os.environ.pop('TEST_PORT', None)
    
    def test_sync_field_to_env_with_none(self):
        """Test sync_field_to_env skips None values."""
        os.environ['TEST_VAR'] = 'existing'
        
        sync_field_to_env('test_field', None, 'TEST_VAR')
        
        # Should not overwrite
        assert os.environ.get('TEST_VAR') == 'existing'
        os.environ.pop('TEST_VAR', None)
    
    def test_sync_field_to_env_resolves_env_reference(self):
        """Test sync_field_to_env resolves os.environ/VAR references."""
        os.environ['SOURCE_VAR'] = 'source_value'
        os.environ.pop('DEST_VAR', None)
        
        sync_field_to_env('test_field', 'os.environ/SOURCE_VAR', 'DEST_VAR')
        
        assert os.environ.get('DEST_VAR') == 'source_value'
        
        os.environ.pop('SOURCE_VAR', None)
        os.environ.pop('DEST_VAR', None)


class TestEnvSyncIntegration:
    """Integration tests for full config loading scenarios."""
    
    def test_multiple_models_sync_to_same_env_var(self):
        """Test that when multiple models sync to same env var, last one wins."""
        os.environ.pop('DATABASE_URL', None)
        
        # Create GeneralSettings first
        general = GeneralSettings(
            master_key="sk-test-key",
            database_url="postgresql://general:pass@localhost:5432/db1"
        )
        assert os.environ.get('DATABASE_URL') == "postgresql://general:pass@localhost:5432/db1"
        
        # Create LiteLLMSettings second - should overwrite
        litellm = LiteLLMSettings(
            database_url="postgresql://litellm:pass@localhost:5432/db2"
        )
        assert os.environ.get('DATABASE_URL') == "postgresql://litellm:pass@localhost:5432/db2"
    
    def test_full_redis_config_sync(self):
        """Test complete Redis configuration sync in realistic scenario."""
        # Clear all Redis env vars
        for var in ['REDIS_HOST', 'REDIS_PORT', 'REDIS_PASSWORD']:
            os.environ.pop(var, None)
        
        # Set up source env var for password
        os.environ['REDIS_SECRET'] = "super_secret_redis_password"
        
        # Create Redis config as it would be loaded from YAML
        redis_config = RedisCacheParams(
            host="cache.production.example.com",
            port=6380,
            password="os.environ/REDIS_SECRET"  # Real config would use env reference
        )
        
        # Verify all env vars synced correctly
        assert os.environ.get('REDIS_HOST') == "cache.production.example.com"
        assert os.environ.get('REDIS_PORT') == "6380"
        assert os.environ.get('REDIS_PASSWORD') == "super_secret_redis_password"
        
        # Cleanup
        os.environ.pop('REDIS_SECRET', None)
    
    def test_env_sync_happens_after_validation(self):
        """Test that env sync happens after Pydantic validation."""
        os.environ.pop('REDIS_PORT', None)
        
        # Create with valid port
        redis_params = RedisCacheParams(port=8080)
        assert os.environ.get('REDIS_PORT') == "8080"
        
        # Invalid port should raise validation error before sync
        with pytest.raises(Exception):  # Pydantic validation error
            RedisCacheParams(port=99999)  # Port > 65535


class TestEnvSyncMixinDirectly:
    """Test the EnvSyncMixin class directly with custom models."""
    
    def test_custom_model_with_sync_field(self):
        """Test that custom models can use EnvSyncMixin."""
        from pydantic import BaseModel, Field
        
        class CustomConfig(EnvSyncMixin, BaseModel):
            api_key: str = Field(
                json_schema_extra={"sync_to_env": "CUSTOM_API_KEY"}
            )
        
        os.environ.pop('CUSTOM_API_KEY', None)
        
        config = CustomConfig(api_key="secret123")
        
        assert os.environ.get('CUSTOM_API_KEY') == "secret123"
        os.environ.pop('CUSTOM_API_KEY', None)
    
    def test_model_without_sync_metadata_does_nothing(self):
        """Test that fields without sync_to_env metadata are not synced."""
        from pydantic import BaseModel, Field
        
        class SimpleConfig(EnvSyncMixin, BaseModel):
            name: str  # No json_schema_extra
        
        os.environ.pop('NAME', None)
        
        config = SimpleConfig(name="test")
        
        # Should NOT set NAME env var
        assert 'NAME' not in os.environ


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
