


from types import GeneratorType
import typing as tp

import csv
import json

from collections import namedtuple
from functools import partial

import numpy as np
from numpy.ma import MaskedArray

from static_frame.core.util import DEFAULT_SORT_KIND
from static_frame.core.util import NULL_SLICE
from static_frame.core.util import KEY_MULTIPLE_TYPES
from static_frame.core.util import GetItemKeyType
from static_frame.core.util import GetItemKeyTypeCompound
from static_frame.core.util import CallableOrMapping
from static_frame.core.util import KeyOrKeys
from static_frame.core.util import FilePathOrFileLike
from static_frame.core.util import DtypeSpecifier
from static_frame.core.util import DtypesSpecifier

from static_frame.core.util import IndexSpecifier
from static_frame.core.util import IndexInitializer
from static_frame.core.util import FrameInitializer
from static_frame.core.util import immutable_filter
from static_frame.core.util import column_2d_filter
from static_frame.core.util import column_1d_filter

from static_frame.core.util import name_filter
from static_frame.core.util import _gen_skip_middle
from static_frame.core.util import iterable_to_array
from static_frame.core.util import _dict_to_sorted_items
from static_frame.core.util import _array_to_duplicated
from static_frame.core.util import array_set_ufunc_many
from static_frame.core.util import array2d_to_tuples
from static_frame.core.util import _read_url
from static_frame.core.util import write_optional_file
from static_frame.core.util import GetItem
from static_frame.core.util import InterfaceSelection2D
from static_frame.core.util import InterfaceAsType
from static_frame.core.util import IndexCorrespondence
from static_frame.core.util import ufunc_unique
from static_frame.core.util import STATIC_ATTR
from static_frame.core.util import concat_resolved
from static_frame.core.util import DepthLevelSpecifier
from static_frame.core.util import _array_to_groups_and_locations

from static_frame.core.operator_delegate import MetaOperatorDelegate

from static_frame.core.iter_node import IterNodeApplyType
from static_frame.core.iter_node import IterNodeType
from static_frame.core.iter_node import IterNode

from static_frame.core.display import DisplayConfig
from static_frame.core.display import DisplayActive
from static_frame.core.display import Display
from static_frame.core.display import DisplayFormats
from static_frame.core.display import DisplayHeader

from static_frame.core.type_blocks import TypeBlocks

from static_frame.core.series import Series

from static_frame.core.index_base import IndexBase
from static_frame.core.index_base import index_from_optional_constructor

from static_frame.core.index import Index
from static_frame.core.index import IndexGO
from static_frame.core.index import _requires_reindex
from static_frame.core.index import _is_index_initializer
from static_frame.core.index import immutable_index_filter

from static_frame.core.index_hierarchy import IndexHierarchy
from static_frame.core.index_hierarchy import IndexHierarchyGO

from static_frame.core.doc_str import doc_inject




def dtypes_mappable(dtypes: DtypesSpecifier):
    '''
    Determine if the dtypes argument can be used by name lookup, rather than index.
    '''
    return isinstance(dtypes, (dict, Series))


