from .dialect import *
from functools import singledispatchmethod
from .passes import dominates, visit
from .passes import merge_preconditions, move_region_content

def compare_filters(container1, lhs: SSAValue, container2, rhs: SSAValue):
    if lhs.owner.parent_op() == container1:
        return rhs.owner.parent_op() == container2

    if isinstance(lhs.owner, IsOwnedBy) and isinstance(rhs.owner, IsOwnedBy):
        return lhs.owner.player == rhs.owner.player and compare_filters(container1, lhs.owner.unit, container2, rhs.owner.unit)

    print("not implemented")
    print(lhs)
    print(rhs)
    assert(False)
    return False

def equivalent_filter_lists(subject: FilterList, candidate: FilterList):
    assert(len(subject.base_subject.first_block.ops) == 2 and len(candidate.base_subject.first_block.ops) == 2)
    if not refers_to(subject.base_subject.first_block.first_op, candidate.base_subject.first_block.first_op):
        return False

    return compare_filters(subject, subject.constraint.first_block.last_op.value[0], candidate, candidate.constraint.first_block.last_op.value[0])

# returns true if the subject operation that defines some subject could refer to the candidate.
def refers_to(subject: Operation, candidate: Operation):
    if isinstance(candidate, All):
        return subject.result.type == candidate.result.type
    if isinstance(subject, OneOf):
        if isinstance(candidate, OneOf):
            return one_of_refers_to(subject, candidate)
        return False
    if isinstance(subject, FilterList):
        if isinstance(candidate, FilterList):
            return equivalent_filter_lists(subject, candidate)
        return False
    print("not equivalent filter lists")
    print(subject)
    print(candidate)
    assert False

def one_of_refers_to(subject: OneOf, candidate):
    return refers_to( subject.base_subject.first_block.first_op, candidate.base_subject.first_block.first_op)

