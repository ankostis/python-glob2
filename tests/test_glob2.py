import os
from os import path
import shutil
import tempfile

import glob2

# Sep='/' so assertions works also on Windows.
g = glob2.Globber(with_matches=True, sep='/')

class TestFnmatch(object):

    def test_filter_everything(self):
        names = (
            'fooABC', 'barABC', 'foo',)
        assert g.filter(names, 'foo*') == [
            ('fooABC', ('ABC',)),
            ('foo', ('',))
        ]
        assert g.filter(names, '*AB*') == [
            ('fooABC', ('foo', 'C')),
            ('barABC', ('bar', 'C'))
        ]

    def test_filter_single_character(self):
        names = (
            'fooA', 'barA', 'foo',)
        assert g.filter(names, 'foo?') == [
            ('fooA', ('A',)),
        ]
        assert g.filter(names, '???A') == [
            ('fooA', ('f', 'o', 'o',)),
            ('barA', ('b', 'a', 'r',)),
        ]

    def test_sequence(self):
        names = (
            'fooA', 'fooB', 'fooC', 'foo',)
        assert g.filter(names, 'foo[AB]') == [
            ('fooA', ('A',)),
            ('fooB', ('B',)),
        ]
        assert g.filter(names, 'foo[!AB]') == [
            ('fooC', ('C',)),
        ]


class BaseTest(object):

    def setup(self):
        self.basedir = tempfile.mkdtemp()
        self._old_cwd = os.getcwd()
        os.chdir(self.basedir)

        self.setup_files()

    def setup_files(self):
        pass

    def teardown(self):
        os.chdir(self._old_cwd)
        shutil.rmtree(self.basedir)

    def makedirs(self, *names):
        for name in names:
            os.makedirs(path.join(self.basedir, name))

    def touch(self, *names):
        for name in names:
            open(path.join(self.basedir, name), 'w').close()


class TestPatterns(BaseTest):

    def test(self):
        self.makedirs('dir1', 'dir22')
        self.touch(
            'dir1/a-file', 'dir1/b-file', 'dir22/a-file', 'dir22/b-file')
        assert g.glob('dir?/a-*') == [
            ('dir1/a-file', ('1', 'file'))
        ]


class TestRecursive(BaseTest):

    def setup_files(self):
        self.makedirs('a', 'b', 'a/foo')
        self.touch('file.py', 'file.txt', 'a/bar.py', 'README', 'b/py',
                   'b/bar.py', 'a/foo/hello.py', 'a/foo/world.txt')

    def test_recursive(self):
        # ** includes the current directory
        assert sorted(g.glob('**/*.py')) == [
            ('a/bar.py', ('a', 'bar')),
            ('a/foo/hello.py', ('a/foo', 'hello')),
            ('b/bar.py', ('b', 'bar')),
            ('file.py', ('', 'file')),
        ]

    def test_exclude_root_directory(self):
        # If files from the root directory should not be included,
        # this is the syntax to use:
        assert sorted(g.glob('*/**/*.py')) == [
            ('a/bar.py', ('a', '', 'bar')),
            ('a/foo/hello.py', ('a', 'foo', 'hello')),
            ('b/bar.py', ('b', '', 'bar'))
        ]

    def test_only_directories(self):
        # Return directories only
        assert sorted(g.glob('**/')) == [
            ('a/', ('a',)),
            ('a/foo/', ('a/foo',)),
            ('b/', ('b',)),
        ]

    def test_parent_dir(self):
        # Make sure ".." can be used
        os.chdir(path.join(self.basedir, 'b'))
        assert sorted(g.glob('../a/**/*.py')), [
            ('../a/bar.py', ('', 'bar')),
            ('../a/foo/hello.py', ('foo', 'hello'))
        ]

    def test_fixed_basename(self):
        assert sorted(g.glob('**/bar.py')) == [
            ('a/bar.py', ('a',)),
            ('b/bar.py', ('b',)),
        ]

    def test_all_files(self):
        # Return all files
        os.chdir(path.join(self.basedir, 'a'))
        assert sorted(g.glob('**')) == [
            ('bar.py', ('bar.py',)),
            ('foo', ('foo',)),
            ('foo/hello.py', ('foo/hello.py',)),
            ('foo/world.txt', ('foo/world.txt',)),
        ]

    def test_root_directory_not_returned(self):
        # Ensure that a certain codepath (when the basename is globbed
        # with ** as opposed to the dirname) does not cause
        # the root directory to be part of the result.
        # -> b/ is NOT in the result!
        assert sorted(g.glob('b/**')) == [
            ('b/bar.py', ('bar.py',)),
            ('b/py', ('py',)),
        ]

    def test_non_glob(self):
        # Test without patterns.
        assert glob2.glob(__file__, with_matches=True) == [
            (__file__, ())
        ]
        assert glob2.glob(__file__) == [
            (__file__)
        ]


class TestIncludeHidden(BaseTest):

    def setup_files(self):
        self.makedirs('a', 'b', 'a/.foo')
        self.touch('file.py', 'file.txt', 'a/.bar', 'README', 'b/py',
                   'b/.bar', 'a/.foo/hello.py', 'a/.foo/world.txt')

    def test_hidden(self):
        # ** includes the current directory
        assert sorted(glob2.glob('*/*', with_matches=True, include_hidden=True, sep='/')), [
            ('a/.bar', ('a', '.bar')),
            ('a/.foo', ('a', '.foo')),
            ('b/.bar', ('b', '.bar')),
            ('b/py', ('b', 'py')),
        ]
