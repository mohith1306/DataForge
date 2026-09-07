"""Tests for Verification Engine."""
import pytest
from apps.api.app.execution.verification import (
    VerificationEngine,
    VerificationLevel,
    VerificationStatus,
)


@pytest.mark.asyncio
async def test_verification_syntax_passed():
    """Test syntax verification passes for valid action."""
    engine = VerificationEngine()
    
    action = {"action_type": "dbt", "parameters": {}}
    result = await engine.verify(action)
    
    # Check level 1 (syntax)
    syntax_level = result.levels[0]
    assert syntax_level.level == VerificationLevel.LEVEL_1_SYNTAX
    assert syntax_level.status == VerificationStatus.PASSED


@pytest.mark.asyncio
async def test_verification_syntax_failed():
    """Test syntax verification fails for invalid action."""
    engine = VerificationEngine()
    
    action = {"parameters": {}}  # Missing action_type
    result = await engine.verify(action)
    
    syntax_level = result.levels[0]
    assert syntax_level.status == VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_verification_semantic_warning():
    """Test semantic verification warns for high replica count."""
    engine = VerificationEngine()
    
    action = {
        "action_type": "scale",
        "parameters": {"replicas": 15},
    }
    result = await engine.verify(action)
    
    semantic_level = result.levels[1]
    assert semantic_level.level == VerificationLevel.LEVEL_2_SEMANTIC
    assert semantic_level.status == VerificationStatus.WARNING


@pytest.mark.asyncio
async def test_verification_safety_warning():
    """Test safety verification warns for dangerous actions."""
    engine = VerificationEngine()
    
    action = {
        "action_type": "delete",
        "parameters": {"environment": "production"},
    }
    result = await engine.verify(action)
    
    safety_level = result.levels[2]
    assert safety_level.level == VerificationLevel.LEVEL_3_SAFETY
    assert safety_level.status == VerificationStatus.WARNING


@pytest.mark.asyncio
async def test_verification_integration_passed():
    """Test integration verification passes."""
    engine = VerificationEngine()
    
    action = {"action_type": "dbt", "parameters": {}}
    execution_result = {"success": True, "status": "completed"}
    result = await engine.verify(action, execution_result)
    
    integration_level = result.levels[3]
    assert integration_level.level == VerificationLevel.LEVEL_4_INTEGRATION
    assert integration_level.status == VerificationStatus.PASSED


@pytest.mark.asyncio
async def test_verification_integration_failed():
    """Test integration verification fails when execution fails."""
    engine = VerificationEngine()
    
    action = {"action_type": "dbt", "parameters": {}}
    execution_result = {"success": False, "status": "failed"}
    result = await engine.verify(action, execution_result)
    
    integration_level = result.levels[3]
    assert integration_level.status == VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_verification_business_passed():
    """Test business verification passes."""
    engine = VerificationEngine()
    
    action = {"action_type": "dbt", "parameters": {}}
    context = {"business_rules": []}
    result = await engine.verify(action, context=context)
    
    business_level = result.levels[4]
    assert business_level.level == VerificationLevel.LEVEL_5_BUSINESS
    assert business_level.status == VerificationStatus.PASSED


@pytest.mark.asyncio
async def test_verification_full():
    """Test full verification flow."""
    engine = VerificationEngine()
    
    action = {"action_type": "dbt", "parameters": {"command": "run"}}
    result = await engine.verify(action)
    
    assert len(result.levels) == 5
    assert result.verification_id is not None
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_verification_overall_status():
    """Test overall status determination."""
    engine = VerificationEngine()
    
    # All passed
    action = {"action_type": "cleanup", "parameters": {}}
    result = await engine.verify(action)
    assert result.overall_status == VerificationStatus.PASSED
    
    # Has warning
    action = {"action_type": "scale", "parameters": {"replicas": 15}}
    result = await engine.verify(action)
    assert result.overall_status == VerificationStatus.WARNING


def test_verification_history():
    """Test verification history."""
    engine = VerificationEngine()
    
    history = engine.get_verification_history()
    assert isinstance(history, list)
    
    stats = engine.get_verification_stats()
    assert "total_verifications" in stats
    assert "pass_rate" in stats
