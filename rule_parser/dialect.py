from abc import ABC, abstractmethod
from xdsl.ir import Block, Region, Dialect, Attribute, ParametrizedAttribute, EnumAttribute, SSAValue, Operation
from xdsl.passes import ModulePass, PassPipeline
from xdsl.transforms.canonicalize import CanonicalizePass
from functools import lru_cache
from xdsl.builder import Builder, InsertPoint
from xdsl.rewriter import Rewriter
from xdsl.context import Context
from xdsl.printer import Printer
from xdsl.traits import NoTerminator, IsTerminator, OpTrait, Pure, RecursivelySpeculatable
from xdsl.dialects.builtin import ModuleOp, StringAttr, IntAttr, AnyOf, AttrConstraint
from xdsl.irdl import irdl_op_definition, OpResult, Operand, IRDLOperation, result_def, irdl_attr_definition, attr_constr_coercion, Data, attr_def, operand_def, region_def, BaseAttr, OpTraits, traits_def, ParamDef, opt_operand_def, opt_result_def, var_operand_def
from enum import Enum, StrEnum, auto


class TargetingTypeInterface(ABC):
    pass

class TargetableTypeInterface(ABC):
    pass

class EventTypeInterface(ABC):
    pass

# means that the operation has a filter in a region
class FilteringInterface(OpTrait):
    def get_this_model(self, op):
        raise NotImplementedError()

class CanDefineOperand(OpTrait):
    def replace_with_operand_defining_op(self, op):
        raise NotImplementedError()

    def get_optionally_defined_operand(self, op) -> SSAValue:
        raise NotImplementedError()

class HasPreconditions(OpTrait):
    pass

@irdl_attr_definition
class UnknownType(ParametrizedAttribute):
    name = "rul.unkown"

@irdl_attr_definition
class TemporaryEffectType(ParametrizedAttribute):
    name = "rul.temporary_effect_type"

@irdl_attr_definition
class ModelType(ParametrizedAttribute, TargetableTypeInterface):
    name = "rul.model"

@irdl_attr_definition
class UnitType(ParametrizedAttribute, TargetableTypeInterface):
    name = "rul.unit"

@irdl_attr_definition
class StratagemType(ParametrizedAttribute, TargetingTypeInterface):
    name = "rul.stratagem"


@irdl_attr_definition
class BoolType(ParametrizedAttribute):
    name = "rul.bool"

@irdl_attr_definition
class ListType(ParametrizedAttribute):
    name = "rul.list"
    underlying: Attribute

    @classmethod
    @lru_cache(maxsize=None)
    def make(cls, type):
        return ListType(type)

@irdl_attr_definition
class AbilityType(ParametrizedAttribute, TargetingTypeInterface):
    name = "rul.ability"

@irdl_attr_definition
class StratagemUseType(ParametrizedAttribute, EventTypeInterface):
    name = "rul.strategem_use"

@irdl_attr_definition
class AbilityUseType(ParametrizedAttribute, EventTypeInterface):
    name = "rul.ability_use"

@irdl_attr_definition
class AttackType(ParametrizedAttribute, EventTypeInterface, TargetingTypeInterface):
    name = "rul.attack"

@irdl_attr_definition
class OnTargetedEventType(ParametrizedAttribute, EventTypeInterface):
    name = "rul.on_targeted_event"


class Player(StrEnum):
    YOU = auto()
    OPPONENT = auto()
    ANY = auto()

class PlayerAttr(EnumAttribute[Player]):
    name = "rul.player"

@irdl_op_definition
class All(IRDLOperation):
    name = "rul.All"
    result: OpResult = result_def()

    assembly_format = "attr-dict `->` type($result)"

    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, type):
        return cls.build(result_types=[ListType.make(type)])


@irdl_op_definition
class ThisSubject(IRDLOperation):
    name = "rul.this_subject"
    result: OpResult = result_def()

    traits: OpTraits = traits_def(Pure())
    assembly_format = "attr-dict `->` type($result)"

    @classmethod
    def make(cls, type):
        return cls.build(result_types=[type])

@irdl_op_definition
class IsAttackMadeWeapon(IRDLOperation):
    name = "rul.is_attack_made_with"
    weapon_name: Attribute = attr_def(StringAttr)
    attack: Operand = operand_def(AttackType)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, operand: SSAValue, name: str):
        return cls.build(operands=[operand], result_types=[BoolType()], attributes={"weapon_name": StringAttr(name)})

class AbilityKind(StrEnum):
    DEEP_STRIKE = auto()
    FEEL_NO_PAIN = auto()
    STEALTH = auto()

class AbilityKindAttr(EnumAttribute[AbilityKind]):
    name = "rul.ability_kind"

@irdl_op_definition
class Ability(IRDLOperation):
    name = "rul.ability"
    ability_kind: Attribute = attr_def(AbilityKindAttr)
    result: OpResult = result_def(AbilityType)
    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, ability_kind: AbilityKind):
        return cls.build(result_types=[AbilityType()], attributes={"ability_kind": AbilityKindAttr(ability_kind)})

