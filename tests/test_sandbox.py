"""Tests for sandbox code execution."""

import pytest

from sandbox.executor import execute_analysis


class TestExecuteAnalysis:
    """Test sandboxed code execution."""

    @pytest.mark.asyncio
    async def test_simple_arithmetic(self):
        result = await execute_analysis("result = 2 + 2")
        assert result["result"] == 4

    @pytest.mark.asyncio
    async def test_list_operations(self):
        code = "data = [1, 2, 3, 4, 5]\nresult = sum(data)"
        result = await execute_analysis(code)
        assert result["result"] == 15

    @pytest.mark.asyncio
    async def test_dict_operations(self):
        code = 'scores = {"alice": 90, "bob": 85}\nresult = sum(scores.values()) / len(scores)'
        result = await execute_analysis(code)
        assert result["result"] == 87.5

    @pytest.mark.asyncio
    async def test_import_json(self):
        code = 'import json\ndata = {"key": "value"}\nresult = json.dumps(data)'
        result = await execute_analysis(code)
        assert result["result"] == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_import_math(self):
        code = "import math\nresult = math.sqrt(16)"
        result = await execute_analysis(code)
        assert result["result"] == 4.0

    @pytest.mark.asyncio
    async def test_no_code(self):
        result = await execute_analysis("")
        assert result["error"] == "No code provided"

    @pytest.mark.asyncio
    async def test_syntax_error_returns_error(self):
        result = await execute_analysis("def foo(")
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_runtime_error_returns_error(self):
        result = await execute_analysis("result = 1 / 0")
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_captures_stdout(self):
        result = await execute_analysis("print('hello world')")
        assert "hello world" in result["output"]

    @pytest.mark.asyncio
    async def test_execution_time_tracked(self):
        result = await execute_analysis("result = 1")
        assert result["execution_time"] >= 0
