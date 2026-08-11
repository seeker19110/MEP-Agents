from src.tools import calculate


def test_calculate_basic_arithmetic():
    result = calculate.invoke({"expression": "25 * 4"})
    assert "100" in result


def test_calculate_supports_parens_and_float():
    result = calculate.invoke({"expression": "(2 + 3) * 1.5"})
    assert "7.5" in result


def test_calculate_rejects_name_access():
    """The old implementation used eval(expr, {"__builtins__": {}}) which is famously
    escapable via attribute-chain tricks like ().__class__.__base__.__subclasses__().
    The AST-based evaluator only understands numeric literals + arithmetic operators,
    so any expression referencing a name is rejected outright."""
    result = calculate.invoke({"expression": "().__class__.__base__.__subclasses__()"})
    assert "Lỗi tính toán" in result


def test_calculate_rejects_function_calls():
    result = calculate.invoke({"expression": "__import__('os').system('echo pwned')"})
    assert "Lỗi tính toán" in result


def test_calculate_rejects_arbitrary_names():
    result = calculate.invoke({"expression": "open('/etc/passwd').read()"})
    assert "Lỗi tính toán" in result
