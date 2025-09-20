from .dialect import *
from functools import singledispatchmethod
from .passes import dominates
from .passes import merge_preconditions

class SemanticalAnalyzer(ModulePass):
    name = "semantical-analyze-pass"

    def apply(self, ctx: Context, module: ModuleOp):
        self.visit(module)

    def __init__(self):
        super().__init__()
        self.builder = None
        self.rewriter = Rewriter()
        self.seen_subjects = []

    def add(self, operation):
        self.builder.insert(operation)
        return operation

    def visit(self, node: Operation):
        if node.parent is not None:
            self.builder.insertion_point = InsertPoint.after(node)
        self._visit(node)


    @singledispatchmethod
    def _visit(self, node):
        print(type(node))
        raise NotImplementedError()

    @_visit.register
    def _(self, op: Any):
        pass

    @_visit.register
    def _(self, op: IsOwnedBy):
        pass

    @_visit.register
    def _(self, op: WithinEngagementRange):
        pass

    @_visit.register
    def _(self, module: ModuleOp):
        self.builder = Builder(InsertPoint.at_start(module.body.first_block))
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
        print(cond)
        assert(cond.lhs.type == cond.rhs.type)
        pass

    @_visit.register
    def _(self, cond: HasKeyword):
        pass

    @_visit.register
    def _(self, cond: MakesAnAttack):
        for op in list(cond.condition.ops):
            self.visit(op)

        self._rewrite_any_matching_subject_as_filter(cond)

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

        self._rewrite_any_matching_subject_as_filter(cond, 0)
        self._rewrite_any_matching_subject_as_filter(cond, 1)

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

        op: AnyMatchingSubject
        op = filtering_op.get_single_selection_candidate(index)
        block = filtering_op.regions[index].first_block
        if not isinstance(op, AnyMatchingSubject):
            return

        filter: AnyMatchingSubject
        belong: BelongsTo
        yield_op: Yield
        yield_op = block.last_op
        belong = yield_op.value.owner
        filter = belong.rhs.owner

        filter.constraint.first_block.args[0].replace_by(block.args[0])
        self.rewriter.erase_op(yield_op)
        self.rewriter.erase_op(belong)

        self.rewriter.inline_block(filter.constraint.first_block, InsertPoint.at_end(block))
        base_subject = filter.base_subject.first_block.last_op.value

        self.rewriter.erase_op(filter.base_subject.first_block.last_op)
        self.rewriter.inline_block(filter.base_subject.first_block, InsertPoint.before(block.last_op))

        is_same = IsSame.make(block.args[0], base_subject)
        self.rewriter.insert_op(is_same, InsertPoint.before(block.last_op))
        and_op = And.make(is_same.result, block.last_op.value)
        self.rewriter.insert_op(and_op, InsertPoint.before(block.last_op))
        block.last_op.operands[0] = and_op.result

        self.rewriter.erase_op(filter)


    @_visit.register
    def _(self, cond: SelectSubject):
        for op in list(cond.condition.ops):
            self.visit(op)

        self.rewriter.replace_value_with_new_type(cond.result, cond.get_belongs_to_argument_type().underlying)
        self._rewrite_any_matching_subject_as_filter(cond)
        self.seen_subjects.append(cond.result)


    @_visit.register
    def _(self, cond: TimedEffect):
        for op in list(cond.condition.ops):
            self.visit(op)
        for op in list(cond.effect.ops):
            self.visit(op)


    @_visit.register
    def _(self, cond: ConditionalEffect):
        for op in list(cond.condition.ops):
            self.visit(op)
        for op in list(cond.effect.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: ThisSubject):
        pass

    @_visit.register
    def _(self, cond: Leading):
        self.seen_subjects.append(cond.leader)
        self.seen_subjects.append(cond.unit)

    @_visit.register
    def _(self, cond: ObtainWeaponAbility):
        for op in list(cond.beneficient.ops):
            self.visit(op)

    @_visit.register
    def _(self, cond: TrueOp):
        pass


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
        raise NotImplementedError()

    @_visit.register
    def _(self, ref: AnyMatchingSubject):
        for op in list(ref.base_subject.ops):
            self.visit(op)
        new_type = ref.base_subject.first_block.last_op.value.type
        result_type = new_type if isinstance(new_type, ListType) else ListType.make(new_type)
        base_type = new_type.underlying if isinstance(new_type, ListType) else new_type
        self.rewriter.replace_value_with_new_type(ref.result, result_type)
        self.rewriter.replace_value_with_new_type(ref.constraint.first_block.args[0], base_type)
        for op in list(ref.constraint.ops):
            self.visit(op)

        base_subject = ref.single_base_subject()
        contraint = ref.single_constraint()

        if isinstance(base_subject, AnyMatchingSubject):
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
        if isinstance(cond.model.owner, Any):
            op = SubjectsIn.make(cond.model.type, cond.rhs)
            self.rewriter.insert_op(op,InsertPoint.before(cond))
            cond.result.replace_by(op.result)
            self.rewriter.erase_op(cond)




    @_visit.register
    def _(self, cond: SubjectsIn):
        assert(cond.unit.type == UnitType())
        assert(cond.result.type == ListType.make(ModelType()))

    @_visit.register
    def _(self, cond: Yield):
        pass


