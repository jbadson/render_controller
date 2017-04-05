from setuptools import setup

setup(name='rendercontroller',
    version='0.5.0',
    description='A network rendering manager for Blender and Terragen',
    url='https://github.com/jbadson/render_controller',
    author='James Adson',
    license='GPLv3',
    packages=['rendercontroller'],
    install_requires=['pyyaml', 'tkinter'],
    data_files=[
        ('/etc/rendercontroller', ['conf/server.conf', 'conf/gui.conf']),
        ('/var/log/rendercontroller', []),
        ('/var/run/rendercontroller', []),
    ],
    entry_points={
        'console_scripts': [ ]
    },
    setup_requires=[],
    tests_require=[],
)
