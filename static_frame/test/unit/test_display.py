from itertools import zip_longest
from itertools import combinations
import unittest
from collections import OrderedDict
from io import StringIO
import string
import hashlib
import json
import sys


import numpy as np
import pytest

from static_frame.test.test_case import TestCase
from static_frame.test.test_case import skip_win

import static_frame as sf
# assuming located in the same directory
from static_frame import Index
from static_frame import IndexGO
from static_frame import Series
from static_frame import Frame
from static_frame import FrameGO
from static_frame import TypeBlocks
from static_frame import Display
from static_frame import mloc
from static_frame import DisplayConfig
from static_frame import DisplayConfigs
from static_frame import DisplayFormats

from static_frame.core.util import _isna
from static_frame.core.util import resolve_dtype
from static_frame.core.util import resolve_dtype_iter
from static_frame.core.util import _array_to_duplicated

from static_frame.core.display import DisplayTypeCategoryFactory

from static_frame.core.operator_delegate import _all
from static_frame.core.operator_delegate import _any
from static_frame.core.operator_delegate import _nanall
from static_frame.core.operator_delegate import _nanany

nan = np.nan

LONG_SAMPLE_STR = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.'


class TestUnit(TestCase):

    #---------------------------------------------------------------------------
    # display tests

    def test_display_config_a(self):
        config = DisplayConfig.from_default(type_color=False)
        d = Display.from_values(np.array([[1, 2], [3, 4]], dtype=np.int64), 'header', config=config)
        self.assertEqual(d.to_rows(),
                ['header', '1 2', '3 4', '<int64>'])

    def test_display_config_b(self):
        post = sf.DisplayConfig.from_default(cell_align_left=False)

        self.assertFalse(post.cell_align_left)



    def test_display_config_c(self):
        config_right = sf.DisplayConfig.from_default(cell_align_left=False)
        config_left = sf.DisplayConfig.from_default(cell_align_left=True)

        msg = config_right.to_json()



    def test_display_cell_align_left_a(self):
        config_right = sf.DisplayConfig.from_default(cell_align_left=False, type_color=False)
        config_left = sf.DisplayConfig.from_default(cell_align_left=True, type_color=False)

        index = Index((x for x in 'abc'))

        self.assertEqual(index.display(config=config_left).to_rows(),
                ['<Index>', 'a', 'b', 'c', '<object>'])

        self.assertEqual(
                index.display(config=config_right).to_rows(),
                [' <Index>', '       a', '       b', '       c', '<object>'])




    @skip_win
    def test_display_cell_align_left_b(self):
        config_right = sf.DisplayConfig.from_default(cell_align_left=False, type_color=False)
        config_left = sf.DisplayConfig.from_default(cell_align_left=True, type_color=False)

        s = Series(range(3), index=('a', 'b', 'c'), dtype=np.int64)

        self.assertEqual(s.display(config_right).to_rows(),
                ['<Series>', ' <Index>', '       a       0', '       b       1', '       c       2', '   <<U1> <int64>']
                )

        self.assertEqual(s.display(config_left).to_rows(),
                ['<Series>', '<Index>', 'a        0', 'b        1', 'c        2', '<<U1>    <int64>'])

        records = (
                (2, 2, 'a', False, False),
                (30, 34, 'b', True, False),
                (2, 95, 'c', False, False),
                )

        f1 = Frame.from_records(records,
                columns=('p', 'q', 'r', 's', 't'),
                index=('w', 'x', 'y'))

        self.assertEqual(f1.display(config_left).to_rows(),
                ['<Frame>',
                '<Index> p       q       r     s      t      <<U1>',
                '<Index>',
                'w       2       2       a     False  False',
                'x       30      34      b     True   False',
                'y       2       95      c     False  False',
                '<<U1>   <int64> <int64> <<U1> <bool> <bool>'])

        self.assertEqual(f1.display(config_right).to_rows(),
                ['<Frame>',
                '<Index>       p       q     r      s      t <<U1>',
                '<Index>',
                '      w       2       2     a  False  False',
                '      x      30      34     b   True  False',
                '      y       2      95     c  False  False',
                '  <<U1> <int64> <int64> <<U1> <bool> <bool>'])


    @skip_win
    def test_display_type_show_a(self):
        config_type_show_true = sf.DisplayConfig.from_default(type_show=True, type_color=False)
        config_type_show_false = sf.DisplayConfig.from_default(type_show=False, type_color=False)

        records = (
                    (2, 2, 'a', False, False),
                (30, 34, 'b', True, False),
                (2, 95, 'c', False, False),
                )

        f1 = Frame.from_records(records,
                columns=('p', 'q', 'r', 's', 't'),
                index=('w', 'x', 'y'))

        self.assertEqual(f1.display(config_type_show_false).to_rows(),
                ['<Frame>',
                '<Index> p  q  r s     t',
                '<Index>',
                'w       2  2  a False False',
                'x       30 34 b True  False',
                'y       2  95 c False False',
                ])

        self.assertEqual(f1.display(config_type_show_true).to_rows(),
                ['<Frame>',
                '<Index> p       q       r     s      t      <<U1>',
                '<Index>',
                'w       2       2       a     False  False',
                'x       30      34      b     True   False',
                'y       2       95      c     False  False',
                '<<U1>   <int64> <int64> <<U1> <bool> <bool>'])



    @skip_win
    def test_display_cell_fill_width_a(self):

        config_width_12 = sf.DisplayConfig.from_default(cell_max_width=12, cell_max_width_leftmost=12, type_color=False)
        config_width_6 = sf.DisplayConfig.from_default(cell_max_width=6, cell_max_width_leftmost=6, type_color=False)

        def chunks(size, count):
            pos = 0
            for _ in range(count):
                yield LONG_SAMPLE_STR[pos: pos + size]
                pos = pos + size

        s = Series(chunks(20, 3), index=('a', 'b', 'c'))


        self.assertEqual(s.display(config=config_width_12).to_rows(),
                [
                '<Series>',
                '<Index>',
                'a        Lorem ips...',
                'b        t amet, c...',
                'c        adipiscin...',
                '<<U1>    <<U20>'])

        self.assertEqual(s.display(config=config_width_6).to_rows(),
                [
                '<Se...',
                '<In...',
                'a      Lor...',
                'b      t a...',
                'c      adi...',
                '<<U1>  <<U20>']
                )

        config = sf.DisplayConfig.from_default(type_color=False, cell_max_width_leftmost=20)

        row_count = 2
        index = [str(chr(x)) for x in range(97, 97+row_count)]
        f = FrameGO(index=index)

        for i in range(4):
            chunker = iter(chunks(10, row_count))
            s = Series((x for x in chunker), index=index)
            f[i] = s

        f.columns._update_array_cache()

        self.assertEqual(f.display(config=config).to_rows(),
                ['<FrameGO>',
                '<IndexGO> 0          1          2          3          <int64>',
                '<Index>',
                'a         Lorem ipsu Lorem ipsu Lorem ipsu Lorem ipsu',
                'b         m dolor si m dolor si m dolor si m dolor si',
                '<<U1>     <<U10>     <<U10>     <<U10>     <<U10>'])

        self.assertEqual(f.display(config=config_width_6).to_rows(),
                ['<Fr...',
                '<In... 0      1      2      3      <in...',
                '<In...',
                'a      Lor... Lor... Lor... Lor...',
                'b      m d... m d... m d... m d...',
                '<<U1>  <<U10> <<U10> <<U10> <<U10>']
                )


    def test_display_display_rows_a(self):

        config_rows_12 = sf.DisplayConfig.from_default(display_rows=12, type_color=False)
        config_rows_7 = sf.DisplayConfig.from_default(display_rows=7, type_color=False)

        index = list(''.join(x) for x in combinations(string.ascii_lowercase, 2))
        s = Series(range(len(index)), index=index, dtype=np.int64)


        self.assertEqual(s.display(config_rows_12).to_rows(),
                [
                '<Series>',
                '<Index>',
                'ab       0',
                'ac       1',
                'ad       2',
                'ae       3',
                '...      ...',
                'wz       321',
                'xy       322',
                'xz       323',
                'yz       324',
                '<<U2>    <int64>'])

        self.assertEqual(s.display(config_rows_7).to_rows(),
                [
                '<Series>',
                '<Index>',
                'ab       0',
                'ac       1',
                '...      ...',
                'xz       323',
                'yz       324',
                '<<U2>    <int64>'])



    @skip_win
    def test_display_display_columns_a(self):

        config_columns_8 = sf.DisplayConfig.from_default(display_columns=8, type_color=False)
        config_columns_5 = sf.DisplayConfig.from_default(display_columns=5, type_color=False)

        columns = list(''.join(x) for x in combinations(string.ascii_lowercase, 2))
        f = FrameGO(index=range(4))
        for i, col in enumerate(columns):
            f[col] = Series(i, index=range(4))

        self.assertEqual(
                f.display(config_columns_8).to_rows(),
                ['<FrameGO>',
                '<IndexGO> ab      ac      ... xz      yz      <<U2>',
                '<Index>                   ...',
                '0         0       1       ... 323     324',
                '1         0       1       ... 323     324',
                '2         0       1       ... 323     324',
                '3         0       1       ... 323     324',
                '<int64>   <int64> <int64> ... <int64> <int64>']
                )

        self.assertEqual(
                f.display(config_columns_5).to_rows(),
                ['<FrameGO>',
                '<IndexGO> ab      ... yz      <<U2>',
                '<Index>           ...',
                '0         0       ... 324',
                '1         0       ... 324',
                '2         0       ... 324',
                '3         0       ... 324',
                '<int64>   <int64> ... <int64>'])


    @skip_win
    def test_display_display_columns_b(self):

        config_columns_4 = sf.DisplayConfig.from_default(display_columns=4, type_color=False)
        config_columns_5 = sf.DisplayConfig.from_default(display_columns=5, type_color=False)

        records = (
                (2, 2, 'a', False, False),
                (30, 34, 'b', True, False),
                (2, 95, 'c', False, False),
                )

        f = Frame.from_records(records,
                columns=('p', 'q', 'r', 's', 't'),
                index=('w', 'x', 'y'))

        self.assertEqual(
                f.display(config_columns_4).to_rows(),
                ['<Frame>',
                '<Index> p       ... t      <<U1>',
                '<Index>         ...',
                'w       2       ... False',
                'x       30      ... False',
                'y       2       ... False',
                '<<U1>   <int64> ... <bool>'])

        # at one point the columns woiuld be truncated shorter than the frame when the max xolumns was the same
        self.assertEqual(
                f.display(config_columns_5).to_rows(),
                ['<Frame>',
                '<Index> p       q       r     s      t      <<U1>',
                '<Index>',
                'w       2       2       a     False  False',
                'x       30      34      b     True   False',
                'y       2       95      c     False  False',
                '<<U1>   <int64> <int64> <<U1> <bool> <bool>']
                )


    def test_display_truncate_a(self):

        config_rows_12_cols_8 = sf.DisplayConfig.from_default(display_rows=12, display_columns=8)
        config_rows_7_cols_5 = sf.DisplayConfig.from_default(display_rows=7, display_columns=5)


        size = 10000
        columns = 100
        a1 = (np.arange(size * columns)).reshape((size, columns)) * .001
        # insert random nan in very other columns
        for col in range(0, 100, 2):
            a1[:100, col] = np.nan

        index = (hashlib.sha224(str(x).encode('utf-8')).hexdigest()
                for x in range(size))
        columns = (hashlib.sha224(str(x).encode('utf-8')).hexdigest()
                for x in range(columns))

        f = Frame(a1, index=index, columns=columns)

        self.assertEqual(
                len(f.display(config_rows_12_cols_8).to_rows()), 13)

        self.assertEqual(
                len(f.display(config_rows_7_cols_5).to_rows()), 9)


    def test_display_type_attributes_a(self):

        x, z = Display.type_attributes(np.dtype('int8'), DisplayConfigs.DEFAULT)
        self.assertEqual(x, '<int8>')

    def test_display_type_attributes_b(self):

        with self.assertRaises(NotImplementedError):
            x, z = Display.type_attributes(None, DisplayConfigs.DEFAULT)


    def test_display_type_category_a(self):

        x = DisplayTypeCategoryFactory.to_category(np.dtype(int))
        self.assertEqual(x.__name__, 'DisplayTypeInt')

        x = DisplayTypeCategoryFactory.to_category(np.dtype(object))
        self.assertEqual(x.__name__, 'DisplayTypeObject')

    def test_display_type_category_b(self):
        # force getting the default
        x = DisplayTypeCategoryFactory.to_category(None)
        self.assertEqual(x.__name__, 'DisplayTypeCategory')
        self.assertTrue(x.in_category(None))

    def test_display_config_from_json_a(self):
        json_data = json.dumps(dict(type_show=False))
        dc = DisplayConfig.from_json(json_data)
        self.assertEqual(dc.type_show, False)

        # with a bad name, we filter out the key
        json_data = json.dumps(dict(show=False))
        dc = DisplayConfig.from_json(json_data)
        self.assertEqual(dc.type_show, True)

    def test_display_flatten_a(self):
        config = DisplayConfig.from_default(type_color=False)

        d1 = Display.from_values(np.array([1, 2, 3, 4], dtype=np.int64), 'header', config=config)
        self.assertEqual(d1.flatten().to_rows(), ['header 1 2 3 4 <int64>'])


        d2 = Display.from_values(np.array([5, 6, 7, 8], dtype=np.int64), 'header', config=config)

        # mutates in place
        d1.extend_display(d2)
        self.assertEqual(
                d1.to_rows(),
                ['header  header', '1       5', '2       6', '3       7', '4       8', '<int64> <int64>'])

        self.assertEqual(d1.flatten().to_rows(),
                ['header header 1 5 2 6 3 7 4 8 <int64> <int64>'])

        self.assertEqual(d1.transform().to_rows(),
                ['header 1 2 3 4 <int64>', 'header 5 6 7 8 <int64>'])


    @skip_win
    def test_display_html_pre_a(self):
        f = Frame.from_dict(dict(a=(1, 2),
                b=(1.2, 3.4),
                c=(False, True)))

        expected = f.display(sf.DisplayConfig(
                display_format='html_pre', type_color=False))

        html = '''<div style="white-space: pre; font-family: monospace">&lt;Frame&gt;
&lt;Index&gt; a       b         c      &lt;&lt;U1&gt;
&lt;Index&gt;
0       1       1.2       False
1       2       3.4       True
&lt;int64&gt; &lt;int64&gt; &lt;float64&gt; &lt;bool&gt;</div>'''

        self.assertEqual(html.strip(), str(expected).strip())


    @skip_win
    def test_display_html_table_a(self):
        f = sf.Frame.from_dict(
            dict(a=(1,2,3,4), b=(True, False, True, False), c=list('qrst')))
        f = f.set_index_hierarchy(['a', 'b'])
        f = f.reindex_add_level(columns='I')
        f = f.reindex_add_level(columns='J')

        expected = f.display(sf.DisplayConfig(
                display_format='html_table', type_color=False))
        html = '''
<table border="1"><thead><tr><th>&lt;Frame&gt;</th><th></th><th></th><th></th><th></th><th></th></tr><tr><th>&lt;IndexHierarchy&gt;</th><th></th><th>J</th><th>J</th><th>J</th><th>&lt;&lt;U1&gt;</th></tr><tr><th></th><th></th><th>I</th><th>I</th><th>I</th><th>&lt;&lt;U1&gt;</th></tr><tr><th></th><th></th><th>a</th><th>b</th><th>c</th><th>&lt;&lt;U1&gt;</th></tr><tr><th>&lt;IndexHierarchy&gt;</th><th></th><th></th><th></th><th></th><th></th></tr></thead><tbody><tr><th>1</th><th>True</th><td>1</td><td>True</td><td>q</td><td></td></tr><tr><th>2</th><th>False</th><td>2</td><td>False</td><td>r</td><td></td></tr><tr><th>3</th><th>True</th><td>3</td><td>True</td><td>s</td><td></td></tr><tr><th>4</th><th>False</th><td>4</td><td>False</td><td>t</td><td></td></tr><tr><th>&lt;object&gt;</th><th>&lt;object&gt;</th><td>&lt;int64&gt;</td><td>&lt;bool&gt;</td><td>&lt;&lt;U1&gt;</td><td></td></tr></tbody></table>
        '''

        # import ipdb; ipdb.set_trace()
        self.assertEqual(html.strip(), str(expected).strip())


    def test_display_html_table_b(self):
        records = (
                (2, 'a', False),
                (30, 'b', False),
                )
        f = Frame.from_records(records,
                columns=('p', 'q', 'r'),
                index=('w', 'x'))

        self.assertEqual(f._repr_html_(),
            '<table border="1"><thead><tr><th><span style="color: #777777">&lt;Frame&gt;</span></th><th></th><th></th><th></th></tr><tr><th><span style="color: #777777">&lt;Index&gt;</span></th><th>p</th><th>q</th><th>r</th></tr><tr><th><span style="color: #777777">&lt;Index&gt;</span></th><th></th><th></th><th></th></tr></thead><tbody><tr><th>w</th><td>2</td><td>a</td><td>False</td></tr><tr><th>x</th><td>30</td><td>b</td><td>False</td></tr></tbody></table>')


    def test_display_html_series_a(self):
        records = (
                (2, 'a', False),
                (30, 'b', False),
                )
        f = Frame.from_records(records,
                columns=('p', 'q', 'r'),
                index=('w', 'x'))
        self.assertEqual(f['q']._repr_html_(),
            '<table border="1"><thead><tr><th><span style="color: #777777">&lt;Series: q&gt;</span></th><th></th></tr><tr><th><span style="color: #777777">&lt;Index&gt;</span></th><th></th></tr></thead><tbody><tr><th>w</th><td>a</td></tr><tr><th>x</th><td>b</td></tr></tbody></table>')

    def test_display_html_index_a(self):
        records = (
                (2, 'a', False),
                (30, 'b', False),
                )
        f = Frame.from_records(records,
                columns=('p', 'q', 'r'),
                index=('w', 'x'))

        self.assertEqual(f.index._repr_html_(),
                '<table border="1"><thead><tr><th><span style="color: #777777">&lt;Index&gt;</span></th></tr></thead><tbody><tr><td>w</td></tr><tr><td>x</td></tr></tbody></table>')

        f1 = f.set_index_hierarchy(('p', 'q'))
        self.assertEqual(f1.index._repr_html_(),
                '<table border="1"><thead><tr><th><span style="color: #777777">&lt;IndexHierarchy: (&#x27;p&#x27;, &#x27;q&#x27;)&gt;</span></th><th></th></tr></thead><tbody><tr><td>2</td><td>a</td></tr><tr><td>30</td><td>b</td></tr></tbody></table>'
                )

    def test_display_html_index_b(self):
        records = (
                (2, 'a', False),
                (30, 'b', False),
                )
        f = Frame.from_records(records,
                columns=('p', 'q', 'r'),
                index=('w', 'x'))
        f = f.set_index_hierarchy(('p', 'q'))

        # this uses cell width normaliz
        post = f.display(sf.DisplayConfig(
                display_format=DisplayFormats.HTML_PRE,
                cell_max_width_leftmost=20)).to_rows()

        self.assertEqual(post[2],
                '<span style="color: #777777">&lt;IndexHierarchy: ...</span>')

        post = f.display(sf.DisplayConfig(
                display_format=DisplayFormats.HTML_PRE,
                cell_max_width_leftmost=36)).to_rows()

        self.assertEqual(post[2],
                '<span style="color: #777777">&lt;IndexHierarchy: (&#x27;p&#x27;, &#x27;q&#x27;)&gt;</span>')



    def test_display_max_width_a(self):
        records = (
                (2, 'a', False),
                (30, 'b', False),
                )
        f1 = Frame.from_records(records,
                columns=('p', 'q', 'r'),
                index=('w', 'x'))
        f2 = f1.set_index_hierarchy(('p', 'q'))

        post = f2.display(sf.DisplayConfig(type_color=False, cell_max_width_leftmost=20)).to_rows()
        self.assertEqual(post[2], '<IndexHierarchy: ...')

        post = f2.display(sf.DisplayConfig(type_color=False, cell_max_width_leftmost=30)).to_rows()
        self.assertEqual(post[2], "<IndexHierarchy: ('p', 'q')>")


    @unittest.skip('too colorful')
    def test_display_type_color_a(self):

        f = Frame(dict(a=(1, 2),
                b=(1.2, 3.4),
                c=(False, True),
                d=(object(), []),
                e=(1j, 3j),
                f=(np.datetime64('2014'), np.datetime64('2015')),
                g=(np.datetime64('2014')-np.datetime64('2015'),
                np.datetime64('2014')-np.datetime64('2015'))
                ),
                index=tuple('xy'))
        print(f)
        print(f.loc['x'])

        print(f.display(DisplayConfigs.COLOR))
        print(f.loc['x'].display(DisplayConfigs.COLOR))

        f = sf.Frame.from_dict(dict(a=(1,2,3,4), b=(True, False, True, False), c=list('qrst')))
        f = f.set_index_hierarchy(['a', 'b'])
        f = f.reindex_add_level(columns='I')
        f = f.reindex_add_level(columns='J')
        print(f)

        # columns = sf.IndexHierarchy.from_product((96361, 96345), (0, 1))
        # index = sf.IndexHierarchy.from_product((32155, 32175), (0, 4))
        # columns = range(4)
        # index = range(4)
        # f = sf.Frame.from_records(
        #     ([y for y in range(x, x + 4)] for x in range(4)),
        #     index=index, columns=columns)

        from itertools import product
        index = (0x2210, 0x2330)
        columns = (0x1, 0xe)
        f = Frame.from_element_loc_items(
                ((x, chr(sum(x))) for x in product(index, columns)),
                index=index,
                columns=columns,
                dtype=str)
        print(f)


        columns = list('abcdefgh')
        index = range(1, 9)

        f = sf.Frame(np.empty((8, 8), dtype='U1'), columns=columns, index=index)
        print(f)

        # f.display(sf.DisplayActive.get(display_format='html_datatables'))

        # f.to_html_datatables()
        columns = tuple('efgh')
        index = range(3, 0, -1)

        f = Frame.from_element_loc_items(
                (
                ((2, 'f'), chr(0x265F)), # pawn
                ((2, 'g'), chr(0x265F)),
                ((2, 'h'), chr(0x265F)),
                ((1, 'e'), chr(0x265A)), # king
                ((1, 'h'), chr(0x265C)), # rook
                ),
                index=index,
                columns=columns,
                dtype=str)

        #part of Sicilian Defense Najdorf Variation
        columns = tuple('hgfe')
        index = range(6, 9)

        f = Frame.from_element_loc_items(
                (
                ((7, 'h'), chr(0x265F)), # pawn
                ((6, 'g'), chr(0x265F)),
                ((7, 'f'), chr(0x265F)),
                ((7, 'e'), chr(0x265F)),
                ((8, 'e'), chr(0x265A)), # king
                ((7, 'g'), chr(0x265D)), # biship
                ((6, 'f'), chr(0x265E)), # horse
                ((8, 'h'), chr(0x265C)), # rook
                ),
                index=index,
                columns=columns,
                dtype=str)

        # s = Series(('', chr(0x265C), '', chr(0x265A)), index=tuple('efgh'))

        # s = Series.from_items((('f', chr(0x265C)), ('h', chr(0x265A)))).reindex(tuple('efgh'), fill_value='')

        s = Series.from_items((('f', chr(0x265C)), ('g', chr(0x265A))))

        f.assign.loc[8, :](s, fill_value='')



if __name__ == '__main__':
    unittest.main()