class MovementKind(StrEnum):
    NORMAL = auto()
    ADVANCE = auto()
    FALL_BACK = auto()
    BLISTERING_ASSAULT = auto()
    ANY = auto()
    REMAIN_STATIONARY = auto()

class MovementKindAttr(EnumAttribute[MovementKind]):
    name = "rul.movement_kind"

class WeaponQualifierKind(StrEnum):
    MELEE = auto()
    RANGED = auto()
    ANY = auto()

class WeaponQualifierKindAttr(EnumAttribute[WeaponQualifierKind]):
    name = "rul.weapon_qualifier_kind"

class Keyword(StrEnum):
    CHARACTER = auto()
    TYRANID = auto()
    MONSTER = auto()
    INFANTRY = auto()
    TERMAGANTS = auto()
    PSYKER = auto()
    NEUROGAUNT = auto()
    SYNAPSE = auto()
    FLY = auto()
    TITANIC = auto()

class KeywordAttr(EnumAttribute[Keyword]):
    name = "rul.keyword"

class Characteristic(StrEnum):
    LEADERSHIP = auto()
    MOVE = auto()
    OC = auto()

class CharacteristicAttr(EnumAttribute[Characteristic]):
    name = "rul.characteristic"

class WeaponCharacteristic(Enum):
    ATTACKS = auto()
    AP = auto()
    DAMAGE = auto()

class WeaponCharacteristicAttr(EnumAttribute[WeaponCharacteristic]):
    name = "rul.weapon_characteristic"

class WeaponAbilityKind(StrEnum):
    DEVASTATING_WOUNDS = auto()
    LETHAL_HITS = auto()
    ASSAULT = auto()
    SUSTAINED_HITS = auto()

class WeaponAbilityKindAttr(EnumAttribute[WeaponAbilityKind]):
    name = "rul.weapon_ability_kind_attr"

@irdl_attr_definition
class WeaponAbilityAttr(ParametrizedAttribute):
    name = "rul.weapon_ability"
    ability: WeaponAbilityKindAttr
    value: IntAttr

    @classmethod
    def make(cls, ability_kind: WeaponAbilityKindAttr, value: int=0):
        return cls(ability_kind, IntAttr(value))

class TimeQualifier(StrEnum):
    START = auto()
    DURING = auto()
    END = auto()

class TimeQualifierAttr(EnumAttribute[TimeQualifier]):
    name = "rul.time_qualifier"

class TimeInstant(StrEnum):
    FIGHT_PHASE = auto()
    CURRENT_PHASE = auto()
    BATTLE_SHOCK_STEP = auto()
    COMMAND_PHASE = auto()
    SHADOW_IN_THE_WARP = auto()
    SHOOTING_PHASE= auto()
    TURN = auto()
    ANY_BATTLE_ROUND = auto()
    FIRST_BATTLE_ROUND = auto()
    BATTLE = auto()
    MOVEMENT_PHASE = auto()

class TimeInstantAttr(EnumAttribute[TimeInstant]):
    name = "rul.time_instant"



@irdl_attr_definition
class TimeEventType(ParametrizedAttribute, EventTypeInterface):
    name = "rul.time_event"
    time_instant: TimeInstantAttr
    time_qualifier: TimeQualifierAttr
    player: PlayerAttr

    def event_name(self):
        return f"on_{self.player.data}_{self.time_instant.data}_{self.time_qualifier.data}"

    @classmethod
    @lru_cache(maxsize=None)
    def make(cls, time_instant: TimeInstant, time_qualifier: TimeQualifier, player=Player.ANY):
        return cls(TimeInstantAttr(time_instant), TimeQualifierAttr(time_qualifier), PlayerAttr(player))

@irdl_op_definition
class CreateTemporaryEffect(IRDLOperation):
    name = "rul.create_temporary_effect"
    effect: Operand = operand_def(TemporaryEffectType)
    args: Operand = var_operand_def()

    assembly_format = "$effect ($args^ `:` type($args))? attr-dict"

    @classmethod
    def make(cls, effect: SSAValue, *args) -> 'CreateTemporaryEffect':
        to_return = cls.build(operands=[effect, *args])
        return to_return

@irdl_op_definition
class GlobalTemporaryEffect(IRDLOperation):
    name = "rul.global_temporary_effect"
    effect = region_def()
    result = result_def(TemporaryEffectType)
    traits: OpTraits = traits_def(HasPreconditions())

    assembly_format = "$effect attr-dict `->` type($result)"

    @classmethod
    def make(cls, effect: Block) -> 'GlobalTemporaryEffect':
        to_return = cls.build(regions=[Region(effect)], result_types=[TemporaryEffectType()])
        return to_return

@irdl_op_definition
class UntilEffect(IRDLOperation):
    name = "rul.until_effect"
    event: Attribute = attr_def(TimeEventType)
    effect = region_def()
    traits: OpTraits = traits_def(HasPreconditions())

    assembly_format = "$effect attr-dict "

    @classmethod
    def make(cls, time_event: TimeEventType) -> 'UntilEffect':
        to_return = cls.build(regions=[Region(Block())], attributes={"event": time_event})
        return to_return

