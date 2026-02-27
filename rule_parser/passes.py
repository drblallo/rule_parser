from .dialect import *
from typing import List
from functools import singledispatchmethod
import sys

def ancesor_of_type(op: Operation, ancestor_type: type):
    parent = op.parent_op()
    while parent is not None:
        if isinstance(parent, ancestor_type):
            return parent
        parent = parent.parent_op()
    return None

def erase_final_yield(rewriter, region):
    rewriter.erase_op(region.first_block.last_op)

def move_region_content(dest: Region, src: Region):
    for block in list(dest.blocks):
        dest.erase_block(block)
    for block in list(src.blocks):
        src.detach_block(block)
        dest.add_block(block)

def find_parent_of_type(operation: Operation, type) -> Operation:
    parent = operation.parent_op()
    while parent is not None and not isinstance(parent, type):
        parent = parent.parent_op()
    return parent

def move_all_ops(src: Block, dst: Block) -> None:
    # snapshot because we'll mutate src
    ops = list(src.ops)

    # detach every op from the source (keeps SSA uses intact)
    for op in ops:
        src.detach_op(op)

    # append to destination, preserving order
    if dst.is_empty:
        dst.add_ops(ops)
    else:
        # append after the current last op (instead of add_ops which would error
        # if last op is considered a terminator in that context)
        dst.insert_ops_after(ops, dst.last_op)


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

class VerifyPass(ModulePass):
    name = "verify-pass"


    def apply(self, ctx: Context, module: ModuleOp):
        module.verify()

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

    # until effects must be hoisted out into the a global effect with captures
    def extract_until_effects(self, rewriter, module):

        # mark as captured all non local references
        for op in visit(module, ThisSubject):
            op: ThisSubject

            # ToDo: generalize this by saying that some operations override what "this x" means
            if op.result.type == AttackType() and ancesor_of_type(op, MakesAnAttack):
                continue

            until = ancesor_of_type(op, UntilEffect)
            if until is None:
                continue

            capture = CapturedReference.make(op.result)
            rewriter.insert_op(capture, InsertPoint.before(op))
            op.detach()
            rewriter.insert_op(op, InsertPoint.before(until))
            op.result.replace_by_if(capture.result, lambda use: use.operation != capture)



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


    def apply(self, ctx: ModuleOp, module: ModuleOp):
        rewriter = Rewriter()
        self.extract_until_effects(rewriter, module)

