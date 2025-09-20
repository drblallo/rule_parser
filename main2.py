import argparse
import traceback
import sys
from rule_parser import *

def parse(text):
    with open("./40k.lark", encoding="utf-8") as f:
        grammar = f.read()

    parser = Lark(grammar, start="start", parser="earley")
    tree = parser.parse(text)
    transformer = ToAst()
    ast = transformer.visit(tree)
    return ast

def make_pipeline(args, out):
    passes = []
    if args.unchecked:
        passes.append(PrintModulePass(out))
        return passes

    passes.append(SemanticalAnalyzer())
    if args.type_checked:
        passes.append(PrintModulePass(out))
        return passes

    passes.append(InlineDependantEffects())
    if args.after_inline:
        passes.append(PrintModulePass(out))
        return passes
    passes.append(ExtractTemporaryEffectsPass())

    passes.append(OptimizeFilteringPass())
    passes.append(FlattenConditionalsPass())
    if args.canonicalized:
        passes.append(PrintModulePass(out))
        return passes
    passes.append(RewriteEventsPass())
    passes.append(ResolveAbsoluteReferencesPass())
    passes.append(DropUselessOperations())
    passes.append(CanonicalizePass())
    if args.before_printing:
        passes.append(PrintModulePass(out))
        return passes
    passes.append(RLCSerializer(out))
    return passes

def run_pipeline(ast: ModuleOp, args, out):
    pm = PassPipeline(make_pipeline(args, out))

    ctx = Context()
    pm.apply(ctx, ast)

def main():
    ap = argparse.ArgumentParser(
        description="Parse game rules and turns them into rulebook code."
                    "Pass '-' to read from stdin.")
    ap.add_argument("path", help="path to dump file or '-' for stdin", default="-", nargs="?")
    ap.add_argument("-o", help="output", default="-", nargs="?")
    ap.add_argument("--unchecked", action='store_true', default=False)
    ap.add_argument("--type-checked", action='store_true', default=False)
    ap.add_argument("--canonicalized", action='store_true', default=False)
    ap.add_argument("--before-printing", action='store_true', default=False)
    ap.add_argument("--after-inline", action='store_true', default=False)
    ap.add_argument("--verify", action='store_true', default=False)
    args = ap.parse_args()

    content = sys.stdin if args.path == "-" else open(args.path, encoding="utf-8")
    out = sys.stdout if args.o == "-" else open(args.o, "w+")

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