@irdl_op_definition
class EachTimeEffect(IRDLOperation):
    name = "rul.each_time_effect"
    event = region_def()
    effect = region_def()

    assembly_format = "`event` $event `effect` $effect attr-dict "

    @classmethod
    def make(cls) -> 'EachTimeEffect':
        to_return = cls.build(regions=[Region(Block()),Region(Block())])
        return to_return

class RollKind(StrEnum):
    HIT_ROLL = auto()
    WOUND_ROLL = auto()
    BATTLE_SHOCK_ROLL = auto()
    CHARGE_ROLL = auto()
    ADVANCE_ROLL = auto()
    SAVING_THROW_ROLL = auto()

class RollKindAttr(EnumAttribute[RollKind]):
    name = "rul.roll_kind"

@irdl_op_definition
class GiveCharacteristicModifier(IRDLOperation):
    name = "rul.give_characteristic_modifier"
    characteristic: Attribute = attr_def(CharacteristicAttr)
    quantity: Attribute = attr_def(IntAttr)
    beneficient: Operand = operand_def(ModelType)
    traits: OpTraits = traits_def(HasPreconditions())

    assembly_format = "$characteristic $quantity $beneficient attr-dict `:` type($beneficient)"

    @classmethod
    def make(cls, beneficient: SSAValue, characteristic: Characteristic, quantity: int) -> 'GiveCharacteristicModifier':
        to_return = cls.build(attributes={"characteristic": characteristic, 'quantity': quantity}, operands=[beneficient])
        return to_return

@irdl_op_definition
class ModifyCharacteristic(IRDLOperation):
    name = "rul.modify_characteristic"
    characteristic: Attribute = attr_def(CharacteristicAttr)
    quantity: Attribute = attr_def(IntAttr)
    condition = region_def()
    beneficient = region_def()
    traits: OpTraits = traits_def(HasPreconditions())

    assembly_format = "$characteristic $quantity $condition $beneficient attr-dict"

    @classmethod
    def make(cls, characteristic: Characteristic, quantity: int) -> 'ModifyRoll':
        to_return = cls.build(attributes={"characteristic": CharacteristicAttr(characteristic), 'quantity': IntAttr(quantity)}, regions=[Region(Block()), Region(Block())])
        return to_return

@irdl_op_definition
class ModifyRoll(IRDLOperation):
    name = "rul.modify_roll"
    to_modify: Operand = operand_def(AttackType)
    roll: Attribute = attr_def(RollKindAttr)
    quantity: Attribute = attr_def(IntAttr)

    assembly_format = "$to_modify $roll $quantity attr-dict `:` type($to_modify)"

    @classmethod
    def make(cls, to_modify: SSAValue, roll: RollKind, quantity: int) -> 'ModifyRoll':
        to_return = cls.build(attributes={"roll": RollKindAttr(roll), 'quantity': IntAttr(quantity)}, operands=[to_modify])
        return to_return

@irdl_op_definition
class TimedEffect(IRDLOperation):
    name = "rul.timed_effect"
    event: Attribute = attr_def(TimeEventType)
    condition = region_def()
    effect = region_def()
    traits: OpTraits = traits_def(HasPreconditions())

    assembly_format = "`condition` $condition  `effect` $effect `event` $event attr-dict "

    def event_name(self) -> str:
        return self.event.event_name()

    @classmethod
    def make(cls, time_event: TimeEventType) -> 'TimedEffect':
        to_return = cls.build(regions=[Region(Block()),Region(Block())], attributes={"event": time_event})
        return to_return

class FilteringOp:
    def get_single_selection_candidate(self, index = 0):
        return self.regions[index].first_block.first_op

    def filter_argument(self, index = 0):
        return self.regions[index].first_block.args[0]


    def get_belongs_to_argument_type(self, index = 0):
        return self.regions[index].first_block.last_op.value.owner.rhs.type

    def is_filtering_structure(self, index = 0):
        return isinstance(self.regions[index].first_block.last_op.value.owner, BelongsTo)

@irdl_op_definition
class SelectSubject(IRDLOperation, FilteringOp):
    name = "rul.select_subject"
    condition = region_def()
    result: OpResult = result_def()
    traits: OpTraits = traits_def(FilteringInterface())

    assembly_format = " $condition attr-dict `->` type($result)"

    @classmethod
    def make(cls) -> 'SelectSubject':
        to_return = cls.build(regions=[Region(Block())], result_types=[UnknownType()])
        to_return.condition.first_block.insert_arg(UnknownType(), 0)
        to_return.condition.first_block.args[0].name_hint = "selection"
        return to_return


@irdl_op_definition
class MakeReferrable(IRDLOperation):
    name = "rul.make_referrable"
    subject: Operand = operand_def()

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(operands=[unit])

    assembly_format = "$subject attr-dict `:` type($subject) "

