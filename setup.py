#!/usr/bin/env python

from setuptools import setup
setup(
    name="relations",
    version="0.2.8",
    package_dir = {'': 'lib'},
    py_modules = [
        'relations',
        'relations.source',
        'relations.sql',
        'relations.query',
        'relations.unittest',
        'relations.field',
        'relations.model',
        'relations.record',
        'relations.relation'
    ],
    install_requires=[]
)
