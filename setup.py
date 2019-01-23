from setuptools import setup, find_packages

setup(
        name='pcw',
        version='0.1',
        py_modules=['pcw', 'pcwd'],
        install_requires=[
            'Click',
            'boto3',
            'django',
            'djangorestframework',
            'django-tables2',
            'django-filters',
            'django-bootstrap3'
            ],
        entry_points='''
            [console_scripts]
            pcw=pcw:cli
            ''',
)
