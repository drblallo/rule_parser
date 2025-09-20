import argparse
import sys
from functools import singledispatchmethod
from lark import Lark, ast_utils, Transformer, v_args, Tree, Token
from lark.tree import Meta
from typing import Iterable, List
import re
from dataclasses import dataclass, asdict, field
from enum import Enum
from dataclasses import is_dataclass, fields
from typing import Any, Dict, Union

def paren_pformat(obj, indent=2, width=80):
    s = repr(obj).replace(" ", "")
    out = []
    level = 0
    for ch in s:
        if ch in "([{":
            out.append(ch)
            level += 1
            out.append("\n" + " " * (level * indent))
        elif ch in ")]}":
            level -= 1
            out.append("\n" + " " * (level * indent) + ch)
        elif ch == ",":
            out.append(ch)
            out.append("\n" + " " * (level * indent))
        else:
            out.append(ch)
    return "".join(out)

# a proposition that can evaluate to true or false
class Condition:pass

# a condition that must be evaluated in the context of a model
class ModelCondition:pass

# a condition that must be evaluated in the context of a unit
class UnitCondition:pass

# a condition that must be evaluated in the context of a stratagem
class StratagemCondition:pass

# a condition that must be evaluated in the context of a stratagem
class AttackCondition:pass
class WeaponCondition:pass

# a condition that refers to a given zone of the table
class WeaponCondition:pass

# a condition that bust be evaluted in the context of a ability being resolved
class AbilityCondition:pass

# a condition that bust be evaluted when performing a selection
class SelectionCondition:pass

# a condition that bust be evaluted when considering a point of the table
class LocationCondition:pass

class EffectType(Enum):
    MODIFIER = 1 # a modifier that is active if some condition is true (ex while this model is leading a unit, the unit has the rule X)
    ACTIVATED_ACTION = 2 # a action that can have requirements, but is triggered during a open game state at the discretion of the player(ex: during your turn, you can remove this model from the board)
    TRIGGERED_ACTION = 3 # a mandatory action that must be performed at a given event, when some conditions happen
    RAW_EFFECT = 4 # a effect that specifies what is to be done imeprativelly. The top level effect of a rule should never be a raw effect, since it would have no specification of when to do it. (ex: roll a dice)
    TEMPORARY_EFFECT = 5 # a effect that lasts up to a given time event in the future. Typically other events spawn a temporary effect (ex a triggered action that generates a temporary effect: when you attack, until the end of the turn the attacked unit has X)

# a effect that changes the game state
@dataclass(kw_only=True)
class Effect:
    effect_type: EffectType = None


# a effect that changes some property of the game, but if the modifier is lost, the characteristic is reverted to the original value. A modifier must be applied by some other AST node. Before being appplied it just describes its effect
class Modifier:pass
class UnitModifier:pass
class ModelModifier:pass
class AttackModifier:pass
class RollModifier:pass
class StratagemModifier:pass

# a modifier that changes the state of a weapon
class WeaponModifier:pass

class Unreferrable: pass
# used to tag AST nodes that rappresent the exact same subject as their contained sub subject, for example QualifiedSubject(ThisUnit, SomeCondition), where both QualifiedSubject and ThisUnit really point to the same subject at runtime.
class Qualification: pass

# a game element that can be referred to
@dataclass(kw_only=True)
class Subject:
    # a description of the state of a subject when the game is being player. For example, ThisModel() would have the runtime type ModelSubject, but All(Model())  would hav ethe runtime type List(ModelSubject). This is needed because some nodes have context dependant types, such as Such()
    runtime_type: type = None
    subject_index: int = -1

    def is_reference_to_me(self, other: 'Subject') -> bool:
        return type(self) == type(other)

class UsableSubject(Subject):pass # describes a subject that can be used, such as a ability
class UnitSubject(Subject):pass
class ModelSubject(Subject):pass
class CharacteristicSubject(Subject):pass
class AttackSubject(Subject):pass
class OptionSubject(UsableSubject):pass
class RollSubject(Subject):pass
class ActionSubject(UsableSubject):pass
class WeaponSubject(Subject):pass
class AbilitySubject(UsableSubject):pass
class WeaponAbilitySubject(Subject):pass
class StratagemSubject(UsableSubject):pass

# a effect performed by a subject
class Action(Effect): pass

# a effect that generates a before, during and after moments that other rules can refer to.
@dataclass(kw_only=True)
class Event:
    conditions: List[Condition] = field(default_factory=list)

    def unique_event_name(self):
        raise NotImplementedError()

    # returns the subjects that take part in the event, for example in a event such as "this model deals damage to a model within 3' of a objective", returns [ThisModel, CondSubject(Model, Wihtin(Objective, 3))]
    def event_subjects(self) -> List[Subject]:
        raise NotImplementedError()

class ModelAction(Action): pass
class UnitAction(Action): pass

# a effect that introduce a subject, for example "for each enemy unit, destroy that unit", that for each must introduce the enemy unit in the scope
class SubjectIntroducingEffect:
    def get_introduced_subjects(self) -> List[Subject]:
        raise NotImplemented()
    # adds a additional effect to this effect, to allow to hoist effects inside this one
    def add_additional_effect(self, effect: Effect):
        raise NotImplemented()


class ASTNode(ast_utils.Ast):
    def __init__(self):
        self._parent = None

    def __setattr__(self, name: str, value):
        if isinstance(value, ASTNode) and name != "_parent":
            value._parent = self
        super().__setattr__(name, value)

    def swap(self, new_value):
        if self._parent == None or new_value.parent == None:
            raise NotImplementedError()

        self.replace(new_value)
        new_value.replace(self)


    def replace(self, new_value):
        if self._parent == None:
            return
        for attr_name, value in vars(self._parent).items():
            if value is self:
                setattr(self._parent, attr_name, new_value)

    def drop(self):
        self.replace(None)

@dataclass
class AttackMadeWithWeapon(ASTNode, AttackCondition):
    weapon_name: str

class AbilityKind(Enum):
    DEEP_STRIKE = 1
    FEEL_NO_PAIN = 2
    STEALTH = 3

@dataclass
class Ability(ASTNode, AbilitySubject):
    kind: AbilityKind
    value: int = -1

class MovementKind(Enum):
    NORMAL = 1
    ADVANCE = 2
    FALL_BACK = 3
    BLISTERING_ASSAULT = 4
    ANY = 5
    REMAIN_STATIONARY = 6

class WeaponQualifier(Enum):
    MELEE = 1
    RANGED = 2
    ANY = 3

class Keyword(Enum):
    CHARACTER = 1
    TYRANID = 2
    MONSTER = 2
    INFANTRY = 3
    TERMAGANTS = 4
    PSYKER = 5
    NEUROGAUNT = 6
    SYNAPSE = 7
    FLY = 8
    TITANIC = 9

class Characteristic(Enum):
    LEADERSHIP = 1
    MOVE = 2
    OC = 3

class WeaponCharacteristic(Enum):
    ATTACKS = 1
    AP = 2
    DAMAGE = 3

class WeaponAbilityKind(Enum):
    DEVASTATING_WOUNDS = 1
    LETHAL_HITS = 2
    ASSAULT = 3
    SUSTAINED_HITS = 4

@dataclass
class WeaponAbility(ASTNode, WeaponAbilitySubject):
    kind: WeaponAbilityKind
    value: int = 0

class TimeQualifier(Enum):
    START = 1
    DURING = 2
    END = 3

    def event_name(self):
        if self == TimeQualifier.START:
            return "start"
        elif self == TimeQualifier.END:
            return "end"
        else:
            raise NotImplementedError()

class Player(Enum):
    YOU = 1
    OPPONENT = 2
    ANY = 3

@dataclass
class BelowHalfStrenght(ASTNode, UnitCondition):
    subject: UnitSubject

@dataclass
class ThatIsTargeting(ASTNode, AttackCondition, StratagemCondition, AbilityCondition):
    subject: Union[UnitSubject, ModelSubject]

@dataclass
class AddUnitToArmy(ASTNode):
    pass

@dataclass
class TargetedWith(ASTNode, Event):
    target: Subject
    subject: Subject

    def unique_event_name(self):
        return "on_stratagem_use"

    def event_subjects(self) -> List[Subject]:
        return [self.target, self.subject]

@dataclass
class BattleShocked(ASTNode, UnitCondition):
    pass

@dataclass
class Leading(ASTNode, ModelCondition):
    subject: UnitSubject

@dataclass
class Destroyed(ASTNode, UnitCondition, ModelCondition):
    pass

@dataclass
class Resolving(ASTNode, Action):
    stratagem: StratagemSubject

# obtain cover against a particular source model
@dataclass
class ObtainCover(ASTNode, UnitModifier, ModelModifier):
    subject: AttackSubject

@dataclass
class ObtainInvulnerableSave(ASTNode, UnitModifier, ModelModifier):
    value: int

@dataclass
class OnTheBattleField(ASTNode, UnitCondition, ModelCondition):
    pass

@dataclass
class NumberRange(ASTNode):
    min: int
    max: int

@dataclass
class FellBack(ASTNode, ModelCondition, UnitCondition):
    pass

@dataclass
class DiceExpression(ASTNode):
    dices_to_roll: int
    dice_faces: int
    raw_extra: int = 0

    def __eq__(self, other):
        return asdict(self) == asdict(other)

@dataclass
class BelowItsStartingStrenght(ASTNode, UnitCondition):
    pass

@dataclass
class With(ASTNode, UnitCondition, ModelCondition):
    subject: Subject

@dataclass
class SetUp(ASTNode, UnitAction, ModelAction):
    pass

@dataclass
class UsingAbility(ASTNode, ModelCondition, UnitCondition):
    ability: Ability

@dataclass
class In(ASTNode, ModelCondition):
    subject: UnitSubject

@dataclass
class TrueCondition(ASTNode, Condition):
    pass

# turns a specific condition that must be evaluated on a object into a general condition by wrapping it with the subject that specify how to get that object.
@dataclass
class SubjectIs(ASTNode, Condition):
    subject: Subject
    predicate: Condition

@dataclass
class ThisOption(ASTNode,OptionSubject):
    pass

# Binds a roll mdifier to a given roll, turning it a modified subject
@dataclass
class ModifiedRoll(ASTNode, RollSubject):
    subject: RollSubject
    roll_modifier: RollModifier

# Modifies a given weapon
@dataclass
class ModifyWeapons(ASTNode, Effect):
    subject: WeaponSubject
    weapon_modifier: WeaponModifier
    weapon_qualifier: WeaponQualifier


@dataclass
class Stratagem(ASTNode, StratagemSubject):
    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Stratagem)


@dataclass
class AddAbilityModifier(ASTNode,WeaponModifier):
    ability: WeaponAbility

@dataclass
class AddSynapse(ASTNode, UnitModifier):
    player: Player

@dataclass
class ModelWithKeyword(ASTNode, ModelSubject):
    keyword: Keyword

# refers to each subject matching the pattern provided,
# except for the before mentioned unit
@dataclass
class EveryOther(ASTNode, UnitSubject, Qualification):
    subject: UnitSubject

@dataclass
class NoEffect(ASTNode,Effect):
    pass

@dataclass
class StringSubject(ASTNode, Subject):
    text: str

@dataclass
class LimitOncePerPhase(ASTNode,Effect):
    action: Action


@dataclass
class CanBeSetup(ASTNode,UnitModifier):
    condition: Condition

@dataclass
class SpecificModel(ASTNode,ModelSubject):
    model: str

@dataclass
class CannotCharge(ASTNode,UnitModifier):
    pass

@dataclass
class CannotHaveCover(ASTNode,UnitModifier):
    pass

@dataclass
class CannotAdvance(ASTNode,UnitModifier):
    predicate: LocationCondition


@dataclass
class MustMoveAsCloseAsPossibleTo(ASTNode,UnitModifier):
    target: Subject

@dataclass
class DeclareShoot(ASTNode,UnitAction):
    pass

@dataclass
class DeclareCharge(ASTNode,UnitAction):
    pass

# a effect that includes a test, and that test is modified
@dataclass
class ModifiedTest(ASTNode, RollSubject, Qualification):
    roll: RollSubject
    modifier: RollModifier

@dataclass
class VisibleTo(ASTNode, ModelCondition, UnitCondition):
    subject: Union[ModelSubject, UnitSubject]

@dataclass
class MovedOver(ASTNode, UnitCondition):
    by: Subject
    time_condition: Condition

class NumberCaseKind(Enum):
    GREATER_EQUAL = 1
    EQUAL = 2

