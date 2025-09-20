import pytest
import sys
import pathlib
from rule_parser import *

folder = pathlib.Path("./test/examples/")
files = list(folder.glob("*.txt"))

@pytest.mark.parametrize("filepath", files, ids=[f.name for f in files])
def test_concrete_examples(filepath: str):
    run_on_file(filepath, sys.stdout)
