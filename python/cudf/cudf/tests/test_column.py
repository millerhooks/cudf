# Copyright (c) 2020, NVIDIA CORPORATION.

import cupy as cp
import numpy as np
import pandas as pd
import pytest

import cudf
from cudf.tests.utils import assert_eq

dtypes = [
    "int8",
    "int16",
    "int32",
    "int64",
    "float32",
    "float64",
    "datetime64[ns]",
    "str",
    "category",
]


@pytest.fixture(params=dtypes, ids=dtypes)
def pandas_input(request):
    data = np.random.randint(0, 1000, 100)
    return pd.Series(data, dtype=request.param)


@pytest.mark.parametrize("offset", [0, 1, 15])
@pytest.mark.parametrize("size", [None, 50, 10, 0])
def test_column_offset_and_size(pandas_input, offset, size):
    col = cudf.core.column.as_column(pandas_input)
    col = cudf.core.column.build_column(
        data=col.base_data,
        dtype=col.dtype,
        mask=col.base_mask,
        size=size,
        offset=offset,
        children=col.base_children,
    )

    if cudf.utils.dtypes.is_categorical_dtype(col.dtype):
        assert col.size == col.codes.size
        assert col.size == (col.codes.data.size / col.codes.dtype.itemsize)
    elif pd.api.types.is_string_dtype(col.dtype):
        assert col.size == (col.children[0].size - 1)
        assert col.size == (
            (col.children[0].data.size / col.children[0].dtype.itemsize) - 1
        )
    else:
        assert col.size == (col.data.size / col.dtype.itemsize)

    got = cudf.Series(col)

    if offset is None:
        offset = 0
    if size is None:
        size = 100
    else:
        size = size + offset

    slicer = slice(offset, size)
    expect = pandas_input.iloc[slicer].reset_index(drop=True)

    assert_eq(expect, got)


@pytest.mark.parametrize(
    "data",
    [
        np.array([[23, 68, 2, 38, 9, 83, 72, 6, 98, 30]]),
        np.array([[1, 2], [7, 6]]),
    ],
)
def test_column_series_multi_dim(data):
    with pytest.raises(ValueError):
        cudf.Series(data)

    with pytest.raises(ValueError):
        cudf.core.column.as_column(data)


@pytest.mark.parametrize("data", [["1.0", "2", -3], ["1", "0.11", 0.1]])
def test_column_series_misc_input(data):
    psr = pd.Series(data)
    sr = cudf.Series(data)

    assert_eq(psr.dtype, sr.dtype)
    assert_eq(psr.astype("str"), sr)


@pytest.mark.parametrize("data", [[1.1, 2.2, 3.3, 4.4], [1, 2, 3, 4]])
@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_column_series_cuda_array_dtype(data, dtype):
    psr = pd.Series(np.asarray(data), dtype=dtype)
    sr = cudf.Series(cp.asarray(data), dtype=dtype)

    assert_eq(psr, sr)

    psr = pd.Series(data, dtype=dtype)
    sr = cudf.Series(data, dtype=dtype)

    assert_eq(psr, sr)
