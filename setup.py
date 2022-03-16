from datetime import datetime
from setuptools import setup, find_packages

setup(
    name="memorious-dip",
    version=datetime.utcnow().date().isoformat(),
    classifiers=[],
    keywords="",
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=[],
    include_package_data=True,
    zip_safe=False,
    install_requires=["memorious", "furl", "pyicu", "regex==2022.3.2"],
)