@irdl_op_definition
class BelowStartingStrenght(IRDLOperation):
    name = "rul.below_half_strenght"
    unit: Operand = operand_def(UnitType)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())
    assembly_format = "$unit attr-dict `:` type($unit) `->` type($result)"

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[unit])

@irdl_op_definition
class HasKeyword(IRDLOperation):
    name = "rul.has_keyword"
    unit: Operand = operand_def(AnyOf([ModelType, UnitType]))
    keyword: Attribute = attr_def(KeywordAttr)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = "$unit $keyword attr-dict `:` type($unit) "

    @classmethod
    def make(cls, unit: SSAValue, keyword: Keyword):
        return cls.build(result_types=[BoolType()], operands=[unit], attributes={"keyword": KeywordAttr(keyword)})

@irdl_op_definition
class TrueOp(IRDLOperation):
    name = "rul.true"
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = "attr-dict `->` type($result)"

    @classmethod
    def make(cls):
        return cls.build(result_types=[BoolType()])

@irdl_op_definition
class And(IRDLOperation):
    name = "rul.and"
    lhs: Operand = operand_def(BoolType)
    rhs: Operand = operand_def(BoolType)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())


    assembly_format = "$lhs `,` $rhs attr-dict `:` type($lhs) `,` type($rhs) `->` type($result)"

    @classmethod
    def make(cls, lhs: SSAValue, rhs: Player):
        return cls.build(result_types=[BoolType()], operands=[lhs, rhs])

@irdl_op_definition
class IsSame(IRDLOperation):
    name = "rul.is_same"
    lhs: Operand = operand_def()
    rhs: Operand = operand_def()
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = " $lhs $rhs attr-dict  `:` type($lhs) `,` type($rhs)`->` type($result)"

    @classmethod
    def make(cls, lhs: SSAValue, rhs: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[lhs, rhs])


@irdl_op_definition
class IsOwnedBy(IRDLOperation):
    name = "rul.is_owned_by"
    unit: Operand = operand_def(AnyOf([ModelType, UnitType]))
    player: Attribute = attr_def(PlayerAttr)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = " $unit $player attr-dict  `:` type($unit)`->` type($result)"

    @classmethod
    def make(cls, unit: SSAValue, player: Player):
        return cls.build(result_types=[BoolType()], operands=[unit], attributes={"player": PlayerAttr(player)})

@irdl_op_definition
class BelowHalfStrenght(IRDLOperation):
    name = "rul.below_half_strenght"
    unit: Operand = operand_def(UnitType)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[unit])

@irdl_op_definition
class WithinRange(IRDLOperation):
    name = "rul.within_range"
    distance: Attribute = attr_def(IntAttr)
    source: Operand = operand_def(AnyOf([UnitType, ModelType]))
    target: Operand = operand_def(AnyOf([UnitType, ModelType]))
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = "$distance $source $target attr-dict  `:` type($source) `,` type($target)`->` type($result)"

    @classmethod
    def make(cls, distance: int, source: SSAValue, target: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[source, target], attributes={"distance": IntAttr(distance)})

@irdl_op_definition
class WithinEngagementRange(IRDLOperation):
    name = "rul.within_engagement_range"
    source: Operand = operand_def(AnyOf([UnitType, ModelType]))
    target: Operand = operand_def(AnyOf([UnitType, ModelType]))
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = " $source $target attr-dict  `:` type($source) `,` type($target)`->` type($result)"

    @classmethod
    def make(cls, source: SSAValue, target: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[source, target])



@irdl_op_definition
class BelongsTo(IRDLOperation):
    name = "rul.belongs_to"
    model: Operand = operand_def(ModelType)
    rhs: Operand = operand_def(AnyOf([ListType, UnitType]))
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = "$model $rhs attr-dict `:` type($model) `,` type($rhs) `->` type($result)"


    @classmethod
    def make(cls, model: SSAValue, rhs: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[model, rhs])


