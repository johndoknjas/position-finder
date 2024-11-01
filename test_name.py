from __future__ import annotations

import subprocess
import pytest
from dataclasses import dataclass

initial_name_args = "python name.py"
initial_main_args_name = "python main.py name"

@dataclass
class SpecsTestCase:
    db_names: str
    substrings: str
    filename_expected_output: str

class MyTestCase:
    def __init__(self, initial_args: str, specs: SpecsTestCase) -> None:
        self.initial_args = initial_args.split()
        self.db_names = specs.db_names.split()
        self.substrings = specs.substrings.split()
        self.filename_expected_output = specs.filename_expected_output

    def expected_output(self) -> str:
        with open(f"test-files/{self.filename_expected_output}", 'r') as f:
            return f.read() + '\n'

    def actual_output(self) -> str:
        return subprocess.run(self.initial_args + self.db_names + self.substrings,
                              capture_output=True, text=True).stdout

    def run_test(self) -> None:
        assert self.expected_output() == self.actual_output()

def factory(specs: SpecsTestCase, name_py: bool, main_py_name_feat: bool) -> list[MyTestCase]:
    objects = []
    if name_py:
        objects.append(MyTestCase(initial_name_args, specs))
    if main_py_name_feat:
        objects.append(MyTestCase(initial_main_args_name, specs))
    assert objects
    return objects

def generate_test_cases() -> list[MyTestCase]:
    return [
        *factory(SpecsTestCase('wip local', 'kasparov', '2.txt'), True, True),
        *factory(SpecsTestCase('local wip', 'kasparov', '3.txt'), True, True),
        *factory(SpecsTestCase('openings', 'bayonet', '1.txt'), True, True),
    ]

@pytest.mark.parametrize("test_case", generate_test_cases())
def tests(test_case: MyTestCase):
    test_case.run_test()