@doc_inject(selector='container_init', class_name='Frame')
class Frame(metaclass=MetaOperatorDelegate):
    '''
    A two-dimensional ordered, labelled collection, immutable and of fixed size.

    Args:
        data: An iterable of row iterables, a 2D numpy array, or dictionary mapping column names to column values.
        {index}
        {columns}
        {own_data}
        {own_index}
        {own_columns}
    '''

    __slots__ = (
            '_blocks',
            '_columns',
            '_index',
            '_name'
            )

    _blocks: TypeBlocks
    _columns: IndexBase
    _index: IndexBase
    _name: tp.Hashable

    _COLUMN_CONSTRUCTOR = Index

    @classmethod
    def from_concat(cls,
            frames: tp.Iterable[tp.Union['Frame', Series]],
            *,
            axis: int = 0,
            union: bool = True,
            index: IndexInitializer = None,
            columns: IndexInitializer = None,
            name: tp.Hashable = None,
            consolidate_blocks: bool = False
            ):
        '''
        Concatenate multiple Frames into a new Frame. If index or columns are provided and appropriately sized, the resulting Frame will use those indices. If the axis along concatenation (index for axis 0, columns for axis 1) is unique after concatenation, it will be preserved.

        Args:
            frames: Iterable of Frames.
            axis: Integer specifying 0 to concatenate supplied frames vertically (aligning on columns), 1 to concatenate horizontally (aligning on rows).
            union: If True, the union of the aligned indices is used; if False, the intersection is used.
            index: Optionally specify a new index.
            columns: Optionally specify new columns.

        Returns:
            :py:class:`static_frame.Frame`
        '''

        # when doing axis 1 concat (growin horizontally) Series need to be presented as rows (axis 0)
        # axis_series = (0 if axis is 1 else 1)
        frames = [f if isinstance(f, Frame) else f.to_frame(axis) for f in frames]

        # switch if we have reduced the columns argument to an array
        from_array_columns = False
        from_array_index = False

        own_columns = False
        own_index = False

        if axis == 1: # stacks columns (extends rows horizontally)
            # index can be the same, columns must be redefined if not unique
            if columns is None:
                # returns immutable array
                columns = concat_resolved([frame._columns.values for frame in frames])
                from_array_columns = True
                # avoid sort for performance; always want rows if ndim is 2
                if len(ufunc_unique(columns, axis=0)) != len(columns):
                    raise RuntimeError('Column names after horizontal concatenation are not unique; supply a columns argument.')

            if index is None:
                index = array_set_ufunc_many(
                        (frame._index.values for frame in frames),
                        union=union)
                index.flags.writeable = False
                from_array_index = True

            def blocks():
                for frame in frames:
                    if len(frame.index) != len(index) or (frame.index != index).any():
                        frame = frame.reindex(index=index)
                    for block in frame._blocks._blocks:
                        yield block

        elif axis == 0: # stacks rows (extends columns vertically)
            if index is None:
                # returns immutable array
                index = concat_resolved([frame._index.values for frame in frames])
                from_array_index = True
                # avoid sort for performance; always want rows if ndim is 2
                if len(ufunc_unique(index, axis=0)) != len(index):
                    raise RuntimeError('Index names after vertical concatenation are not unique; supply an index argument.')

            if columns is None:
                columns = array_set_ufunc_many(
                        (frame._columns.values for frame in frames),
                        union=union)
                # import ipdb; ipdb.set_trace()
                columns.flags.writeable = False
                from_array_columns = True

            def blocks():
                aligned_frames = []
                previous_frame = None
                block_compatible = True
                reblock_compatible = True

                for frame in frames:
                    if len(frame.columns) != len(columns) or (frame.columns != columns).any():
                        frame = frame.reindex(columns=columns)
                    aligned_frames.append(frame)
                    # column size is all the same by this point
                    if previous_frame is not None:
                        if block_compatible:
                            block_compatible &= frame._blocks.block_compatible(
                                    previous_frame._blocks)
                        if reblock_compatible:
                            reblock_compatible &= frame._blocks.reblock_compatible(
                                    previous_frame._blocks)
                    previous_frame = frame

                if block_compatible or reblock_compatible:
                    if not block_compatible and reblock_compatible:
                        type_blocks = [f._blocks.consolidate() for f in aligned_frames]
                    else:
                        type_blocks = [f._blocks for f in aligned_frames]

                    # all TypeBlocks have the same number of blocks by here
                    for block_idx in range(len(type_blocks[0]._blocks)):
                        block_parts = []
                        for frame_idx in range(len(type_blocks)):
                            b = column_2d_filter(
                                    type_blocks[frame_idx]._blocks[block_idx])
                            block_parts.append(b)
                        # returns immutable array
                        yield concat_resolved(block_parts)
                else:
                    # must just combine .values; returns immutable array
                    yield concat_resolved([frame.values for frame in frames])
        else:
            raise NotImplementedError('no support for axis', axis)

        if from_array_columns:
            if columns.ndim == 2: # we have a hierarchical index
                column_cls = (IndexHierarchy
                        if cls._COLUMN_CONSTRUCTOR.STATIC else IndexHierarchyGO)
                columns = column_cls.from_labels(columns)
                own_columns = True

        if from_array_index:
            if index.ndim == 2: # we have a hierarchical index
                index = IndexHierarchy.from_labels(index)
                own_index = True

        if consolidate_blocks:
            block_gen = lambda: TypeBlocks.consolidate_blocks(blocks())
        else:
            block_gen = blocks

        return cls(TypeBlocks.from_blocks(block_gen()),
                index=index,
                columns=columns,
                name=name,
                own_data=True,
                own_columns=own_columns,
                own_index=own_index)

    @classmethod
    def from_records(cls,
            records: tp.Iterable[tp.Any],
            *,
            index: tp.Optional[IndexInitializer] = None,
            columns: tp.Optional[IndexInitializer] = None,
            dtypes: DtypesSpecifier = None,
            name: tp.Hashable = None,
            consolidate_blocks: bool = False
            ) -> 'Frame':
        '''Frame constructor from an iterable of rows.

        Args:
            records: Iterable of row values, provided either as arrays, tuples, lists, or namedtuples.
            index: Optionally provide an iterable of index labels, equal in length to the number of records.
            columns: Optionally provide an iterable of column labels, equal in length to the length of each row.
            dtypes: Optionally provide an iterable of dtypes, equal in length to the length of each row, or mapping by column name. If a dtype is given as None, NumPy's default type determination will be used.

        Returns:
            :py:class:`static_frame.Frame`
        '''
        derive_columns = False
        if columns is None:
            derive_columns = True
            # leave columns list in outer scope for blocks() to populate
            columns = []

        # if records is np; we can just pass it to constructor, as is alrady a consolidate type
        if isinstance(records, np.ndarray):
            if dtypes is not None:
                raise NotImplementedError('handling of dtypes when using NP records is no yet implemented')
            return cls(records, index=index, columns=columns)

        dtypes_is_map = dtypes_mappable(dtypes)
        def get_col_dtype(col_idx):
            if dtypes_is_map:
                return dtypes.get(columns[col_idx], None)
            return dtypes[col_idx]

        def blocks():
            if not hasattr(records, '__len__'):
                rows = list(records)
            else:
                rows = records

            row_reference = rows[0]
            row_count = len(rows)
            col_count = len(row_reference)

            # if dtypes is not None and len(dtypes) != col_count:
            #     raise RuntimeError('length of dtypes does not match rows')

            column_getter = None
            if isinstance(row_reference, dict):
                col_idx_iter = (k for k, _ in _dict_to_sorted_items(row_reference))
                if derive_columns: # just pass the key back
                    column_getter = lambda key: key
            elif isinstance(row_reference, Series):
                raise RuntimeError('Frame.from_records() does not support Series. Use Frame.from_concat() instead.')
            else:
                # all other iterables
                col_idx_iter = range(col_count)
                if hasattr(row_reference, '_fields') and derive_columns:
                    column_getter = row_reference._fields.__getitem__


            # derive types from first rows
            for col_idx, col_key in enumerate(col_idx_iter):
                if column_getter: # append as side effect of generator!
                    columns.append(column_getter(col_key))

                # for each column, try to get a column_type, or None
                if dtypes is None:
                    field_ref = row_reference[col_key]
                    # string, datetime64 types requires size in dtype specification, so cannot use np.fromiter, as we do not know the size of all columns
                    column_type = (type(field_ref)
                            if not isinstance(field_ref, (str, np.datetime64))
                            else None)
                    column_type_explicit = False
                else: # column_type returned here can be None.
                    column_type = get_col_dtype(col_idx)
                    column_type_explicit = True

                values = None
                if column_type is not None:
                    try:
                        values = np.fromiter(
                                (row[col_key] for row in rows),
                                count=row_count,
                                dtype=column_type)
                    except ValueError:
                        # the column_type may not be compatible, so must fall back on using np.array to determine the type, i.e., ValueError: cannot convert float NaN to integer
                        if not column_type_explicit:
                            # reset to None if not explicit and failued in fromiter
                            column_type = None
                if values is None:
                    # let array constructor determine type if column_type is None
                    values = np.array([row[col_key] for row in rows],
                            dtype=column_type)

                values.flags.writeable = False
                yield values

        if consolidate_blocks:
            block_gen = lambda: TypeBlocks.consolidate_blocks(blocks())
        else:
            block_gen = blocks

        return cls(TypeBlocks.from_blocks(block_gen()),
                index=index,
                columns=columns,
                name=name,
                own_data=True)

    @classmethod
    def from_json(cls,
            json_data: str,
            *,
            name: tp.Hashable = None,
            dtypes: DtypesSpecifier = None
            ) -> 'Frame':
        '''Frame constructor from an in-memory JSON document.

        Args:
            json_data: a string of JSON, encoding a table as an array of JSON objects.

        Returns:
            :py:class:`static_frame.Frame`
        '''
        data = json.loads(json_data)
        return cls.from_records(data, name=name, dtypes=dtypes)

    @classmethod
    def from_json_url(cls,
            url: str,
            *,
            name: tp.Hashable = None,
            dtypes: DtypesSpecifier = None
            ) -> 'Frame':
        '''Frame constructor from a JSON documenst provided via a URL.

        Args:
            url: URL to the JSON resource.

        Returns:
            :py:class:`static_frame.Frame`
        '''
        return cls.from_json(_read_url(url), name=name, dtypes=dtypes)


    @classmethod
    def from_items(cls,
            pairs: tp.Iterable[tp.Tuple[tp.Hashable, tp.Iterable[tp.Any]]],
            *,
            index: IndexInitializer = None,
            fill_value: object = np.nan,
            name: tp.Hashable = None,
            dtypes: DtypesSpecifier = None,
            consolidate_blocks: bool = False):
        '''Frame constructor from an iterator or generator of pairs, where the first value is the column name and the second value an iterable of column values.

        Args:
            pairs: Iterable of pairs of column name, column values.
            index: Iterable of values to create an Index.
            fill_value: If pairs include Series, they will be reindexed with the provided index; reindexing will use this fill value.
            consoidate_blocks: If True, same typed adjacent columns will be consolidated into a contiguous array.

        Returns:
            :py:class:`static_frame.Frame`
        '''
        columns = []

        # if an index initializer is passed, and we expect to get Series, we need to create the index in advance of iterating blocks
        own_index = False
        if _is_index_initializer(index):
            index = Index(index)
            own_index = True

        dtypes_is_map = dtypes_mappable(dtypes)
        def get_col_dtype(col_idx):
            if dtypes_is_map:
                return dtypes.get(columns[col_idx], None)
            return dtypes[col_idx]

        def blocks():
            for col_idx, (k, v) in enumerate(pairs):
                columns.append(k) # side effet of generator!

                if dtypes:
                    column_type = get_col_dtype(col_idx)
                else:
                    column_type = None

                if isinstance(v, np.ndarray):
                    # NOTE: we rely on TypeBlocks constructor to check that these are same sized
                    if column_type is not None:
                        yield v.astype(column_type)
                    else:
                        yield v
                elif isinstance(v, Series):
                    if index is None:
                        raise RuntimeError('can only consume Series in Frame.from_items if an Index is provided.')

                    if column_type is not None:
                        v = v.astype(column_type)

                    if _requires_reindex(v.index, index):
                        yield v.reindex(index, fill_value=fill_value).values
                    else:
                        yield v.values

                elif isinstance(v, Frame):
                    raise NotImplementedError('Frames are not supported in from_items constructor.')
                else:
                    values = np.array(v, dtype=column_type)
                    values.flags.writeable = False
                    yield values

        if consolidate_blocks:
            block_gen = lambda: TypeBlocks.consolidate_blocks(blocks())
        else:
            block_gen = blocks

        return cls(TypeBlocks.from_blocks(block_gen()),
                index=index,
                columns=columns,
                name=name,
                own_data=True,
                own_index=own_index)


    @classmethod
    def from_dict(cls,
            dict: tp.Dict[tp.Hashable, tp.Iterable[tp.Any]],
            *,
            index: IndexInitializer = None,
            fill_value: object = np.nan,
            name: tp.Hashable = None,
            dtypes: DtypesSpecifier = None,
            consolidate_blocks: bool = False):
        '''
        Create a Frame from a dictionary, or any object that has an items() method.
        '''
        return cls.from_items(dict.items(),
                index=index,
                fill_value=fill_value,
                name=name,
                dtypes=dtypes,
                consolidate_blocks=consolidate_blocks)


    @classmethod
    def from_structured_array(cls,
            array: np.ndarray,
            *,
            name: tp.Hashable = None,
            index_column: tp.Optional[IndexSpecifier] = None,
            dtypes: DtypesSpecifier = None,
            consolidate_blocks: bool = False) -> 'Frame':
        '''
        Convert a NumPy structed array into a Frame.

        Args:
            array: Structured NumPy array.
            index_column: Optionally provide the name or position offset of the column to use as the index.

        Returns:
            :py:class:`static_frame.Frame`
        '''

        names = array.dtype.names
        if isinstance(index_column, int):
            index_name = names[index_column]
        else:
            index_name = index_column

        # assign in generator; requires  reading through gen first
        index_array = None
        # cannot use names of we remove an index; might be a more efficient way as we kmnow the size
        columns = []
        columns_with_index = []

        dtypes_is_map = dtypes_mappable(dtypes)
        def get_col_dtype(col_idx):
            if dtypes_is_map:
                return dtypes.get(columns_with_index[col_idx], None)
            return dtypes[col_idx]

        def blocks():
            for col_idx, name in enumerate(names):
                # append here as we iterate for usage in get_col_dtype
                columns_with_index.append(name)

                # this is not expected to make a copy
                array_final = array[name]
                if dtypes:
                    dtype = get_col_dtype(col_idx)
                    if dtype is not None:
                        array_final = array_final.astype(dtype)

                if name == index_name:
                    nonlocal index_array
                    index_array = array_final
                    continue

                columns.append(name)
                yield array_final

        if consolidate_blocks:
            block_gen = lambda: TypeBlocks.consolidate_blocks(blocks())
        else:
            block_gen = blocks

        return cls(TypeBlocks.from_blocks(block_gen()),
                columns=columns,
                index=index_array,
                name=name,
                own_data=True)

    #---------------------------------------------------------------------------
    # iloc/loc pairs constructors: these are not yet documented

    @classmethod
    def from_element_iloc_items(cls,
            items,
            *,
            index,
            columns,
            dtype,
            name: tp.Hashable = None
            ) -> 'Frame':
        '''
        Given an iterable of pairs of iloc coordinates and values, populate a Frame as defined by the given index and columns. Dtype must be specified.

        Returns:
            :py:class:`static_frame.Frame`
        '''
        index = Index(index)
        columns = cls._COLUMN_CONSTRUCTOR(columns)

        tb = TypeBlocks.from_element_items(items,
                shape=(len(index), len(columns)),
                dtype=dtype)
        return cls(tb,
                index=index,
                columns=columns,
                name=name,
                own_data=True,
                own_index=True,
                own_columns=True)

    @classmethod
    def from_element_loc_items(cls,
            items,
            *,
            index,
            columns,
            dtype=None,
            name: tp.Hashable = None
            ) -> 'Frame':
        '''
        This function is partialed (seeting the index and columns) and used by ``IterNodeDelegate`` as as the apply constructor for doing application on iteration.

        Returns:
            :py:class:`static_frame.Frame`
        '''

        # index = Index(index)
        # columns = cls._COLUMN_CONSTRUCTOR(columns)

        index = index_from_optional_constructor(index, Index)
        columns = index_from_optional_constructor(columns, cls._COLUMN_CONSTRUCTOR)

        items = (((index.loc_to_iloc(k[0]), columns.loc_to_iloc(k[1])), v)
                for k, v in items)

        dtype = dtype if dtype is not None else object
        tb = TypeBlocks.from_element_items(items,
                shape=(len(index), len(columns)),
                dtype=dtype)

        return cls(tb,
                index=index,
                columns=columns,
                name=name,
                own_data=True,
                own_index=True,
                own_columns=True)

    #---------------------------------------------------------------------------
    # file, data format loaders

    @classmethod
    def from_csv(cls,
            fp: FilePathOrFileLike,
            *,
            delimiter: str = ',',
            index_column: tp.Optional[tp.Union[int, str]] = None,
            skip_header: int = 0,
            skip_footer: int = 0,
            header_is_columns: bool = True,
            quote_char: str = '"',
            dtypes: DtypesSpecifier = None,
            encoding: tp.Optional[str] = None
            ) -> 'Frame':
        '''
        Create a Frame from a file path or a file-like object defining a delimited (CSV, TSV) data file.

        Args:
            fp: A file path or a file-like object.
            delimiter: The character used to seperate row elements.
            index_column: Optionally specify a column, by position or name, to become the index.
            skip_header: Number of leading lines to skip.
            skip_footer: Numver of trailing lines to skip.
            header_is_columns: If True, columns names are read from the first line after the first skip_header lines.
            dtypes: set to None by default to permit discovery

        Returns:
            :py:class:`static_frame.Frame`
        '''
        # https://docs.scipy.org/doc/numpy/reference/generated/numpy.loadtxt.html
        # https://docs.scipy.org/doc/numpy/reference/generated/numpy.genfromtxt.html

        delimiter_native = '\t'

        if delimiter != delimiter_native:
            # this is necessary if there are quoted cells that include the delimiter
            def to_tsv():
                if isinstance(fp, str):
                    with open(fp, 'r') as f:
                        for row in csv.reader(f, delimiter=delimiter, quotechar=quote_char):
                            yield delimiter_native.join(row)
                else:
                    # handling file like object works for stringio but not for bytesio
                    for row in csv.reader(fp, delimiter=delimiter, quotechar=quote_char):
                        yield delimiter_native.join(row)
            file_like = to_tsv()
        else:
            file_like = fp

        array = np.genfromtxt(file_like,
                delimiter=delimiter_native,
                skip_header=skip_header,
                skip_footer=skip_footer,
                names=header_is_columns,
                dtype=None,
                encoding=encoding,
                invalid_raise=False,
                missing_values={''},
                )
        # can own this array so set it as immutable
        array.flags.writeable = False
        return cls.from_structured_array(array,
                index_column=index_column,
                dtypes=dtypes
                )

    @classmethod
    def from_tsv(cls, fp, **kwargs) -> 'Frame':
        '''
        Specialized version of :py:meth:`Frame.from_csv` for TSV files.

        Returns:
            :py:class:`static_frame.Frame`
        '''
        return cls.from_csv(fp, delimiter='\t', **kwargs)


    @classmethod
    @doc_inject()
    def from_pandas(cls,
            value,
            *,
            own_data: bool = False) -> 'Frame':
        '''Given a Pandas DataFrame, return a Frame.

        Args:
            value: Pandas DataFrame.
            {own_data}

        Returns:
            :py:class:`static_frame.Frame`
        '''
        # create generator of contiguous typed data
        # calling .values will force type unification accross all columns
        def blocks():
            #import ipdb; ipdb.set_trace()
            pairs = value.dtypes.items()
            column_start, dtype_current = next(pairs)

            column_last = column_start
            for column, dtype in pairs:

                if dtype != dtype_current:
                    # use loc to select before calling .values
                    array = value.loc[NULL_SLICE,
                            slice(column_start, column_last)].values
                    if own_data:
                        array.flags.writeable = False
                    yield array
                    column_start = column
                    dtype_current = dtype

                column_last = column

            # always have left over
            array = value.loc[NULL_SLICE, slice(column_start, None)].values
            if own_data:
                array.flags.writeable = False
            yield array

        blocks = TypeBlocks.from_blocks(blocks())

        # avoid getting a Series if a column
        if 'name' not in value.columns and hasattr(value, 'name'):
            name = value.name
        else:
            name = None

        is_go = not cls._COLUMN_CONSTRUCTOR.STATIC

        return cls(blocks,
                index=IndexBase.from_pandas(value.index),
                columns=IndexBase.from_pandas(value.columns, is_go=is_go),
                name=name,
                own_data=True,
                own_index=True,
                own_columns=True)

    #---------------------------------------------------------------------------

    def __init__(self,
            data: FrameInitializer = None,
            *,
            index: IndexInitializer = None,
            columns: IndexInitializer = None,
            name: tp.Hashable = None,
            own_data: bool = False,
            own_index: bool = False,
            own_columns: bool = False
            ) -> None:
        '''
        Args:
            own_data: if True, assume that the data being based in can be owned entirely by this Frame; that is, that a copy does not need to made.
            own_index: if True, the index is taken as is and is not passed to an Index initializer.
        '''
        self._name = name if name is None else name_filter(name)

        #-----------------------------------------------------------------------
        # blocks assignment

        blocks_constructor = None

        if isinstance(data, TypeBlocks):
            if own_data:
                self._blocks = data
            else:
                # assume we need to create a new TB instance; this will not copy underlying arrays as all blocks are immutable
                self._blocks = TypeBlocks.from_blocks(data._blocks)
        elif isinstance(data, np.ndarray):
            if own_data:
                data.flags.writeable = False
            self._blocks = TypeBlocks.from_blocks(data)

        elif isinstance(data, dict):
            raise RuntimeError('use Frame.from_dict to create a Frmae from a dict')

        elif data is None and (columns is None or index is None):
            def blocks_constructor(shape):
                self._blocks = TypeBlocks.from_none(shape)

        elif not hasattr(data, '__len__') and not isinstance(data, str):
            # data is not None, single element to scale to size of index and columns
            def blocks_constructor(shape):
                a = np.full(shape, data)
                a.flags.writeable = False
                self._blocks = TypeBlocks.from_blocks(a)
        else:
            # could be list of lists to be made into an array
            a = np.array(data)
            a.flags.writeable = False
            self._blocks = TypeBlocks.from_blocks(a)

        # counts can be zero (not None) if _block was created but is empty
        row_count, col_count = self._blocks._shape if not blocks_constructor else (None, None)

        #-----------------------------------------------------------------------
        # index assignment

        if own_columns or (
                hasattr(columns, STATIC_ATTR)
                and columns.STATIC
                and self._COLUMN_CONSTRUCTOR.STATIC):
            # if it is a STATIC index we can assign directly
            self._columns = columns
        elif columns is None or (hasattr(columns, '__len__') and len(columns) == 0):
            col_count = 0 if col_count is None else col_count
            self._columns = self._COLUMN_CONSTRUCTOR(
                    range(col_count),
                    loc_is_iloc=True,
                    dtype=np.int64)
        else:
            self._columns = self._COLUMN_CONSTRUCTOR(columns)

        if own_index or (hasattr(index, STATIC_ATTR) and index.STATIC):
            self._index = index
        elif index is None or (hasattr(index, '__len__') and len(index) == 0):
            row_count = 0 if row_count is None else row_count
            self._index = Index(range(row_count),
                    loc_is_iloc=True,
                    dtype=np.int64)
        else:
            self._index = Index(index)

        # permit bypassing this check if the

        if blocks_constructor:
            row_count = self._index.__len__()
            col_count = self._columns.__len__()
            blocks_constructor((row_count, col_count))

        if row_count and len(self._index) != row_count:
            # row count might be 0 for an empty DF
            raise RuntimeError(
                    'Index has incorrect size (got {}, expected {})'.format(
                    len(self._index), row_count))
        if len(self._columns) != col_count:
            raise RuntimeError(
                    'Columns has incorrect size (got {}, expected {})'.format(
                    len(self._columns), col_count))

    #---------------------------------------------------------------------------
    # name interface

    @property
    def name(self) -> tp.Hashable:
        return self._name

    def rename(self, name: tp.Hashable) -> 'Frame':
        '''
        Return a new Frame with an updated name attribute.
        '''
        # copying blocks does not copy underlying data
        return self.__class__(self._blocks.copy(),
                index=self._index,
                columns=self._columns, # let constructor handle if GO
                name=name,
                own_data=True,
                own_index=True)

    #---------------------------------------------------------------------------
    # interfaces

    @property
    def loc(self) -> GetItem:
        return GetItem(self._extract_loc)

    @property
    def iloc(self) -> GetItem:
        return GetItem(self._extract_iloc)

    @property
    def drop(self) -> InterfaceSelection2D:
        return InterfaceSelection2D(
            func_iloc=self._drop_iloc,
            func_loc=self._drop_loc,
            func_getitem=self._drop_getitem)

    @property
    def mask(self) -> InterfaceSelection2D:
        return InterfaceSelection2D(
            func_iloc=self._extract_iloc_mask,
            func_loc=self._extract_loc_mask,
            func_getitem=self._extract_getitem_mask)

    @property
    def masked_array(self) -> InterfaceSelection2D:
        return InterfaceSelection2D(
            func_iloc=self._extract_iloc_masked_array,
            func_loc=self._extract_loc_masked_array,
            func_getitem=self._extract_getitem_masked_array)

    @property
    def assign(self) -> InterfaceSelection2D:
        return InterfaceSelection2D(
            func_iloc=self._extract_iloc_assign,
            func_loc=self._extract_loc_assign,
            func_getitem=self._extract_getitem_assign)

    @property
    def astype(self) -> InterfaceAsType:
        return InterfaceAsType(func_getitem=self._extract_getitem_astype)

    # generators
    @property
    def iter_array(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_array,
            function_items=self._axis_array_items,
            yield_type=IterNodeType.VALUES
            )

    @property
    def iter_array_items(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_array,
            function_items=self._axis_array_items,
            yield_type=IterNodeType.ITEMS
            )

    @property
    def iter_tuple(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_tuple,
            function_items=self._axis_tuple_items,
            yield_type=IterNodeType.VALUES
            )

    @property
    def iter_tuple_items(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_tuple,
            function_items=self._axis_tuple_items,
            yield_type=IterNodeType.ITEMS
            )

    @property
    def iter_series(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_series,
            function_items=self._axis_series_items,
            yield_type=IterNodeType.VALUES
            )

    @property
    def iter_series_items(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_series,
            function_items=self._axis_series_items,
            yield_type=IterNodeType.ITEMS
            )

    @property
    def iter_group(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_group_loc,
            function_items=self._axis_group_loc_items,
            yield_type=IterNodeType.VALUES
            )

    @property
    def iter_group_items(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_group_loc,
            function_items=self._axis_group_loc_items,
            yield_type=IterNodeType.ITEMS
            )

    @property
    def iter_group_index(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_group_index,
            function_items=self._axis_group_index_items,
            yield_type=IterNodeType.VALUES
            )

    @property
    def iter_group_index_items(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._axis_group_index,
            function_items=self._axis_group_index_items,
            yield_type=IterNodeType.ITEMS
            )


    @property
    def iter_element(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._iter_element_loc,
            function_items=self._iter_element_loc_items,
            yield_type=IterNodeType.VALUES,
            apply_type=IterNodeApplyType.FRAME_ELEMENTS
            )

    @property
    def iter_element_items(self) -> IterNode:
        return IterNode(
            container=self,
            function_values=self._iter_element_loc,
            function_items=self._iter_element_loc_items,
            yield_type=IterNodeType.ITEMS,
            apply_type=IterNodeApplyType.FRAME_ELEMENTS
            )

    #---------------------------------------------------------------------------
    # index manipulation

    def _reindex_other_like_iloc(self,
            value: tp.Union[Series, 'Frame'],
            iloc_key: GetItemKeyTypeCompound,
            fill_value=np.nan
            ) -> 'Frame':
        '''Given a value that is a Series or Frame, reindex it to the index components, drawn from this Frame, that are specified by the iloc_key.
        '''
        if isinstance(iloc_key, tuple):
            row_key, column_key = iloc_key
        else:
            row_key, column_key = iloc_key, None

        # within this frame, get Index objects by extracting based on passed-in iloc keys
        nm_row, nm_column = self._extract_axis_not_multi(row_key, column_key)
        v = None

        if nm_row and not nm_column:
            # only column is multi selection, reindex by column
            if isinstance(value, Series):
                v = value.reindex(self._columns._extract_iloc(column_key),
                        fill_value=fill_value)
        elif not nm_row and nm_column:
            # only row is multi selection, reindex by index
            if isinstance(value, Series):
                v = value.reindex(self._index._extract_iloc(row_key),
                        fill_value=fill_value)
        elif not nm_row and not nm_column:
            # both multi, must be a Frame
            if isinstance(value, Frame):
                target_column_index = self._columns._extract_iloc(column_key)
                target_row_index = self._index._extract_iloc(row_key)
                # this will use the default fillna type, which may or may not be what is wanted
                v = value.reindex(
                        index=target_row_index,
                        columns=target_column_index,
                        fill_value=fill_value)
        if v is None:
            raise Exception(('cannot assign '
                    + value.__class__.__name__
                    + ' with key configuration'), (nm_row, nm_column))
        return v


    def reindex(self,
            index: tp.Union[Index, tp.Sequence[tp.Any]] = None,
            columns: tp.Union[Index, tp.Sequence[tp.Any]] = None,
            fill_value=np.nan) -> 'Frame':
        '''
        Return a new Frame based on the passed index and/or columns.
        '''
        if index is None and columns is None:
            raise Exception('must specify one of index or columns')


        if index is not None:
            if isinstance(index, (Index, IndexHierarchy)):
                # always use the Index constructor for safe reuse when possible
                index = index.__class__(index)
            else: # create the Index if not already an index, assume 1D
                index = Index(index)
            index_ic = IndexCorrespondence.from_correspondence(self._index, index)
        else:
            index = self._index
            index_ic = None

        if columns is not None:
            if isinstance(columns, (Index, IndexHierarchy)):
                # always use the Index constructor for safe reuse when possible
                if columns.STATIC != self._COLUMN_CONSTRUCTOR.STATIC:
                    raise Exception('static status of index does not match expected column static status')
                columns = columns.__class__(columns)
            else: # create the Index if not already an columns, assume 1D
                columns = self._COLUMN_CONSTRUCTOR(columns)
            columns_ic = IndexCorrespondence.from_correspondence(self._columns, columns)
        else:
            columns = self._columns
            columns_ic = None

        return self.__class__(
                TypeBlocks.from_blocks(self._blocks.resize_blocks(
                        index_ic=index_ic,
                        columns_ic=columns_ic,
                        fill_value=fill_value)),
                index=index,
                columns=columns,
                name=self._name,
                own_data=True)


    def relabel(self,
            index: CallableOrMapping = None,
            columns: CallableOrMapping = None) -> 'Frame':
        '''
        Return a new Frame based on a mapping (or callable) from old to new index values.
        '''
        # create new index objects in both cases so as to call with own*
        index = self._index.relabel(index) if index else self._index.copy()
        columns = self._columns.relabel(columns) if columns else self._columns.copy()

        return self.__class__(
                self._blocks.copy(), # does not copy arrays
                index=index,
                columns=columns,
                name=self._name,
                own_data=True,
                own_index=True,
                own_columns=True)


    def reindex_flat(self,
            index: bool = False,
            columns: bool = False) -> 'Frame':
        '''
        Return a new Frame, where an ``IndexHierarchy`` defined on the index or columns is replaced with a flat, one-dimension index of tuples.
        '''

        index = self._index.flat() if index else self._index.copy()
        columns = self._columns.flat() if columns else self._columns.copy()

        return self.__class__(
                self._blocks.copy(), # does not copy arrays
                index=index,
                columns=columns,
                name=self._name,
                own_data=True,
                own_index=True,
                own_columns=True)

    def reindex_add_level(self,
            index: tp.Hashable = None,
            columns: tp.Hashable = None) -> 'Frame':
        '''
        Return a new Frame, adding a new root level to the ``IndexHierarchy`` defined on the index or columns.
        '''

        index = self._index.add_level(index) if index else self._index.copy()
        columns = self._columns.add_level(columns) if columns else self._columns.copy()

        return self.__class__(
                self._blocks.copy(), # does not copy arrays
                index=index,
                columns=columns,
                name=self._name,
                own_data=True,
                own_index=True,
                own_columns=True)

    @doc_inject(selector='reindex')
    def reindex_drop_level(self,
            index: int = 0,
            columns: int = 0
            ) -> 'Frame':
        '''
        Return a new Frame, dropping one or more levels from the ``IndexHierarchy`` defined on the index or columns. {count}
        '''

        index = self._index.drop_level(index) if index else self._index.copy()
        columns = self._columns.drop_level(columns) if columns else self._columns.copy()

        return self.__class__(
                self._blocks.copy(), # does not copy arrays
                index=index,
                columns=columns,
                name=self._name,
                own_data=True,
                own_index=True,
                own_columns=True)


    #---------------------------------------------------------------------------
    # na handling

    def isna(self) -> 'Frame':
        '''
        Return a same-indexed, Boolean Frame indicating True which values are NaN or None.
        '''
        # always return a Frame, even if this is a FrameGO
        return Frame(self._blocks.isna(),
                index=self._index,
                columns=self._columns,
                own_data=True)


    def notna(self) -> 'Frame':
        '''
        Return a same-indexed, Boolean Frame indicating True which values are not NaN or None.
        '''
        # always return a Frame, even if this is a FrameGO
        return Frame(self._blocks.notna(),
                index=self._index,
                columns=self._columns,
                own_data=True)

    def dropna(self,
            axis: int = 0,
            condition: tp.Callable[[np.ndarray], bool] = np.all) -> 'Frame':
        '''
        Return a new Frame after removing rows (axis 0) or columns (axis 1) where condition is True, where condition is an NumPy ufunc that process the Boolean array returned by isna().
        '''
        # returns Boolean areas that define axis to keep
        row_key, column_key = self._blocks.dropna_to_keep_locations(
                axis=axis,
                condition=condition)

        # NOTE: if not values to drop and this is a Frame (not a FrameGO) we can return self as it is immutable
        if self.__class__ is Frame:
            if (row_key is not None and column_key is not None
                    and row_key.all() and column_key.all()):
                return self
        return self._extract(row_key, column_key)

    def fillna(self, value) -> 'Frame':
        '''Return a new Frame after replacing NaN or None values with the supplied value.
        '''
        return self.__class__(self._blocks.fillna(value),
                index=self._index,
                columns=self._columns,
                name=self._name,
                own_data=True)



    def fillna_leading(self,
            value: tp.Any,
            *,
            axis: int = 0):
        '''
        Return a new ``Frame`` after filling leading (and only leading) null (NaN or None) with the supplied value.
        '''
        return self.__class__(self._blocks.fillna_leading(value, axis=axis),
                index=self._index,
                columns=self._columns,
                name=self._name,
                own_data=True)


    def fillna_trailing(self,
            value: tp.Any,
            *,
            axis: int = 0):
        '''
        Return a new ``Frame`` after filling trailing (and only trailing) null (NaN or None) with the supplied value.
        '''
        return self.__class__(self._blocks.fillna_trailing(value, axis=axis),
                index=self._index,
                columns=self._columns,
                name=self._name,
                own_data=True)


    #---------------------------------------------------------------------------

    def __len__(self) -> int:
        '''Length of rows in values.
        '''
        return self._blocks._shape[0]

    def display(self,
            config: tp.Optional[DisplayConfig] = None
            ) -> Display:
        config = config or DisplayActive.get()

        # create an empty display, then populate with index
        d = Display([[]],
                config=config,
                outermost=True,
                index_depth=self._index.depth,
                columns_depth=self._columns.depth + 2)

        display_index = self._index.display(config=config)
        d.extend_display(display_index)

        if self._blocks._shape[1] > config.display_columns:
            # columns as they will look after application of truncation and insertion of ellipsis
            # get target column count in the absence of meta data, subtracting 2
            data_half_count = Display.truncate_half_count(
                    config.display_columns - Display.DATA_MARGINS)

            column_gen = partial(_gen_skip_middle,
                    forward_iter=partial(self._blocks.axis_values, axis=0),
                    forward_count=data_half_count,
                    reverse_iter=partial(self._blocks.axis_values, axis=0, reverse=True),
                    reverse_count=data_half_count,
                    center_sentinel=Display.ELLIPSIS_CENTER_SENTINEL
                    )
        else:
            column_gen = partial(self._blocks.axis_values, axis=0)

        for column in column_gen():
            if column is Display.ELLIPSIS_CENTER_SENTINEL:
                d.extend_ellipsis()
            else:
                d.extend_iterable(column, header='')

        config_transpose = config.to_transpose()
        display_cls = Display.from_values((),
                header=DisplayHeader(self.__class__, self._name),
                config=config_transpose)

        # need to apply the column config such that it truncates it based on the the max columns, not the max rows
        display_columns = self._columns.display(
                config=config_transpose)

        # add spacers for a wide index
        for _ in range(self._index.depth - 1):
            # will need a width equal to the column depth
            row = [Display.to_cell('', config=config)
                    for _ in range(self._columns.depth)]
            spacer = Display([row])
            display_columns.insert_displays(spacer,
                    insert_index=1) # after the first, the name

        if self._columns.depth > 1:
            display_columns_horizontal = display_columns.transform()
        else: # can just flatten a single column into one row
            display_columns_horizontal = display_columns.flatten()

        d.insert_displays(
                display_cls.flatten(),
                display_columns_horizontal,
                )
        return d

    def __repr__(self) -> str:
        return repr(self.display())

    def _repr_html_(self):
        '''
        Provide HTML representation for Jupyter Notebooks.
        '''
        # modify the active display to be fore HTML
        config = DisplayActive.get(
                display_format=DisplayFormats.HTML_TABLE,
                type_show=False
                )
        return repr(self.display(config))

    #---------------------------------------------------------------------------
    # accessors

    @property
    def values(self) -> np.ndarray:
        return self._blocks.values

    @property
    def index(self) -> Index:
        return self._index

    @property
    def columns(self) -> Index:
        return self._columns

    #---------------------------------------------------------------------------
    # common attributes from the numpy array

    @property
    def dtypes(self) -> Series:
        '''
        Return a Series of dytpes for each realizable column.

        Returns:
            :py:class:`static_frame.Series`
        '''
        return Series(self._blocks.dtypes, index=self._columns.values)

    @property
    def mloc(self) -> np.ndarray:
        '''Return an immutable ndarray of NP array memory location integers.
        '''
        return self._blocks.mloc

    #---------------------------------------------------------------------------

    @property
    def shape(self) -> tp.Tuple[int, int]:
        '''
        Return a tuple describing the shape of the underlying NumPy array.

        Returns:
            :py:class:`tp.Tuple[int]`
        '''
        return self._blocks._shape

    @property
    def ndim(self) -> int:
        '''
        Return the number of dimensions, which for a `Frame` is always 2.

        Returns:
            :py:class:`int`
        '''
        return self._blocks.ndim

    @property
    def size(self) -> int:
        '''
        Return the size of the underlying NumPy array.

        Returns:
            :py:class:`int`
        '''

        return self._blocks.size

    @property
    def nbytes(self) -> int:
        '''
        Return the total bytes of the underlying NumPy array.

        Returns:
            :py:class:`int`
        '''
        return self._blocks.nbytes

    #---------------------------------------------------------------------------
    @staticmethod
    def _extract_axis_not_multi(row_key, column_key) -> tp.Tuple[bool, bool]:
        '''
        If either row or column is given with a non-multiple type of selection (a single scalar), reduce dimensionality.
        '''
        row_nm = False
        column_nm = False
        if row_key is not None and not isinstance(row_key, KEY_MULTIPLE_TYPES):
            row_nm = True # axis 0
        if column_key is not None and not isinstance(column_key, KEY_MULTIPLE_TYPES):
            column_nm = True # axis 1
        return row_nm, column_nm


    def _extract(self,
            row_key: GetItemKeyType = None,
            column_key: GetItemKeyType = None) -> tp.Union['Frame', Series]:
        '''
        Extract based on iloc selection (indices have already mapped)
        '''
        blocks = self._blocks._extract(row_key=row_key, column_key=column_key)

        if not isinstance(blocks, TypeBlocks):
            return blocks # reduced to an element

        own_index = True # the extracted Frame can always own this index
        row_key_is_slice = isinstance(row_key, slice)
        if row_key is None or (row_key_is_slice and row_key == NULL_SLICE):
            index = self._index
        else:
            index = self._index._extract_iloc(row_key)
            if not row_key_is_slice:
                name_row = self._index.values[row_key]
                if self._index.depth > 1:
                    name_row = tuple(name_row)

        # can only own columns if _COLUMN_CONSTRUCTOR is static
        column_key_is_slice = isinstance(column_key, slice)
        if column_key is None or (column_key_is_slice and column_key == NULL_SLICE):
            columns = self._columns
            own_columns = self._COLUMN_CONSTRUCTOR.STATIC
        else:
            columns = self._columns._extract_iloc(column_key)
            own_columns = True
            if not column_key_is_slice:
                name_column = self._columns.values[column_key]
                if self._columns.depth > 1:
                    name_column = tuple(name_column)

        axis_nm = self._extract_axis_not_multi(row_key, column_key)

        if blocks._shape == (1, 1):
            # if TypeBlocks did not return an element, need to determine which axis to use for Series index
            if axis_nm[0]: # if row not multi
                return Series(blocks.values[0],
                        index=immutable_index_filter(columns),
                        name=name_row)
            elif axis_nm[1]:
                return Series(blocks.values[0],
                        index=index,
                        name=name_column)
            # if both are multi, we return a Frame
        elif blocks._shape[0] == 1: # if one row
            if axis_nm[0]: # if row key not multi
                # best to use blocks.values, as will need to consolidate dtypes; will always return a 2D array
                return Series(blocks.values[0],
                        index=immutable_index_filter(columns),
                        name=name_row)
        elif blocks._shape[1] == 1: # if one column
            if axis_nm[1]: # if column key is not multi
                return Series(
                        column_1d_filter(blocks._blocks[0]),
                        index=index,
                        name=name_column)

        return self.__class__(blocks,
                index=index,
                columns=columns,
                name=self._name,
                own_data=True, # always get new TypeBlock instance above
                own_index=own_index,
                own_columns=own_columns
                )


    def _extract_iloc(self, key: GetItemKeyTypeCompound) -> 'Frame':
        '''
        Give a compound key, return a new Frame. This method simply handles the variabiliyt of single or compound selectors.
        '''
        if isinstance(key, tuple):
            return self._extract(*key)
        return self._extract(row_key=key)

    def _compound_loc_to_iloc(self,
            key: GetItemKeyTypeCompound) -> tp.Tuple[GetItemKeyType, GetItemKeyType]:
        '''
        Given a compound iloc key, return a tuple of row, column keys. Assumes the first argument is always a row extractor.
        '''
        if isinstance(key, tuple):
            loc_row_key, loc_column_key = key
            iloc_column_key = self._columns.loc_to_iloc(loc_column_key)
        else:
            loc_row_key = key
            iloc_column_key = None

        iloc_row_key = self._index.loc_to_iloc(loc_row_key)
        return iloc_row_key, iloc_column_key

    def _compound_loc_to_getitem_iloc(self,
            key: GetItemKeyTypeCompound) -> tp.Tuple[GetItemKeyType, GetItemKeyType]:
        '''Handle a potentially compound key in the style of __getitem__. This will raise an appropriate exception if a two argument loc-style call is attempted.
        '''
        if isinstance(key, tuple):
            raise KeyError('__getitem__ does not support multiple indexers')
        iloc_column_key = self._columns.loc_to_iloc(key)
        return None, iloc_column_key

    def _extract_loc(self, key: GetItemKeyTypeCompound) -> 'Frame':
        iloc_row_key, iloc_column_key = self._compound_loc_to_iloc(key)
        return self._extract(row_key=iloc_row_key,
                column_key=iloc_column_key)

    def __getitem__(self, key: GetItemKeyType):
        return self._extract(*self._compound_loc_to_getitem_iloc(key))

    #---------------------------------------------------------------------------

    def _drop_iloc(self, key: GetItemKeyTypeCompound) -> 'Frame':
        '''
        Args:
            key: If a Boolean Series was passed, it has been converted to Boolean NumPy array already in loc to iloc.
        '''

        blocks = self._blocks.drop(key)

        if isinstance(key, tuple):
            iloc_row_key, iloc_column_key = key

            index = self._index._drop_iloc(iloc_row_key)
            own_index = True

            columns = self._columns._drop_iloc(iloc_column_key)
            own_columns = True
        else:
            iloc_row_key = key # no column selection

            index = self._index._drop_iloc(iloc_row_key)
            own_index = True

            columns = self._columns
            own_columns = False

        return self.__class__(blocks,
                columns=columns,
                index=index,
                name=self._name,
                own_data=True,
                own_columns=own_columns,
                own_index=own_index
                )

    def _drop_loc(self, key: GetItemKeyTypeCompound) -> 'Frame':
        key = self._compound_loc_to_iloc(key)
        return self._drop_iloc(key=key)

    def _drop_getitem(self, key: GetItemKeyTypeCompound) -> 'Frame':
        key = self._compound_loc_to_getitem_iloc(key)
        return self._drop_iloc(key=key)


    #---------------------------------------------------------------------------
    def _extract_iloc_mask(self, key: GetItemKeyTypeCompound) -> 'Frame':
        masked_blocks = self._blocks.extract_iloc_mask(key)
        return self.__class__(masked_blocks,
                columns=self._columns,
                index=self._index,
                own_data=True)

    def _extract_loc_mask(self, key: GetItemKeyTypeCompound) -> 'Frame':
        key = self._compound_loc_to_iloc(key)
        return self._extract_iloc_mask(key=key)

    def _extract_getitem_mask(self, key: GetItemKeyTypeCompound) -> 'Frame':
        key = self._compound_loc_to_getitem_iloc(key)
        return self._extract_iloc_mask(key=key)

    #---------------------------------------------------------------------------
    def _extract_iloc_masked_array(self, key: GetItemKeyTypeCompound) -> MaskedArray:
        masked_blocks = self._blocks.extract_iloc_mask(key)
        return MaskedArray(data=self.values, mask=masked_blocks.values)

    def _extract_loc_masked_array(self, key: GetItemKeyTypeCompound) -> MaskedArray:
        key = self._compound_loc_to_iloc(key)
        return self._extract_iloc_masked_array(key=key)

    def _extract_getitem_masked_array(self, key: GetItemKeyTypeCompound) -> 'Frame':
        key = self._compound_loc_to_getitem_iloc(key)
        return self._extract_iloc_masked_array(key=key)

    #---------------------------------------------------------------------------
    def _extract_iloc_assign(self, key: GetItemKeyTypeCompound) -> 'FrameAssign':
        return FrameAssign(self, iloc_key=key)

    def _extract_loc_assign(self, key: GetItemKeyTypeCompound) -> 'FrameAssign':
        # extract if tuple, then pack back again
        key = self._compound_loc_to_iloc(key)
        return self._extract_iloc_assign(key=key)

    def _extract_getitem_assign(self, key: GetItemKeyTypeCompound) -> 'FrameAssign':
        # extract if tuple, then pack back again
        key = self._compound_loc_to_getitem_iloc(key)
        return self._extract_iloc_assign(key=key)


    #---------------------------------------------------------------------------

    def _extract_getitem_astype(self, key: GetItemKeyType) -> 'FrameAsType':
        # extract if tuple, then pack back again
        _, key = self._compound_loc_to_getitem_iloc(key)
        return FrameAsType(self, column_key=key)



    #---------------------------------------------------------------------------
    # dictionary-like interface

    def keys(self):
        '''Iterator of column labels.
        '''
        return self._columns

    def __iter__(self):
        '''
        Iterator of column labels, same as :py:meth:`Frame.keys`.
        '''
        return self._columns.__iter__()

    def __contains__(self, value) -> bool:
        '''
        Inclusion of value in column labels.
        '''
        return self._columns.__contains__(value)

    def items(self) -> tp.Generator[tp.Tuple[tp.Any, Series], None, None]:
        '''Iterator of pairs of column label and corresponding column :py:class:`Series`.
        '''
        return zip(self._columns.values,
                (Series(v, index=self._index) for v in self._blocks.axis_values(0)))

    def get(self, key, default=None):
        '''
        Return the value found at the columns key, else the default if the key is not found. This method is implemented to complete the dictionary-like interface.
        '''
        if key not in self._columns:
            return default
        return self.__getitem__(key)


    #---------------------------------------------------------------------------
    # operator functions

    def _ufunc_unary_operator(self, operator: tp.Callable) -> 'Frame':
        # call the unary operator on _blocks
        return self.__class__(
                self._blocks._ufunc_unary_operator(operator=operator),
                index=self._index,
                columns=self._columns)

    def _ufunc_binary_operator(self, *, operator, other):
        if isinstance(other, Frame):
            # reindex both dimensions to union indices
            columns = self._columns.union(other._columns)
            index = self._index.union(other._index)
            self_tb = self.reindex(columns=columns, index=index)._blocks
            other_tb = other.reindex(columns=columns, index=index)._blocks
            return self.__class__(self_tb._ufunc_binary_operator(
                    operator=operator, other=other_tb),
                    index=index,
                    columns=columns,
                    own_data=True
                    )
        elif isinstance(other, Series):
            columns = self._columns.union(other._index)
            self_tb = self.reindex(columns=columns)._blocks
            other_array = other.reindex(columns).values
            return self.__class__(self_tb._ufunc_binary_operator(
                    operator=operator, other=other_array),
                    index=self._index,
                    columns=columns,
                    own_data=True
                    )
        # handle single values and lists that can be converted to appropriate arrays
        if not isinstance(other, np.ndarray) and hasattr(other, '__iter__'):
            other = np.array(other)
        # assume we will keep dimensionality
        return self.__class__(self._blocks._ufunc_binary_operator(
                operator=operator, other=other),
                index=self._index,
                columns=self._columns,
                own_data=True
                )

    #---------------------------------------------------------------------------
    # axis functions

    def _ufunc_axis_skipna(self, *,
            axis,
            skipna,
            ufunc,
            ufunc_skipna,
            dtype):
        # axis 0 sums ros, deliveres column index
        # axis 1 sums cols, delivers row index
        assert axis < 2

        # TODO: need to handle replacing None with nan in object blocks!
        if skipna:
            post = self._blocks.block_apply_axis(ufunc_skipna, axis=axis, dtype=dtype)
        else:
            post = self._blocks.block_apply_axis(ufunc, axis=axis, dtype=dtype)
        # post has been made immutable so Series will own
        if axis == 0:
            return Series(post, index=immutable_index_filter(self._columns))
        return Series(post, index=self._index)

    #---------------------------------------------------------------------------
    # axis iterators
    # NOTE: if there is more than one argument, the axis argument needs to be key-word only

    def _axis_array(self, axis):
        '''Generator of arrays across an axis
        '''
        yield from self._blocks.axis_values(axis)

    def _axis_array_items(self, axis):
        keys = self._index if axis == 1 else self._columns
        yield from zip(keys, self._blocks.axis_values(axis))


    def _axis_tuple(self, axis):
        '''Generator of named tuples across an axis.

        Args:
            axis: 0 iterates over columns (index axis), 1 iterates over rows (column axis)
        '''
        if axis == 1:
            Tuple = namedtuple('Axis', self._columns.values)
        elif axis == 0:
            Tuple = namedtuple('Axis', self._index.values)
        else:
            raise NotImplementedError()

        for axis_values in self._blocks.axis_values(axis):
            yield Tuple(*axis_values)

    def _axis_tuple_items(self, axis):
        keys = self._index if axis == 1 else self._columns
        yield from zip(keys, self._axis_tuple(axis=axis))


    def _axis_series(self, axis):
        '''Generator of Series across an axis
        '''
        if axis == 1:
            index = self._columns.values
        elif axis == 0:
            index = self._index
        for axis_values in self._blocks.axis_values(axis):
            yield Series(axis_values, index=index)

    def _axis_series_items(self, axis):
        keys = self._index if axis == 1 else self._columns
        yield from zip(keys, self._axis_series(axis=axis))


    #---------------------------------------------------------------------------
    # grouping methods naturally return their "index" as the group element

    def _axis_group_iloc_items(self, key, *, axis):

        for group, selection, tb in self._blocks.group(axis=axis, key=key):
            if axis == 0:
                # axis 0 is a row iter, so need to slice index, keep columns
                yield group, self.__class__(tb,
                        index=self._index[selection],
                        columns=self._columns, # let constructor determine ownership
                        own_index=True,
                        own_data=True)
            elif axis == 1:
                # axis 1 is a column iterators, so need to slice columns, keep index
                yield group, self.__class__(tb,
                        index=self._index,
                        columns=self._columns[selection],
                        own_index=True,
                        own_columns=True,
                        own_data=True)
            else:
                raise NotImplementedError()

    def _axis_group_loc_items(self, key, *, axis=0):
        if axis == 0: # row iterator, selecting columns for group by
            key = self._columns.loc_to_iloc(key)
        elif axis == 1: # column iterator, selecting rows for group by
            key = self._index.loc_to_iloc(key)
        else:
            raise NotImplementedError()
        yield from self._axis_group_iloc_items(key=key, axis=axis)

    def _axis_group_loc(self, key, *, axis=0):
        yield from (x for _, x in self._axis_group_loc_items(key=key, axis=axis))



    def _axis_group_index_items(self,
            depth_level: DepthLevelSpecifier = 0,
            *,
            axis=0):

        if axis == 0: # maintain columns, group by index
            ref_index = self._index
        elif axis == 1: # maintain index, group by columns
            ref_index = self._columns
        else:
            raise NotImplementedError()

        values = ref_index.values_at_depth(depth_level)
        group_to_tuple = values.ndim > 1

        groups, locations = _array_to_groups_and_locations(values)

        for idx, group in enumerate(groups):
            selection = locations == idx

            if axis == 0:
                # axis 0 is a row iter, so need to slice index, keep columns
                tb = self._blocks._extract(row_key=selection)
                yield group, self.__class__(tb,
                        index=self._index[selection],
                        columns=self._columns, # let constructor determine ownership
                        own_index=True,
                        own_data=True)

            elif axis == 1:
                # axis 1 is a column iterators, so need to slice columns, keep index
                tb = self._blocks._extract(column_key=selection)
                yield group, self.__class__(tb,
                        index=self._index,
                        columns=self._columns[selection],
                        own_index=True,
                        own_columns=True,
                        own_data=True)
            else:
                raise NotImplementedError()

    def _axis_group_index(self,
            depth_level: DepthLevelSpecifier = 0,
            *,
            axis=0):
        yield from (x for _, x in self._axis_group_index_items(
                depth_level=depth_level, axis=axis))


    #---------------------------------------------------------------------------

    def _iter_element_iloc_items(self):
        yield from self._blocks.element_items()

    def _iter_element_iloc(self):
        yield from (x for _, x in self._iter_element_iloc_items())

    def _iter_element_loc_items(self) -> tp.Iterator[
            tp.Tuple[tp.Tuple[tp.Hashable, tp.Hashable], tp.Any]]:
        '''
        Generator of pairs of (index, column), value.
        '''
        yield from (
                ((self._index[k[0]], self._columns[k[1]]), v)
                for k, v in self._blocks.element_items()
                )

    def _iter_element_loc(self):
        yield from (x for _, x in self._iter_element_loc_items())


    #---------------------------------------------------------------------------
    # transformations resulting in the same dimensionality

    def __reversed__(self) -> tp.Iterator[tp.Hashable]:
        '''
        Returns a reverse iterator on the frame's columns.
        '''
        return reversed(self._columns)

    def sort_index(self,
            ascending: bool = True,
            kind: str = DEFAULT_SORT_KIND) -> 'Frame':
        '''
        Return a new Frame ordered by the sorted Index.
        '''
        # argsort lets us do the sort once and reuse the results
        order = np.argsort(self._index.values, kind=kind)
        if not ascending:
            order = order[::-1]

        index_values = self._index.values[order]
        index_values.flags.writeable = False
        blocks = self._blocks.iloc[order]
        return self.__class__(blocks,
                index=index_values,
                columns=self._columns,
                own_data=True,
                name=self._name)

    def sort_columns(self,
            ascending: bool = True,
            kind: str = DEFAULT_SORT_KIND) -> 'Frame':
        '''
        Return a new Frame ordered by the sorted Columns.
        '''
        # argsort lets us do the sort once and reuse the results
        order = np.argsort(self._columns.values, kind=kind)
        if not ascending:
            order = order[::-1]

        columns_values = self._columns.values[order]
        columns_values.flags.writeable = False
        blocks = self._blocks[order]
        return self.__class__(blocks,
                index=self._index,
                columns=columns_values,
                own_data=True,
                name=self._name)

    def sort_values(self,
            key: KeyOrKeys,
            ascending: bool = True,
            axis: int = 1,
            kind=DEFAULT_SORT_KIND) -> 'Frame':
        '''
        Return a new Frame ordered by the sorted values, where values is given by single column or iterable of columns.

        Args:
            key: a key or tuple of keys. Presently a list is not supported.
        '''
        # argsort lets us do the sort once and reuse the results
        if axis == 0: # get a column ordering based on one or more rows
            col_count = self._columns.__len__()
            if key in self._index:
                iloc_key = self._index.loc_to_iloc(key)
                sort_array = self._blocks._extract_array(row_key=iloc_key)
                order = np.argsort(sort_array, kind=kind)
            else: # assume an iterable of keys
                # order so that highest priority is last
                iloc_keys = (self._index.loc_to_iloc(key) for key in reversed(key))
                sort_array = [self._blocks._extract_array(row_key=key)
                        for key in iloc_keys]
                order = np.lexsort(sort_array)
        elif axis == 1: # get a row ordering based on one or more columns
            if key in self._columns:
                iloc_key = self._columns.loc_to_iloc(key)
                sort_array = self._blocks._extract_array(column_key=iloc_key)
                order = np.argsort(sort_array, kind=kind)
            else: # assume an iterable of keys
                # order so that highest priority is last
                iloc_keys = (self._columns.loc_to_iloc(key) for key in reversed(key))
                sort_array = [self._blocks._extract_array(column_key=key)
                        for key in iloc_keys]
                order = np.lexsort(sort_array)
        else:
            raise NotImplementedError()


        if not ascending:
            order = order[::-1]

        if axis == 0:
            column_values = self._columns.values[order]
            column_values.flags.writeable = False
            blocks = self._blocks[order]
            return self.__class__(blocks,
                    index=self._index,
                    columns=column_values,
                    own_data=True,
                    name=self._name)

        index_values = self._index.values[order]
        index_values.flags.writeable = False
        blocks = self._blocks.iloc[order]
        return self.__class__(blocks,
                index=index_values,
                columns=self._columns,
                own_data=True,
                name=self._name)

    def isin(self, other) -> 'Frame':
        '''
        Return a same-sized Boolean Frame that shows if the same-positioned element is in the iterable passed to the function.
        '''
        # cannot use assume_unique because do not know if values is unique
        v, _ = iterable_to_array(other)
        # TODO: is it faster to do this at the block level and return blocks?
        array = np.isin(self.values, v)
        array.flags.writeable = False
        return self.__class__(array, columns=self._columns, index=self._index)

    @doc_inject(class_name='Frame')
    def clip(self,
            lower=None,
            upper=None,
            axis: tp.Optional[int] = None):
        '''{}

        Args:
            lower: value, ``Series``, ``Frame``
            upper: value, ``Series``, ``Frame``
            axis: required if ``lower`` or ``upper`` are given as a ``Series``.
        '''
        args = [lower, upper]
        for idx, arg in enumerate(args):
            bound = -np.inf if idx == 0 else np.inf
            if isinstance(arg, Series):
                if axis is None:
                    raise RuntimeError('cannot use a Series argument without specifying an axis')
                target = self._index if axis == 0 else self._columns
                values = arg.reindex(target).fillna(bound).values
                if axis == 0: # duplicate the same column over the width
                    args[idx] = np.vstack([values] * self.shape[1]).T
                else:
                    args[idx] = np.vstack([values] * self.shape[0])
            elif isinstance(arg, Frame):
                args[idx] = arg.reindex(
                        index=self._index,
                        columns=self._columns).fillna(bound).values
            elif hasattr(arg, '__iter__'):
                raise RuntimeError('only Series or Frame are supported as iterable lower/upper arguments')
            # assume single value otherwise, no change necessary

        array = np.clip(self.values, *args)
        array.flags.writeable = False
        return self.__class__(array,
                columns=self._columns,
                index=self._index)


    def transpose(self) -> 'Frame':
        '''Return a tansposed version of the Frame.
        '''
        return self.__class__(self._blocks.transpose(),
                index=self._columns,
                columns=self._index,
                own_data=True,
                name=self.name)

    @property
    def T(self) -> 'Frame':
        return self.transpose()


    def duplicated(self,
            axis=0,
            exclude_first=False,
            exclude_last=False) -> 'Series':
        '''
        Return an axis-sized Boolean Series that shows True for all rows (axis 0) or columns (axis 1) duplicated.
        '''
        # NOTE: can avoid calling .vaalues with extensions to TypeBlocks
        duplicates = _array_to_duplicated(self.values,
                axis=axis,
                exclude_first=exclude_first,
                exclude_last=exclude_last)
        duplicates.flags.writeable = False
        if axis == 0: # index is index
            return Series(duplicates, index=self._index)
        return Series(duplicates, index=self._columns)

    def drop_duplicated(self,
            axis=0,
            exclude_first: bool = False,
            exclude_last: bool = False
            ) -> 'Frame':
        '''
        Return a Frame with duplicated values removed.
        '''
        # NOTE: can avoid calling .vaalues with extensions to TypeBlocks
        duplicates = _array_to_duplicated(self.values,
                axis=axis,
                exclude_first=exclude_first,
                exclude_last=exclude_last)

        if not duplicates.any():
            return self

        keep = ~duplicates
        if axis == 0: # return rows with index indexed
            return self.__class__(self.values[keep],
                    index=self._index[keep],
                    columns=self._columns)
        return self.__class__(self.values[:, keep],
                index=self._index,
                columns=self._columns[keep])

    def set_index(self,
            column: GetItemKeyType,
            *,
            drop: bool = False,
            index_constructor=Index) -> 'Frame':
        '''
        Return a new frame produced by setting the given column as the index, optionally removing that column from the new Frame.
        '''
        column_iloc = self._columns.loc_to_iloc(column)

        if drop:
            blocks = TypeBlocks.from_blocks(
                    self._blocks._drop_blocks(column_key=column_iloc))
            columns = self._columns._drop_iloc(column_iloc)
            own_data = True
            own_columns = True
        else:
            blocks = self._blocks
            columns = self._columns
            own_data = False
            own_columns = False

        index_values = self._blocks._extract_array(column_key=column_iloc)
        index = index_constructor(index_values, name=column)

        return self.__class__(blocks,
                columns=columns,
                index=index,
                own_data=own_data,
                own_columns=own_columns,
                own_index=True
                )

    def set_index_hierarchy(self,
            columns: GetItemKeyType,
            drop: bool = False
            ) -> 'Frame':
        '''
        Given an iterable of column labels, return a new ``Frame`` with those columns as an ``IndexHierarchy`` on the index.

        Args:
            columns: Iterable of column labels.
            drop: Boolean to determine if selected columns should be removed from the data.

        Returns:
            :py:class:`IndexHierarchy`
        '''

        # columns cannot be a tuple
        if isinstance(columns, tuple):
            column_loc = list(columns)
            column_name = columns
        else:
            column_loc = columns
            column_name = None # could be a slice, must get post iloc conversion

        column_iloc = self._columns.loc_to_iloc(column_loc)

        if column_name is None:
            column_name = tuple(self._columns.values[column_iloc])

        if drop:
            blocks = TypeBlocks.from_blocks(
                    self._blocks._drop_blocks(column_key=column_iloc))
            columns = self._columns._drop_iloc(column_iloc)
            own_data = True
            own_columns = True
        else:
            blocks = self._blocks
            columns = self._columns
            own_data = False
            own_columns = False

        index_labels = self._blocks._extract_array(column_key=column_iloc)
        # index is always immutable
        index = IndexHierarchy.from_labels(index_labels, name=column_name)

        return self.__class__(blocks,
                columns=columns,
                index=index,
                own_data=own_data,
                own_columns=own_columns,
                own_index=True
                )

    def roll(self,
            index: int = 0,
            columns: int = 0,
            include_index: bool = False,
            include_columns: bool = False) -> 'Frame':
        '''
        Args:
            include_index: Determine if index is included in index-wise rotation.
            include_columns: Determine if column index is included in index-wise rotation.
        '''
        shift_index = index
        shift_column = columns

        blocks = TypeBlocks.from_blocks(
                self._blocks._shift_blocks(
                row_shift=shift_index,
                column_shift=shift_column,
                wrap=True
                ))

        if include_index:
            index = self._index.roll(shift_index)
            own_index = True
        else:
            index = self._index
            own_index = False

        if include_columns:
            columns = self._columns.roll(shift_column)
            own_columns = True
        else:
            columns = self._columns
            own_columns = False

        return self.__class__(blocks,
                columns=columns,
                index=index,
                name=self._name,
                own_data=True,
                own_columns=own_columns,
                own_index=own_index,
                )

    def shift(self,
            index: int = 0,
            columns: int = 0,
            fill_value=np.nan) -> 'Frame':

        shift_index = index
        shift_column = columns

        blocks = TypeBlocks.from_blocks(
                self._blocks._shift_blocks(
                row_shift=shift_index,
                column_shift=shift_column,
                wrap=False,
                fill_value=fill_value
                ))

        return self.__class__(blocks,
                columns=self._columns,
                index=self._index,
                name=self._name,
                own_data=True,
                )

    #---------------------------------------------------------------------------
    # transformations resulting in reduced dimensionality

    def head(self, count: int = 5) -> 'Frame':
        '''Return a Frame consisting only of the top rows as specified by ``count``.
        '''
        return self.iloc[:count]

    def tail(self, count: int = 5) -> 'Frame':
        '''Return a Frame consisting only of the bottom rows as specified by ``count``.
        '''
        return self.iloc[-count:]


    #---------------------------------------------------------------------------
    # utility function to numpy array

    def unique(self, axis: tp.Optional[int] = None) -> np.ndarray:
        '''
        Return a NumPy array of unqiue values. If the axis argument is provied, uniqueness is determined by columns or row.
        '''
        return ufunc_unique(self.values, axis=axis)

    #---------------------------------------------------------------------------
    # exporters

    def to_pairs(self, axis) -> tp.Iterable[
            tp.Tuple[tp.Hashable, tp.Iterable[tp.Tuple[tp.Hashable, tp.Any]]]]:
        '''
        Return a tuple of major axis key, minor axis key vlaue pairs, where major axis is determined by the axis argument.
        '''
        # TODO: find a common interfave on IndexHierarchy that cna give hashables
        if isinstance(self._index, IndexHierarchy):
            index_values = list(array2d_to_tuples(self._index.values))
        else:
            index_values = self._index.values

        if isinstance(self._columns, IndexHierarchy):
            columns_values = list(array2d_to_tuples(self._columns.values))
        else:
            columns_values = self._columns.values

        if axis == 1:
            major = index_values
            minor = columns_values
        elif axis == 0:
            major = columns_values
            minor = index_values
        else:
            raise NotImplementedError()

        return tuple(
                zip(major, (tuple(zip(minor, v))
                for v in self._blocks.axis_values(axis))))

    def to_pandas(self):
        '''
        Return a Pandas DataFrame.
        '''
        import pandas
        df = pandas.DataFrame(self.values.copy(),
                index=self._index.to_pandas(),
                columns=self._columns.to_pandas(),
                )
        if 'name' not in df.columns and self._name is not None:
            df.name = self._name
        return df

    def to_frame_go(self):
        '''
        Return a FrameGO view of this Frame. As underlying data is immutable, this is a no-copy operation.
        '''
        # copying blocks does not copy underlying data
        return FrameGO(self._blocks.copy(),
                index=self.index,
                columns=self.columns.values, # NOTE: does not support IndexHierarchy
                name=self._name,
                own_data=True,
                own_index=True,
                own_columns=False # need to make grow only
                )

    def to_csv(self,
            fp: FilePathOrFileLike,
            sep: str = ',',
            include_index: bool = True,
            include_columns: bool = True,
            encoding: tp.Optional[str] = None,
            line_terminator: str = '\n'
            ):
        '''
        Given a file path or file-like object, write the Frame as delimited text.
        '''
        # to_str = str

        if isinstance(fp, str):
            f = open(fp, 'w', encoding=encoding)
            is_file = True
        else:
            f = fp # assume an open file like
            is_file = False
        try:
            if include_columns:
                if include_index:
                    if self._index.name is not None:
                        f.write(f'{self._index.name}{sep}')
                    else:
                        f.write(f'index{sep}')
                # iter directly over columns in case it is an IndexGO and needs to update cache
                f.write(sep.join(f'{x}' for x in self._columns))
                f.write(line_terminator)

            col_idx_last = self._blocks._shape[1] - 1
            # avoid row creation to avoid joining types; avoide creating a list for each row
            row_current_idx = None
            for (row_idx, col_idx), element in self._iter_element_iloc_items():
                if row_idx != row_current_idx:
                    if row_current_idx is not None:
                        f.write(line_terminator)
                    if include_index:
                        f.write(f'{self._index._labels[row_idx]}{sep}')
                        # f.write(to_str(self._index._labels[row_idx]) + sep)
                    row_current_idx = row_idx
                # f.write(to_str(element))
                f.write(f'{element}')
                if col_idx != col_idx_last:
                    f.write(sep)
            # not sure if we need a final line terminator
        except:
            raise
        finally:
            if is_file:
                f.close()
        if is_file:
            f.close()

    def to_tsv(self,
            fp: FilePathOrFileLike, **kwargs):
        '''
        Given a file path or file-like object, write the Frame as tab-delimited text.
        '''
        return self.to_csv(fp=fp, sep='\t', **kwargs)

    @doc_inject(class_name='Frame')
    def to_html(self,
            config: tp.Optional[DisplayConfig] = None
            ):
        '''
        {}
        '''
        # if a config is given, try to use all settings; if using active, hide types
        config = config or DisplayActive.get(type_show=False)
        config = config.to_display_config(
                display_format=DisplayFormats.HTML_TABLE,
                )
        return repr(self.display(config))

    @doc_inject(class_name='Frame')
    def to_html_datatables(self,
            fp: tp.Optional[FilePathOrFileLike] = None,
            show: bool = True,
            config: tp.Optional[DisplayConfig] = None
            ) -> str:
        '''
        {}
        '''
        config = config or DisplayActive.get(type_show=False)
        config = config.to_display_config(
                display_format=DisplayFormats.HTML_DATATABLES,
                )
        content = repr(self.display(config))
        fp = write_optional_file(content=content, fp=fp)

        if show:
            import webbrowser
            webbrowser.open_new_tab(fp)
        return fp

