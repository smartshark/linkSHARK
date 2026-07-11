#!/usr/bin/env python

import sys

from setuptools import setup, find_packages

if not sys.version_info[0] == 3:
    print('only python3 supported!')
    sys.exit(1)

setup(
    name='linkSHARK',
    version='2.1.1',
    description='Issue linking for smartSHARK.',
    install_requires=['mongoengine', 'pymongo', 
                      'pycoshark @ git+https://github.com/smartshark/pycoSHARK.git@2.0.0'],
    author='sherbold',
    author_email='herbold@cs.uni-goettingen.de',
    url='https://github.com/smartshark/linkSHARK',
    download_url='https://github.com/smartshark/linkSHARK/zipball/master',
    test_suite='linkSHARK.tests',
    packages=find_packages(),
    zip_safe=False,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache2.0 License",
        "Operating System :: POSIX :: Linux",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
