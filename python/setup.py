import os.path
import re
from setuptools import setup


def find_version():
    path = os.path.join(os.path.dirname(__file__), "rendercontroller", "__init__.py")
    with open(path, "r") as f:
        txt = f.read()
    m = re.search('__version__ = "([0-9\.]+)"', txt)
    if m:
        return m.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name="rendercontroller",
    version=find_version(),
    description="A network rendering manager for Blender and Terragen",
    url="https://github.com/jbadson/render_controller",
    author="James Adson",
    license="GPLv3",
    install_requires=["pyyaml"],
    packages=["rendercontroller"],
    data_files=[("/etc", ["conf/rendercontroller.conf"])],
    entry_points={"console_scripts": [
        "rcontroller-server = rendercontroller:main",
        "rcontroller = rendercontroller:cli.main",
        "framechecker = rendercontroller:framechecker.main",
    ]},
    setup_requires=[],
    tests_require=[],
)
