import subprocess
from dataclasses import dataclass

initial_name_args = ["python", "name.py"]
initial_main_args_name = ["python", "main.py", "name"]

@dataclass
class MyTestCase:
    db_names: list[str]
    substrings: list[str]
    filename_expected_output: str

    def expected_output(self) -> str:
        with open(f"test-files/{self.filename_expected_output}", 'r') as f:
            return f.read() + '\n'

    def actual_output(self) -> str:
        return subprocess.run(initial_name_args + self.db_names + self.substrings,
                              capture_output=True, text=True).stdout

    def run_test(self) -> None:
        assert self.expected_output() == self.actual_output()

def test1():
    MyTestCase(["openings"], ["bayonet"], 'expected1.txt').run_test()