class FrameGO(Frame):
    '''A two-dimensional, ordered, labelled collection, immutable with grow-only columns. Initialization arguments are the same as for :py:class:`Frame`.
    '''

    __slots__ = (
            '_blocks',
            '_columns',
            '_index',
            '_name'
            )

    _COLUMN_CONSTRUCTOR = IndexGO


    def __setitem__(self,
            key: tp.Hashable,
            value,
            fill_value=np.nan):
        '''For adding a single column, one column at a time.
        '''
        # TODO: support assignment from iterables of keys, values?

        if key in self._columns:
            raise RuntimeError('key already defined in columns; use .assign to get new Frame')

        row_count = len(self._index)

        if isinstance(value, Series):
            # TODO: performance test if it is faster to compare indices and not call reindex() if we can avoid it?
            # select only the values matching our index
            self._blocks.append(
                    value.reindex(
                    self.index, fill_value=fill_value).values)
        elif isinstance(value, np.ndarray): # is numpy array
            # this permits unaligned assignment as no index is used, possibly remove
            if value.ndim != 1 or len(value) != row_count:
                # block may have zero shape if created without columns
                raise RuntimeError('incorrectly sized, unindexed value')
            self._blocks.append(value)
        else:
            if isinstance(value, GeneratorType):
                value = np.array(tuple(value))
            elif not hasattr(value, '__len__') or isinstance(value, str):
                value = np.full(row_count, value)
            else:
                # for now, we assume all values make sense to convert to NP array
                value = np.array(value)
                if value.ndim != 1 or len(value) != row_count:
                    raise RuntimeError('incorrectly sized, unindexed value')

            value.flags.writeable = False
            self._blocks.append(value)

        # this might fail if key is a sequence
        self._columns.append(key)


    def extend_items(self,
            pairs: tp.Iterable[tp.Tuple[tp.Hashable, Series]],
            fill_value=np.nan):
        '''
        Given an iterable of pairs of column name, column value, extend this FrameGO.
        '''
        for k, v in pairs:
            self.__setitem__(k, v, fill_value)


    def extend(self,
            container: tp.Union['Frame', Series],
            fill_value=np.nan
            ):
        '''Extend this FrameGO (in-place) with another Frame's blocks or Series array; as blocks are immutable, this is a no-copy operation when indices align. If indices do not align, the passed-in Frame or Series will be reindexed (as happens when adding a column to a FrameGO).

        If a Series is passed in, the column name will be taken from the Series ``name`` attribute.

        This method differs from FrameGO.extend_items() by permitting contiguous underlying blocks to be extended from another Frame into this Frame.
        '''

        if not len(container.index): # must be empty data, empty index container
            return

        # self's index will never change; we only take what aligns in the passed container
        if _requires_reindex(self._index, container._index):
            container = container.reindex(self._index, fill_value=fill_value)

        if isinstance(container, Frame):
            if not len(container.columns):
                return
            self._columns.extend(container.keys())
            self._blocks.extend(container._blocks)
        elif isinstance(container, Series):
            self._columns.append(container.name)
            self._blocks.append(container.values)
        else:
            raise NotImplementedError(
                    'no support for extending with %s' % type(container))

        if len(self._columns) != self._blocks._shape[1]:
            raise RuntimeError('malformed Frame was used in extension')


    #---------------------------------------------------------------------------
    def to_frame(self):
        '''
        Return Frame version of this Frame.
        '''
        # copying blocks does not copy underlying data
        return Frame(self._blocks.copy(),
                index=self.index,
                columns=self.columns.values,
                name=self._name,
                own_data=True,
                own_index=True,
                own_columns=False # need to make static only
                )


    def to_frame_go(self):
        '''
        Return a FrameGO version of this Frame.
        '''
        raise NotImplementedError('Already a FrameGO')