class SemanticalAnalyzer(ModulePass):
    name = "semantical-analyze-pass"

    def analyze_subjects(self, module: ModuleOp):
        referrable_subject = sorted(visit(module, MakeReferrable), key=lambda x: x.index.data)
        for subject in referrable_subject:
            subject: MakeReferrable
            if not isinstance(subject.subject.owner, Block):
                self.visit(subject.subject.owner)
            self.visit(subject)

    def apply(self, ctx: Context, module: ModuleOp):
        self.builder = Builder(InsertPoint.at_start(module.body.first_block))
        self.analyze_subjects(module)

        self.visit(module)

    def __init__(self):
        super().__init__()
        self.builder = None
        self.rewriter = Rewriter()
        self.seen_subjects = []
        self.last_optionally_usable = None

    def add(self, operation):
        self.builder.insert(operation)
        return operation

    def visit(self, node: Operation):
        if isinstance(node, Block):
            self.builder.insertion_point = InsertPoint.at_start(node)
        elif node.parent is not None:
            self.builder.insertion_point = InsertPoint.after(node)
        self._visit(node)


    @singledispatchmethod
    def _visit(self, node):
        print(type(node))
        raise NotImplementedError()

    @_visit.register
    def _(self, op: CapturedReference):
        self.rewriter.replace_value_with_new_type(op.result, op.value.type)

    @_visit.register
    def _(self, op: WithinRange):
        pass

    @_visit.register
    def _(self, op: All):
        pass

    @_visit.register
    def _(self, op: IsOwnedBy):
        pass

    @_visit.register
    def _(self, op: WithinEngagementRange):
        pass

    @_visit.register
    def _(self, module: ModuleOp):
        for op in list(module.body.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: ModifyRoll):
        pass

    @_visit.register
    def _(self, cond: And):
        pass

    @_visit.register
    def _(self, cond: IsSame):
        assert(cond.lhs.type == cond.rhs.type)
        pass

    @_visit.register
    def _(self, cond: HasKeyword):
        pass

    @_visit.register
    def _(self, cond: MakesAnAttack):
        for op in list(cond.subject.ops):
            self.visit(op)
        for op in list(cond.condition.ops):
            self.visit(op)


    @_visit.register
    def _(self, cond: GainCP):
        pass

    @_visit.register
    def _(self, cond: Destroys):
        for op in list(cond.source.ops):
            self.visit(op)
        for op in list(cond.target.ops):
            self.visit(op)
        for op in list(cond.effect.ops):
            self.visit(op)
        for op in list(cond.condition.ops):
            self.visit(op)


    @_visit.register
    def _(self, cond: AdditionalEffect):
        for op in list(cond.body.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: BelowStartingStrenght):
        pass

    @_visit.register
    def _(self, cond: MakeBattleShockTest):
        pass

    @_visit.register
    def _(self, cond: ItSubject):
        cond.result.replace_by(self.seen_subjects[-1])
        self.rewriter.erase_op(cond)


    @_visit.register
    def _(self, cond: ConstrainedSuchSubject):
        for op in list(cond.body.ops):
            self.visit(op)
        self.rewriter.replace_value_with_new_type(cond.result, cond.body.first_block.last_op.result.type)
        # we are going to assume that inside this guy there is always a OneOf FilterList
        subject = cond.body.first_block.first_op
        for candidate in reversed(self.seen_subjects):
            if refers_to(subject, candidate.owner):
                if dominates(candidate.owner, cond):
                    cond.result.replace_by(candidate)
                else:
                    caputured_reference = CapturedReference.make(candidate)
                    cond.result.replace_by(caputured_reference.result)
                    self.rewriter.insert_op(caputured_reference, InsertPoint.before(cond))
                self.rewriter.erase_op(cond)
                return

        print("could not find referred candidate")
        print(self)
        print(self.seen_subjects)
        assert False


    @_visit.register
    def _(self, cond: IfStatement):
        for op in list(cond.condition.ops):
            self.visit(op)
        for op in list(cond.true_branch.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: EachTimeEffect):
        for op in list(cond.event.ops):
            self.visit(op)
        for op in list(cond.effect.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: UntilEffect):
        for op in list(cond.effect.ops):
            self.visit(op)

    def _rewrite_any_matching_subject_as_filter(self, filtering_op: FilteringOp, index = 0):
        if not filtering_op.is_filtering_structure(index):
            self.rewriter.replace_value_with_new_type(filtering_op.filter_argument(index), filtering_op.get_belongs_to_argument_type(index))
            return

        self.rewriter.replace_value_with_new_type(filtering_op.filter_argument(index), filtering_op.get_belongs_to_argument_type(index).underlying)

        op: FilterList
        op = filtering_op.get_single_selection_candidate(index)
        block = filtering_op.regions[index].first_block
        if not isinstance(op, FilterList):
            return

        filter: FilterList
        belong: BelongsTo
        yield_op: Yield
        yield_op = block.last_op
        belong = yield_op.value[0].owner
        filter = belong.rhs.owner

        filter.constraint.first_block.args[0].replace_by(block.args[0])
        self.rewriter.erase_op(yield_op)
        self.rewriter.erase_op(belong)

        self.rewriter.inline_block(filter.constraint.first_block, InsertPoint.at_end(block))
        base_subject = filter.base_subject.first_block.last_op.value

        self.rewriter.erase_op(filter.base_subject.first_block.last_op)
        self.rewriter.inline_block(filter.base_subject.first_block, InsertPoint.before(block.last_op))

        belongs_to = BelongsTo.make(block.args[0], base_subject)
        self.rewriter.insert_op(belongs_to, InsertPoint.before(block.last_op))
        and_op = And.make(belongs_to.result, block.last_op.value)
        self.rewriter.insert_op(and_op, InsertPoint.before(block.last_op))
        block.last_op.operands[0] = and_op.result

        self.rewriter.erase_op(filter)


    @_visit.register
    def _(self, cond: SelectSubject):
        if not isinstance(cond.result.type, UnknownType):
            return
        for op in list(cond.condition.ops):
            self.visit(op)

        self.rewriter.replace_value_with_new_type(cond.result, cond.get_belongs_to_argument_type().underlying)
        self._rewrite_any_matching_subject_as_filter(cond)

    @_visit.register
    def _(self, cond: MakeReferrable):
        if not isinstance(cond.subject, SuchSubject):
            self.seen_subjects.append(cond.subject)
        self.rewriter.erase_op(cond)

    @_visit.register
    def _(self, cond: TimedEffect):
        for op in list(cond.condition.ops):
            self.visit(op)
        for op in list(cond.effect.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: OptionallyUse):
        self.last_optionally_usable = cond

    @_visit.register
    def _(self, cond: IfItDoes):
        block = cond.effect.first_block
        cond.effect.detach_block(cond.effect.first_block)
        self.last_optionally_usable.effect.add_block(block)
        self.rewriter.erase_op(cond)
        for op in list(self.last_optionally_usable.effect.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: ModifyCPCost):
        return

    @_visit.register
    def _(self, cond: HasAbility):
        return

    @_visit.register
    def _(self, cond: ThisAbility):
        return

    @_visit.register
    def _(self, cond: OncePer):
        for op in list(cond.body.ops):
            self.visit(op)
        self.last_optionally_usable.use_limit = cond.value
        self.rewriter.inline_block(cond.body.first_block, InsertPoint.before(cond))
        self.rewriter.erase_op(cond)


    @_visit.register
    def _(self, cond: ConditionalEffect):
        for op in list(cond.condition.ops):
            self.visit(op)
        for op in list(cond.effect.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: ModifyCharacteristic):
        for op in list(cond.beneficient.ops):
            self.visit(op)
        for op in list(cond.condition.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: ThisSubject):
        pass

    @_visit.register
    def _(self, cond: Leading):
        pass

    @_visit.register
    def _(self, cond: ObtainInvulnerableSave):
        for op in list(cond.beneficient.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: ObtainWeaponAbility):
        for op in list(cond.beneficient.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: TrueOp):
        pass

    @_visit.register
    def _(self, operation: Targets):
        for op in list(operation.subjects.ops):
            self.visit(op)
        for op in list(operation.condition.ops):
            self.visit(op)
        for op in list(operation.effect.ops):
            self.visit(op)


    @_visit.register
    def _(self, ref: SuchSubject):
        sub: SSAValue
        for sub in reversed(self.seen_subjects):
            if ref.result.type != sub.type:
                continue

            if dominates(sub.owner, ref):
                ref.result.replace_by(sub)
            else:
                caputured_reference = CapturedReference.make(sub)
                ref.result.replace_by(caputured_reference.result)
                self.rewriter.insert_op(caputured_reference, InsertPoint.before(ref))
            self.rewriter.erase_op(ref)

            return
        for op in self.seen_subjects:
            print(op.owner)
        print(ref)
        raise NotImplementedError()


    @_visit.register
    def _(self, ref: OneOf):
        for op in list(ref.base_subject.ops):
            self.visit(op)
        subject = ref.base_subject.first_block.last_op.value[0]
        new_type = subject.type
        self.rewriter.replace_value_with_new_type(ref.result, new_type.underlying)

        if not isinstance(new_type, ListType) or isinstance(ref.parent_op(), FilterList):
            ref.result.replace_by(subject)
            self.rewriter.erase_op(ref.base_subject.first_block.last_op)
            self.rewriter.inline_block(ref.base_subject.last_block, InsertPoint.before(ref))
            self.rewriter.erase_op(ref)
            return


    @_visit.register
    def _(self, ref: FilterList):
        for op in list(ref.base_subject.ops):
            self.visit(op)
        new_type = ref.get_yielded_base_subject().type
        result_type = new_type
        base_type = new_type.underlying if isinstance(new_type, ListType) else new_type
        self.rewriter.replace_value_with_new_type(ref.result, result_type)
        self.rewriter.replace_value_with_new_type(ref.constraint.first_block.args[0], base_type)
        for op in list(ref.constraint.ops):
            self.visit(op)

        base_subject = ref.single_base_subject()
        contraint = ref.single_constraint()

        if isinstance(base_subject, FilterList):
            base_subject.detach()
            self.rewriter.insert_op(base_subject, InsertPoint.before(ref))
            merge_preconditions(ref.constraint.first_block, base_subject.constraint.first_block)
            ref.result.replace_by(base_subject.result)
            self.rewriter.erase_op(ref)
            return

        if isinstance(contraint, TrueOp):
            yield_op = ref.base_subject.last_block.last_op
            new_value = yield_op.value
            self.rewriter.erase_op(yield_op)
            self.rewriter.inline_block(ref.base_subject.last_block, InsertPoint.before(ref))
            ref.result.replace_by(new_value)
            self.rewriter.erase_op(ref)
            return


    @_visit.register
    def _(self, cond: BelongsTo):
        if cond.model.type == cond.rhs.type:
            op = IsSame.make(cond.model, cond.rhs)
            self.rewriter.insert_op(op,InsertPoint.before(cond))
            cond.result.replace_by(op.result)
            self.rewriter.erase_op(cond)
            return

    @_visit.register
    def _(self, cond: SubjectsIn):
        assert(cond.unit.type == UnitType())
        assert(cond.result.type == ListType.make(ModelType()))

    @_visit.register
    def _(self, cond: Yield):
        pass


