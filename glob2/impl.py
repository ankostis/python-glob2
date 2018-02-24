"""Filename globbing utility."""

from __future__ import absolute_import

import os
from os.path import join
import re
import sys


try:
    from functools import lru_cache
except ImportError:
    from .compat import lru_cache

try:
    from itertools import imap
except ImportError:
    imap = map


magic_check = re.compile('[*?[]')
magic_check_bytes = re.compile(b'[*?[]')


def has_magic(s):
    if isinstance(s, bytes):
        match = magic_check_bytes.search(s)
    else:
        match = magic_check.search(s)
    return match is not None


def _ishidden(path):
    return path[0] in ('.', b'.'[0])


def _join_paths(paths, sep=None):
    path = join(*paths)
    if sep:
        path = re.sub(r'[\\/]', sep, path)  # cached internally
    return path


def translate(pat):
    """Translate a shell PATTERN to a regular expression.

    There is no way to quote meta-characters.
    """

    i, n = 0, len(pat)
    res = ''
    while i < n:
        c = pat[i]
        i = i+1
        if c == '*':
            res = res + '(.*)'
        elif c == '?':
            res = res + '(.)'
        elif c == '[':
            j = i
            if j < n and pat[j] == '!':
                j = j+1
            if j < n and pat[j] == ']':
                j = j+1
            while j < n and pat[j] != ']':
                j = j+1
            if j >= n:
                res = res + '\\['
            else:
                stuff = pat[i:j].replace('\\','\\\\')
                i = j+1
                if stuff[0] == '!':
                    stuff = '^' + stuff[1:]
                elif stuff[0] == '^':
                    stuff = '\\' + stuff
                res = '%s([%s])' % (res, stuff)
        else:
            res = res + re.escape(c)
    return res + '\Z(?ms)'


@lru_cache(maxsize=256, typed=True)
def _compile_pattern(pat, case_sensitive):
    if isinstance(pat, bytes):
        pat_str = pat.decode('ISO-8859-1')
        res_str = translate(pat_str)
        res = res_str.encode('ISO-8859-1')
    else:
        res = translate(pat)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(res, flags).match


