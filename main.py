#!/home/massimo/Documents/40k/rule_parser/.venv/bin/python

import traceback
import sys
from rule_parser import *


def main():
    ap = get_arg_parser()
    args = ap.parse_args()

    out = sys.stdout if args.o == "-" else open(args.o, "w+")
    content = sys.stdin if args.path == "-" else open(args.path, encoding="utf-8")
    ast = parse("".join(content.readlines()))

    printer = Printer(out)
    try:
        run_pipeline(ast, args, out)
    except Exception:
        print(traceback.format_exc())
        print(ast)
    if args.verify:
        ast.verify()


if __name__ == "__main__":
    main()
