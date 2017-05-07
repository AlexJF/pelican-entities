from setuptools import setup

with open('README.rst') as f:
    long_description = f.read()

version = '0.3.0'

setup(

    # Basic package information:
    name = 'pelican-entities',
    version = version,
    py_modules = ('entities',),

    # Packaging options:
    zip_safe = False,
    include_package_data = True,

    # Package dependencies:
    install_requires = ['pelican>=3.7.0'],

    # Metadata for PyPI:
    author = 'Alexandre Fonseca',
    author_email = 'alexandrejorgefonseca@gmail.com',
    license = 'Apache',
    url = 'https://github.com/AlexJF/pelican-entities',
    download_url = 'https://github.com/AlexJF/pelican-entities/archive/v{version}.zip'.format(version=version),
    keywords = 'pelican blog static generic entities',
    description = ('A generator for Pelican, allowing the use of generic '
            'entities in place of the default page and article ones'),
    long_description = long_description
)