# a effect conditional to the fact that the last dice rolled
# had a given value
@dataclass
class NumberCase(ASTNode):
    required_value: int
    kind: NumberCaseKind
    effect: Effect

@dataclass
class RollRequirement(ASTNode):
    subject: Subject
    required_value: int

@dataclass
class RollTresholdReplacement(ASTNode):
    roll_requirement: RollRequirement
    condition: Condition

@dataclass
class ReplaceTresholdOfRoll(ASTNode, RollModifier):
    to_replace: RollSubject
    replacement_tresholds: List[RollTresholdReplacement]

# a effect that specifies which subject ends up getting a modifier applied, turning the modifier into a effect
@dataclass
class ObtainProperty(ASTNode,Effect):
    subject: Union[ModelSubject, RollSubject, UnitSubject, WeaponSubject]
    effect: Union[ModelModifier, RollModifier, UnitModifier, WeaponModifier]

# quantity of models to add to a action that creates a new unit
@dataclass
class QuantityOfModelsToAdd(ASTNode):
    quantity: DiceExpression

# a event that triggers after some time condition has triggered
@dataclass
class AfterEffect(ASTNode,Effect):
    event: Event
    effect: Effect


@dataclass
class ConditionalEffect(ASTNode,Effect):
    condition: Condition
    effect: Effect

@dataclass
class AttackAllocatedTo(ASTNode,Event):
    subject: Union[ModelSubject, UnitSubject]

    def unique_event_name(self):
        return "on_attack_allocated"

    def event_subjects(self) -> List[Subject]:
        raise [self.subject]


@dataclass
class Contains(ASTNode, UnitCondition):
    subject: ModelSubject

@dataclass
class OncePerRound(ASTNode,Effect):
    effect: Effect

@dataclass
class OncePerBattle(ASTNode,Effect):
    effect: Effect

@dataclass
class OncePerTurn(ASTNode,Effect):
    effect: Effect

@dataclass
class AllowForbiddenMovement(ASTNode, UnitModifier):
    region_predicate: LocationCondition


@dataclass
class BattleShockTest(ASTNode, UnitAction):
    pass

# an effect that is created by some other effect and then lingers up to some point of the game.
@dataclass
class TemporaryEffect(ASTNode,Effect, SubjectIntroducingEffect):
    condition: Condition
    effect: Effect
    unique_id: int = -1
    captured_subjects: List[Subject] = field(default_factory=list)

    def get_introduced_subjects(self) -> List[Subject]:
        return self.captured_subjects

    # adds a additional effect to this effect, to allow to hoist effects inside this one
    def add_additional_effect(self, effect: Effect):
        self.effect = And(self.effect, effect)

# Create a instance of a temporary effect to be added
# to the global list of temporary effects.
@dataclass
class CreateTemporaryEffect(ASTNode,Effect):
    temporary_effect_id: int
    captured_references: List[ASTNode]

@dataclass
class CannotSelect(ASTNode, SelectionCondition):
    selectee: Subject
    more_than: DiceExpression

@dataclass
class EffectList(ASTNode,Effect):
    effects: List[Effect]

# an effect that must be hoisted inside the previous conditional
# effect because it is still affected by its condition
@dataclass
class AdditionalEffect(ASTNode,Effect):
    first: Effect
    second: Effect

# an effect that triggers only if the last optional action in the first part of the effect was triggered.
@dataclass
class OnActivationEvent(ASTNode,Effect):
    first: Effect
    consequence: Effect

@dataclass
class UnitNamed(ASTNode, UnitSubject):
    name: str

@dataclass
class BecomesElegibleForTurn(ASTNode,UnitModifier):
    to_do_what: List[Action]
    when_it_does: Action

@dataclass
class EquippedBy(ASTNode, WeaponCondition):
    subject: ModelSubject

@dataclass
class CharacteristicOfWeapons(ASTNode, CharacteristicSubject):
    characteristic: WeaponCharacteristic
    predicate: WeaponSubject

class AttackKind(Enum):
    MELEE = 1
    RANGED = 2
    ANY = 3

@dataclass
class AttackTargets(ASTNode, AttackSubject):
    subject: UnitSubject
    qualifer: AttackKind

class StatusKind(Enum):
    DISRUPTED = 1

@dataclass
class AfflictStatus(ASTNode, UnitModifier):
    kind: StatusKind

@dataclass
class ThisModel(ASTNode, ModelSubject):
    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Model) or isinstance(other, ThisModel)

@dataclass
class DiceResult(ASTNode, RollSubject):
    pass

@dataclass
class UnitOf(ASTNode, UnitSubject):
    subject: ModelSubject

@dataclass
class You(ASTNode,Subject):
    pass

@dataclass
class ObjectiveMarker(ASTNode,Subject):
    pass

@dataclass
class All(ASTNode,Subject, Qualification):
    subject: Subject

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, All) and self.subject.is_reference_to_me(other.subject)

@dataclass
class Opponent(ASTNode,Subject):
    pass

@dataclass
class Multiple(ASTNode, Subject, Qualification):
    min: int
    max: int
    subject: Subject

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Multiple) and self.subject.is_reference_to_me(other.subject) and self.min == other.min and self.max == other.max

@dataclass
class HasFought(ASTNode, UnitCondition):
    pass

@dataclass
class ObtainFightOnDeath(ASTNode, ModelModifier):
    pass

@dataclass
class Not(ASTNode,Condition):
    predicate: Condition

@dataclass
class And(ASTNode):
    lhs: object
    rhs: object

@dataclass
class Or(ASTNode):
    lhs: object
    rhs: object

@dataclass
class Enemy(ASTNode, UnitCondition, ModelCondition):
    pass

@dataclass
class ChangeAttackCharacteristic(ASTNode, AttackModifier):
    characteristic: WeaponCharacteristic
    attack: AttackSubject
    quantity: DiceExpression

# checks if a attack was performed with a given weapon qualifier(melee or ranged)
@dataclass
class PerformedWithItsWeapon(ASTNode,AttackCondition):
    kind: WeaponQualifier

@dataclass
class WithinEngagementRange(ASTNode,LocationCondition):
    subject: UnitSubject

@dataclass
class HitBy(ASTNode, ModelCondition, UnitCondition):
    subject: AttackSubject

@dataclass
class ThoseAttacks(ASTNode, AttackSubject, Unreferrable):
    def is_reference_to_me(self, other: Subject) -> bool:
        return False

@dataclass
class WithinSynapseRange(ASTNode, LocationCondition):
    subject: UnitSubject

@dataclass
class WithinRange(ASTNode, LocationCondition):
    distance: int
    subject: Subject


@dataclass
class OutsideRange(ASTNode, LocationCondition):
    distance: int
    subject: Subject

@dataclass
class WhollyWithinRange(ASTNode, LocationCondition):
    distance: int
    subject: Subject

@dataclass
class Allied(ASTNode, UnitCondition, ModelCondition):
    pass

# refers to a objection mentioned before in the effect by its subject_index
@dataclass
class Reference(ASTNode, Subject, Unreferrable):
    pass


# refer to the last subject of a sentence if self.subject is None, else it searches for the last mentioned subject that is a superset of self.subject
@dataclass
class Such(ASTNode, Subject, Unreferrable, Qualification):
    subject: Subject

    def is_reference_to_me(self, other: Subject) -> bool:
        return False

@dataclass
class SuchAttack(ASTNode, AttackCondition, Unreferrable):
    def is_reference_to_me(self, other: Subject) -> bool:
        return False

@dataclass
class LimitTargetingPerTurn(ASTNode, Modifier):
    targeter: Subject

@dataclass
class LimitEffectPerTurn(ASTNode, Modifier):
    effect: Effect

@dataclass
class ThisAbility(ASTNode, AbilitySubject, Unreferrable):
    def is_reference_to_me(self, other: Subject) -> bool:
        return False


@dataclass
class ThisUnit(ASTNode, UnitSubject, Unreferrable):
    def is_reference_to_me(self, other: Subject) -> bool:
        return False

@dataclass
class TheTarget(ASTNode, Subject, Unreferrable):
    def is_reference_to_me(self, other: Subject) -> bool:
        return False

@dataclass
class SelectAlternativeAction(ASTNode, Effect):
    alternatives: List[Effect]

@dataclass
class TheSelectedUnits(ASTNode, UnitSubject, Unreferrable):
    def is_reference_to_me(self, other: Subject) -> bool:
        return False

# a subject on which a condition is applied that thus gets turned into a conditional subject
@dataclass
class ConditionalSubject(ASTNode,Subject, Qualification):
    subject: Subject
    condition: ModelCondition

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, ConditionalSubject) and self.subject.is_reference_to_me(other.subject) and asdict(self.condition) == asdict(other.condition)

@dataclass
class Model(ASTNode, ModelSubject):
    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Model)



@dataclass
class HasKeyword(ASTNode, UnitCondition, ModelCondition):
    keyword: Keyword

class RollKind(Enum):
    HIT_ROLL = 1
    WOUND_ROLL = 2
    BATTLE_SHOCK_ROLL = 3
    CHARGE_ROLL = 4
    ADVANCE_ROLL = 5
    SAVING_THROW_ROLL = 6

@dataclass
class Roll(ASTNode, RollSubject):
    kinds: List[RollKind]

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, RollKind) and asdict(self.kinds) == asdict(other.kinds)


# a event triggered when a roll is performed by a subject
@dataclass
class RollIsPerformed(ASTNode, Event):
    roll: RollSubject
    author: Union[ModelSubject, UnitSubject]

    def unique_event_name(self):
        return "on_roll"

    def event_subjects(self) -> List[Subject]:
        raise [self.roll, self.author]

# a qualifier of a roll that specifies that the result should be considered unnmodified
@dataclass
class Unmodified(ASTNode, RollSubject, Qualification):
    subject: RollSubject

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Unmodified) and self.subject.is_reference_to_me(other)

@dataclass
class GainCPEffect(ASTNode,Effect):
    quantity: int

# adds a quantity to all rolls roll
@dataclass
class ModifyRoll(ASTNode, Effect):
    quantity: int
    roll: List[RollKind] = field(default_factory=list)

@dataclass
class ModifyWeaponCharacteristic(ASTNode, WeaponModifier):
    characteristic: WeaponCharacteristic
    subject: WeaponSubject
    quantity: int

@dataclass
class ModifyCharacteristicExpression(ASTNode):
    additional_quantity: int
    multiplication_quantity: int = 1

# applies a given modifier to a subject
@dataclass
class ModifyCharacteristicEffect(ASTNode, Effect):
    characteristic: Characteristic
    subject: Union[ModelSubject, UnitSubject]
    expression: ModifyCharacteristicExpression

@dataclass
class Unit(ASTNode, UnitSubject):
    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Unit)

@dataclass
class AttackEvent(ASTNode, Event):
    source: Subject
    attack: AttackKind = AttackKind.ANY
    target: UnitSubject = Unit()

    def unique_event_name(self):
        return "on_attack"

@dataclass
class SetModelsOfSpawnedUnits(ASTNode, Effect):
    quantity: int


@dataclass
class ActionReplacementEffect(ASTNode,Modifier):
    to_be_replaced: Action
    replacement: Effect

# the action performed by the subject, mentioned before in the
# effect
@dataclass
class ActionOf(ASTNode, ActionSubject):
    subject: Subject

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, ActionOf) and self.subject.is_reference_to_me(other.subject)

@dataclass
class Destroy(ASTNode, UnitAction, ModelAction):
    pass

@dataclass
class AddKeyword(ASTNode, UnitModifier, ModelModifier):
    keyword: Keyword

@dataclass
class AddAbility(ASTNode, UnitModifier, ModelModifier):
    ability: Ability

@dataclass
class PlaceInStrategicReserve(ASTNode, UnitAction):
    subject: UnitSubject

@dataclass
class AddUnitToTheGame(ASTNode, UnitAction):
    unit_count: str
    subject: UnitSubject
    content_predicate: str
    setup_predicate: int


@dataclass
class RawMove(ASTNode, ModelAction):
    amount: DiceExpression

@dataclass
class MakeMove(ASTNode, UnitAction):
    kind: MovementKind
    amount: DiceExpression

@dataclass
class Destroys(ASTNode, Event):
    attacker: Union[UnitSubject, ModelSubject]
    target: Union[UnitSubject, ModelSubject]

    def unique_event_name(self):
        return "on_destruction"

    def event_subjects(self) -> List[Subject]:
        raise [self.attacker, self.target]

@dataclass
class LosesWounds(ASTNode, Event):
    subject: ModelSubject

    def unique_event_name(self):
        return "on_wounds_lost"

    def event_subjects(self) -> List[Subject]:
        raise [self.subject]