@irdl_op_definition
class SubjectsIn(IRDLOperation):
    name = "rul.subjects_in"
    unit: Operand = operand_def(UnitType)
    result: OpResult = result_def(ListType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = "$unit attr-dict `:` type($unit) `->` type($result)"

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(result_types=[ListType.make(ModelType())], operands=[unit])

@irdl_op_definition
class Destroys(IRDLOperation, FilteringOp):
    name = "rul.destroys"
    source: Region = region_def()
    target: Region = region_def()
    effect: Region = region_def()
    traits: OpTraits = traits_def(FilteringInterface())

    assembly_format = "`source` $source `target` $target `effect` $effect attr-dict"

    @classmethod
    def make(cls):
        op = cls.build(regions=[Region(Block()), Region(Block()), Region(Block())])
        op.source.first_block.insert_arg(ModelType(), 0)
        op.target.first_block.insert_arg(ModelType(), 0)
        op.effect.first_block.insert_arg(ModelType(), 0)
        op.effect.first_block.insert_arg(ModelType(), 1)
        return op


@irdl_op_definition
class MakesAnAttack(IRDLOperation, FilteringOp):
    name = "rul.makes_an_attack"
    condition: Region = region_def()
    effect: Region = region_def()
    traits: OpTraits = traits_def(FilteringInterface())

    assembly_format = "`condition` $condition `effect` $effect attr-dict"

    @classmethod
    def make(cls):
        op = cls.build(regions=[Region(Block()), Region(Block())])
        op.condition.first_block.insert_arg(ModelType(), 0)
        op.condition.first_block.insert_arg(UnitType(), 1)
        op.condition.first_block.insert_arg(AttackType(), 2)
        op.effect.first_block.insert_arg(ModelType(), 0)
        op.effect.first_block.insert_arg(UnitType(), 1)
        op.effect.first_block.insert_arg(AttackType(), 2)
        return op

@irdl_op_definition
class ThatIsTargeting(IRDLOperation):
    name = "rul.that_is_targeting"
    event: Operand = operand_def(BaseAttr(TargetingTypeInterface))
    target: Operand = operand_def(BaseAttr(TargetableTypeInterface))
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, event: SSAValue, target: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[source, target])

@irdl_op_definition
class AddUnitToArmy(IRDLOperation):
    name = "rul.add_unit_to_army"

@irdl_op_definition
class Yield(IRDLOperation):
    name = "rul.yield"
    traits: OpTraits = traits_def(IsTerminator())
    value: Operand = opt_operand_def()

    assembly_format = "($value^ `:` type($value))?  attr-dict "

    @classmethod
    def make(cls, value: SSAValue = None):
        if value == None:
            return cls.build(operands=[None])
        return cls.build(operands=[value])

@irdl_op_definition
class ConditionalEffect(IRDLOperation):
    name = "rul.conditional_effect"
    condition = region_def()
    effect = region_def()

    traits: OpTraits = traits_def(HasPreconditions())

    assembly_format = "`condition` $condition `effect` $effect attr-dict "

    @classmethod
    def make(cls) -> 'ConditionalEffect':
        to_return = cls.build(regions=[Region(Block()),Region(Block())])
        return to_return


@irdl_op_definition
class TargetedWith(IRDLOperation):
    name = "rul.on_being_targeted"
    target = region_def()
    targeting_event = region_def()
    target_result: OpResult = result_def(BaseAttr(TargetableTypeInterface))
    targeting_result : OpResult = result_def(BaseAttr(TargetingTypeInterface))
    event_result: OpResult = result_def(BaseAttr(EventTypeInterface))

    @classmethod
    def make(cls):
        to_return = cls.build(result_types=[UnknownType(), UnknownType(), UnknownType()], regions=[Region(),Region()])
        to_return.targeting_event.add_block(Block())
        to_return.target.add_block(Block())
        return to_return

@irdl_op_definition
class ItSubject(IRDLOperation):
    name = "rul.it"
    traits: OpTraits = traits_def(Pure())
    result: OpResult = result_def(BoolType)

    assembly_format = "attr-dict `->` type($result)"

    @classmethod
    def make(cls, type=UnknownType()):
        return cls.build(result_types=[type])

@irdl_op_definition
class MakeBattleShockTest(IRDLOperation):
    name = "rul.make_battle_shock"
    unit: Operand = operand_def(UnitType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = "$unit attr-dict `:` type($unit)"

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(operands=[unit])


@irdl_op_definition
class BattleShocked(IRDLOperation):
    name = "rul.battle_shocked"
    unit: Operand = operand_def(UnitType)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[unit])


@irdl_op_definition
class LeadedUnit(IRDLOperation):
    name = "rul.leaded_unit"
    leader: Operand = operand_def(AnyOf([UnitType, ModelType]))
    result: OpResult = result_def(BoolType)
    unit: OpResult = result_def(UnitType)
    traits: OpTraits = traits_def(Pure())

    assembly_format = "$leader attr-dict `:` type($leader)  `->` type($result) `,` type($unit)"

    @classmethod
    def make(cls, leader: SSAValue, unit_type: type) -> 'LeadedUnit':
        return cls.build(result_types=[BoolType(), unit_type], operands=[leader])

@irdl_op_definition
class Leading(IRDLOperation):
    name = "rul.leading"
    leader: Operand = operand_def(AnyOf([UnitType, ModelType]))
    unit: Operand = operand_def(UnitType)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(CanDefineOperand(), Pure())

    assembly_format = "$leader `,` $unit attr-dict `:` type($leader) `,` type($unit) `->` type($result)"

    def get_optionally_defined_operand(self) -> SSAValue:
        return self.unit

    def replace_with_operand_defining_op(self, builder: Rewriter):
        replacement = LeadedUnit.make(self.leader, self.unit.type)
        builder.insert_op(replacement,InsertPoint.after(self))
        any_unit = self.unit.op
        self.unit.replace_by(replacement.unit)
        any_unit.detach()
        self.result.replace_by(replacement.result)
        self.detach()
        return self.unit

    @classmethod
    def make(cls, leader: SSAValue, unit: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[leader, unit])

