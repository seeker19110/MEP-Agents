from src.tools import execute_python_code


def test_allows_basic_python():
    result = execute_python_code.invoke({"code": "print(1 + 1)"})
    assert "Thực thi Python thành công" in result
    assert "2" in result


def test_allows_math_module():
    result = execute_python_code.invoke({"code": "import math\nprint(math.sqrt(16))"})
    assert "4.0" in result


def test_blocks_open_builtin():
    result = execute_python_code.invoke({"code": "open('/etc/passwd').read()"})
    assert "Lỗi quá trình thực thi Python" in result


def test_blocks_os_import():
    result = execute_python_code.invoke({"code": "import os\nos.system('echo pwned')"})
    assert "Lỗi quá trình thực thi Python" in result
    assert "không được phép" in result


def test_blocks_subprocess_import():
    result = execute_python_code.invoke({"code": "import subprocess\nsubprocess.run(['ls'])"})
    assert "Lỗi quá trình thực thi Python" in result


def test_blocks_dunder_import_bypass():
    result = execute_python_code.invoke({"code": "__import__('os').system('echo pwned')"})
    assert "Lỗi quá trình thực thi Python" in result
