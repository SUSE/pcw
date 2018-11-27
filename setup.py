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
            ],
        entry_points='''
            [console_scripts]
            pcw=pcw:cli
            ''',
)