@irdl_op_definition
class CapturedReference(IRDLOperation):
    name = "rul.captured_reference"
    value: Operand = operand_def()
    result: OpResult = result_def()
    traits: OpTraits = traits_def(Pure())
    assembly_format = "$value attr-dict `:` type($value) `->` type($result)"

    @classmethod
    def make(cls, operand: SSAValue):
        return cls.build(result_types=[operand.type], operands=[operand])

@irdl_op_definition
class ConstrainedSuchSubject(IRDLOperation):
    name = "rul.constrained_such_subject"
    result: OpResult = result_def()
    body: Region = region_def()
    traits: OpTraits = traits_def(Pure(), NoTerminator())
    assembly_format = "$body attr-dict `->` type($result)"

    @classmethod
    def make(cls) -> 'ConstrainedSuchSubject':
        to_return = cls.build(result_types=[type], regions=[Region(Block())])
        return to_return

@irdl_op_definition
class SuchSubject(IRDLOperation):
    name = "rul.such_subject"
    traits: OpTraits = traits_def(NoTerminator())
    result: OpResult = result_def()
    traits: OpTraits = traits_def(Pure())
    assembly_format = "attr-dict `->` type($result)"

    @classmethod
    def make(cls, type=UnknownType()):
        return cls.build(result_types=[type])

@irdl_op_definition
class GainCP(IRDLOperation):
    name = "rul.gain_cp"
    quantity: Attribute = attr_def(IntAttr)
    assembly_format = "$quantity attr-dict "

    @classmethod
    def make(cls, quantity: int):
        return cls.build(attributes={"quantity": IntAttr(quantity)})

@irdl_op_definition
class DestroyedSubject(IRDLOperation):
    name = "rul.destroyed"
    body: Region = region_def()
    traits: OpTraits = traits_def(frozenset([NoTerminator()]))
    result: OpResult = result_def(AnyOf([UnitType, ModelType]))

    @classmethod
    def make(cls):
        return cls.build(result_types=[UnknownType()], regions=[Region(Block())])

@irdl_op_definition
class OneOf(IRDLOperation):
    name = "rul.one_of"

    base_subject: Region = region_def()
    result: OpResult = result_def()
    traits: OpTraits = traits_def(RecursivelySpeculatable())

    assembly_format = "$base_subject attr-dict `->` type($result)"

    @classmethod
    def make(cls, base_type: Attribute) -> 'OneOf':
        return cls.build(result_types=[base_type], regions=[Region(Block())])


@irdl_op_definition
class FilterList(IRDLOperation):
    name = "rul.filter_list"

    base_subject: Region = region_def()
    constraint: Region = region_def()
    result: OpResult = result_def()
    traits: OpTraits = traits_def(RecursivelySpeculatable())

    assembly_format = "$base_subject $constraint attr-dict `->` type($result)"

    def single_base_subject(self):
        if len(self.base_subject.first_block.ops) == 2:
            self.base_subject.first_block.last_op.value.owner == self.base_subject.first_block.first_op
            return self.base_subject.first_block.first_op
        return None

    def single_constraint(self):
        if len(self.base_subject.first_block.ops) == 2:
            self.constraint.first_block.last_op.value.owner == self.constraint.first_block.first_op
            return self.constraint.first_block.first_op
        return None

    @classmethod
    def make(cls, base_type: Attribute) -> 'FilterList':
        contraint = Region(Block())
        contraint.first_block.insert_arg(base_type, 0)
        return cls.build(result_types=[ListType.make(base_type)], regions=[Region(Block()), contraint])


@irdl_op_definition
class UsingAbilitySubject(IRDLOperation):
    name = "rul.using_ability"
    user_region: Region = region_def()
    ability_region: Region = region_def()
    traits: OpTraits = traits_def(NoTerminator(), Pure())
    result: OpResult = result_def(UnitType)

    @classmethod
    def make(cls):
        return cls.build(result_types=[UnitType()], regions=[Region(Block()), Region(Block())])

# obtain cover against a particular source model
@irdl_op_definition
class ObtainCover(IRDLOperation):
    name = "rul.obtain_cover"
    beneficient: Operand = operand_def(AnyOf([UnitType, ModelType]))
    attack_source: Operand = operand_def(AnyOf([UnitType, ModelType]))

    @classmethod
    def make(cls, beneficient: SSAValue, attack_source: SSAValue):
        return cls.build(operands=[beneficient, attack_source])