@dataclass
class SpecialRule(ASTNode, AbilitySubject):
    special_rule: str

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, SpecialRule) and self.special_rule == other.special_rule

@dataclass
class CanUseIt(ASTNode, Action):
    pass

# a effect that generates a event from using a thing that can be used, such as using a event
@dataclass
class Use(ASTNode, Action):
    subject: UsableSubject
    after_use_effect: Effect = None

@dataclass
class ThisRoll(ASTNode, RollSubject):
    pass

class StratagemKind(Enum):
    HEROIC_INTERVENTION = 1
    RAPID_INGRESS = 2
    FIRE_OVERWATCH = 3
    ANY = 4

@dataclass
class ChangeStratCost(ASTNode, Effect):
    stratagem_use: StratagemKind
    quantity: int

class LimitKind(Enum):
    PHASE = 1
    ROUND = 5
    TURN = 2
    CANNOT = 3
    NO_LIMIT = 4

@dataclass
class ReplaceCostOfStratagem(ASTNode, StratagemModifier):
    new_cost: int
    can_reuse_stratagem: LimitKind

@dataclass
class ReplaceCharacteristic(ASTNode, ModelModifier, UnitModifier):
    new_value: int
    to_replace: Characteristic

class StratagemUseClause: pass

@dataclass
class TargetsWithStratagem(ASTNode, Event):
    target: Subject
    accepted_stratagems: List[StratagemKind]
    predicate: StratagemUseClause

    def event_subjects(self) -> List[Subject]:
        raise [self.subject]

@dataclass
class ReturnModels(ASTNode, UnitAction):
    quantity: DiceExpression
    unit_to_add_to: UnitSubject

@dataclass
class Reroll(ASTNode, RollModifier):
    roll_kind: RollKind
    number_to_reroll: int = -1

@dataclass
class RegainWounds(ASTNode, ModelAction):
    quantity: int

@dataclass
class SuffersMortalWounds(ASTNode, ModelAction):
    quantity: int

@dataclass
class ForEachSubject(ASTNode, Effect):
    effect: Effect
    subject: Subject
    filter: Condition

@dataclass
class PerformRoll(ASTNode, RollSubject, Effect):
    dice_to_roll: DiceExpression
    roll_modifier: DiceExpression
    effect: Effect

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, PerformRoll) and self.dice_to_roll == other.dice_to_roll

class UsageKind(Enum):
    MANDATORY = 1
    OPTIONAL = 2

# modifiles a action with a modifier
@dataclass
class ModifyAction(ASTNode, Action):
    action: Action
    predicate: Modifier


# specifies if a action is optional or mandatory
@dataclass
class QualifiedAction(ASTNode, Action):
    action: Action
    usage: UsageKind
    usage_limit: LimitKind = LimitKind.NO_LIMIT

@dataclass
class InterpretDice(ASTNode, Effect):
    interpretations: List[NumberCase]

# binds a action to the actor performing it, and turns it into a a effect
@dataclass
class Performs(ASTNode, Effect, Event):
    subject: Subject
    action: Action
    usage: UsageKind = UsageKind.MANDATORY
    usage_limit: LimitKind = LimitKind.NO_LIMIT


    def event_subjects(self) -> List[Subject]:
        raise [self.subject]

@dataclass
class TriggeredEffect(ASTNode, Effect, SubjectIntroducingEffect):
    event: Event
    effect: Effect

    def get_introduced_subjects(self) -> List[Subject]:
        return self.event.event_subjects()

    # adds a additional effect to this effect, to allow to hoist effects inside this one
    def add_additional_effect(self, effect: Effect):
        self.effect = And(self.effect, effect)

# just like each time except the effect is written before
# the subject and thus the formed can contain a subject used by the latter
@dataclass
class TriggeredEffectReversed(ASTNode, Effect):
    subject: Subject
    effect: Action
    event: Event


# ask the player to select one subject from the list of candidates
@dataclass
class Select(ASTNode, SubjectIntroducingEffect):
    introduced_target: Subject
    effect: Effect
    target_condition: Condition = TrueCondition() #tells if you it a given target is elegible to be selected

    def get_introduced_subjects(self) -> List[Subject]:
        return [self.introduced_target]

    # adds a additional effect to this effect, to allow to hoist effects inside this one
    def add_additional_effect(self, effect: Effect):
        self.effect = And(self.effect, effect)

class TimeInstant(Enum):
    FIGHT_PHASE = 1
    CURRENT_PHASE = 2
    BATTLE_SHOCK_STEP = 3
    COMMAND_PHASE = 4
    SHADOW_IN_THE_WARP = 5
    SHOOTING_PHASE= 6
    TURN = 7
    ANY_BATTLE_ROUND = 8
    FIRST_BATTLE_ROUND = 9
    BATTLE = 10
    MOVEMENT_PHASE = 11

    def event_name(self):
        return self.name.lower()


@dataclass
class Army(ASTNode,Subject):
    owner: Player

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Army) and self.owner == other.owher

# rappresents a moment in time related to a action performed by a subject
@dataclass
class When(ASTNode, Event):
    author: Subject
    action: Action


@dataclass
class TimeEvent(ASTNode, Event):
    time_qualifier: TimeQualifier
    time_instant: TimeInstant
    player: Player

    def event_subjects(self) -> List[Subject]:
        return []

    def unique_event_name(self):
        return f"on_{self.time_instant.event_name()}_{self.time_qualifier.event_name()}"

@dataclass
class During(ASTNode, Effect):
    condition: TimeEvent
    effect: Effect

@dataclass
class ConditionalTimeMoment(ASTNode, Event):
    event: TimeEvent
    condition: Condition

    def event_subjects(self) -> List[Subject]:
        return self.event.event_subjects()

@dataclass
class IsWarlord(ASTNode, ModelCondition, UnitCondition):
    player: Player

@dataclass
class IfIsHappening(ASTNode, Condition):
    action: Action

@dataclass
class IsExactly(ASTNode, Condition):
    subject: Subject

@dataclass
class ThatMove(ASTNode, ActionSubject):
    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, ThatMove)

# refers to the top level action of shooting, instead of making attacks
@dataclass
class Shoot(ASTNode, ActionSubject):
    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Shoot)

# refers to the top level action of fighting, instead of making attacks
@dataclass
class Fight(ASTNode, ActionSubject):
    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Fight)

# refers to the top level action of moving indipendently from the exact kind of move being done.
@dataclass
class Move(ASTNode, ActionSubject):
    move_kind: MovementKind

    def is_reference_to_me(self, other: Subject) -> bool:
        return isinstance(other, Move) and self.move_kind == other.move_kind

@dataclass
class After(ASTNode, Event):
    actor: Subject
    action: Action

    def event_subjects(self) -> List[Subject]:
        return [self.actor]

@dataclass
class WhenDoingLastMentionedAction(ASTNode, Event):
    pass

# used to refer to the next subject introduced in the ast
@dataclass
class NextSubject(ASTNode, Subject, Unreferrable, Qualification):
    def is_reference_to_me(self, other: Subject) -> bool:
        return False

@dataclass
class WhenSelected(ASTNode, Event):
    actor: Subject
    action: ActionSubject

    def unique_event_name(self):
        return "on_selection"

    def event_subjects(self) -> List[Subject]:
        return [self.actor]

@dataclass
class AfterAllAttacks(ASTNode, Event):
    attacks_source: Union[UnitSubject, ModelSubject]

    def unique_event_name(self):
        return "on_all_attacks_compleated"

    def event_subjects(self) -> List[Subject]:
        return [self.attacks_source]

def text2int(textnum, numwords={}):
    if textnum.isnumeric():
        return int(textnum)
    if not numwords:
      units = [
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
        "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
        "sixteen", "seventeen", "eighteen", "nineteen",
      ]

      tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

      scales = ["hundred", "thousand", "million", "billion", "trillion"]

      numwords["and"] = (1, 0)
      for idx, word in enumerate(units):    numwords[word] = (1, idx)
      for idx, word in enumerate(tens):     numwords[word] = (1, idx * 10)
      for idx, word in enumerate(scales):   numwords[word] = (10 ** (idx * 3 or 2), 0)

    current = result = 0
    for word in textnum.split():
        if word not in numwords:
            raise Exception("cannot convert "+ textnum)

        scale, increment = numwords[word]
        current = current * scale + increment
        if scale > 100:
            result += current
            current = 0

    return result + current



