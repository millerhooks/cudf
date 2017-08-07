import pandas as pd

from .dataframe import Series
from . import numerical, utils, series_impl
from .buffer import Buffer


class CategoricalAccessor(object):
    """
    This mimicks pandas `df.cat` interface.
    """
    def __init__(self, parent, categories, ordered):
        self._parent = parent
        self._categories = tuple(categories)
        self._ordered = ordered

    @property
    def categories(self):
        return self._categories

    @property
    def ordered(self):
        return self._ordered

    @property
    def codes(self):
        data = self._parent.data
        if self._parent.has_null_mask:
            mask = self._parent.mask
            null_count = self._parent.null_count
            return Series.from_masked_array(data=data.mem, mask=mask.mem,
                                            null_count=null_count)
        else:
            return Series.from_buffer(data)


class CategoricalSeriesImpl(series_impl.SeriesImpl):
    """
    Implements a Categorical Series that treats integral values as index
    into a dictionary that map to arbitrary objects (e.g. string).
    """
    def __init__(self, dtype, codes_dtype, categories, ordered):
        super(CategoricalSeriesImpl, self).__init__(dtype)
        self._categories = categories
        self._ordered = ordered
        # This contains the `.code` series implementation
        self._codes_impl = numerical.NumericalSeriesImpl(codes_dtype)

    def __eq__(self, other):
        return (isinstance(other, CategoricalSeriesImpl) and
                self.dtype == other.dtype and
                tuple(self._categories) == tuple(other._categories) and
                self._ordered == other._ordered and
                self._codes_impl == other._codes_impl)

    def _encode(self, value):
        for i, cat in enumerate(self._categories):
            if cat == value:
                return i
        return -1

    def _decode(self, value):
        for i, cat in enumerate(self._categories):
            if i == value:
                return cat

    def cat(self, series):
        return CategoricalAccessor(series, categories=self._categories,
                                   ordered=self._ordered)

    def element_to_str(self, value):
        return str(value)

    def binary_operator(self, binop, lhs, rhs):
        msg = 'Categorical cannot perform the operation: {}'.format(binop)
        raise TypeError(msg)

    def unary_operator(self, unaryop, series):
        msg = 'Categorical cannot perform the operation: {}'.format(unaryop)
        raise TypeError(msg)

    def unordered_compare(self, cmpop, lhs, rhs):
        if self != rhs._impl:
            raise TypeError('Categoricals can only compare with the same type')
        return self._codes_impl.unordered_compare(cmpop, lhs, rhs)

    def ordered_compare(self, cmpop, lhs, rhs):
        if not (self._ordered and rhs._impl._ordered):
            msg = "Unordered Categoricals can only compare equality or not"
            raise TypeError(msg)
        if self != rhs._impl:
            raise TypeError('Categoricals can only compare with the same type')
        return self._codes_impl.ordered_compare(cmpop, lhs, rhs)

    def normalize_compare_value(self, series, other):
        code = self._codes_impl.dtype.type(self._encode(other))
        darr = utils.scalar_broadcast_to(code, shape=len(series))
        out = series_impl.empty_like_same_mask(series, impl=self)
        # FIXME: not efficient
        out.data.mem.copy_to_device(darr)
        return out

    def element_indexing(self, series, index):
        val = self._codes_impl.element_indexing(series, index)
        return self._decode(val) if val is not None else val

    def sort_by_values(self, series, ascending):
        return self._codes_impl.sort_by_values(series, ascending)

    def as_index(self, series):
        return self._codes_impl.as_index(series)

    def to_pandas(self, series, index=True):
        if index is True:
            index = series.index.to_pandas()
        data = pd.Categorical.from_codes(series.cat.codes.to_array(),
                                         categories=self._categories,
                                         ordered=self._ordered)
        return pd.Series(data, index=index)

    def shim_wrap_column(self, column):
        return column.view(CategoricalColumn, dtype=self.dtype,
                           categories=self._categories,
                           ordered=self._ordered)


class CategoricalColumn(series_impl.ColumnOps):
    def __init__(self, **kwargs):
        categories = kwargs.pop('categories')
        ordered = kwargs.pop('ordered')
        super(CategoricalColumn, self).__init__(**kwargs)
        self._categories = tuple(categories)
        self._ordered = bool(ordered)

    def _replace_defaults(self):
        params = super(CategoricalColumn, self)._replace_defaults()
        params.update(dict(categories=self._categories,
                           ordered=self._ordered))
        return params

    @property
    def as_numerical(self):
        return self.view(numerical.NumericalColumn, dtype=self.data.dtype)

    def cat(self):
        return CategoricalAccessor(self, categories=self._categories,
                                   ordered=self._ordered)

    @property
    def shim_impl(self):
        return CategoricalSeriesImpl(dtype=self.dtype,
                                     codes_dtype=self.data.dtype,
                                     categories=self._categories,
                                     ordered=self._ordered)

    def binary_operator(self, binop, rhs):
        msg = 'Categorical cannot perform the operation: {}'.format(binop)
        raise TypeError(msg)

    def unary_operator(self, unaryop):
        msg = 'Categorical cannot perform the operation: {}'.format(unaryop)
        raise TypeError(msg)

    def unordered_compare(self, cmpop, rhs):
        if self.shim_impl != rhs.shim_impl:
            raise TypeError('Categoricals can only compare with the same type')
        return self.as_numerical.unordered_compare(cmpop, rhs)

    def ordered_compare(self, cmpop, rhs):
        if not (self._ordered and rhs._ordered):
            msg = "Unordered Categoricals can only compare equality or not"
            raise TypeError(msg)
        if self.shim_impl != rhs.shim_impl:
            raise TypeError('Categoricals can only compare with the same type')
        return self.as_numerical.ordered_compare(cmpop, rhs)

    def normalize_compare_value(self, other):
        code = self.data.dtype.type(self._encode(other))
        ary = utils.scalar_broadcast_to(code, shape=len(self))
        col = self.replace(data=Buffer(ary), dtype=self.dtype,
                           categories=self._categories, ordered=self._ordered)
        return col

    def astype(self, dtype):
        return self.as_numerical.astype(dtype)

    def _encode(self, value):
        for i, cat in enumerate(self._categories):
            if cat == value:
                return i
        return -1

    def _decode(self, value):
        for i, cat in enumerate(self._categories):
            if i == value:
                return cat