# Sometimes, effects are written in a different sentence than the logical place where they are triggered.
class InlineDependantEffects(ModulePass):
    name = "inline-dependant-effects"

    # additional effects appear to specify that a dependant effect is to executed only if the conditional part of the previous sentence is true. that is, it is inlined in the true branch
    def inline_additional_effects(self, rewriter: Rewriter, module: ModuleOp):
        for additional_effect in visit(module, AdditionalEffect):
            additional_effect: AdditionalEffect
            captured_references = list(visit(additional_effect, CapturedReference))
            assert len(captured_references) == 1
            reference = captured_references[0]
            reference: CapturedReference
            referred = reference.value.owner
            referred: Operation
            conditional_effect = find_parent_of_type(referred, ConditionalEffect)
            conditional_effect: ConditionalEffect
            assert conditional_effect != None

            erase_final_yield(rewriter, additional_effect.body)
            rewriter.inline_block(additional_effect.body.first_block, InsertPoint.before(conditional_effect.effect.first_block.last_op))

            reference.result.replace_by(reference.value)
            rewriter.erase_op(reference)

            rewriter.erase_op(additional_effect)




    def apply(self, ctx: Context, module: ModuleOp):
        rewriter = Rewriter()
        objects = []
        self.inline_additional_effects(rewriter, module)

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

    def inline_subject_constraint_region(self, to_inline: Region, func_arg: SSAValue, condition_region: Region, inline_at_start=True):
        rewriter = Rewriter()
        yield_op = to_inline.first_block.last_op
        yield_op: Yield
        is_same = IsSame.make(func_arg, yield_op.value[0])
        yield_op.operands[0] = is_same.result
        merge_preconditions(to_inline.first_block, condition_region, inline_at_start)
        rewriter.insert_op(is_same, InsertPoint.before(condition_region.last_op.prev_op))

    def inline_subject_beloning_constraint_region(self, to_inline: Region, func_arg: SSAValue, condition_region: Region, inline_at_start=True):
        rewriter = Rewriter()
        yield_op = to_inline.first_block.last_op
        yield_op: Yield
        is_same = BelongsTo.make(func_arg, yield_op.value[0])
        rewriter.insert_op(is_same, InsertPoint.before(yield_op))
        yield_op.operands[0] = is_same.result
        merge_preconditions(to_inline.first_block, condition_region, insert_first=inline_at_start)

    def rewrite_conditional_effect_as_function(self, op: MappableOntoFunction):
        new_op = RLCFunction.make(op)
        rewriter = Rewriter()

        rewriter.insert_op(new_op, InsertPoint.before(op))

        if_stmt = IfStatement.make()
        rewriter.insert_op(if_stmt, InsertPoint.at_end(new_op.body.first_block))

        if_stmt_condition = if_stmt.condition.first_block

        yielded_values = []
        for region in [op.condition]:
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
        rewriter.erase_op(op.effect.first_block.last_op)
        rewriter.inline_block(op.effect.first_block, InsertPoint.before(if_stmt.true_branch.first_block.last_op))

        return (new_op, if_stmt.condition.first_block, if_stmt.true_branch.first_block)

    def apply(self, ctx: ModuleOp, module: ModuleOp):
        rewriter = Rewriter()
        for op in visit(module, ObtainWeaponAbility):
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function(op)
            self.inline_subject_beloning_constraint_region(op.beneficient, func.get_arg("evaluated_model"), cond, False)
            rewriter.insert_op(GiveWeaponAbility.make(func.get_arg('evaluated_model'), op.ability, op.qualifier), InsertPoint.at_start(true_branch))
            rewriter.erase_op(op)

        for op in visit(module, ObtainInvulnerableSave):
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function(op)
            self.inline_subject_constraint_region(op.beneficient, func.get_arg("evaluated_model"), cond, False)
            rewriter.insert_op(GiveInvulterability.make(op.value, func.get_arg('evaluated_model')), InsertPoint.at_start(true_branch))
            rewriter.erase_op(op)

        for op in visit(module, ModifyCharacteristic):
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function(op)
            self.inline_subject_constraint_region(op.beneficient, func.get_arg("evaluated_model"), cond, False)
            rewriter.insert_op(GiveCharacteristicModifier.make(func.get_arg("evaluated_model"), op.characteristic, op.quantity), InsertPoint.at_start(true_branch))
            rewriter.erase_op(op)

        for op in visit(module, TimedEffect):
            op: TimedEffect
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function(op)
            rewriter.erase_op(op)

        for op in visit(module, MakesAnAttack):
            op: MakesAnAttack
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function(op)
            self.inline_subject_constraint_region(op.subject, func.get_arg("source_model"), cond)
            rewriter.erase_op(op)

        for op in visit(module, Destroys):
            op: Destroys
            (func, cond, true_branch) = self.rewrite_conditional_effect_as_function(op)
            self.inline_subject_constraint_region(op.source, func.get_arg("source_model"), cond)
            self.inline_subject_constraint_region(op.target, func.get_arg("target_model"), cond)
            rewriter.erase_op(op)

def merge_preconditions(to_move: Block, target: Block, insert_first=True):
    rewriter = Rewriter()
    for op in reversed(list(to_move.ops)[:-1]):
        op.detach()
        target.insert_op_before(op, target.first_op if insert_first else target.last_op)

    for arg1, arg2 in zip(to_move.args, target.args):
        arg1.replace_by(arg2)

    and_op = And.make(to_move.last_op.value, target.last_op.value)
    target.insert_op_before(and_op, target.last_op)
    target.last_op.operands[0] = and_op.result

