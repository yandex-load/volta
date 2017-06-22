from setuptools import setup, find_packages

setup(
    name='volta',
    version='0.1.0',
    description='yandex package for mobile energy consumption measurements',
    longer_description='''
yandex package for mobile energy consumption measurements
''',
    maintainer='Alexey Lavrenuke (load testing)',
    maintainer_email='direvius@yandex-team.ru',
    url='https://github.com/yandex-load/volta',
    packages=find_packages(exclude=["tests", "tmp", "docs", "data"]),
    install_requires=[
        'tornado',
        'pandas',
        'seaborn',
        'numpy',
        'scipy',
        'matplotlib',
        'requests',
        'pyserial',
        'progressbar2',
        'pyusb',
        'pyyaml'
    ],
    setup_requires=[
        'pytest-runner',
    ],
    tests_require=[
        'pytest',
    ],
    entry_points={
        'console_scripts': [
            'volta = volta.api.cli:main',
            'volta-http = volta.api.http:main',
            'volta-uploader = volta.core.postloader:main',
        ],
    },
    license='MPLv2',
    package_data={
        'volta.phones': [
            'binary/*.apk'
        ]
    },
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)',
        'Operating System :: POSIX',
        'Topic :: Software Development :: Quality Assurance',
        'Topic :: Software Development :: Testing',
        'Topic :: Software Development :: Testing :: Traffic Generation',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
    ],
    use_2to3=True, )
