from os.path import abspath, dirname, join, normpath

from setuptools import setup


setup(

    # Basic package information:
    name = 'pelican-entities',
    version = '0.1.0',
    py_modules = ('entities',),

    # Packaging options:
    zip_safe = False,
    include_package_data = True,

    # Package dependencies:
    install_requires = ['pelican>=3.4.0'],

    # Metadata for PyPI:
    author = 'Alexandre Fonseca',
    author_email = 'alexandrejorgefonseca@gmail.com',
    license = 'Apache',
    url = 'https://github.com/AlexJF/pelican-entities',
    keywords = 'pelican blog static generic entities',
    description = ('A generator for Pelican, allowing the use of generic '
            'entities in place of the default page and article ones'),
    long_description = open(normpath(join(dirname(abspath(__file__)),
        'README.md'))).read()
)
