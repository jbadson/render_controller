from setuptools import setup

setup(name='rendercontroller',
    version='0.6.0',
    description='A network rendering manager for Blender and Terragen',
    url='https://github.com/jbadson/render_controller',
    author='James Adson',
    license='GPLv3',
    install_requires=['pyyaml'],
    packages=['rendercontroller'],
    data_files=[
        ('/etc', ['conf/rendercontroller.conf']),
    ],
    entry_points={
        'console_scripts': [
            'rcontroller = rendercontroller:main',
        ]
    },
    setup_requires=[],
    tests_require=[],
)
