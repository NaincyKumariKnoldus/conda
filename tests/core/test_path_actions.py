# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from logging import getLogger
from os.path import basename, isdir, join, lexists, isfile, dirname
from tempfile import gettempdir
from unittest import TestCase
from uuid import uuid4

import sys

from conda._vendor.auxlib.collection import AttrDict

from conda.common.path import get_python_site_packages_short_path, get_python_noarch_target_path, \
    get_python_short_path, pyc_path
from conda.core.path_actions import LinkPathAction, CompilePycAction
from conda.gateways.disk.create import mkdir_p, create_link
from conda.gateways.disk.delete import rm_rf
from conda.models.enums import LinkType, NoarchType
from conda.common.compat import PY2


log = getLogger(__name__)


def make_test_file(target_dir, suffix=''):
    if not isdir(target_dir):
        mkdir_p(target_dir)
    fn = str(uuid4())[:8]
    full_path = join(target_dir, fn + suffix)
    with open(full_path, 'w') as fh:
        fh.write(str(uuid4()))
    return full_path


def load_python_file(py_file_full_path):
    if PY2:
        import imp
        return imp.load_compiled("module.name", py_file_full_path)
    elif sys.version_info < (3, 5):
        raise RuntimeError("this doesn't work for .pyc files")
        from importlib.machinery import SourceFileLoader
        return SourceFileLoader("module.name", py_file_full_path).load_module()
    else:
        import importlib.util
        spec = importlib.util.spec_from_file_location("module.name", py_file_full_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class PathActionsTests(TestCase):

    def setUp(self):
        tempdirdir = gettempdir()

        prefix_dirname = str(uuid4())[:8]
        self.prefix = join(tempdirdir, prefix_dirname)
        mkdir_p(self.prefix)
        assert isdir(self.prefix)

        pkgs_dirname = str(uuid4())[:8]
        self.pkgs_dir = join(tempdirdir, pkgs_dirname)
        mkdir_p(self.pkgs_dir)
        assert isdir(self.pkgs_dir)

    def tearDown(self):
        rm_rf(self.prefix)
        assert not lexists(self.prefix)
        rm_rf(self.pkgs_dir)
        assert not lexists(self.pkgs_dir)

    def test_CompilePycAction_generic(self):
        package_info = AttrDict(package_metadata=AttrDict(noarch=AttrDict(type=NoarchType.generic)))
        noarch = package_info.package_metadata and package_info.package_metadata.noarch
        assert noarch.type == NoarchType.generic
        axns = CompilePycAction.create_actions({}, package_info, self.prefix, None, ())
        assert axns == ()

        package_info = AttrDict(package_metadata=None)
        axns = CompilePycAction.create_actions({}, package_info, self.prefix, None, ())
        assert axns == ()

    def test_CompilePycAction_noarch_python(self):
        target_python_version = '%d.%d' % sys.version_info[:2]
        sp_dir = get_python_site_packages_short_path(target_python_version)
        transaction_context = {
            'target_python_version': target_python_version,
            'target_site_packages_short_path': sp_dir,
        }
        package_info = AttrDict(package_metadata=AttrDict(noarch=AttrDict(type=NoarchType.python)))

        file_link_actions = [
            AttrDict(
                source_short_path='site-packages/something.py',
                target_short_path=get_python_noarch_target_path('site-packages/something.py', sp_dir),
            ),
            AttrDict(
                # this one shouldn't get compiled
                source_short_path='something.py',
                target_short_path=get_python_noarch_target_path('something.py', sp_dir),
            ),
        ]
        axns = CompilePycAction.create_actions(transaction_context, package_info, self.prefix,
                                               None, file_link_actions)

        assert len(axns) == 1
        axn = axns[0]
        assert axn.source_full_path == join(self.prefix, get_python_noarch_target_path('site-packages/something.py', sp_dir))
        assert axn.target_full_path == join(self.prefix, pyc_path(get_python_noarch_target_path('site-packages/something.py', sp_dir), target_python_version))

        # make .py file in prefix that will be compiled
        mkdir_p(dirname(axn.source_full_path))
        with open(axn.source_full_path, 'w') as fh:
            fh.write("value = 42\n")

        # symlink the current python
        python_full_path = join(self.prefix, get_python_short_path(target_python_version))
        mkdir_p(dirname(python_full_path))
        create_link(sys.executable, python_full_path, LinkType.softlink)

        axn.execute()
        assert isfile(axn.target_full_path)

        # remove the source .py file so we're sure we're importing the pyc file below
        rm_rf(axn.source_full_path)
        assert not isfile(axn.source_full_path)

        if (3, ) > sys.version_info >= (3, 5):
            # we're probably dropping py34 support soon enough anyway
            imported_pyc_file = load_python_file(axn.target_full_path)
            assert imported_pyc_file.value == 42

        axn.reverse()
        assert not isfile(axn.target_full_path)


    def test_CreatePythonEntryPointAction(self):
        pass







    def test_simple_LinkPathAction_hardlink(self):
        source_full_path = make_test_file(self.pkgs_dir)
        target_short_path = source_short_path = basename(source_full_path)
        axn = LinkPathAction({}, None, self.pkgs_dir, source_short_path, self.prefix,
                             target_short_path, LinkType.hardlink)

        assert axn.target_full_path == join(self.prefix, target_short_path)
        axn.verify()
        axn.execute()
        assert isfile(axn.target_full_path)
        # assert not islink(axn.target_full_path)

        axn.reverse()
        assert not lexists(axn.target_full_path)

    def test_simple_LinkPathAction_softlink(self):
        pass

    def test_simple_LinkPathAction_directory(self):
        pass

    def test_simple_LinkPathAction_copy(self):
        source_full_path = make_test_file(self.pkgs_dir)
        target_short_path = source_short_path = basename(source_full_path)
        axn = LinkPathAction({}, None, self.pkgs_dir, source_short_path, self.prefix,
                             target_short_path, LinkType.copy)

        assert axn.target_full_path == join(self.prefix, target_short_path)
        axn.verify()
        axn.execute()
        assert isfile(axn.target_full_path)
        # assert not islink(axn.target_full_path)

        axn.reverse()
        assert not lexists(axn.target_full_path)
