import os

from setuptools import setup
from setuptools import find_packages

here = os.path.abspath(os.path.dirname(__file__))
try:
    README = open(os.path.join(here, 'README.rst')).read()
except IOError:
    README = ''
try:
    CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()
except IOError:
    CHANGES = ''

version = '0.1dev'

install_requires = [
    'Kotti>=1.0.0',
]


setup(
    name='kotti_jsonapi',
    version=version,
    description="Add on for Kotti",
    long_description='\n\n'.join([README, CHANGES]),
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Framework :: Pylons",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        "License :: Public Domain",
    ],
    author='Joseph Rawson',
    author_email='joseph.rawson.works@gmail.com',
    url='https://github.com/umeboshi2/kotti_jsonapi',
    keywords='kotti web cms wcms pylons pyramid sqlalchemy bootstrap',
    license="Public Domain",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=install_requires,
    tests_require=[],
    dependency_links=[],
    extras_require={},
)