class DropUselessOperations(ModulePass):
    name = "drop-useless-operations-pass"

    def apply(self, ctx: OpResult, module: ModuleOp):
        rewriter = Rewriter()

        # if thre is a belongs(subjectsIn(X)) just write belongsTo(x)
        for op in visit(module, BelongsTo):
            unit = op.rhs.owner
            if isinstance(unit, SubjectsIn):
                if unit.result.uses.get_length() == 1:
                   unit.result.replace_by(unit.unit)
                   rewriter.erase_op(unit)


        # if there is a pure operation that returns a unit X, and that unit has two users, and those users are is_leading Y X and belongs_to Z X, then we can rewrite as X = leaded_unit Y, belongs_to Z X
        for op in visit_traits(module, Pure):
            op: Operation
            if len(op.results) != 1 or not isinstance(op.result_types[0], UnitType):
                continue

            if op.results[0].uses.get_length() != 2:
                continue
            (belongs_to, leading) = op.results[0].uses
            (belongs_to, leading) = (belongs_to.operation, leading.operation)
            if not isinstance(belongs_to, BelongsTo):
                (belongs_to, leading) = (leading, belongs_to)
            if not isinstance(belongs_to, BelongsTo) or not isinstance(leading, Leading):
                continue
            leading: Leading
            belongs_to: BelongsTo

            leaded = LeadedUnit.make(leading.leader, UnitType())
            op.results[0].replace_by(leaded.unit)
            leading.result.replace_by(leaded.result)
            rewriter.insert_op(leaded, InsertPoint.before(op))
            rewriter.erase_op(leading)
            rewriter.erase_op(op)



        # if there is a Y = OneOf X followed by a IsSame Y Z, just replace them both with BelongsTo Z X
        for op in visit(module, IsSame):
            op: IsSame
            if isinstance(op.rhs.owner, OneOf) and op.rhs.uses.get_length() == 1:
                any_of: OneOf
                any_of = op.rhs.owner
                subject_list = any_of.base_subject.first_block.last_op.value
                rewriter.erase_op(any_of.base_subject.first_block.last_op)
                rewriter.inline_block(any_of.base_subject.first_block, InsertPoint.before(any_of))
                belongs_to = BelongsTo.make(op.lhs, subject_list)
                rewriter.insert_op(belongs_to, InsertPoint.before(op))
                op.result.replace_by(belongs_to.result)
                rewriter.erase_op(op)
                rewriter.erase_op(any_of)

            if isinstance(op.lhs.owner, OneOf) and op.lhs.uses.get_length() == 1:
                any_of: OneOf
                any_of = op.lhs.owner
                subject_list = any_of.base_subject.first_block.last_op.value
                rewriter.erase_op(any_of.base_subject.first_block.last_op)
                rewriter.inline_block(any_of.base_subject.first_block, InsertPoint.before(any_of))
                belongs_to = BelongsTo.make(op.rhs, subject_list)
                rewriter.insert_op(belongs_to, InsertPoint.before(op))
                op.result.replace_by(belongs_to.result)
                rewriter.erase_op(op)
                rewriter.erase_op(any_of)

        # if there is a BelongsTo(X, All()), replace with True
        for op in visit(module, BelongsTo):
            unit = op.rhs.owner
            if isinstance(unit, All):
                if unit.result.uses.get_length() == 1:
                   true_op = TrueOp.make()
                   op.result.replace_by(true_op.result)
                   rewriter.insert_op(true_op, InsertPoint.before(op))
                   rewriter.erase_op(op)
                   rewriter.erase_op(unit)

        for op in visit(module, BelongsTo):
            unit = op.rhs.owner
            unit: FilterList
            if isinstance(unit, FilterList) and isinstance(unit.single_base_subject(), All):
                if unit.result.uses.get_length() != 1:
                    continue

                unit.constraint.first_block.args[0].replace_by(op.model)
                op.result.replace_by(unit.constraint.first_block.last_op.value[0])
                rewriter.erase_op(unit.constraint.first_block.last_op)
                rewriter.inline_block(unit.constraint.first_block, InsertPoint.before(op))
                rewriter.erase_op(op)
                rewriter.erase_op(unit)

        for op in visit(module, IfStatement):
            op: IfStatement
            if len(op.condition.first_block.ops) != 2:
                continue
            yield_op = op.condition.first_block.last_op
            if yield_op.value[0].owner != op.condition.first_block.first_op:
                continue
            if isinstance(yield_op.value[0].owner, TrueOp):
                rewriter.erase_op(op.true_branch.first_block.last_op)
                rewriter.inline_block(op.true_branch.first_block, InsertPoint.before(op))
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



