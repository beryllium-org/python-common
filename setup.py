from setuptools import setup, find_packages

setup(
    name="beryllium",
    version="1.11.0",
    packages=find_packages(),
    install_requires=["pyrunning", "pysetting", "pyalpm"],
    description="Common python functions used in Beryllium applications",
    author="Bill Sideris",
    author_email="bill88t@feline.gr",
    url="https://github.com/beryllium-org/python-common",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.12",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Natural Language :: English",
    ],
    project_urls={
        "Source": "https://github.com/beryllium-org/python-common",
        "Issues": "https://github.com/beryllium-org/python-common/issues",
    },
    python_requires=">=3.12",
)