@v_args(inline=True)
class ToAst(Transformer):
    def devastating_wounds(self):
        return WeaponAbility(WeaponAbilityKind.DEVASTATING_WOUNDS)

    def sustained_hits(self, quantity):
        return WeaponAbility(WeaponAbilityKind.SUSTAINED_HITS, quantity)

    def letal_hits(self):
        return WeaponAbility(WeaponAbilityKind.LETHAL_HITS, )

    def assault(self):
        return WeaponAbility(WeaponAbilityKind.ASSAULT)

    def charge_roll(self):
        return RollKind.CHARGE_ROLL

    def advance_roll(self):
        return RollKind.ADVANCE_ROLL

    def saving_throw_roll(self):
        return RollKind.SAVING_THROW_ROLL

    def hit_roll(self):
        return RollKind.HIT_ROLL

    def wound_roll(self):
        return RollKind.WOUND_ROLL

    def time_start(self):
        return TimeQualifier.START

    def time_end(self):
        return TimeQualifier.END

    def current_phase(self):
        return TimeInstant.CURRENT_PHASE

    def start(self, content):
        return content

    def signle_effect(self, child):
        return child

    def gain_cp_effect(self, quantity):
        return GainCPEffect(quantity)

    def effect_seq(self, *effects):
        return [effect for effect in effects if str(effect) != "."]

    def opponent_qualifier(self, *effects):
        return Player.OPPONENT

    def any_player_qualifier(self):
        return Player.ANY

    def you_qualifier(self, *effects):
        return Player.YOU

    def fighting_phase(self):
        return TimeInstant.FIGHT_PHASE

    def shooting_phase(self):
        return TimeInstant.SHOOTING_PHASE

    def movement_phase(self):
        return TimeInstant.MOVEMENT_PHASE

    def command_phase(self):
        return TimeInstant.COMMAND_PHASE

    def battle_shock_step(Self):
        return TimeInstant.BATTLE_SHOCK_STEP

    def suffers_such_test(self, subject):
        return RollIsPerformed(ThisRoll(), subject)

    def endable_action(self, action):
        return action

    def time_condition(self, base_time_condition, predicate):
        if predicate is None:
            return base_time_condition
        return ConditionalTimeMoment(base_time_condition, predicate)

    def subject_action(self, main_action, predicate, extra_action):
        if predicate:
            main_action = ModifyAction(main_action, predicate)
        if not extra_action:
            return main_action
        return And(main_action, extra_action)

    def during_attack(self, subject):
        return IfIsHappening(Attack(subject, AttackKind.ANY))

    def roll_made_for(self, roll, author):
        return RollIsPerformed(roll, author)

    def makes_attacks(self, subject, attack_kind):
        return AttackEvent(source=subject, attack=attack_kind if attack_kind else AttackKind.ANY)

    def normal_move(self):
        return MovementKind.NORMAL

    def has_fly_keyword(self):
        return HasKeyword(Keyword.FLY)

    def excluding_keyworded_units(self, keyword):
        return Not(HasKeyword(keyword))

    def advance_move(self):
        return MovementKind.ADVANCE

    def remain_stationary(self):
        return MovementKind.REMAIN_STATIONARY

    def blistering_assault(self):
        return MovementKind.BLISTERING_ASSAULT

    def fall_back(self):
        return MovementKind.FALL_BACK

    def movement(self, *movements):
        if len(movements) == 1:
            return movements[0]
        current = movements[0]
        for movement in movements[1:]:
            current = Or(current, movement)
        return MakeMove(current, -1)

    def make_movement(self, movement_kind, quantity):
        return MakeMove(movement_kind, quantity)

    def must_action(self, subject_action: Action):
        return QualifiedAction(subject_action, UsageKind.MANDATORY)

    def must_move_as_close_as_possible(self, target):
        return MustMoveAsCloseAsPossibleTo(target)

    def can_action(self, subject_action: Action):
        return QualifiedAction(subject_action, UsageKind.OPTIONAL)

    def can_use(self, subject: Subject, condition: Condition):
        return TriggeredEffectReversed(subject, CanUseIt(), condition)

    def destroys_target(self, attacker, subject):
        return Destroys(attacker, subject)

    def is_destroyed(self, subject, attacker):
        return Destroys(subject, attacker)

    def raw_number_outer(self, *number):
        return int("".join(str(num) for num in number))

    def obtain_property(self, predicate):
        return predicate

    def can_be_set_up(self, predicate):
        return CanBeSetup(predicate)


    def word_number(self, number):
        return text2int(str(number))

    def number(self, *items):
        return int("".join(items))

    def set_models_of_spawned_unit(self, quantity):
        return SetModelsOfSpawnedUnits(quantity)

    def word_quantity(self, *items):
        words = " ".join(items)
        val = text2int(words)
        if val is None: raise ValueError(f"Bad number words: {words}")
        return val

    def army_subject(self, friend):
        return Army(friend)

    def enemy(self):
        return Player.OPPONENT

    def allied(self):
        return Player.YOU

    def this_model_subject(self, *args):
        return ThisModel()

    def each_time_effect(self, action: Performs, comma, effect):
        return TriggeredEffect(action, effect)

    def event_stratagem_subject(self):
        return Stratagem()

    def event_model_subject(self, predicates):
        if predicates:
            return ConditionalSubject(Model(), condition=predicates)
        return Model()

    def event_unit_subject(self, predicates):
        if predicates:
            return ConditionalSubject(Unit(), condition=predicates)
        return Unit()

    def prefixed_predicates(self, friend, keyword):
        condition = None
        if friend:
            condition = Enemy() if friend==Player.OPPONENT else Allied()
        if keyword:
            condition = And(condition, HasKeyword(keyword)) if condition is not None else HasKeyword(keyword)
        return condition

    def model_subject(self, quantity, prefixed_predicate):
        models = ConditionalSubject(Model(), prefixed_predicate) if prefixed_predicate is not None else Model()

        if quantity is not None:
            return Multiple(min=quantity, max=quantity, subject=models)
        return models

    def phase_condition2(self, time_qualifier, player_qualifier, phase_instant):
        return TimeEvent(time_qualifier if time_qualifier is not None else TimeQualifier.DURING, phase_instant, player_qualifier )

    def phase_condition(self, time_qualifier, phase_instant, player_qualifier):
        return TimeEvent(time_qualifier, phase_instant, player_qualifier if player_qualifier  else Player.ANY)

    def first_battle_round(self):
        return TimeInstant.FIRST_BATTLE_ROUND

    def battle_round_condition(self, time_qualifier, battle_round_index):
        return TimeEvent(time_qualifier, battle_round_index if battle_round_index else TimeInstant.ANY_BATTLE_ROUND, Player.ANY)

    def step_condition(self, time_qualifier, step_instant, player_qualifier, phase_instant ):
        return TimeEvent(time_qualifier, step_instant, player_qualifier if player_qualifier else Player.ANY)

    def selection(self, subject, effect):
        return Select(introduced_target=subject, effect=NoEffect() if not effect else effect)

    def roll_modifier(self, quantity):
        return quantity

    def for_each_effect(self, subject, comma, effect):
        return ForEachSubject(effect, subject, TrueCondition())

    def roll_action(self, dice_expression, for_each_subject, for_each_predicate, comma, roll_modifier, effect):
        action = PerformRoll(dice_to_roll=dice_expression, roll_modifier=roll_modifier, effect=effect)
        if for_each_subject:
            return ForEachSubject(action, for_each_subject, for_each_predicate)
        return action

    def optional_selection(self, subject, effect):
        if effect is None:
            effect = NoEffect()
        sel_action = Select(introduced_target=subject, effect=effect)
        return QualifiedAction(sel_action, UsageKind.OPTIONAL)

    def timed_action(self, time_condition, comma, effect):
        return During(condition=time_condition, effect=effect)

    def within_engagement_range(self, subject):
        return WithinEngagementRange(subject)

    def within_synapse_range(self, subject):
        return WithinSynapseRange(subject)

    def weapon_effect(self, qualifier, subject, modifier):
        if qualifier is None:
           qualifier = WeaponQualifier.ANY
        return ModifyWeapons(subject=subject, weapon_modifier=modifier, weapon_qualifier=qualifier)

    def ranged_weapon(self):
        return WeaponQualifier.RANGED

    def melee_weapon(self):
        return WeaponQualifier.MELEE

    def character_keyword(self):
        return Keyword.CHARACTER

    def tyranid_keyword(self):
        return Keyword.TYRANID

    def obtain_cover(self, subject):
        if not subject:
            ObtainCover(Model())
        return ObtainCover(subject)

    def monster_keyword(self):
        return Keyword.MONSTER

    def psyker_keyword(self):
        return Keyword.PSYKER

    def neurogaunt_keyword(self):
        return Keyword.NEUROGAUNT

    def synapse_keyword(self):
        return Keyword.SYNAPSE

    def titanic_keyword(self):
        return Keyword.TITANIC

    def termagants_keyword(self):
        return Keyword.TERMAGANTS

    def infantry_keyword(self):
        return Keyword.INFANTRY

    def within_range(self, range, subject):
        return WithinRange(range, subject)

    def within_range_of(self, subject):
        return WithinRange(-1, subject)

    def single_effect(self, effect):
        return effect

    def objective_marker_subject(self):
        return ObjectiveMarker()

    def property(self, property):
        return property

    def has_properties(self, property, *other_properties):
        if len(other_properties) == 0:
            return property
        for other in other_properties:
            property = And(property, other)
        return property

    def obtain_property_list(self, subject, property, *other_properties):
        if len(other_properties) == 0:
            return ObtainProperty(subject, property)
        for other in other_properties:
            property = And(property, other)
        return ObtainProperty(subject, property)

    def outside_range(self, range, subject):
        return OutsideRange(range, subject)

    def wholly_within_range(self, range, subject):
        return WithinRange(range, subject)

    def until_effect(self, time_condition, comma, effect):
        return TemporaryEffect(time_condition, effect)

    def that_targets(self, subject):
        return ThatIsTargeting(subject)

    def dependant_reroll_action(self, reroll):
        return reroll

    def reroll_exact_number(self, subject, number_to_reroll):
        return Reroll(subject, number_to_reroll)

    def modified_test_effect(self, roll, comma, quantity):
        return ModifiedTest(roll, quantity)

    def is_condition(self, subject, predicate):
        return SubjectIs(subject=subject, predicate=predicate)

    def after_attacking(self, subject):
        return AfterAllAttacks(subject)

    def after_resolving(self, subject):
        return Resolving(subject)

    def player_turn_condition(self, qualifier, player):
        return TimeEvent(qualifier if qualifier is not None else TimeQualifier.START, TimeInstant.TURN, player)

    def turn_condition(self, qualifier, player):
        return TimeEvent(qualifier if qualifier is not None else TimeQualifier.START, TimeInstant.TURN, Player.ANY if not player else player)

    def battle_condition(self, qualifier):
        return TimeEvent(qualifier if qualifier is not None else TimeQualifier.START, TimeInstant.BATTLE, Player.ANY)

    def after_shooting(self, subject):
        return After(subject, Shoot())


    def single_weapon_ability(self, weapon_ability):
        return AddAbilityModifier(ability=weapon_ability)

    def multiple_weapon_abilities(self, weapon_ability, weapon_ability2):
        return And(AddAbilityModifier(ability=weapon_ability), AddAbilityModifier(ability=weapon_ability2))

    def reduce_strat_cost(self, reduce_increase, subject, quantity):
        return ChangeStratCost(subject, quantity=quantity * reduce_increase)

    def reduce(self):
        return -1

    def targets_with_specific_stratagem(self, subject, stratagems, predicate):
        return TargetsWithStratagem(subject, stratagems, predicate)

    def targets_with_stratagem(self, subject):
        return TargetsWithStratagem(subject, [StratagemKind.ANY], None)

    def opponent_subject(self):
        return Opponent()

    def other_subjects(self, subject):
        return EveryOther(subject)

    def is_warlord(self, friend):
        return IsWarlord(friend)

    def increase(self):
        return 1

    def one_or_more_subject(self, subject):
        return Multiple(1, -1,  subject)

    def are_on_the_battlefield(self):
        return OnTheBattleField()

    def modifier(self, subject, weapon_modifier):
        return ApplyWeaponModifier(subject=subject, weapon_modifier=weapon_modifier, )

    def model_with_keyword(self, keyword):
        return ModelWithKeyword(keyword)

    def attack_targets_subject(self, qualifier, subject):
        return AttackTargets(subject, qualifier if qualifier else AttackKind.ANY)

    def leading_subject(self, subject):
        return Leading(subject)

    def targeted_with_a_stratagem(self, subject, stratagem_subject):
        return TargetedWith(subject, stratagem_subject)

    def battle_shock_test(self):
        return BattleShockTest()

    def below_starting_strenght(self):
        return BelowItsStartingStrenght()

    def below_half_strenght(self):
        return BelowHalfStrenght()

    def such_subject(self, subject):
        return Such(subject)

    def it_subject(self):
        return Such(None)

    def this_unit(self):
        return ThisUnit()

    def the_target(self):
        return TheTarget()

    def the_selected_units(self):
        return TheSelectedUnits()

    def leadership(self):
        return Characteristic.LEADERSHIP

    def direct_if_effect(self, condition, when_condition, comma, effect):
        if when_condition:
            condition = And(condition, when_condition)
        return ConditionalEffect(condition=condition, effect=effect)

    def conditional_effect(self, condition, comma, effect):
        return ConditionalEffect(condition=condition, effect=effect)

    def after_effect(self, event, comma, effect):
        return AfterEffect(event=event, effect=effect)

    def attack_made_with_weapon(self, weapon_name: Tree):
        return AttackMadeWithWeapon(weapon_name.data)

    def attack_subject_outer(self, subject):
        return subject

    def melee_attack_kind(self):
        return AttackKind.MELEE

    def ranged_attack_kind(self):
        return AttackKind.RANGED

    def attack_subject(self, attack_kind, predicate):
        if not attack_kind:
            attack_kind = AttackKind.ANY
        if not predicate:
            return Attack(attack_kind)
        return ConditionalSubject(Attack(attack_kind), predicate)

    def subordinate_if_effect(self, original_effect, dot, condition, comma, effect):
        return AdditionalEffect(original_effect, ConditionalEffect(condition=condition, effect=effect))

    def in_the_moment_effect(self, time_moment, comma, effect):
        return ConditionalEffect(condition=time_moment, effect=effect)

    def modify_roll(self, reduce_increase, quantity, roll_kind):
        return ModifyRoll(reduce_increase*quantity, roll_kind)

    def in_subject(self, subject):
        return In(subject)

    def halve_characteristic(self, characteristic, subject):
        return ModifyCharacteristicEffect(characteristic, subject, ModifyCharacteristicExpression(0, 0.5))

    def modify_weapon_characteristic(self, reduce_increase, weapon_characteristic, subject, quantity):
        return ModifyWeaponCharacteristic(weapon_characteristic, subject, quantity*reduce_increase)

    def the_same_subject(self, subject):
        return subject

    def subtract_effect(self, effect):
        return effect

    def each_time_subtract_effect(self, effect, event):
        return TriggeredEffect(event, effect)

    def battle_shocked(self):
        return BattleShocked()


    def you_subject(self):
        return You()

    def declare_charge_action(self):
        return DeclareCharge()

    def declare_shoot_action(self):
        return DeclareShoot()

    def fell_back_action(self):
        return FellBack()

    def cannot_charge(self):
        return CannotCharge()

    def cannot_have_cover(self):
        return CannotHaveCover()

    def elegibility_list(self, *actions):
        return [action for action in actions]

    def is_elegible_to(self, actions, action):
        return BecomesElegibleForTurn(actions, action)

    def shadow_in_the_warp(self, subject):
        return TimeEvent(TimeQualifier.DURING, TimeInstant.SHADOW_IN_THE_WARP, subject)

    def player_action_outer(self, action):
        return action

    def forward_player_action(self, action):
        return action

    def action(self, subject, action: Action):
        return Performs(subject, action)

    def once_per_round(self, COMMA, effect):
        return OncePerRound(effect)

    def once_per_turn(self, COMMA, effect):
        return OncePerTurn(effect)

    def once_per_battle(self, COMMA, effect):
        return OncePerBattle(effect)

    def battle_shock_roll(self):
        return Roll([RollKind.BATTLE_SHOCK_ROLL])

    def subtract_from_such(self, subtract_effect):
        return ModifiedRoll(Such(None), subtract_effect)

    def selected_to_shoot(self, subject):
        return WhenSelected(NextSubject() if subject is None else subject, Shoot())

    def selected_to_fight(self, subject):
        return WhenSelected(NextSubject() if subject is None else subject, Fight())


    def selected_to_move(self, subject, move_kind):
        return WhenSelected(NextSubject() if subject is None else subject, Move(move_kind))

    def complex_roll(self, *rolls):
        return [roll for roll in rolls]

    def base_roll(self, roll):
        return roll

    def hits_roll(self):
        return Roll([RollKind.HIT_ROLL])

    def in_addition_effect(self, effect, dot, comma, effect2):
        return AdditionalEffect(effect, effect2)

    def effect(self, effect, *effects):
        if len(effects) == 0:
            return effect
        for extra in effects:
            effect = And(effect, extra)
        return effect

    def if_it_does(self, effect, dot, comma, effect2):
        return OnActivationEvent(effect, effect2)

    def worsen_characteristic2(self, reduce_increase, quantity, characterirstic):
        return ModifyCharacteristicEffect(characterirstic, Such(None), ModifyCharacteristicEffect(reduce_increase*quantity))

    def worsen_characteristic(self, reduce_increase, characterirstic, subject, quantity):
        return ModifyCharacteristicEffect(characterirstic, subject, ModifyCharacteristicExpression(reduce_increase*quantity))

    def non_attack_subject(self, subject, predicate):
        if predicate is None:
            return subject
        if isinstance(subject, ConditionalSubject):
            subject.condition = And(subject.condition, predicate)
            return subject
        return ConditionalSubject(subject, predicate)

    def predicate(self, *predicates):
        if len(predicates) == 0:
            raise Exception("empty predicate")
        if len(predicates) == 1:
            return predicates[0]
        current = predicates[0]
        for predicate in predicates[1:]:
            current = And(current, predicate)
        return current

    def with_this_ability(self):
        return With(ThisAbility())

    def using_ability(self, ability):
        return UsingAbility(ability)

    def from_army(self, friend):
        if friend == Player.YOU:
            return Allied()
        elif friend == Player.OPPONENT:
            return Enemy()
        return TrueCondition()

    def reroll(self, roll_kind):
        return Reroll(roll_kind)

    def optional_player_action(self, action):
        return QualifiedAction(action, UsageKind.OPTIONAL)

    def add_unit_to_game(self, quantity, name, models_predicate, setup_predicate):
        return AddUnitToTheGame(quantity, UnitNamed(name=name.data), models_predicate, setup_predicate)

    def regain_wounds(self, quantity):
        return RegainWounds(quantity)

    def _raw_unit_subject(self, prefixed_predicates):
        return ConditionalSubject(Unit(), prefixed_predicates) if prefixed_predicates is not None else Unit()

    def upper_bounded_unit_subject(self, quantity, prefixed_predicates):
        subject = self._raw_unit_subject(prefixed_predicates)
        return Multiple(min=0, max=quantity, subject=subject)

    def unit_subject(self, quantity, prefixed_predicate):
        subject = self._raw_unit_subject(prefixed_predicate)
        if quantity is not None:
            return Multiple(min=quantity, max=quantity, subject=subject)
        return subject

    def loses_wounds(self, subject):
        return LosesWounds(subject)

    def mortal_wound_modifier(self, effect):
        return ConditionalEffect(SuffersMortalWounds(-1), effect)

    def limit_once_per_phase(self):
        return LimitOncePerPhase(ThisAbility())

    def return_models(self, quantity, subject):
        return ReturnModels(quantity, subject)

    def add_synapse(self, friend):
        return AddSynapse(friend)

    def unit_of_subject(self, subject):
        return UnitOf(subject)

    def unit_by_name(self, name):
        return UnitNamed(name.data)

    def predicate_or_subject(self, obj):
        return obj

    def weapon_attacks(self):
        return WeaponCharacteristic.ATTACKS

    def armour_penetration(self):
        return WeaponCharacteristic.AP

    def damage_weapon_characteristic(self):
        return WeaponCharacteristic.DAMAGE

    def weapon_characteristic_subject_outer(self, subject):
        return subject

    def weapon_characteristic_subject(self, characteristic, weapon_predicate):
        return CharacteristicOfWeapons(characteristic, weapon_predicate)

    def equipped_by(self, subject):
        return EquippedBy(subject)

    def dice_interpretation_effect(self, effect):
        return effect

    def dice_result(self):
        return DiceResult()

    def move_up_to(self, quantity):
        return RawMove(quantity)

    def dice_interpretation(self, *interpretations):
        return InterpretDice(interpretations)

    def visible_to(self, subject):
        return VisibleTo(subject)

    def are_always_considered(self, subject):
        return subject

    def suffers_mortal_wounds(self, quantity):
        return SuffersMortalWounds(quantity)

    def not_predicate(self, predicate):
        return Not(predicate)

    def of_those_attacks(self, predicate):
        return Not(predicate)

    def all_subject(self, subject):
        return All(subject)

    def ends_action(self, subject, action):
        return TimeEvent(TimeQualifier.END, When(subject, action), Player.ANY)

    def has_fought(self):
        return HasFought()

    def hit_by(self, subject):
        return HitBy(subject)

    def reroll_outer(self, reroll):
        return reroll

    def instead_of(self, effect, action):
        return ActionReplacementEffect(action, effect)

    def but_effect(self, effect, comma, effect2):
        return And(effect, effect2)

    def modified_property(self, property, property2):
        return And(property, property2)


    def those_attacks(self):
        return ThoseAttacks()

    def can_reuse_stratagem_turn(self, _):
        return LimitKind.TURN

    def neurothrope_name(self):
        return "neurothrope"

    def can_reuse_stratagem_phase(self, _):
        return LimitKind.PHASE

    def discount_stratagems(self, new_cost, can_reuse_stratagem):
        return ReplaceCostOfStratagem(new_cost, can_reuse_stratagem)

    def stratagems(self, stratagems):
        return stratagems

    def status_disrupted(self):
        return StatusKind.DISRUPTED

    def move_characteristic(self):
        return Characteristic.MOVE

    def oc_characteristic(self):
        return Characteristic.OC

    def atomic_predicate(self, *predicates):
        if len(predicates) == 1:
            return predicates[0]
        current = predicates[0]
        for pred in predicates[1:]:
            current = And(current, pred)
        return current

    def afflict_status(self, status):
        return AfflictStatus(status)

    def with_its_weapons(self, weapons_kind):
        return PerformedWithItsWeapon(weapons_kind)

    def anywhere_on_the_battlefield(self, predicate):
        return predicate

    def stratagem_list(self, *stratagems):
        return [strat for strat in stratagems]

    def heroic_intervention(self):
        return StratagemKind.HEROIC_INTERVENTION

    def rapid_ingress(self):
        return StratagemKind.RAPID_INGRESS

    def fire_overwatch(self):
        return StratagemKind.FIRE_OVERWATCH

    def fight_on_death(self):
        return ObtainFightOnDeath()

    def usage_of(self, subject):
        return subject

    def raw_number(self, number):
        return number

    def that_stratagem(self):
        return Such(subject=Stratagem())

    def must_do_instead(self, subject, replacement):
        return ActionReplacementEffect(ActionOf(subject), replacement)

    def indented_effect_seq(self, star, effect_seq):
        return effect_seq

    def final_indented_effect_seq(self, star, effect_seq):
        return effect_seq

    def add_models_predicate(self, first, *other):
        if len(other) == 0:
            return first
        for pred in other:
            first = And(first, pred)
            return first

    def add_unit_to_army(self):
        return AddUnitToArmy()

    def this_option(self):
        return ThisOption()

    def cannot_select_model_multiple_times(self, quantity):
        return quantity

    def cannot_select(self, selectee, quantity):
        return CannotSelect(selectee, quantity)

    def during_that_move(self):
        return IfIsHappening(ThatMove())

    def roll_requirements(self, roll_requirement, comma, other_requirement, condition):
        if not comma:
            return [RollTresholdReplacement(roll_requirement, TrueCondition())]
        return [RollTresholdReplacement(roll_requirement, TrueCondition()), RollTresholdReplacement(other_requirement, condition)]

    def roll_requirement(self, roll_subject, raw_number):
        return RollRequirement(roll_subject, raw_number)

    def replace_required_roll(self, roll_subject, requirements):
        return RollTresholdReplacement(roll_subject, requirements)

    def add_models_quantity(self, quantity):
        return QuantityOfModelsToAdd(quantity)

    def moved_over(self, by, condition):
        return MovedOver(by, condition)

    def specific_model_name(self, name):
        return SpecificModel(name)

    def contains(self, subject):
        return Contains(subject)

    def neurothrope(self):
        return "neurothrope"

    def obtain_invulnerable_save(self, quantity):
        return ObtainInvulnerableSave(quantity)

    def select_one_of_the_following(self, effects):
        return QualifiedAction(SelectAlternativeAction(effects), UsageKind.OPTIONAL)

    def select_one_of_the_following_mandatory(self, effects):
        return QualifiedAction(SelectAlternativeAction(effects), UsageKind.MANDATORY)

    def indented_effect(self, *alternatives):
        return alternatives

    def destroyed_subject(self, subject):
        return ConditionalSubject(subject, Destroyed())

    def can_be_moved(subject, predicate):
        return AllowForbiddenMovement(predicate)

    def and_effect(self, effect, comma, comma2, effect2):
        return And(effect, effect2)

    def deep_strike(self):
        return Ability(AbilityKind.DEEP_STRIKE)

    def feel_no_pain(self, value):
        return Ability(AbilityKind.FEEL_NO_PAIN, value)

    def destroy(self):
        return Destroy()

    def special_rule_subject(self, subject):
        return subject

    def stealth_ability(self):
        return Ability(AbilityKind.STEALTH, 0)

    def subterranean_tunnel(self):
        return SpecialRule("subterranean tunnel")

    def parentetic_predicate(self, predicate):
        return predicate

    def that_attack(self):
        return SuchAttack()

    def event_subject(self, subject):
        return subject

    def this_ability(self):
        return ThisAbility()

    def change_attack_characteristic(self, characteristic, subject, quantity):
        return ChangeAttackCharacteristic(characteristic, subject, quantity)

    def subtract_effect(self, effect):
        return effect

    def attack_allocated_to(self, subject):
        return AttackAllocatedTo(subject)

    def limit_targeting_per_turn(self, subject):
        return LimitTargetingPerTurn(subject)

    def limit_effect_per_turn(self, effect):
        return LimitEffectPerTurn(effect)

    def range_number_greater(self, number):
        return NumberRange(number, -1)

    def range_number_range(self, min, max):
        return NumberRange(min,max)

    def range_number_exact(self, min):
        return NumberRange(min,min)

    def limit_actions_per_phase(self, predicate):
        return LimitOncePerPhase(predicate)

    def doing_so(self):
        return WhenDoingLastMentionedAction()

    def not_terminated_effect_seq(this, first, *other):
        if len(other) == 0:
            return first
        for item in other:
            first = And(first, other)

    def if_list(self, condition, effect_list):
        if len(effect_list) == 0:
            return ConditionalEffect(condition=condition, effect=effect_list[0])
        first = effect_list[0]
        for effect in effect_list[1:]:
            first = And(first, effect)
        return ConditionalEffect(condition=condition, effect=first)

    def or_subject(self, s1, s2):
        return Or(s1, s2)

    def any_move(self):
        return [MovementKind.ANY]

    def replace_characteristic(self, char, new_value):
        return ReplaceCharacteristic(new_value, char)

    def aquire_keyword(self, keyword):
        return AddKeyword(keyword)

    def aquire_ability(self, ability):
        return AddAbility(ability)

    def cannot_advance_near(self, distance, target):
        return CannotAdvance(WithinRange(distance, target))

    def is_setup(self, subject):
        return After(subject, SetUp())

    def place_in_strategic_reserve(self, subject):
        return PlaceInStrategicReserve(subject)

    def unmodified_roll_subject(self, subject):
        return Unmodified(subject)

    def greater_than_number_case(self, value, effect):
        return NumberCase(value, NumberCaseKind.GREATER_EQUAL, effect)

    def exact_number_case(self, value, effect):
        return NumberCase(value, NumberCaseKind.EQUAL, effect)

    def dice_value(self, num_dices_to_roll, number, raw_extra):
        return DiceExpression(1 if num_dices_to_roll is None else str(num_dices_to_roll),number, raw_extra if raw_extra else 0)

    def select_subject(self, subject):
        return Select(introduced_target=subject, effect=NoEffect())


