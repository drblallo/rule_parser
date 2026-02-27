from lark import Lark, ast_utils, Tree, Token
from lark.visitors import Interpreter
from typing import List
import sys
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
        self.subject_index = 0

    def make_scope(self, region: Region = None, subject: SSAValue = None):
        return Scope(self, region=region, subject=subject)

    def current_subject(self) -> SSAValue:
        return self.scopes[-1].current_subject()

    def add(self, operation):
        self.buider.insert(operation)
        return operation

    def __default__(self, tree):
        print(tree, file=sys.stderr)
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

    def if_it_does(self, node):
        to_return = self.add(IfItDoes.make())
        with self.make_scope(region=to_return.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))

        with self.make_scope(region=to_return.effect) as scope:
            condition = self.visit(node.children[0])
            self.add(Yield.make())

        return to_return

    def if_effect(self, node):
        to_return = self.add(ConditionalEffect.make())
        with self.make_scope(region=to_return.condition) as scope:
            condition = self.visit(node.children[0])
            self.add(Yield.make(condition))

        with self.make_scope(region=to_return.effect) as scope:
            condition = self.visit(node.children[1])
            self.add(Yield.make())

        return to_return

    def reduce_cp_cost(self, node):
        (quantity, ) = self.visit_children(node)
        return self.add(ModifyCPCost.make(-1*quantity))

    def ranged_weapon(self, node):
        return WeaponQualifierKindAttr.get(WeaponQualifierKind.RANGED)


    def time_condition(self, node):
        (qualifier, instant) = self.visit_children(node)
        return TimeEventType.make(instant, qualifier)

    def any_phase_instant(self, node):
        (qualifier, ) = self.visit_children(node)
        return TimeEventType.make(TimeInstant.ANY_PHASE, qualifier)

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

    def list_of_subjects(self, node):
        return self.visit_children(node)[0]

    def can_use(self, node):
        reserved_index = self.reserve_index()
        user = self.visit(node.children[0])
        self.make_referrable(user, reserved_index)

        reserved_index = self.reserve_index()
        used = self.visit(node.children[1])
        self.make_referrable(used, reserved_index)

        return self.add(OptionallyUse.make(user, used))

    def stratagem_subject_type(self, node):
        return StratagemType()

    def subject_obtains_property(self, node):
        return self.visit(node.children[0])

    def obtains_invulnerable_save(self, node):
        value = self.visit(node.children[1])
        to_return = self.add(ObtainInvulnerableSave.make(value=value))

        with self.make_scope(region=to_return.beneficient) as scope:
            reserved_index = self.reserve_index()
            subject = self.visit(node.children[0])
            self.make_referrable(subject, reserved_index)
            self.add(Yield.make(subject))

        with self.make_scope(region=to_return.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))


        with self.make_scope(region=to_return.effect) as scope:
            self.add(Yield.make())
        return to_return

    def ability_subject(self, node):
        return AbilityType()

    def enemy(self, node):
        return self.add(IsOwnedBy.make(self.current_subject(), Player.OPPONENT))

    def allied(self, node):
        return self.add(IsOwnedBy.make(self.current_subject(), Player.YOU))

    def within_constraint(self, node):
        reserved_index = self.reserve_index()
        (quantity, s1) = self.visit_children(node)
        self.make_referrable(s1, reserved_index)

        return self.add(WithinRange.make(quantity, self.current_subject(), s1))

    def constraint(self, node):
        return self.visit(node.children[0])

    def with_this_ability(self, node):
        reserved_index = self.reserve_index()
        this_ability = self.add(ThisAbility.make())
        self.make_referrable(this_ability, reserved_index)

        return self.add(HasAbility.make(self.current_subject() ,this_ability))

    def from_your_army(self, node):
        return self.add(IsOwnedBy.make(self.current_subject(), Player.YOU))

    def battle_round_limit(self, node):
        return UseLimit.ROUND

    def turn_limit(self, node):
        return UseLimit.TURN

    def battle_limit(self, node):
        return UseLimit.BATTLE

    def once_per_effect(self, node):
        limit = self.visit(node.children[0])
        obj = self.add(OncePer.make(limit))

        with self.make_scope(region=obj.body) as scope:
            self.visit(node.children[1])
            return obj

    def boolean_expression(self, node):
        reserved_index = self.reserve_index()
        subject = self.visit(node.children[0])
        self.make_referrable(subject, reserved_index)

        with self.make_scope(subject=subject) as scope:
            return self.visit(node.children[1])

    def within_engagement_range(self, node):
        (s1, ) = self.visit_children(node)
        return self.add(WithinEngagementRange.make(self.current_subject(), s1))

    def select_subject(self, node):
        reserved_index = self.reserve_index()
        select = self.add(SelectSubject.make())
        self.make_referrable(select, reserved_index)
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

        with self.make_scope(region=op.source) as scope:
            reserved_index = self.reserve_index()
            subject1 = self.visit(node.children[0])
            self.make_referrable(subject1, reserved_index)
            self.add(Yield.make(subject1))

        with self.make_scope(region=op.target) as scope:
            reserved_index = self.reserve_index()
            subject2 = self.visit(node.children[1])
            self.make_referrable(subject2, reserved_index)
            self.add(Yield.make(subject2))

        with self.make_scope(region=op.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))

        with self.make_scope(region=op.effect) as scope:
            self.add(Yield.make())

        return op


    def makes_an_attack(self, node):
        op = self.add(MakesAnAttack.make())
        with self.make_scope(region=op.subject) as scope:
            reserved_index = self.reserve_index()
            (subject, ) = self.visit_children(node)
            self.make_referrable(subject, reserved_index)
            self.add(Yield.make(subject))
        with self.make_scope(region=op.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))
        with self.make_scope(region=op.effect) as scope:
            self.add(Yield.make())
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
            reserved_index = self.reserve_index()
            subject = self.visit(node.children[1])
            self.make_referrable(subject, reserved_index)
            self.add(Yield.make(subject))

        with self.make_scope(region=to_return.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))

        with self.make_scope(region=to_return.effect) as scope:
            self.add(Yield.make())
        return to_return

    def subtract_effect(self, node):
        (quantity, kind) = self.visit_children(node)
        return self.add(ModifyRoll.make(self.add(ThisSubject.make(AttackType())), kind, quantity*-1))

    def each_time(self, node):
        event = self.visit(node.children[0])

        with self.make_scope(region=event.effect) as scope:
            self.visit(node.children[1])

        return event

    def tyranid_keyword(self, node):
        return Keyword.TYRANID

    def is_targeted_with(self, node):
        op  = self.add(Targets.make())
        with self.make_scope(region=op.subjects) as scope:
            reserved_index = self.reserve_index()
            subj = self.visit(node.children[0])
            self.make_referrable(subj, reserved_index)

            reserved_index = self.reserve_index()
            event = self.visit(node.children[1])
            self.make_referrable(event, reserved_index)
            self.add(Yield.make([event, subj]))

        with self.make_scope(region=op.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))
        with self.make_scope(region=op.effect) as scope:
            self.add(Yield.make())

        return op

    def trailing_when_effect(self, node):
        rewrter = Rewriter()
        region = Region(Block())
        with self.make_scope(region=region) as scope:
            self.visit(node.children[0])

        event = self.visit(node.children[1])
        rewrter.inline_block(region.first_block, InsertPoint.before(event.effect.first_block.last_op))

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
        with self.make_scope(region=such.body) as scope:
            condition = self.visit(node.children[0])

        return such.result

    def it_subject(self, node):
        return self.add(ItSubject.make())

    def generate_battle_shock_test(self, node):
        index = self.reserve_index()
        subject = self.visit(node.children[0])
        self.make_referrable(subject, index)
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
            reserved_index = self.reserve_index()
            subject = self.visit(node.children[1])
            self.make_referrable(subject, reserved_index)
            self.add(Yield.make(subject))

        with self.make_scope(region=to_return.condition) as scope:
            self.add(Yield.make(self.add(TrueOp.make())))


        with self.make_scope(region=to_return.effect) as scope:
            self.add(Yield.make())

        return to_return

    def devastating_wounds(self, node):
        return WeaponAbilityKindAttr(WeaponAbilityKind.DEVASTATING_WOUNDS)

    def letal_hits(self, node):
        return WeaponAbilityKindAttr(WeaponAbilityKind.LETHAL_HITS)

    def make_referrable(self, subject: SSAValue, index):
        self.add(MakeReferrable.make(subject, index))

    def reserve_index(self):
        to_return = self.subject_index
        self.subject_index = self.subject_index + 1
        return to_return

    def leading_constraint(self, node):
        reserved_index = self.reserve_index()
        (rhs, ) = self.visit_children(node)
        self.make_referrable(rhs, reserved_index)
        return self.add(Leading.make(leader=self.current_subject(), unit=rhs)).result

    def any(self, node):
        typ = self.visit(node.children[0])
        return self.add(All.make(typ)).result

    def subject(self, node):
        return self.visit(node.children[0])

    def gain_cps(self, node):
        (quantity,) = self.visit_children(node)
        return self.add(GainCP.make(quantity))

    def forward_constrained_subject(self, node):
        reference = self.add(FilterList.make(base_type=UnknownType()))

        with self.make_scope(region=reference.constraint, subject=reference.constraint.first_block.args[0]) as scope:
            subject_contraints = self.visit(node.children[0])
            self.add(Yield.make(subject_contraints))
        with self.make_scope(region=reference.base_subject) as scope:
            subject = self.visit(node.children[1])
            self.add(Yield.make(subject))


        return reference.result

    def singular_subject(self, node):
        to_return = self.add(OneOf.make(UnknownType()))
        with self.make_scope(region=to_return.base_subject) as scope:
            subject = self.visit(node.children[0])
            self.add(Yield.make(subject))

        return to_return

    def base_subject(self, node):
        return self.visit_children(node)[0]

    def constrained_subject_with_constraint(self, node):
        reference = self.add(FilterList.make(base_type=UnknownType()))
        with self.make_scope(region=reference.base_subject) as scope:
            subject = self.visit(node.children[0])
            self.add(Yield.make(subject))

        with self.make_scope(region=reference.constraint, subject=reference.constraint.first_block.args[0]) as scope:
            subject_contraints = self.visit(node.children[1])
            self.add(Yield.make(subject_contraints))

        return reference.result

    def in_subject(self, node):
        reserved_index = self.reserve_index()
        (_, rhs) = self.visit_children(node)
        self.make_referrable(rhs, reserved_index)
        return self.add(SubjectsIn.make(rhs)).result

    def unit(self, node):
        return UnitType()

    def model(self, node):
        return ModelType()