@irdl_op_definition
class RLCFunction(IRDLOperation):
    name = "rul.rlc_fun"
    sym_name: Attribute = attr_def(StringAttr)
    body: Region = region_def()
    traits: OpTraits = traits_def(NoTerminator())

    def get_this_model(self):
        return self.body.first_block.args[1]

    def get_attack_source(self):
        return self.body.first_block.args[2]

    def get_attack_target(self):
        return self.body.first_block.args[3]

    def get_attack_attack(self):
        return self.body.first_block.args[4]

    assembly_format = "$sym_name $body attr-dict "

    @classmethod
    def make_time_event(cls, name: str) -> 'RLCFunction':
        op = cls.build(regions=[Region(Block())], attributes={"sym_name": StringAttr(name)})
        op.body.first_block.insert_arg(UnitType(), 0) # this_unit
        op.body.first_block.args[0].name_hint = "this_unit"
        op.body.first_block.insert_arg(ModelType(), 1) # this_model
        op.body.first_block.args[1].name_hint = "this_model"
        return op


    @classmethod
    def make_event(cls, name: str) -> 'RLCFunction':
        op = cls.build(regions=[Region(Block())], attributes={"sym_name": StringAttr(name)})
        op.body.first_block.insert_arg(UnitType(), 0) # this_unit
        op.body.first_block.args[0].name_hint = "this_unit"
        op.body.first_block.insert_arg(ModelType(), 1) # this_model
        op.body.first_block.args[1].name_hint = "this_model"
        op.body.first_block.insert_arg(UnitType(), 2) # unit_being_evaluated
        op.body.first_block.args[2].name_hint = "evaluated_unit"
        op.body.first_block.insert_arg(ModelType(), 3) # model_being_evaluated
        op.body.first_block.args[3].name_hint = "evaluated_model"
        return op

    @classmethod
    def make_attack_event(cls, name: str) -> 'RLCFunction':
        op = cls.build(regions=[Region(Block())], attributes={"sym_name": StringAttr(name)})
        op.body.first_block.insert_arg(UnitType(), 0)
        op.body.first_block.args[0].name_hint = "this_unit"
        op.body.first_block.insert_arg(ModelType(), 1)
        op.body.first_block.args[1].name_hint = "this_model"
        op.body.first_block.insert_arg(ModelType(), 2)
        op.body.first_block.args[2].name_hint = "source_model"
        op.body.first_block.insert_arg(UnitType(), 3)
        op.body.first_block.args[3].name_hint = "target_unit"
        op.body.first_block.insert_arg(AttackType(), 4)
        op.body.first_block.args[4].name_hint = "attack"
        return op

    @classmethod
    def make_destroys_event(cls, name: str) -> 'RLCFunction':
        op = cls.build(regions=[Region(Block())], attributes={"sym_name": StringAttr(name)})
        op.body.first_block.insert_arg(UnitType(), 0)
        op.body.first_block.args[0].name_hint = "this_unit"
        op.body.first_block.insert_arg(ModelType(), 1)
        op.body.first_block.args[1].name_hint = "this_model"
        op.body.first_block.insert_arg(ModelType(), 2)
        op.body.first_block.args[2].name_hint = "source_model"
        op.body.first_block.insert_arg(UnitType(), 3)
        op.body.first_block.args[3].name_hint = "target_unit"
        return op

@irdl_op_definition
class AdditionalEffect(IRDLOperation):
    name = "rul.additiona_effect"
    body: Region = region_def()
    traits: OpTraits = traits_def(RecursivelySpeculatable())

    assembly_format = "$body attr-dict"

    @classmethod
    def make(cls) -> 'AdditionalEffect':
        return cls.build(regions=[Region(Block())])

@irdl_op_definition
class ForAllStatement(IRDLOperation):
    name = "rul.for_all_statement"
    iterable: Operand = operand_def(ListType)
    body: Region = region_def()
    traits: OpTraits = traits_def(RecursivelySpeculatable())

    assembly_format = "$iterable $body attr-dict `:` type($iterable)"

    @classmethod
    def make(cls, operand: SSAValue) -> 'ForAllStatement':
        to_return = cls.build(regions=[Region(Block())], operands=[operand])
        to_return.body.first_block.insert_arg(operand.type.underlying, 0)
        return to_return


@irdl_op_definition
class IfStatement(IRDLOperation):
    name = "rul.if_statement"
    condition: Region = region_def()
    true_branch: Region = region_def()
    traits: OpTraits = traits_def(RecursivelySpeculatable())

    assembly_format = "$condition $true_branch attr-dict"

    @classmethod
    def make(cls) -> 'IfStatement':
        return cls.build(regions=[Region(Block()), Region(Block())])

@irdl_op_definition
class GiveWeaponAbility(IRDLOperation):
    name = "rul.assign_weapon_ability"
    beneficient: Operand = operand_def(ModelType)
    ability: Attribute = attr_def(WeaponAbilityAttr)
    qualifier: Attribute = attr_def(WeaponQualifierKindAttr)

    assembly_format = "$beneficient `ability` $ability `qualifier` $qualifier `:` type($beneficient) attr-dict "

    @classmethod
    def make(cls, model: SSAValue, ability: WeaponAbilityKindAttr, qualifier: WeaponQualifierKindAttr) -> 'GiveWeaponAbility':
        return cls.build(operands=[model], attributes={"ability": ability, "qualifier": qualifier})