DROP = object()  # sentinel meaning "remove this node"

class ASTTransformer:
    """Transform a dataclass AST by dispatching on the node's *Python class*.
    Method name: transform_<ClassName>(self, node) -> replacement | DROP | node
    """

    # --- public API ---
    def transform(self, node):
        return self._tx(node)

    # --- core ---
    def _tx(self, node):
        if isinstance(node, List):
            return [self._tx(n) for n in node]
        if isinstance(node, type):
            return node
        if not is_dataclass(node):
            return node

        # default: recurse into fields
        for f in fields(node):
            val = getattr(node, f.name)
            setattr(node, f.name, self._tx_value(val))

        # dispatch by class name, walking MRO so base handlers work too
        out = self.visit(node)
        if out is not node:      # replaced, inlined, or dropped
            return None if out is DROP else out

        return node

    def _tx_value(self, v):
        if is_dataclass(v):
            return self._tx(v)
        if isinstance(v, list):
            out = []
            for item in v:
                if is_dataclass(item):
                    t = self._tx(item)
                    if t is not DROP:
                        out.append(t)
                else:
                    out.append(item)
            return out
        if isinstance(v, tuple):
            items = []
            for item in v:
                if is_dataclass(item):
                    t = self._tx(item)
                    if t is not DROP:
                        items.append(t)
                else:
                    items.append(item)
            return tuple(items)
        if isinstance(v, dict):
            return {k: (self._tx(val) if is_dataclass(val) else val) for k, val in v.items()}
        return v

