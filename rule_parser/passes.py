from .dialect import *
from typing import List
from functools import singledispatchmethod

def dominates(dominator: Operation, dominatee: Operation):
    must_contain = dominator.parent_op()
    parent = dominatee
    while parent is not None:
        if isinstance(parent, UntilEffect):
            return False
        if must_contain == parent:
            return True
        parent = parent.parent_op()
    return False

class PrintModulePass(ModulePass):
    name = "print-module-pass"

    def __init__(self, out):
        super().__init__()
        self.printer = Printer(out)

    def apply(self, ctx: Context, module: ModuleOp):
        self.printer.print_op(module)

def visit(module, type):
    ops = [op for op in module.walk() if isinstance(op, type)]
    for op in ops:
        yield op

def visit_traits(module, trait):
    ops = [op for op in module.walk() if op.has_trait(trait)]
    for op in ops:
        yield op

class ExtractTemporaryEffectsPass(ModulePass):
    name = "extract-temporary-effecs"

    def apply(self, ctx: ModuleOp, module: ModuleOp):
        rewriter = Rewriter()
        captures = [capture for capture in visit(module, CapturedReference)]

        for op in visit(module, UntilEffect):
            op: UntilEffect

            effect = op.effect
            effect_b = effect.first_block

            operands = []

            for index, capture in enumerate(captures):
                capture: CapturedReference
                effect_b.insert_arg(capture.result.type, index)
                operands.append(capture.value)

                capture.result.replace_by(effect_b.args[index])
                rewriter.erase_op(capture)

            effect.detach_block(0)

            temporary_effect = GlobalTemporaryEffect.make(effect_b)
            rewriter.insert_op(temporary_effect, InsertPoint.at_end(module.body.first_block))

            create_temporary_effect = CreateTemporaryEffect.make(temporary_effect.result, operands)
            rewriter.insert_op(create_temporary_effect, InsertPoint.after(op))
            rewriter.erase_op(op)


class InlineDependantEffects(ModulePass):
    name = "inline-dependant-effects"

    def apply(self, ctx: ModuleOp, module: ModuleOp):
        rewriter = Rewriter()
        objects = []
        for top_level_object in list(module.body.ops):
            objects.append([])
            for op in visit(top_level_object, CapturedReference):
                objects[-1].append(op)

        for top_level_object, objs in zip(list(module.body.ops), objects):
            for obj in objs:
                top_level_object.detach()
                rewriter.insert_op(top_level_object, InsertPoint.after(obj.value.owner))
                break

        for op in visit(module, CapturedReference):
            op: CapturedReference
            if dominates(op.value.owner, op):
                op.result.replace_by(op.value)
                rewriter.erase_op(op)

class RewriteEventsPass(ModulePass):
    name = "rewrite-events-pass"

    def rewrite_conditional_effect_as_function(self, regions: List[Region], new_op: RLCFunction):
        rewriter = Rewriter()
        rewriter.insert_op(new_op, InsertPoint.before(regions[0].parent_op()))

        if_stmt = IfStatement.make()
        rewriter.insert_op(if_stmt, InsertPoint.at_end(new_op.body.first_block))

        if_stmt_condition = if_stmt.condition.first_block

        yielded_values = []
        for region in regions:
            yielded_value = region.first_block.last_op.value
            rewriter.erase_op(region.first_block.last_op)
            rewriter.inline_block(region.first_block, InsertPoint.at_start(if_stmt_condition))
            yielded_values.append(yielded_value)

        final_to_yield = yielded_values[0]
        for value in yielded_values[1:]:
            and_op = And.make(final_to_yield, value)
            rewriter.insert_op(and_op, InsertPoint.at_end(if_stmt_condition))
            final_to_yield = and_op

        yield_op = Yield.make(final_to_yield)
        rewriter.insert_op(yield_op, InsertPoint.at_end(if_stmt_condition))

        rewriter.insert_op(Yield.create(), InsertPoint.at_end(if_stmt.true_branch.first_block))

        return (new_op, if_stmt.condition.first_block, if_stmt.true_branch.first_block)

    def apply(self, ctx: ModuleOp, module: ModuleOp):
        rewriter = Rewriter()
        for op in visit(module, ObtainWeaponAbility):
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function([op.condition], RLCFunction.make_event("on_evaluate_weapon_abilities"))
            condition_value1 = cond.last_op.value
            rewriter.erase_op(cond.last_op)

            acceptable_models = op.beneficient.first_block.last_op.value
            rewriter.erase_op(op.beneficient.first_block.last_op)
            rewriter.inline_block(op.beneficient.first_block, InsertPoint.at_end(cond))

            belongs_to = BelongsTo.make(func.body.first_block.args[3], acceptable_models)
            rewriter.insert_op(belongs_to, InsertPoint.after(cond.last_op))
            and_op = And.make(condition_value1, belongs_to.result)
            rewriter.insert_op(and_op, InsertPoint.after(cond.last_op))
            rewriter.insert_op(Yield.make(and_op), InsertPoint.after(cond.last_op))

            rewriter.erase_op(op)
            rewriter.insert_op(GiveWeaponAbility.make(func.body.first_block.args[3], op.ability, op.qualifier), InsertPoint.at_start(true_branch))

        for op in visit(module, TimedEffect):
            op: TimedEffect
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function([op.condition], RLCFunction.make_time_event(op.event_name()))
            rewriter.erase_op(op.effect.first_block.last_op)
            rewriter.inline_block(op.effect.first_block, InsertPoint.at_start(true_branch))
            rewriter.erase_op(op)

        for op in visit(module, MakesAnAttack):
            op: MakesAnAttack
            func = RLCFunction.make_attack_event("on_attack")
            op.condition.first_block.args[0].replace_by(func.get_attack_source())
            op.condition.first_block.args[1].replace_by(func.get_attack_target())
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function([op.condition], func)
            op.effect.first_block.args[0].replace_by(func.get_attack_source())
            op.effect.first_block.args[1].replace_by(func.get_attack_target())
            rewriter.erase_op(op.effect.first_block.last_op)
            rewriter.inline_block(op.effect.first_block, InsertPoint.before(true_branch.last_op))
            rewriter.erase_op(op)

        for op in visit(module, Destroys):
            op: Destroys
            func = RLCFunction.make_attack_event("on_destroys")
            op.source.first_block.args[0].replace_by(func.get_attack_source())
            op.target.first_block.args[0].replace_by(func.get_attack_target())
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function([op.source, op.target], func)
            op.effect.first_block.args[0].replace_by(func.get_attack_source())
            op.effect.first_block.args[1].replace_by(func.get_attack_target())
            rewriter.erase_op(op.effect.first_block.last_op)
            rewriter.inline_block(op.effect.first_block, InsertPoint.before(true_branch.last_op))
            rewriter.erase_op(op)

