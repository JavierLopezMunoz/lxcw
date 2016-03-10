from setuptools import setup, find_packages

setup(
    name='lxcw',
    version='3.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'ansible',
        'Click',
    ],
    entry_points={
        'console_scripts': [
            'lxcw = lxcw.scripts.wrapper:cli',
        ]
    }
)
