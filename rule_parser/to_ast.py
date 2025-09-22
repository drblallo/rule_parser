from lark import Lark, ast_utils, Tree, Token
from lark.visitors import Interpreter
from typing import List
from functools import singledispatchmethod
from .dialect import *

class Scope:
    def __init__(self, to_ast: 'ToAst', region: Region= None, subject: SSAValue = None):
        self.to_ast = to_ast
        self.pop_block = region is not None
        self.region = region
        self.subject = subject
        if self.pop_block:
            self.insertion_point_to_restore = to_ast.buider.insertion_point
            to_ast.buider.insertion_point = InsertPoint.at_start(region.first_block)

    def __enter__(self):
        self.to_ast.scopes.append(self)

    def current_subject(self) -> SSAValue:
        return self.subject

    def __exit__(self, *args):
        if self.pop_block:
            self.to_ast.buider.insertion_point = self.insertion_point_to_restore
        self.to_ast.scopes.pop(-1)

class ToAst(Interpreter):
    def __init__(self):
        super().__init__()
        self.module = ModuleOp(Region(Block()))
        self.buider = Builder(InsertPoint(self.module.body.first_block))
        self.scopes = [Scope(self, None)]

    def make_scope(self, region: Region = None, subject: SSAValue = None):
        return Scope(self, region=region, subject=subject)

    def current_subject(self) -> SSAValue:
        return self.scopes[-1].current_subject()

    def add(self, operation):
        self.buider.insert(operation)
        return operation

    def __default__(self, tree):
        print(tree)
        raise NotImplementedError()

    def start(self, node: Tree):
        self.visit_children(node)
        return self.module

    def effect(self, node):
        self.visit_children(node)

    def effect_seq(self, node):
        effects = self.visit_children(node)

    def single_effect(self, node):
        self.visit_children(node)

    def battle_shock_step(self, node):
        return TimeInstant.BATTLE_SHOCK_STEP

    def command_phase(self, node):
        return TimeInstant.COMMAND_PHASE

    def if_effect(self, node):
        to_return = self.add(IfStatement.make())
        with self.make_scope(region=to_return.condition) as scope:
            condition = self.visit(node.children[0])
            self.add(Yield.make(condition))

        with self.make_scope(region=to_return.true_branch) as scope:
            condition = self.visit(node.children[1])
            self.add(Yield.make())

        return to_return

    def time_condition(self, node):
        (qualifier, instant) = self.visit_children(node)
        return TimeEventType.make(instant, qualifier)

    def oppo_step_condition(self, node):
        (step_instant, phase_instant) = self.visit_children(node)
        return TimeEventType.make(step_instant, TimeQualifier.DURING, player=Player.OPPONENT)

    def time_end(self, node):
        return TimeQualifier.END

    def time_start(self, node):
        return TimeQualifier.START

    def fighting_phase(self, node):
        return TimeInstant.FIGHT_PHASE

    def current_phase(self, node):
        return TimeInstant.CURRENT_PHASE

    def enemy(self, node):
        return self.add(IsOwnedBy.make(self.current_subject(), Player.OPPONENT))

    def within_constraint(self, node):
        (quantity, s1) = self.visit_children(node)
        self.make_referrable(self.current_subject())
        self.make_referrable(s1)
        return self.add(WithinRange.make(quantity, self.current_subject(), s1))

    def constraint(self, node):
        return self.visit(node.children[0])

    def boolean_expression(self, node):
        subject = self.visit(node.children[0])

        with self.make_scope(subject=subject) as scope:
            return self.visit(node.children[1])

    def within_engagement_range(self, node):
        (s1, ) = self.visit_children(node)
        return self.add(WithinEngagementRange.make(self.current_subject(), s1))

    def select_subject(self, node):
        select = self.add(SelectSubject.make())
        self.make_referrable(select)
        with self.make_scope(region=select.condition, subject=select.condition.first_block.args[0]) as scope:
            subject = self.visit(node.children[0])
            to_return = self.add(BelongsTo.make(select.condition.first_block.args[0], subject))
            self.add(Yield.make(to_return))
        return select

    def until_effect(self, node):
        event = self.visit(node.children[0])
        conditional_effect = self.add(UntilEffect.make(event))

        with self.make_scope(region=conditional_effect.effect) as scope:
            self.visit(node.children[1])
            self.add(Yield.make())

        return conditional_effect

    def raw_number_outer(self, node):
        (number, ) = self.visit_children(node)
        return number

    def hit_roll(self, node):
        return RollKind.HIT_ROLL

    def character_keyword(self, node):
        return Keyword.CHARACTER

    def number(self, node):
        return int("".join(node.children))

    def keyworded_constraint(self, node):
        keyword = self.visit(node.children[0])
        node = self.add(HasKeyword.make(self.current_subject(), keyword)).result
        return node

    def destroys(self, node):
        op: Destroys
        op = self.add(Destroys.make())

        with self.make_scope(region=op.source, subject=op.filter_argument(0)) as scope:
            subject1 = self.visit(node.children[0])
            to_return1 = self.add(BelongsTo.make(op.filter_argument(0), subject1))
            self.make_referrable(subject1)
            self.add(Yield.make(to_return1))

        with self.make_scope(region=op.target, subject=op.filter_argument(1)) as scope:
            subject2 = self.visit(node.children[1])
            to_return2 = self.add(BelongsTo.make(op.filter_argument(1), subject2))
            self.make_referrable(subject2)
            self.add(Yield.make(to_return2))

        return op


    def makes_an_attack(self, node):
        op = self.add(MakesAnAttack.make())
        with self.make_scope(region=op.condition, subject=op.filter_argument(0)) as scope:
            (subject, ) = self.visit_children(node)
            self.make_referrable(subject)
            to_return = self.add(BelongsTo.make(op.filter_argument(), subject))
            self.add(Yield.make(to_return))
        return op

    def subject_in_subject(self, node):
        (s1, ) = self.visit_children(node)
        return self.add(BelongsTo.make(self.current_subject(), s1))

    def additional_effect(self, node):
        to_return = self.add(AdditionalEffect.make())
        with self.make_scope(region=to_return.body) as scope:
            (effect, ) = self.visit_children(node)
            self.add(Yield.make())
        return  to_return

    def leadership(self, node):
        return Characteristic.LEADERSHIP

    def worsen_characteristic(self, node):
        characteristic = self.visit(node.children[0])
        quantity = self.visit(node.children[2])
        to_return = self.add(ModifyCharacteristic.make(characteristic, quantity*-1))
        with self.make_scope(region=to_return.beneficient) as scope:
            subject = self.visit(node.children[1])
            self.make_referrable(subject)
            self.add(Yield.make(subject))

        with self.make_scope(region=to_return.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))
        return to_return

    def subtract_effect(self, node):
        (quantity, kind) = self.visit_children(node)
        return self.add(ModifyRoll.make(self.add(ThisSubject.make(AttackType())), kind, quantity*-1))

    def each_time(self, node):
        event = self.visit(node.children[0])

        with self.make_scope(region=event.effect) as scope:
            self.visit(node.children[1])
            self.add(Yield.make())

        return event

    def at_event(self, node):
        event = self.visit(node.children[0])
        conditional_effect = self.add(TimedEffect.make(event))

        with self.make_scope(region=conditional_effect.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))

        with self.make_scope(region=conditional_effect.effect) as scope:
            self.visit(node.children[1])
            self.add(Yield.make())

        return conditional_effect

    def while_true_effect(self, node):
        conditional_effect = self.add(ConditionalEffect.make())

        with self.make_scope(region=conditional_effect.condition) as scope:
            condition = self.visit(node.children[0])
            self.add(Yield.make(condition))

        with self.make_scope(region=conditional_effect.effect) as scope:
            self.visit(node.children[1])
            self.add(Yield.make())

        self.buider.insertion_point = InsertPoint.after(conditional_effect)
        return conditional_effect

    def is_condition(self, node) -> SSAValue[BoolType]:
        subject = self.visit(node.children[0])
        (predicate, ) = self.visit(node.children[1])
        return predicate

    def such_subject_type(self, node):
        (typ, ) = self.visit_children(node)
        return self.add(SuchSubject.make(typ))


    def such_subject(self, node):
        such = self.add(ConstrainedSuchSubject.make())
        with self.make_scope(region=such.body, subject=such.body.first_block.args[0]) as scope:
            condition = self.visit(node.children[0])
            self.add(Yield.make(condition))


        return such.result

    def it_subject(self, node):
        return self.add(ItSubject.make())

    def generate_battle_shock_test(self, node):
        subject = self.visit(node.children[0])
        return self.add(MakeBattleShockTest.make(subject))

    def below_its_starting_strenght(self, node):
        return self.add(BelowStartingStrenght.make(self.current_subject())).result

    def this_model(self, node):
        (typ, ) = self.visit_children(node)
        return self.add(ThisSubject.make(typ)).result

    def obtain_weapon_ability(self, node):
        qualifier = self.visit(node.children[0]) if node.children[0] is not None else None
        weapon_ability = self.visit(node.children[2])
        if qualifier is None:
            qualifier = WeaponQualifierKindAttr(WeaponQualifierKind.ANY)
        to_return = self.add(ObtainWeaponAbility.make(ability=weapon_ability, qualifier=qualifier))
        with self.make_scope(region=to_return.beneficient) as scope:
            subject = self.visit(node.children[1])
            self.make_referrable(subject)
            self.add(Yield.make(subject))

        with self.make_scope(region=to_return.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))

        return to_return

    def devastating_wounds(self, node):
        return WeaponAbilityKindAttr(WeaponAbilityKind.DEVASTATING_WOUNDS)

    def make_referrable(self, subject: SSAValue):
        self.add(MakeReferrable.make(subject))

    def leading_constraint(self, node):
        (rhs, ) = self.visit_children(node)
        self.make_referrable(self.current_subject())
        self.make_referrable(rhs)
        return self.add(Leading.make(leader=self.current_subject(), unit=rhs)).result

    def any(self, node):
        typ = self.visit(node.children[0])
        return self.add(Any.make(typ)).result

    def subject(self, node):
        return self.visit(node.children[0])

    def gain_cps(self, node):
        (quantity,) = self.visit_children(node)
        return self.add(GainCP.make(quantity))

    def forward_constrained_subject(self, node):
        reference = self.add(AnyMatchingSubject.make(base_type=UnknownType()))
        with self.make_scope(region=reference.base_subject) as scope:
            subject = self.visit(node.children[1])
            self.add(Yield.make(subject))

        with self.make_scope(region=reference.constraint, subject=reference.constraint.first_block.args[0]) as scope:
            subject_contraints = self.visit(node.children[0])
            self.add(Yield.make(subject_contraints))

        return reference.result

    def singular_subject(self, node):
        to_return = self.add(OneOf.make(UnknownType()))
        with self.make_scope(region=to_return.base_subject) as scope:
            subject = self.visit(node.children[0])
            self.add(Yield.make(subject))

        return to_return

    def constrained_subject(self, node):
        reference = self.add(AnyMatchingSubject.make(base_type=UnknownType()))
        with self.make_scope(region=reference.base_subject) as scope:
            subject = self.visit(node.children[0])
            self.add(Yield.make(subject))

        with self.make_scope(region=reference.constraint, subject=reference.constraint.first_block.args[0]) as scope:
            subject_contraints = self.visit(node.children[1])
            self.add(Yield.make(subject_contraints))

        return reference.result

    def in_subject(self, node):
        (_, rhs) = self.visit_children(node)
        self.make_referrable(rhs)
        return self.add(SubjectsIn.make(rhs)).result

    def unit(self, node):
        return UnitType()

    def model(self, node):
        return ModelType()