class Globber(object):
    """
    :ivar with_matches:
        if true, then for each matching path a 2-tuple will be returned;
        the second element if the tuple will be a list of the parts
        of the path that matched the individual wildcards.
    :ivar include_hidden:
        When true, filenames starting with a dot are matched by '*' and '?'
        patterns.
    :ivar norm_paths:
        A tri-state boolean:
        when true, invokes `os.path,.normcase()` on both paths,
        when `None`, just equalize slashes/backslashes to `os.sep`,
        when false, does not touch paths at all.

        Note that a side-effect of `normcase()` on *Windows* is that
        it converts to lower-case all matches of `?glob()` functions.
    :ivar case_sensitive:
        defines the case-sensitiviness of regex doing the matches
    :ivar sep:
        in case only slahes replaced, what sep-char to substitute with;
        if false, `os.sep` is used.

    Notice that by default, `normcase()` causes insensitive matching
    on *Windows*, regardless of `case_insensitive` param.
    Set ``norm_paths=None, case_sensitive=False`` to preserve
    verbatim mathces and still behaves like Windows.
    """

    listdir = staticmethod(os.listdir)
    isdir = staticmethod(os.path.isdir)
    islink = staticmethod(os.path.islink)
    exists = staticmethod(os.path.lexists)

    def walk(self, top):
        """A simplified version of os.walk (code copied) that uses
        ``self.listdir``, and the other local filesystem methods.

        Because we don't care about file/directory distinctions, only
        a single list is returned.
        """
        try:
            names = self.listdir(top)
        except os.error as err:
            return

        items = list(names)

        yield top, items

        for name in items:
            new_path = _join_paths([top, name], sep=self.sep)
            if self.followlinks or not self.islink(new_path):
                for x in self.walk(new_path):
                    yield x


    with_matches = False
    include_hidden = False
    followlinks = False
    norm_paths = None
    case_sensitive = (os.name != 'nt')
    sep = None

    def __init__(self, **kw):
        vars(self).update(**kw)

    def filter(self, names, pat):
        """Return the subset of the list NAMES that match PAT."""
        result = []
        pat = self._norm_paths(pat)
        match = _compile_pattern(pat, self.case_sensitive)
        for name in names:
            m = match(self._norm_paths(name))
            if m:
                result.append((name,
                               tuple(self._norm_paths(p) for p in m.groups())))
        return result

    def fnmatchcase(self, name, pat):
        """Test whether FILENAME matches PATTERN, including case.

        This is a version of fnmatch() which doesn't case-normalize
        its arguments.
        """
        match = _compile_pattern(pat, self.case_sensitive)
        return match(name) is not None

    def _norm_paths(self, path):
        if self.norm_paths is None:
            path = re.sub(r'[\\/]', self.sep or os.sep , path)  # cached internally
        elif self.norm_paths:
            path = os.path.normcase(path)
        return path

    def fnmatch(self, name, pat):
        """Test whether FILENAME matches PATTERN.

        Patterns are Unix shell style:

        *       matches everything
        ?       matches any single character
        [seq]   matches any character in seq
        [!seq]  matches any char not in seq

        An initial period in FILENAME is not special.
        Both FILENAME and PATTERN are first case-normalized
        if the operating system requires it.
        If you don't want this, use fnmatchcase(FILENAME, PATTERN).

        :param slashes:
        :param norm_paths:
            A tri-state boolean:
            when true, invokes `os.path,.normcase()` on both paths,
            when `None`, just equalize slashes/backslashes to `os.sep`,
            when false, does not touch paths at all.

            Note that a side-effect of `normcase()` on *Windows* is that
            it converts to lower-case all matches of `?glob()` functions.
        :param case_sensitive:
            defines the case-sensitiviness of regex doing the matches
        :param sep:
            in case only slahes replaced, what sep-char to substitute with;
            if false, `os.sep` is used.

        Notice that by default, `normcase()` causes insensitive matching
        on *Windows*, regardless of `case_insensitive` param.
        Set ``norm_paths=None, case_sensitive=False`` to preserve
        verbatim mathces.
        """
        name, pat = [self._norm_paths(p) for p in (name, pat)]

        return self.fnmatchcase(name, pat)

    def glob(self, pathname):
        """Return a list of paths matching a pathname pattern.

        :param pathname:
            A string/byte pattern that may contain
            simple shell-style wildcards a la fnmatch.
        :return:
            strings or bytes, depending on the `patterns
        """
        return list(self.iglob(pathname))

    def iglob(self, pathname):
        """Return an iterator yielding the paths matching a pathname pattern.

        :param pathname:
            A string/byte pattern that may contain
            simple shell-style wildcards a la fnmatch.
        :return:
            strings or bytes, depending on the `patterns

        If ``with_matches`` is True, then for each matching path
        a 2-tuple will be returned; the second element if the tuple
        will be a list of the parts of the path that matched the individual
        wildcards.
        """
        result = self._iglob(pathname, True)
        if self.with_matches:
            return result
        return imap(lambda s: s[0], result)

    def _iglob(self, pathname, rootcall):
        """Internal implementation that backs :meth:`iglob`.

        ``rootcall`` is required to differentiate between the user's call to
        iglob(), and subsequent recursive calls, for the purposes of resolving
        certain special cases of ** wildcards. Specifically, "**" is supposed
        to include the current directory for purposes of globbing, but the
        directory itself should never be returned. So if ** is the lastmost
        part of the ``pathname`` given the user to the root call, we want to
        ignore the current directory. For this, we need to know which the root
        call is.
        """

        # Short-circuit if no glob magic
        if not has_magic(pathname):
            if self.exists(pathname):
                yield pathname, ()
            return

        # If no directory part is left, assume the working directory
        dirname, basename = os.path.split(pathname)

        # If the directory is globbed, recurse to resolve.
        # If at this point there is no directory part left, we simply
        # continue with dirname="", which will search the current dir.
        # `os.path.split()` returns the argument itself as a dirname if it is a
        # drive or UNC path.  Prevent an infinite recursion if a drive or UNC path
        # contains magic characters (i.e. r'\\?\C:').
        if dirname != pathname and has_magic(dirname):
            # Note that this may return files, which will be ignored
            # later when we try to use them as directories.
            # Prefiltering them here would only require more IO ops.
            dirs = self._iglob(dirname, False)
        else:
            dirs = [(dirname, ())]

        # Resolve ``basename`` expr for every directory found
        for dirname, dir_groups in dirs:
            for name, groups in self.resolve_pattern(dirname, basename, not rootcall):
                yield _join_paths([dirname, name], sep=self.sep), dir_groups + groups

    def resolve_pattern(self, dirname, pattern, globstar_with_root):
        """Apply `pattern` (contains no path elements) to the literal directory in `dirname`.

        If pattern=='', this will filter for directories. This is
        a special case that happens when the user's glob expression ends
        with a slash (in which case we only want directories). It simpler
        and faster to filter here than in :meth:`_iglob`.
        """

        if sys.version_info[0] > 2:
            if isinstance(pattern, bytes):
                dirname = dirname.encode('ASCII')
        else:
            if isinstance(pattern, unicode) and not isinstance(dirname, unicode):
                dirname = unicode(dirname, sys.getfilesystemencoding() or
                                           sys.getdefaultencoding())

        sep = self.sep

        # If no magic, short-circuit, only check for existence
        if not has_magic(pattern):
            if pattern == '':
                if self.isdir(dirname):
                    return [(pattern, ())]
            else:
                if self.exists(_join_paths([dirname, pattern], sep=sep)):
                    return [(pattern, ())]
            return []

        if not dirname:
            dirname = os.curdir

        try:
            if pattern == '**':
                # Include the current directory in **, if asked; by adding
                # an empty string as opposed to '.', we spare ourselves
                # having to deal with os.path.normpath() later.
                names = [''] if globstar_with_root else []
                for top, entries in self.walk(dirname):
                    _mkabs = lambda s: _join_paths([top[len(dirname) + 1:], s],
                                                   sep=sep)
                    names.extend(map(_mkabs, entries))
                # Reset pattern so that fnmatch(), which does not understand
                # ** specifically, will only return a single group match.
                pattern = '*'
            else:
                names = self.listdir(dirname)
        except os.error:
            return []

        if not self.include_hidden and not _ishidden(pattern):
            # Remove hidden files, but take care to ensure
            # that the empty string we may have added earlier remains.
            # Do not filter out the '' that we might have added earlier
            names = filter(lambda x: not x or not _ishidden(x), names)
        return self.filter(names, pattern)