@irdl_op_definition
class ObtainWeaponAbility(IRDLOperation):
    name = "rul.obtain_weapon_ability"
    condition: Region = region_def()
    beneficient: Region = region_def()
    ability: Attribute = attr_def(WeaponAbilityAttr)
    qualifier: Attribute = attr_def(WeaponQualifierKindAttr)
    traits: OpTraits = traits_def(HasPreconditions())

    assembly_format = "`condition` $condition `beneficient` $beneficient `ability` $ability `qualifier` $qualifier attr-dict "

    @classmethod
    def make(cls, ability: WeaponAbilityKindAttr, qualifier: WeaponQualifierKindAttr) -> 'ObtainWeaponAbility':
        return cls.build(regions=[Region(Block()), Region(Block())], attributes={"ability": WeaponAbilityAttr.make(ability, 0), "qualifier": qualifier})


@irdl_op_definition
class ObtainInvulnerableSave(IRDLOperation):
    name = "rul.obtain_cover"
    beneficient: Operand = operand_def(AnyOf([UnitType, ModelType]))
    value: Attribute =  attr_def(IntAttr)

    @classmethod
    def make(cls, beneficient: SSAValue, value: int):
        return cls.build(operands=[beneficient], attributes={"value": IntAttr(value)})

@irdl_op_definition
class OnTheBattleField(IRDLOperation):
    name = "rul.are_on_the_battlefield"
    unit: Operand = operand_def(AnyOf([UnitType, ModelType]))
    result: OpResult = result_def(BoolType)

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[unit])

@irdl_attr_definition
class IntegerRangeAttr(ParametrizedAttribute):
    name = "rul.integer_range"

    min: IntAttr
    max: IntAttr

    @classmethod
    def make(cls, min: int, max: int):
        return cls(IntAttr(min), IntAttr(max))

@irdl_attr_definition
class DiceExpressionAttr(ParametrizedAttribute):
    name = "rul.dice_expression"

    dices_to_roll: IntAttr
    dice_faces: IntAttr
    raw_extra: IntAttr

    @classmethod
    def make(cls, dices_to_roll: int, dice_faces: int, raw_extra: int = 0):
        return cls(IntAttr(dices_to_roll), IntAttr(dice_faces), IntAttr(raw_extra))

@irdl_op_definition
class FellBack(IRDLOperation):
    name = "rul.fell_back"
    unit: Operand = operand_def(AnyOf([UnitType, ModelType]))
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, unit: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[unit])

@irdl_op_definition
class HasAbility(IRDLOperation):
    name = "rul.with_ability"
    subject: Operand = operand_def(AnyOf([UnitType, ModelType]))
    ability: Operand = operand_def(AbilityType)
    result: OpResult = result_def(BoolType)
    traits: OpTraits = traits_def(Pure())

    @classmethod
    def make(cls, subject: SSAValue, ability: SSAValue):
        return cls.build(result_types=[BoolType()], operands=[subject, ability])

@irdl_op_definition
class Setup(IRDLOperation):
    name = "rul.setup"
    subject: Operand = operand_def(AnyOf([UnitType, ModelType]))

    @classmethod
    def make(cls, subject: SSAValue):
        return cls.build(operands=[subject])

class RulDialect(Dialect):
    def __init__(self):
        super().__init__(operations=[SelectSubject, EachTimeEffect,BelongsTo, TimedEffect, UntilEffect, IfStatement, RLCFunction, All, ConditionalEffect, TrueOp,HasKeyword, And, IsOwnedBy, ThisSubject, FilterList, IsAttackMadeWeapon, Ability, MovementKindAttr, WeaponQualifierKindAttr, KeywordAttr, CharacteristicAttr, WeaponCharacteristicAttr, WeaponAbilityKindAttr, WeaponAbilityAttr, ObtainWeaponAbility, TimeQualifierAttr, PlayerAttr, BelowHalfStrenght, BelowStartingStrenght, AddUnitToArmy, TargetedWith, BattleShocked, UsingAbilitySubject, Leading, LeadedUnit, DestroyedSubject, ObtainCover, ObtainInvulnerableSave, OnTheBattleField, FellBack, SubjectsIn, SuchSubject], attributes=[ModelType, BoolType, AbilityKindAttr, AbilityType, UnitType, StratagemUseType, AbilityUseType, UnknownType, StratagemType, IntegerRangeAttr, DiceExpression, TimeInstantAttr, TimeEventType])


if __name__ == "__main__":
    ctx = Context()
    ctx.register_dialect("rul", lambda: RulDialect())
    module = ModuleOp(Region())
    module.body.add_block(Block())
    builder = Builder(insertion_point=InsertPoint.at_end(module.body.first_block))

    result = builder.insert(Ability.make(AbilityKind.DEEP_STRIKE))
    builder.insert(IsAttackMadeWeapon.make(result, "some_weapon"))
    builder.insert(TargetedWith.make())
    printer = Printer()
    printer.print_op(module)
    range = IntegerRangeAttr.make(0, 10)
    printer.print_attribute(range)