@dataclass
class Scope:
    parent_table: 'Scope' = None
    limit: LimitKind = LimitKind.NO_LIMIT
    mentioned_subjects: List[Subject] = field(default_factory=list)
    sentence_subject: Subject = None
    sentence_target: Subject = None # the last target mentioned in a targeting sentence, such as "when a model attacks [a unit]"
    last_usable_subject: UsableSubject = None # the last ability, option, stratagem... subject mentioned
    roll_subject : RollSubject = None # the last roll subject mentioned
    last_optional_usage_mentioned : Use = None # the last optional usage mentioned

    def get_sentence_subject(self) -> Subject:
        if self.parent_table is None or self.sentence_subject is not None:
            return self.sentence_subject

        return self.parent_table.get_sentence_subject()

    def get_sentence_target(self) -> Subject:
        if self.parent_table is None or self.sentence_target is not None:
            return self.sentence_target

        return self.parent_table.get_sentence_target()

    def set_target(self, target):
        self.sentence_target = target


    def get_last_use_of_usable(self) -> Use:
        if self.parent_table is None or self.sentence_target is not None:
            return self.last_optional_usage_mentioned

        return self.parent_table.get_last_use_of_usable()

    def set_last_use_of_usable(self, can_use: Use):
        self.last_optional_usage_mentioned = can_use

    def get_usable_subject(self) -> UsableSubject:
        if self.parent_table is None or self.last_usable_subject is not None:
            return self.last_usable_subject

        return self.parent_table.get_last_roll()

    def set_last_usable_target(self, target):
        self.last_usable_subject = target

    def get_last_roll(self) -> UsableSubject:
        if self.parent_table is None or self.roll_subject is not None:
            return self.roll_subject

        return self.parent_table.get_last_roll()

    def set_last_roll(self, target):
        self.roll_subject = target

    def add_subject(self, subject):
        self.mentioned_subjects.append(subject)

    def find_subject(self, subject_filter: Subject) -> Subject:
        for mentioned_subject in reversed(self.mentioned_subjects):
            if mentioned_subject.is_reference_to_me(subject_filter):
                return mentioned_subject

        if self.parent_table == None:
            return None

        return self.parent_table.find_subject(subject_filter)

class ScopeDropper:
    def __init__(self, analyzer: 'SemanticalAnalyzer'):
        self.analyzer = analyzer
        analyzer.tables.append(Scope())

    def __enter__(self):
        pass

    def __exit__(self, *args):
        self.analyzer.tables.pop()

class SemanticalAnalyzer:
    def create_scope(self):
        return ScopeDropper(self)

    def __init__(self):
        self.tables = [Scope()]
        self.total_emitted_symbols = 0

    def scope(self) -> Scope:
        return self.tables[len(self.tables)-1]

    def visit(self, node):
        replacement = self._visit(node)
        if isinstance(replacement, Subject):
            if not isinstance(replacement, Reference) and not isinstance(replacement, Qualification):
                replacement.subject_index = self.total_emitted_symbols
                self.total_emitted_symbols = self.total_emitted_symbols + 1
                self.scope().add_subject(replacement)
        if isinstance(replacement, UsableSubject):
            self.scope().set_last_usable_target(replacement)

        return replacement

    def _tx_value(self, v):
        if is_dataclass(v):
            return self.visit(v)
        if isinstance(v, list):
            out = []
            for item in v:
                if is_dataclass(item):
                    t = self.visit(item)
                    if t is not DROP:
                        out.append(t)
                else:
                    out.append(item)
            return out
        if isinstance(v, tuple):
            items = []
            for item in v:
                if is_dataclass(item):
                    t = self.visit(item)
                    if t is not DROP:
                        items.append(t)
                else:
                    items.append(item)
            return tuple(items)
        if isinstance(v, dict):
            return {k: (self.visit(val) if is_dataclass(val) else val) for k, val in v.items()}
        return v

    def _recurr(self, node):
        for f in fields(node):
            val = getattr(node, f.name)
            setattr(node, f.name, self._tx_value(val))
        return node

    @singledispatchmethod
    def _visit(self, node):
        if isinstance(node, Subject):
            print(type(node))
        if isinstance(node, Effect):
            print(type(node))
        return self.default(node)

    @_visit.register
    def _(self, condition: Leading):
        return self._recurr(condition)

    @_visit.register
    def _(self, effect: TriggeredEffect):
        self._recurr(effect)
        if effect.effect.effect_type == EffectType.MODIFIER:
            effect.effect_type = EffectType.MODIFIER
        else:
            effect.effect_type = EffectType.TRIGGERED_ACTION
        return effect

    @_visit.register
    def _(self, effect: TriggeredEffectReversed):
        self._recurr(effect)
        if effect.effect.effect_type == EffectType.MODIFIER:
            effect.effect_type = EffectType.MODIFIER
        else:
            effect.effect_type = EffectType.TRIGGERED_ACTION

        # for subject in effect.event.event_subjects():
            # if subject.subject_index == effect.subject.subject_index:
                # subject.replace(effect.subject)

        return TriggeredEffect(effect_type=effect.effect_type, event=effect.event, effect=Performs(effect.effect, effect.effect))

    @_visit.register
    def _(self, condition: SubjectIs):
        condition.subject = self.visit(condition.subject)
        condition.predicate = self.visit(condition.predicate)
        self.scope().sentence_subject = condition.subject
        return condition

    @_visit.register
    def _(self, condition: AddAbilityModifier):
        return self._recurr(condition)

    @_visit.register
    def _(self, node: ObtainProperty):
        self._recurr(node)
        node.effect_type = EffectType.MODIFIER
        return node

    @_visit.register
    def _(self, model: OnActivationEvent):
        self._recurr(model)
        can_use  = self.scope().get_last_use_of_usable()
        if not can_use:
            raise Exception("a AdditionalEffect found no previous optional effect to refer to")
        model.effect_type = model.first.effect_type

        can_use.after_use_effect = effect=model.consequence
        return model.first

    @_visit.register
    def _(self, node: UnitNamed):
        self._recurr(node)
        node.runtime_type = UnitSubject
        return node

    @_visit.register
    def _(self, node: EveryOther):
        self._recurr(node)
        node.runtime_type = list[node.subject.runtime_type]
        return node

    @_visit.register
    def _(self, effect: ConditionalEffect):
        self._recurr(effect)
        effect.effect_type = effect.effect.effect_type
        return effect

    @_visit.register
    def _(self, condition: In):
        return self._recurr(condition)

    @_visit.register
    def _(self, model: ModifyWeapons):
        self._recurr(model)
        model.effect_type = EffectType.MODIFIER
        # if model.subject.runtime_type == List[ModelSubject]:
            # model.runtime_type = List[WeaponSubject]
        # elif model.subject.runtime_type == ModelSubject:
            # model.runtime_type = WeaponSubject
        # else:
            # print(model)
            # raise Exception("a modify weapon rule can only apply to model or a list of models")
        return model

    @_visit.register
    def _(self, model: Multiple):
        self._recurr(model)
        model.runtime_type = List[ModelSubject]
        return model


    @_visit.register
    def _(self, node: Multiple):
        self._recurr(node)
        if node.max == 1 and node.min == 1:
            return node.subject
        node.runtime_type = List[node.subject.runtime_type]
        return node

    @_visit.register
    def _(self, model: NoEffect):
        self._recurr(model)
        model.effect_type = EffectType.RAW_EFFECT
        return model

    @_visit.register
    def _(self, model: TemporaryEffect):
        self._recurr(model)
        model.effect_type = EffectType.TEMPORARY_EFFECT
        return model

    @_visit.register
    def _(self, model: ConditionalSubject):
        self._recurr(model)
        model.runtime_type = model.subject.runtime_type
        model.subject_index = model.subject.subject_index
        return model

    @_visit.register
    def _(self, model: Such):
        if model.subject == None:
            referred = self.scope().get_sentence_subject()
            return Reference(runtime_type=referred.runtime_type, subject_index=referred.subject_index)
        with self.create_scope() as scope:
            self._recurr(model)
        candidate = self.scope().find_subject(model.subject)
        if candidate is None:
            raise Exception("Could not find referred candidate: " + str(model))
        return Reference(runtime_type=candidate.runtime_type, subject_index=candidate.subject_index)

    @_visit.register
    def _(self, effect: AfterEffect):
        self._recurr(effect)
        effect.effect_type = EffectType.TRIGGERED_ACTION
        return effect

    @_visit.register
    def _(self, effect: Performs):
        effect.usage_limit = self.scope().limit
        self._recurr(effect)
        effect.effect_type = effect.action.effect_type
        if isinstance(effect.action, QualifiedAction):
            effect.usage = effect.action.usage
            effect.usage_limit = effect.action.usage_limit
            effect.action = effect.action.action
        return effect

    @_visit.register
    def _(self, effect: TheTarget):
        referred = self.scope().get_sentence_target()
        return Reference(runtime_type=referred.runtime_type, subject_index=referred.subject_index)

    @_visit.register
    def _(self, model: WeaponAbility):
        self._recurr(model)
        model.runtime_type = WeaponSubject
        return model

    @_visit.register
    def _(self, model: Roll):
        model.runtime_type = RollSubject
        return model

    @_visit.register
    def _(self, model: TheSelectedUnits):
        self._recurr(model)
        model.runtime_type = List[UnitSubject]
        return model

    @_visit.register
    def _(self, model: ModifyCharacteristicEffect):
        self._recurr(model)
        model.effect_type = EffectType.RAW_EFFECT
        return model

    @_visit.register
    def _(self, model: OncePerRound):
        self.scope().limit = LimitKind.ROUND
        self._recurr(model)
        return model.effect

    @_visit.register
    def _(self, model: CanUseIt):
        self._recurr(model)
        target = self.scope().get_usable_subject()
        to_return = QualifiedAction(Use(effect_type=EffectType.ACTIVATED_ACTION,subject=Reference(runtime_type=target.runtime_type, subject_index=target.subject_index)), UsageKind.OPTIONAL, effect_type=EffectType.ACTIVATED_ACTION, usage_limit=self.scope().limit)
        self.scope().set_last_use_of_usable(to_return.action)
        return to_return

    @_visit.register
    def _(self, model: ThisAbility):
        self._recurr(model)
        model.runtime_type = AbilitySubject
        return model

    @_visit.register
    def _(self, model: Select):
        self._recurr(model)
        if isinstance(model.introduced_target, ConditionalSubject):
            model.target_condition = And(model.target_condition,model.introduced_target.condition)
            model.introduced_target = model.introduced_target.subject
        model.effect_type = EffectType.ACTIVATED_ACTION
        return model

    @_visit.register
    def _(self, model: AddUnitToTheGame):
        self._recurr(model)
        model.effect_type = EffectType.RAW_EFFECT
        return model

    @_visit.register
    def _(self, model: QualifiedAction):
        self._recurr(model)
        model.usage_limit = self.scope().limit
        if model.usage == UsageKind.OPTIONAL:
            model.effect_type = EffectType.ACTIVATED_ACTION
            self.scope().set_last_usable_target(model)
        else:
            model.effect_type = model.action.effect_type
        return model

    @_visit.register
    def _(self, model: During):
        self._recurr(model)
        if model.condition.time_qualifier != TimeQualifier.DURING:
            model.effect_type = EffectType.TRIGGERED_ACTION
        else:
            model.effect_type = model.effect.effect_type
        return model

    @_visit.register
    def _(self, model: ChangeStratCost):
        self._recurr(model)
        model.effect_type = EffectType.RAW_EFFECT
        return model

    @_visit.register
    def _(self, model: GainCPEffect):
        self._recurr(model)
        model.effect_type = EffectType.RAW_EFFECT
        return model

    @_visit.register
    def _(self, model: AdditionalEffect):
        raise NotImplemented()
        self._recurr(model)
        can_use  = self.scope().get_last_use_of_usable()
        if not can_use:
            raise Exception("a AdditionalEffect found no previous optional effect to refer to")
        model.effect_type = model.first.effect_type
        return model


    @_visit.register
    def _(self, model: AttackEvent):
        self._recurr(model)
        self.scope().sentence_subject = model.source
        self.scope().set_target(model.target)

        return model

    @_visit.register
    def _(self, model: Destroys):
        self._recurr(model)
        self.scope().sentence_subject = model.attacker
        self.scope().set_target(model.target)

        return model

    @_visit.register
    def _(self, model: ModifyRoll):
        self._recurr(model)
        model.effect_type = EffectType.MODIFIER
        return model

    @_visit.register
    def _(self, model: ModifyRoll):
        self._recurr(model)
        model.effect_type = EffectType.MODIFIER
        return model

    @_visit.register
    def _(self, model: Model):
        self._recurr(model)
        model.runtime_type = ModelSubject
        return model

    @_visit.register
    def _(self, model: UnitOf):
        self._recurr(model)
        if model.subject.runtime_type not in [ModelSubject, List[ModelSubject]]:
            print(model)
            raise Exception("Unit of does not refer to a model/s")
        model.runtime_type = UnitSubject
        return model

    @_visit.register
    def _(self, ability: With):
        self._recurr(ability)
        return ability

    @_visit.register
    def _(self, model: Stratagem):
        self._recurr(model)
        model.runtime_type = StratagemSubject
        return model

    @_visit.register
    def _(self, model: You):
        self._recurr(model)
        model.runtime_type = You
        return model

    @_visit.register
    def _(self, model: Unit):
        self._recurr(model)
        model.runtime_type = UnitSubject
        return model

    @_visit.register
    def _(self, model: ThisModel):
        self._recurr(model)
        model.runtime_type = ModelSubject
        return model

    @singledispatchmethod
    def default(self, node):
        return self._recurr(node)