#-------------------------------------------------------------------------------
# utility delegates returned from selection routines and exposing the __call__ interface.

class FrameAssign:
    __slots__ = ('container', 'iloc_key',)

    def __init__(self,
            container: Frame,
            iloc_key: GetItemKeyTypeCompound
            ) -> None:
        # NOTE: the stored container reference here migth be best as weak reference
        self.container = container
        self.iloc_key = iloc_key

    def __call__(self, value, fill_value=np.nan) -> 'Frame':
        if isinstance(value, (Series, Frame)):
            value = self.container._reindex_other_like_iloc(value,
                    self.iloc_key,
                    fill_value=fill_value).values

        blocks = self.container._blocks.extract_iloc_assign(self.iloc_key, value)
        # can own the newly created block given by extract
        # pass Index objects unchanged, so as to let types be handled elsewhere
        return self.container.__class__(
                data=blocks,
                columns=self.container.columns,
                index=self.container.index,
                name=self.container._name,
                own_data=True)


class FrameAsType:
    '''
    The object returned from the getitem selector, exposing the functional (__call__) interface to pass in the dtype, as well as (optionally) whether blocks are consolidated.
    '''
    __slots__ = ('container', 'column_key',)

    def __init__(self,
            container: Frame,
            column_key: GetItemKeyType
            ) -> None:
        self.container = container
        self.column_key = column_key

    def __call__(self, dtype, consolidate_blocks: bool = True) -> 'Frame':

        blocks = self.container._blocks._astype_blocks(self.column_key, dtype)

        if consolidate_blocks:
            blocks = TypeBlocks.consolidate_blocks(blocks)

        blocks = TypeBlocks.from_blocks(blocks)

        return self.container.__class__(
                data=blocks,
                columns=self.container.columns,
                index=self.container.index,
                name=self.container._name,
                own_data=True)