def merge_preconditions(to_move: Block, target: Block):
    rewriter = Rewriter()
    for op in reversed(list(to_move.ops)[:-1]):
        op.detach()
        target.insert_op_before(op,target.first_op)

    for arg1, arg2 in zip(to_move.args, target.args):
        arg1.replace_by(arg2)

    and_op = And.make(to_move.last_op.value, target.last_op.value)
    target.insert_op_before(and_op, target.last_op)
    target.last_op.operands[0] = and_op.result

class DropUselessOperations(ModulePass):
    name = "drop-useless-operations-pass"

    def apply(self, ctx: OpResult, module: ModuleOp):
        rewriter = Rewriter()
        for op in visit(module, IsSame):
            op: IsSame
            if isinstance(op.lhs.owner, Any) or isinstance(op.rhs.owner, Any):
                true_op = TrueOp.make()
                rewriter.insert_op(true_op, InsertPoint.before(op))
                op.result.replace_by(true_op.result)
                rewriter.erase_op(op)

        for op in visit(module, And):
            if isinstance(op.lhs.op, TrueOp):
                op.result.replace_by(op.rhs)
                inner = op.lhs.op
                rewriter.erase_op(op)
                rewriter.erase_op(inner)
                continue
            if isinstance(op.rhs.op, TrueOp):
                op.result.replace_by(op.lhs)
                inner = op.rhs.op
                rewriter.erase_op(op)
                rewriter.erase_op(inner)


        for op in visit(module, BelongsTo):
            unit = op.rhs.owner
            if isinstance(unit, SubjectsIn):
                if unit.result.uses.get_length() == 1:
                   unit.result.replace_by(unit.unit)
                   rewriter.erase_op(unit)

        for op in visit(module, IfStatement):
            op: IfStatement
            if len(op.condition.first_block.ops) != 2:
                continue
            yield_op = op.condition.first_block.last_op
            if yield_op.value.owner != op.condition.first_block.first_op:
                continue
            if isinstance(yield_op.value.owner, TrueOp):
                rewriter.erase_op(op.true_branch.first_block.last_op)
                rewriter.inline_block(op.true_branch.first_block, InsertPoint.before(op))
                rewriter.erase_op(op)


class FlattenConditionalsPass(ModulePass):
    name = "flatten-conditionals-pass"

    def apply(self, ctx: Context, module: ModuleOp):
        rewriter = Rewriter()

        for op in visit(module, ConditionalEffect):
            if len(op.effect.first_block.ops) == 2 and op.effect.first_block.first_op.has_trait(HasPreconditions):
                merge_preconditions(op.condition.first_block, op.effect.first_block.first_op.condition.first_block)
                rewriter.erase_op(op.effect.first_block.last_op)
                rewriter.inline_block(op.effect.first_block, InsertPoint.before(op))
                rewriter.erase_op(op)

class ResolveAbsoluteReferencesPass(ModulePass):
    name = "resolve-absolute-references-pass"

    def apply(self, ctx: Context, module: ModuleOp):
        rewriter = Rewriter()
        for op in visit(module, ThisSubject):
            parent: RLCFunction
            parent = op.parent_op()
            while parent and not isinstance(parent, RLCFunction):
                parent = parent.parent_op()
            if not parent:
                continue
            if isinstance(op.result.type, ModelType):
                op.result.replace_by(parent.get_this_model())
            elif isinstance(op.result.type, AttackType):
                op.result.replace_by(parent.get_attack_attack())
            else:
                raise NotImplementedError()
            rewriter.erase_op(op)


class OptimizeFilteringPass(ModulePass):
    name = "optimize-filtering-pass"

    def apply(self, ctx: Context, module: ModuleOp):
        rewriter = Rewriter()

        for op in visit_traits(module, CanDefineOperand):
            if isinstance(op.get_optionally_defined_operand().owner, Any):
                op.replace_with_operand_defining_op(rewriter)

        for op in visit(module, AnyMatchingSubject):
            subject = op.single_base_subject()
            constraint = op.single_constraint()
            if isinstance(constraint, BelongsTo) and isinstance(subject, Any):
                subject.detach()
                rewriter.insert_op(subject, InsertPoint.before(op))
                new_op = SubjectsIn.make(constraint.rhs)
                rewriter.insert_op(new_op, InsertPoint.before(op))
                op.result.replace_by(new_op.result)
                rewriter.erase_op(op)