class DropUselessNodes(ASTTransformer):
    @singledispatchmethod
    def visit(self, node):
        return node

    @visit.register
    def _(self, node: ConditionalSubject):
        if isinstance(node.subject, ConditionalSubject):
            node.condition = And(node.condition, node.subject.condition)
            node.subject = node.subject.subject
        return node

    @visit.register
    def _(self, node: And):
        if isinstance(node.rhs, NoEffect) or isinstance(node.rhs, TrueCondition):
            return node.lhs
        if isinstance(node.lhs, NoEffect) or isinstance(node.lhs, TrueCondition):
            return node.rhs
        return node

# hoists top level effects into other effects, if the to be hoised effect refers to a subjected defined inside the hoistee effect
class HoistDependantEffects(ASTTransformer):
    references_in_top_level_rules: List[List[Reference]]
    subject_introducing_effects: List[List[SubjectIntroducingEffect]]

    def __init__(self):
        super().__init__()
        self.subject_introducing_effects = []
        self.references_in_top_level_rules = []

    def _hoist_effect(self, to_inline: Effect, subject_effect: SubjectIntroducingEffect):
        subject_effect.add_additional_effect(to_inline)

    def _try_hoist(self, to_inline: Effect, id1: int, target: Effect, id2: int):
        if id1 == id2:
            return to_inline
        # for reference of this rule
        for reference in self.references_in_top_level_rules[id1]:
            # for introduced subject of that rule
            for subject_effect in self.subject_introducing_effects[id2]:
                for subject in subject_effect.get_introduced_subjects():
                    # if they are the same subject
                    if subject.subject_index == reference.subject_index:
                        self._hoist_effect(to_inline, subject_effect)
                        return None
        return to_inline


    def transform(self, node):
        # discover the subject introducing effects, and the references
        new_list = []
        for id, n in enumerate(node):
            self.references_in_top_level_rules.append([])
            self.subject_introducing_effects.append([])
            new_list.append(super().transform(n))
        node = new_list

        # for every distinct pair of top level rules
        new_list = []
        for i1, node in enumerate(node):
            inlined = False
            for i2, subject_effects in enumerate(self.subject_introducing_effects):
                new_node = self._try_hoist(node, i1, subject_effects, i2)
                if new_node is None:
                    inlined = True
                    break

            if not inlined:
                new_list.append(node)

        return new_list


    @singledispatchmethod
    def visit(self, node):
        return node

    @visit.register
    def _(self, node: SubjectIntroducingEffect):
        self.subject_introducing_effects[-1].append(node)
        return node

    @visit.register
    def _(self, node: Reference):
        self.references_in_top_level_rules[-1].append(node)
        return node

class FindAll(ASTTransformer):
    def __init__(self, type_of_interest: type):
        self.type_of_interest = type_of_interest
        self.results = []

    def visit(self, node):
        if isinstance(node, self.type_of_interest):
            self.results.append(node)
        return node

def find_all(node: ASTNode, to_find: type) -> List:
    finder = FindAll(type_of_interest=to_find)
    finder.transform(node)
    return finder.results

class ReplaceDuring(ASTTransformer):
    def visit(self, node: During):
        if not isinstance(node, During):
            return node
        if node.condition.time_qualifier == TimeQualifier.START or node.condition.time_qualifier == TimeQualifier.END:
            return TriggeredEffect(event=node.condition, effect=node.effect, effect_type=node.effect_type)

        return node

# temporary effects such as "Until" generate a new top level
# effect wrapped into a class, composed of a time limit and of a
# effect. The original temporary effect is replaced with the
# spawning of such temporary effect.
#
# References within a temporary effect that refers to a subject
# outside of the temporary effect become "CapturedVariables" that
# are passed by copy by the spawning mechanism.
class ExtractTemporaryEffects(ASTTransformer):
    def transform(self, node):
        temporary_effects = find_all(node, TemporaryEffect)

        results = []
        for index, temporary_effect in enumerate(temporary_effects):
            captured_references = self.find_captured_references(temporary_effect)
            temporary_effect.captured_subjects = captured_references
            temporary_effect.replace(CreateTemporaryEffect(index, [ref.subject_index for ref in captured_references], effect_type=EffectType.RAW_EFFECT))
            results.append(temporary_effect)
            temporary_effect.unique_id = index

        results = results + node
        return results


    # a captured reference is a reference that refers to something outside of the current TemporaryEffect, and that thus must be passed to the TemporaryEffect when it is construted, similar to other languages lambda fuctions.
    def find_captured_references(self, temporary_effect: TemporaryEffect):
        all_subjects = find_all(temporary_effect, Subject)
        references = [subject for subject in all_subjects if isinstance(subject, Reference)]
        non_reference_subjects = [subject for subject in all_subjects if not isinstance(subject, Reference)]
        captured = []
        for reference in references:
            if len([subject for subject in non_reference_subjects if subject.is_reference_to_me(reference)]) == 0:
                captured.append(reference)
        return captured

def semantically_analyze(ast: List[ASTNode]):
    canonicalizer = SemanticalAnalyzer()
    ast = [canonicalizer.visit(node) for node in ast]
    return ast

class RewriteEventConditions(ASTTransformer):
    @singledispatchmethod
    def _extract_conditions_from_subject(self, subject: Subject):
        return (subject, TrueCondition())

    @_extract_conditions_from_subject.register
    def _(self, subject: ConditionalSubject):
        (true_subject, condition) = self._extract_conditions_from_subject(subject.subject)
        if isinstance(condition, TrueCondition):
            return (true_subject, subject.condition)
        return (subject.subject, And(subject.condition, condition))

    @_extract_conditions_from_subject.register
    def _(self, subject: ThisModel):
        to_return = (Model(subject_index=subject.subject_index, runtime_type=ModelSubject), IsExactly(subject))
        subject.subject_index = -1
        return to_return

    @singledispatchmethod
    def visit(self, subject: Subject):
        return subject

    @visit.register
    def _(self, event: Destroys):
        (true_subject, true_condition) = self._extract_conditions_from_subject(event.attacker)
        event.attacker = true_subject
        event.conditions.append(true_condition)

        (true_subject, true_condition) = self._extract_conditions_from_subject(event.target)
        event.target = true_subject
        event.conditions.append(true_condition)
        return event

    @visit.register
    def _(self, event: TargetedWith):
        (true_subject, true_condition) = self._extract_conditions_from_subject(event.target)
        event.target = true_subject
        event.conditions.append(true_condition)

        (true_subject, true_condition) = self._extract_conditions_from_subject(event.subject)
        event.subject = true_subject
        event.conditions.append(true_condition)
        return event

    @visit.register
    def _(self, event: AttackEvent):
        (true_subject, true_condition) = self._extract_conditions_from_subject(event.source)
        event.source = true_subject
        event.conditions.append(true_condition)

        (true_subject, true_condition) = self._extract_conditions_from_subject(event.target)
        event.target = true_subject
        event.conditions.append(true_condition)
        return event

def canonicalize(ast):
    rewrite_event_conditions = RewriteEventConditions()
    ast = rewrite_event_conditions.transform(ast)

    canonicalizer = HoistDependantEffects()
    ast = canonicalizer.transform(ast)

    canonicalizer = DropUselessNodes()
    ast = canonicalizer.transform(ast)

    extract_temporary_effects = ExtractTemporaryEffects()
    ast = extract_temporary_effects.transform(ast)

    replace_during  = ReplaceDuring()
    ast = replace_during.transform(ast)
    return ast