class FlattenConditionalsPass(ModulePass):
    name = "flatten-conditionals-pass"

    # if a conditional effect has multiple prencoditionalble effects, we are going to split the conditional effect into multiple copies, each that contains one of the preconditionable effects.
    def split_conditional_effects(self, writer: Rewriter, module: ModuleOp):
        for effect in visit(module, ConditionalEffect):
            effect: ConditionalEffect
            effects_to_split = list(effect.effect.first_block.ops)[:-1]
            if not all(op.has_trait(HasPreconditions) for op in effects_to_split):
                continue

            for index1, op in enumerate(effects_to_split):
                clone = effect.clone()
                writer.insert_op(clone, InsertPoint.before(effect))
                clone: ConditionalEffect
                for index2, cloned_effect in enumerate(list(clone.effect.first_block.ops)[:-1]):
                    if index2 != index1:
                        writer.erase_op(cloned_effect)
            writer.erase_op(effect)


    def apply(self, ctx: Context, module: ModuleOp):
        rewriter = Rewriter()

        self.split_conditional_effects(rewriter, module)

        # if a conditional effect has only one conditional child, inline the conditional effect in the child
        for op in visit(module, ConditionalEffect):
            if len(op.effect.first_block.ops) == 2 and op.effect.first_block.first_op.has_trait(HasPreconditions):
                merge_preconditions(op.condition.first_block, op.effect.first_block.first_op.condition.first_block)
                rewriter.erase_op(op.effect.first_block.last_op)
                rewriter.inline_block(op.effect.first_block, InsertPoint.before(op))
                rewriter.erase_op(op)

        # if a conditional effect is the only child of a conditional parent, inline into the parent
        for op in visit(module, ConditionalEffect):
            parent = op.parent_op()
            parent: HasPreconditions
            if parent.has_trait(HasPreconditions) and len(parent.effect.first_block.ops) == 2 and parent.effect.first_block.first_op == op:
                merge_preconditions(op.condition.first_block, parent.condition.first_block, insert_first=False)
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
                op.result.replace_by(parent.get_arg("self_model"))
            elif isinstance(op.result.type, AttackType):
                op.result.replace_by(parent.get_arg("attack"))
            elif isinstance(op.result.type, AbilityType):
                new_value = ThisAbility.make()
                rewriter.insert_op(new_value, InsertPoint.before(op))
                op.result.replace_by(new_value.result)
            else:
                print(op)
                raise NotImplementedError()
            rewriter.erase_op(op)

class ReplaceUnboundedSubjectsWithLoops(ModulePass):
    name = "replace-unbounded-subjects-with-loops"
    def apply(self, ctx: Context, module: ModuleOp):
        rewriter = Rewriter()

        for rlc_fun in visit(module, RLCFunction):
            for node in visit(rlc_fun, OneOf):
                node: OneOf
                for_op = ForAllStatement.make(node.base_subject.first_block.last_op.value[0])
                node.result.replace_by(for_op.body.first_block.args[0])
                move_all_ops(rlc_fun.body.first_block, for_op.body.first_block)
                move_all_ops(node.base_subject.first_block, rlc_fun.body.first_block)
                rewriter.erase_op(rlc_fun.body.first_block.last_op)
                rewriter.insert_op(for_op, InsertPoint.at_end(rlc_fun.body.first_block))
                rewriter.insert_op(Yield.make(), InsertPoint.at_end(for_op.body.first_block))
                rewriter.insert_op(Yield.make(), InsertPoint.at_end(rlc_fun.body.first_block))
                rewriter.erase_op(node)


class OptimizeFilteringPass(ModulePass):
    name = "optimize-filtering-pass"

    def apply(self, ctx: Context, module: ModuleOp):
        rewriter = Rewriter()

        for op in visit_traits(module, CanDefineOperand):
            if isinstance(op.get_optionally_defined_operand().owner, All):
                op.replace_with_operand_defining_op(rewriter)

        for op in visit(module, FilterList):
            subject = op.single_base_subject()
            constraint = op.single_constraint()
            if isinstance(constraint, BelongsTo) and isinstance(subject, All):
                subject.detach()
                rewriter.insert_op(subject, InsertPoint.before(op))
                new_op = SubjectsIn.make(constraint.rhs)
                rewriter.insert_op(new_op, InsertPoint.before(op))
                op.result.replace_by(new_op.result)
                rewriter.erase_op(op)


