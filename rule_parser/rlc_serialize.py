from .dialect import *
from functools import singledispatchmethod

class RLCSerializer(ModulePass):
    def __init__(self, out):
        self.out = out
        self.value_to_var_name = {}
        self.index = 0
        self.indentation_level = 0
        self.new_line = True

    def apply(self, ctx: Context, module: ModuleOp):
        for index, op in enumerate(module.body.ops):
            if isinstance(op, GlobalTemporaryEffect):
                self.value_to_var_name[op.result] = f"global_temporary_effect{index}"
        self.visit(module)

    @singledispatchmethod
    def visit_expression(self, node):
        if isinstance(node, SSAValue):
            if isinstance(node.owner, Block):
                self.write_var(node)
            else:
                self.visit_expression(node.owner)
            return
        print(type(node))
        raise NotImplementedError()

    @visit_expression.register
    def _(self, node: WithinRange):
        self.visit_expression(node.source)
        self.print(".is_within_range(")
        self.visit_expression(node.target)
        self.print(f", {node.distance.data})")

    @visit_expression.register
    def _(self, node: WithinEngagementRange):
        self.visit_expression(node.source)
        self.print(".is_in_engagement_range(")
        self.visit_expression(node.target)
        self.print(")")

    @visit_expression.register
    def _(self, cond: PlayerAttr):
        self.print(f"Player::{cond.data}")

    @visit_expression.register
    def _(self, cond: IsOwnedBy):
        self.print("owned_by(")
        self.write_var(cond.unit)
        self.print(", ")
        self.visit_expression(cond.player)
        self.print(")")

    @visit_expression.register
    def _(self, node: And):
        self.visit_expression(node.lhs)
        self.print(" and ")
        self.visit_expression(node.rhs)

    @visit_expression.register
    def _(self, node: Yield):
        self.visit_expression(node.value)

    @singledispatchmethod
    def visit(self, node):
        print(type(node))
        raise NotImplementedError()

    def println(self, string):
        self.print(string + "\n")
        self.new_line = True

    def print(self, string):
        if self.new_line:
            self.out.write((" " * self.indentation_level) )
        self.out.write(string)
        self.new_line = False


    @visit.register
    def _(self, module: ModuleOp):
        self.builder = Builder(InsertPoint.at_start(module.body.first_block))
        for op in list(module.body.ops):
            self.visit(op)

    @visit.register
    def _(self, cond: IntAttr):
        self.print(f"{cond.data}")

    @visit.register
    def _(self, cond: PlayerAttr):
        self.print(f"Player::{cond.data}")

    @visit.register
    def _(self, cond: KeywordAttr):
        self.print(f"Keyword::{cond.data}")

    @visit.register
    def _(self, cond: IsOwnedBy):
        self.declare_var(cond.result)
        self.print(f" = ")
        self.write_var(cond.unit)
        self.print(f".is_owned_by(")
        self.visit(cond.player)
        self.println(f")")


    @visit.register
    def _(self, cond: GainCP):
        self.print("gain_cp(")
        self.visit(cond.quantity)
        self.println(")")

    @visit.register
    def _(self, cond: IsSame):
        self.declare_var(cond.result)
        self.print(" = ")
        self.write_var(cond.rhs)
        self.print(" == ")
        self.write_var(cond.lhs)
        self.println("")

    @visit.register
    def _(self, cond: HasKeyword):
        self.declare_var(cond.result)
        self.print(f" = ")
        self.write_var(cond.unit)
        self.print(f".has_keyword(")
        self.visit(cond.keyword)
        self.println(f")")

    @visit.register
    def _(self, cond: RollKindAttr):
        self.print(f"RollKind::{cond.data}")

    @visit.register
    def _(self, cond: ModifyRoll):
        self.write_var(cond.to_modify)
        self.print(".modify_roll(")
        self.visit(cond.roll)
        self.print(", ")
        self.visit(cond.quantity)
        self.println(")")

    @visit.register
    def _(self, cond: GlobalTemporaryEffect):
        self.print("global_effect ")
        self.write_var(cond.result)
        self.print("(")
        self.print_args(cond.effect.first_block.args)
        self.println("):")
        self.indentation_level = self.indentation_level + 1
        for op in list(cond.effect.ops)[:-1]:
            self.visit(op)
        self.indentation_level = self.indentation_level - 1

    @visit.register
    def _(self, cond: CreateTemporaryEffect):
        self.print("create_temporary_effect(")
        self.write_var(cond.effect)
        self.print("(")
        for operand in cond.args:
            self.write_var(operand)
            self.print(", ")
        self.print(")")
        self.println(")")

    @visit.register
    def _(self, cond: Yield):
        if cond.value is None:
            return
        self.write_var(cond.value)

    @visit.register
    def _(self, cond: WeaponAbilityAttr):
        self.print("WeaponAbility(WeaponAbilityKind::" + str(cond.ability.data) + f", {cond.value.data})")

    @visit.register
    def _(self, cond: CharacteristicAttr):
        self.print("Characteristic::" + str(cond.data))

    @visit.register
    def _(self, cond: WeaponQualifierKindAttr):
        self.print("WeaponQualifierKind::" + str(cond.data))

    def write_type(self, type):
        if isinstance(type, ModelType):
            self.print("Model")
        elif isinstance(type, UnitType):
            self.print("Unit")
        elif isinstance(type, AttackType):
            self.print("Attack")
        else:
            raise NotImplementedError()

    def print_args(self, args):
        for arg in args:
            arg: SSAValue
            self.write_type(arg.type)
            self.print(" ")
            self.declare_var(arg, False, arg.name_hint)
            self.print(", ")

    @visit.register
    def _(self, cond: GiveCharacteristicModifier):
        self.print("add_characteristic_modifier(")
        self.write_var(cond.beneficient)
        self.print(", ")
        self.visit(cond.characteristic)
        self.print(", ")
        self.visit(cond.quantity)
        self.println(")")


    @visit.register
    def _(self, cond: GiveWeaponAbility):
        self.print("add_ability(")
        self.write_var(cond.beneficient)
        self.print(", ")
        self.visit(cond.ability)
        self.print(", ")
        self.visit(cond.qualifier)
        self.println(")")


    @visit.register
    def _(self, cond: ForAllStatement):
        self.print("for ")
        self.declare_var(cond.body.first_block.args[0])
        self.print(" in ")
        self.write_var(cond.iterable)
        self.println(":")
        self.indentation_level = self.indentation_level + 1
        for op in list(cond.body.ops)[:-1]:
            self.visit(op)
        self.indentation_level = self.indentation_level - 1

    @visit.register
    def _(self, cond: IfStatement):
        for op in list(cond.condition.ops)[:-1]:
            self.visit(op)
        self.print("if ")
        self.write_var(cond.condition.first_block.last_op.value)
        self.println(":")
        self.indentation_level = self.indentation_level + 1
        for op in list(cond.true_branch.ops)[:-1]:
            self.visit(op)
        self.indentation_level = self.indentation_level - 1

    @visit.register
    def _(self, cond: RLCFunction):
        self.print(f"def {cond.sym_name.data}(")
        self.print_args(cond.body.first_block.args)
        self.println("):")
        self.indentation_level = self.indentation_level + 1
        for op in list(cond.body.ops):
            self.visit(op)
        self.indentation_level = self.indentation_level - 1

    @visit.register
    def _(self, cond: Any):
        self.declare_var(cond.result)
        self.println(f"= all_{cond.result.type.underlying.name[4:]}s()")

    def declare_var(self, result: SSAValue, write_let=True, name: str = None):
        if write_let:
            self.print(f"ref ")
        name = name if name is not None else f"var{self.index}"
        self.print(name + " ")
        self.value_to_var_name[result] = name
        self.index = self.index + 1

    def write_var(self, result: SSAValue):
        self.print(self.value_to_var_name[result])

    @visit.register
    def _(self, cond: ThisSubject):
        self.declare_var(cond.result)
        if cond.result.type == UnitType():
            self.println("= this_unit")
        elif cond.result.type == ModelType():
            self.println("= this_model")
        else:
            raise NotImplementedError()

    @visit.register
    def _(self, cond: TimeInstantAttr):
        self.print(cond.data)

    @visit.register
    def _(self, cond: TimeQualifierAttr):
        self.print(cond.data)

    @visit.register
    def _(self, cond: TrueOp):
        self.declare_var(cond.result)
        self.println("= true")

    @visit.register
    def _(self, cond: TimeEventType):
        self.print(f"act on_")
        self.visit(cond.time_instant)
        self.print("_")
        self.visit(cond.time_qualifier)
        self.println("():")

    @visit.register
    def _(self, cond: SelectSubject):
        self.value_to_var_name[cond.result] = cond.condition.first_block.args[0].name_hint
        self.print(f"act select(")
        self.print_args(cond.condition.first_block.args)
        self.print(") {")
        self.visit_expression(cond.condition.first_block.last_op)
        self.println("}")

    @visit.register
    def _(self, cond: TimedEffect):
        self.visit(cond.event)
        self.indentation_level = self.indentation_level + 1
        for op in list(cond.condition.ops)[:-1]:
            self.visit(op)
        self.print("if ")
        self.write_var(cond.condition.first_block.last_op.value)
        self.println(":")
        self.indentation_level = self.indentation_level + 1
        for op in list(cond.effect.ops):
            self.visit(op)
        self.indentation_level = self.indentation_level - 2

    @visit.register
    def _(self, cond: And):
        self.declare_var(cond.result)
        self.print("= ")
        self.write_var(cond.lhs)
        self.print(" and ")
        self.write_var(cond.rhs)
        self.println("")

    @visit.register
    def _(self, cond: BelongsTo):
        self.declare_var(cond.result)
        self.print("= ")
        self.write_var(cond.rhs)
        self.print(".contain(")
        self.write_var(cond.model)
        self.println(")")


    @visit.register
    def _(self, node: WithinRange):
        self.declare_var(node.result)
        self.print("= ")
        self.write_var(node.source)
        self.print(".is_within_range(")
        self.write_var(node.target)
        self.println(f", {node.distance.data})")

    @visit.register
    def _(self, cond: LeadedUnit):
        self.declare_var(cond.result)
        self.print("= ")
        self.write_var(cond.leader)
        self.print(".is_leading_unit(")
        self.println(")")

        self.declare_var(cond.unit)
        self.print("= unit_of(")
        self.write_var(cond.leader)
        self.println(")")

    @visit.register
    def _(self, cond: Leading):
        self.declare_var(cond.result)
        self.print("= ")
        self.write_var(cond.leader)
        self.print(".is_leading(")
        self.write_var(cond.unit)
        self.println(")")

    @visit.register
    def _(self, cond: SubjectsIn):
        self.declare_var(cond.result)
        self.print("= ")
        self.write_var(cond.unit)
        self.println(".models")

    @visit.register
    def _(self, cond: AnyMatchingSubject):
        for op in list(cond.base_subject.ops)[:-1]:
            self.visit(op)
        self.declare_var(cond.result)
        self.println("= []")
        self.print("for ")
        self.declare_var(cond.constraint.first_block.args[0])
        self.print(" in ")
        self.write_var(cond.base_subject.first_block.last_op.value)
        self.println(":")
        self.indentation_level = self.indentation_level + 1
        self.print("if ")
        self.visit_expression(cond.constraint.first_block.last_op.value)
        self.println(":")
        self.indentation_level = self.indentation_level + 1
        self.write_var(cond.result)
        self.print(".append(")
        self.write_var(cond.base_subject.first_block.last_op.value)
        self.println(")")
        self.indentation_level = self.indentation_level - 2


    @visit.register
    def _(self, cond: ConditionalEffect):
        for op in list(cond.condition.ops)[:-1]:
            self.visit(op)
        self.print("if ")
        self.write_var(cond.condition.first_block.last_op.value)
        self.println(":")
        self.indentation_level = self.indentation_level + 1
        for op in list(cond.effect.ops):
            self.visit(op)
        self.indentation_level = self.indentation_level - 1