class RLCSerializer:
    def __init__(self, out):
        self.out = out
        self.indentation_level = 0
        self.new_line = True

        self.subject_index_to_name = {}

    def printnl(self, string):
        self.print(string + "\n")
        self.new_line = True

    def print(self, string):
        if self.new_line:
            self.out.write((" " * self.indentation_level) )
        self.out.write(string)
        self.new_line = False

    def visit(self, node):
        if isinstance(node, list):
            for n in node:
                self.visit(n)
        else:
            self._visit(node)

    @singledispatchmethod
    def _serialize_subject(self, subject):
        self.print(str(type(subject)))

    @_serialize_subject.register
    def _(self, subject: Reference):
        self._serialize_subject(self.subject_index_to_name[subject.subject_index])

    @_serialize_subject.register
    def _(self, subject: ThisModel):
        self.print("this_model")

    @_serialize_subject.register
    def _(self, subject: StringSubject):
        self.print(subject.text)

    @_serialize_subject.register
    def _(self, subject: ThisAbility):
        self.print("this_ability_unique_id")

    @_serialize_subject.register
    def _(self, subject: Model):
        self.print(str(type(subject)))

    @singledispatchmethod
    def _serialize_arity_one_condition(self, node, subject):
        self.print(str(type(node)))

    @_serialize_arity_one_condition.register
    def _(self, condition: TrueCondition, subject: Subject):
        self.print("true")

    @_serialize_arity_one_condition.register
    def _(self, condition: In, subject: Subject):
        self._serialize_subject(condition.subject)
        self.print(".contains(")
        self._serialize_subject(subject)
        self.print(")")

    @_serialize_arity_one_condition.register
    def _(self, condition: WithinEngagementRange, subject: Subject):
        self._serialize_subject(subject)
        self.print(".distance(")
        self._serialize_subject(condition.subject)
        self.print(") < 1")

    @_serialize_arity_one_condition.register
    def _(self, condition: WithinRange, subject: Subject):
        self._serialize_subject(subject)
        self.print(".distance(")
        self._serialize_subject(condition.subject)
        self.print(") <")
        self.serialize_quantity(condition.distance)

    @_serialize_arity_one_condition.register
    def _(self, condition: HasKeyword, subject: Subject):
        self._serialize_subject(subject)
        self.print(".has_keyword(")
        self.print(str(condition.keyword))
        self.print(")")

    @_serialize_arity_one_condition.register
    def _(self, condition: Enemy, subject: Subject):
        if subject.runtime_type == UnitSubject:
            self.print("this_unit.owner != ")
            self._serialize_subject(subject)
            self.print(".onwer")
        elif subject.runtime_type == ModelSubject:
            self.print("this_unit.owner != unit_of(")
            self._serialize_subject(subject)
            self.print(").onwer")
        else:
            raise NotImplementedError()

    @_serialize_arity_one_condition.register
    def _(self, condition: Allied, subject: Subject):
        if subject.runtime_type == UnitSubject:
            self.print("event.player == ")
            self._serialize_subject(subject)
            self.print(".onwer")
        elif subject.runtime_type == ModelSubject:
            self.print("event.player == unit_of(")
            self._serialize_subject(subject)
            self.print(").onwer")
        else:
            raise NotImplementedError()

    @_serialize_arity_one_condition.register
    def _(self, condition: With, subject):
        if condition.subject.runtime_type == AbilitySubject:
            self._serialize_subject(subject)
            self.print(".has_ability(")
            self._serialize_subject(condition.subject)
            self.print(")")
        else:
            raise NotImplementedError()

    @_serialize_arity_one_condition.register
    def _(self, condition: IsExactly, subject):
        self.print("is_exactly(")
        self._serialize_subject(subject)
        self.print(", ")
        self._serialize_subject(condition.subject)
        self.print(")")

    @_serialize_arity_one_condition.register
    def _(self, condition: And, subject):
        self._serialize_arity_one_condition(condition.lhs, subject)
        self.print(" and ")
        self._serialize_arity_one_condition(condition.rhs, subject)

    @singledispatchmethod
    def _visit(self, node):
        self.print(str(type(node)))


    def serialize_quantity(self, quantity):
        self.print(str(quantity))

    @_visit.register
    def _(self, effect: ChangeStratCost):
        if not isinstance(effect.stratagem_use, Stratagem):
            self.print("if event.stratagem == ")
            self._serialize_subject(effect.stratagem_use)
            self.printnl(":")
            self.indentation_level = self.indentation_level + 1
            self.print("event.stratagem_cost = event.stratagem_cost + ")
            self.serialize_quantity(effect.quantity)
            self.indentation_level = self.indentation_level - 1
        else:
            self.print("event.stratagem_cost = event.stratagem_cost + ")
            self.serialize_quantity(effect.quantity)

    def _declare_captured_member(self, subject: Subject):
        self.subject_index_to_name[subject.subject_index] = StringSubject(runtime_type=subject.runtime_type, subject_index=subject.subject_index, text=f"unit{subject.subject_index}")
        if subject.runtime_type == UnitSubject:
            self.printnl(f"Unit unit{subject.subject_index}")
        else:
            raise NotImplementedError()

    @_visit.register
    def _(self, effect: TemporaryEffect):
        self.printnl(f"cls ThisUniqueIDTemporaryEffect{effect.unique_id}:")
        self.indentation_level = self.indentation_level + 1
        for subject in effect.captured_subjects:
            self._declare_captured_member(subject)
        self.indentation_level = self.indentation_level - 1
        self.printnl("")
        self.visit(effect.effect)

    @_visit.register
    def _(self, effect: CreateTemporaryEffect):
        self.print(f"board.create_temporary_effect(this_unique_ability_id_{effect.temporary_effect_id}(")
        for captured_subject in effect.captured_references:
            self._serialize_subject(self.subject_index_to_name[captured_subject])
            self.print(", ")
        self.printnl(f"))")

    @_visit.register
    def _(self, effect: Select):
        self.printnl("actions:")
        self.indentation_level = self.indentation_level + 1
        self.printnl("act do_nothing()")
        self._serialize_target_selection(effect.introduced_target, effect.target_condition)
        self._visit(effect.effect)
        self.indentation_level = self.indentation_level - 1

    def register_subject(self, subject: Subject, name: str):
        self.subject_index_to_name[subject.subject_index] = StringSubject(runtime_type=subject.runtime_type, subject_index=subject.subject_index, text=name)

    @_visit.register
    def _(self, event: TargetedWith):
        self.register_subject(event.subject, "event.stratagem")
        self.register_subject(event.target, "event.target")

        self.print("if not (")
        self._serialize_arity_one_condition(event.conditions[0], self.subject_index_to_name[event.target.subject_index])
        self.print(" and ")
        self._serialize_arity_one_condition(event.conditions[1], self.subject_index_to_name[event.subject.subject_index])
        self.printnl("):")
        self.indentation_level = self.indentation_level + 1
        self.printnl("return")
        self.indentation_level = self.indentation_level - 1

    @_visit.register
    def _(self, effect: Destroys):
        self.register_subject(effect.attacker, "event.attacker")
        self.register_subject(effect.target, "event.target")
        self.print("if not (")
        self._serialize_arity_one_condition(effect.conditions[0], self.subject_index_to_name[effect.attacker.subject_index])
        self.print(" and ")
        self._serialize_arity_one_condition(effect.conditions[1], self.subject_index_to_name[effect.target.subject_index])
        self.printnl("):")
        self.indentation_level = self.indentation_level + 1
        self.printnl("return")
        self.indentation_level = self.indentation_level - 1

    @_visit.register
    def _(self, effect: AttackEvent):
        self.register_subject(effect.source, "event.source")
        self.register_subject(effect.target, "event.target")
        self.print("if not (")
        self._serialize_arity_one_condition(effect.conditions[0], self.subject_index_to_name[effect.source.subject_index])
        self.print(" and ")
        self._serialize_arity_one_condition(effect.conditions[1], self.subject_index_to_name[effect.target.subject_index])
        self.printnl("):")
        self.indentation_level = self.indentation_level + 1
        self.printnl("return")
        self.indentation_level = self.indentation_level - 1

    @_visit.register
    def _(self, effect: TimeEvent):
        if effect.player == Player.ANY:
            return
        if effect.player == Player.YOU:
            self.printnl("if board.current_player == this_unit.owner:")
            self.indentation_level = self.indentation_level + 1
            self.printnl("return")
            self.indentation_level = self.indentation_level - 1
            return
        if effect.player == Player.OPPONENT:
            self.printnl("if board.current_player != this_unit.owner:")
            self.indentation_level = self.indentation_level + 1
            self.printnl("return")
            self.indentation_level = self.indentation_level - 1
            return
        raise NotImplementedError()

    @_visit.register
    def _(self, effect: Performs):
        if effect.effect_type == EffectType.ACTIVATED_ACTION:
            if effect.usage_limit != LimitKind.NO_LIMIT:
                self.printnl("if !board.has_already_used(this_unique_ability_id):")
                self.indentation_level = self.indentation_level + 1

            self.printnl("actions:")
            self.indentation_level = self.indentation_level + 1
            if effect.usage == UsageKind.OPTIONAL:
                self.printnl("act do_nothing()")
                self._serialize_target_selection(effect.subject)
                self.indentation_level = self.indentation_level + 1
            self._serialize_action(effect.action, effect.subject)
            self.printnl("")
            if effect.usage_limit != LimitKind.NO_LIMIT:
                self.printnl("board.mark_used(this_unique_ability_id, " + str(effect.usage_limit) + ")")
                self.indentation_level = self.indentation_level - 1
            self.indentation_level = self.indentation_level - 1
            if effect.usage == UsageKind.OPTIONAL:
                self.indentation_level = self.indentation_level - 1

        else:
            raise NotImplementedError()

    def _serialize_roll_kind_accessor(self, kind: RollKind):
        self.print(kind.name.lower())

    @_visit.register
    def _(self, effect: ModifyRoll):
        for kind in effect.roll:
            self.print("event.")
            self._serialize_roll_kind_accessor(kind)
            self.print(" = ")
            self.print("event.")
            self._serialize_roll_kind_accessor(kind)
            self.print(" + " + str(effect.quantity))

    @_visit.register
    def _(self, effect: GainCPEffect):
        self.printnl(f"board.add_cp_to_current_player({effect.quantity})")

    @_visit.register
    def _(self, effect: TriggeredEffect):
        self._serialize_event_decl(effect.event)
        self.indentation_level = self.indentation_level + 1
        self.visit(effect.event)
        self.visit(effect.effect)
        self.printnl("")
        self.indentation_level = self.indentation_level - 1

    @singledispatchmethod
    def _serialize_event_decl(self, event):
        print(type(event))

    @_serialize_event_decl.register
    def _(self, event: TimeEvent):
        self.print("act ")
        self.print(event.unique_event_name())
        self.printnl("(ctx Unit this_unit, ctx Model this_model):")

    @_serialize_event_decl.register
    def _(self, event: Destroys):
        self.print("act ")
        self.print(event.unique_event_name())
        self.printnl("(ctx Unit this_unit, ctx Model this_model, ctx DestructionEvent event):")

    @_serialize_event_decl.register
    def _(self, event: Stratagem):
        self.print("act ")
        self.print(event.unique_event_name())
        self.printnl("(ctx Unit this_unit, ctx Model this_model, ctx StratagemUse event):")

    @_serialize_event_decl.register
    def _(self, event: AttackEvent):
        self.print("act ")
        self.print(event.unique_event_name())
        self.printnl("(ctx Unit this_unit, ctx Model this_model, ctx Attack event):")

    def _serialize_target_selection(self, subject: Subject, condition: Condition):
        index = subject.subject_index
        if subject.runtime_type == ModelSubject:
            self.print(f"act select_model(frm UnitID unit_id{index}, frm ModelID model_id{index}) " + "{")

            self.subject_index_to_name[index] = StringSubject(f"board[unit_id{index}][model_id{index}]", runtime_type=ModelSubject)
            self._serialize_arity_one_condition(condition, self.subject_index_to_name[index])
            self.printnl("}")
        elif subject.runtime_type == UnitSubject:
            self.print(f"act select_model(frm UnitID unit_id{index}) " + "{")
            self.subject_index_to_name[index] = StringSubject(f"board[unit_id{index}]", runtime_type=UnitSubject)
            self._serialize_arity_one_condition(condition, self.subject_index_to_name[index])
            self.printnl("}")
        else:
            raise NotImplementedError()

    @singledispatchmethod
    def _serialize_action(self, action, actor):
        self.print(str(type(action)))

    @_serialize_action.register
    def _(self, action: Use, actor):
        #ToDo: we should probably consider emitting a event in the future here
        self.visit(action.after_use_effect)

    @_serialize_action.register
    def _(self, action: QualifiedAction, actor):
        if action.usage == UsageKind.MANDATORY:
            self._serialize_action(action.action, actor)
        else:
            self.printnl("actions:")
            self.indentation_level = self.indentation_level + 1
            self.printnl("act do_it():")
            self.indentation_level = self.indentation_level + 1
            self._serialize_action(action.action, actor)
            self.indentation_level = self.indentation_level - 2



class ReplaceReferencesPass(ASTTransformer):

    def __init__(self):
        super().__init__()
        self.first_pass = True
        self.top_level_subjects = {}

    def transform(self, node):
        self.first_pass = True
        node = super().transform(node)
        self.first_pass = False
        node = super().transform(node)
        return node

    @singledispatchmethod
    def visit(self, node):
        return node

    @visit.register
    def _(self, node: ModifyRoll):
        if self.first_pass and not node.subject_index in self.top_level_subjects:
            self.top_level_subjects[node.subject_index] = node
        return node

    @visit.register
    def _(self, node: Subject):
        if self.first_pass and not node.subject_index in self.top_level_subjects:
            self.top_level_subjects[node.subject_index] = node
        return node

    @visit.register
    def _(self, node: Reference):
        if not self.first_pass:
            return self.top_level_subjects[node.subject_index]
        return node

def rlc_serialize(ast, out):
    canonicalizer = RLCSerializer(out)
    canonicalizer.visit(ast)

def parse(text):
    with open("./python/40k.lark", encoding="utf-8") as f:
        grammar = f.read()

    parser = Lark(grammar, start="start", parser="earley")
    tree = parser.parse(text)
    transformer = ToAst()
    return semantically_analyze(transformer.transform(tree))

def main():
    ap = argparse.ArgumentParser(
        description="Parse game rules and turns them into rulebook code."
                    "Pass '-' to read from stdin.")
    ap.add_argument("path", help="path to dump file or '-' for stdin", default="-", nargs="?")
    ap.add_argument("-o", help="output", default="-", nargs="?")
    args = ap.parse_args()

    content = sys.stdin if args.path == "-" else open(args.path, encoding="utf-8")
    out = sys.stdout if args.o == "-" else open(args.o, "w+")

    ast = parse("".join(content.readlines()))
    ast = canonicalize(ast)
    out.write(paren_pformat(str(ast)))
    rlc_serialize(ast, out)


if __name__ == "__main__":
    main()