def glob(pathname, **kw):
    """Return a list of paths matching a pathname pattern.

    :param pathname:
        A string/byte pattern that may contain
        simple shell-style wildcards a la fnmatch.
    :param with_matches:
        if true, then for each matching path a 2-tuple will be returned;
        the second element if the tuple will be a list of the parts
        of the path that matched the individual wildcards.
    :param include_hidden:
        When true, filenames starting with a dot are matched by '*' and '?'
        patterns.
    :param recursive:
        ignored, always implied; for API compatibility
    :param norm_paths:
        A tri-state boolean:
        when true, invokes `os.path,.normcase()` on both paths,
        when `None`, just equalize slashes/backslashes to `os.sep`,
        when false, does not touch paths at all.

        Note that a side-effect of `normcase()` on *Windows* is that
        it converts to lower-case all matches of `?glob()` functions.
    :param case_sensitive:
        defines the case-sensitiviness of regex doing the matches
        [default: False on Windows / True elsewhere]
    :param sep:
        in case only slahes replaced, what sep-char to substitute with;
        if false, `os.sep` is used.
    :return:
        strings or bytes, depending on the `patterns

    Notice that by default, `normcase()` causes insensitive matching
    on *Windows*, regardless of `case_insensitive` param.
    Set ``norm_paths=None, case_sensitive=False`` to preserve
    verbatim mathces.
    """
    return list(iglob(pathname, **kw))

def iglob(pathname, **kw):
    """Return an iterator yielding the paths matching a pathname pattern.

    :param pathname:
        A string/byte pattern that may contain
        simple shell-style wildcards a la fnmatch.
    :param with_matches:
        if true, then for each matching path a 2-tuple will be returned;
        the second element if the tuple will be a list of the parts
        of the path that matched the individual wildcards.
    :param include_hidden:
        When true, filenames starting with a dot are matched by '*' and '?'
        patterns.
    :param recursive:
        ignored, always implied; for API compatibility
    :param norm_paths:
        A tri-state boolean:
        when true, invokes `os.path,.normcase()` on both paths,
        when `None`, just equalize slashes/backslashes to `os.sep`,
        when false, does not touch paths at all.

        Note that a side-effect of `normcase()` on *Windows* is that
        it converts to lower-case all matches of `?glob()` functions.
    :param case_sensitive:
        defines the case-sensitiviness of regex doing the matches
    :param sep:
        in case only slahes replaced, what sep-char to substitute with;
        if false, `os.sep` is used.
    :return:
        strings or bytes, depending on the `patterns

    Notice that by default, `normcase()` causes insensitive matching
    on *Windows*, regardless of `case_insensitive` param.
    Set ``norm_paths=None, case_sensitive=False`` to preserve
    verbatim mathces.
    """
    return Globber(**kw).iglob(pathname)
