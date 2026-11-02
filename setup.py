from setuptools import setup, find_packages

setup(
    name="database-backup-utility",
    version="1.0.0",
    description="Cross-platform CLI utility for multi-DBMS database backup, compression, cloud storage, scheduling, and restore",
    author="Database Backup Utility Team",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "click>=8.1.0",
        "rich>=13.0.0",
        "pydantic>=2.0.0",
        "pyyaml>=6.0",
        "python-dotenv>=1.0.0",
        "psutil>=5.9.0",
        "pymysql>=1.1.0",
        "psycopg2-binary>=2.9.0",
        "pymongo>=4.5.0",
        "boto3>=1.30.0",
        "zstandard>=0.21.0",
        "cryptography>=41.0.0",
        "schedule>=1.2.0",
        "requests>=2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "db-backup=backup_util.cli:main",
            "database-backup=backup_util.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Database",
        "Topic :: System :: Archiving :: Backup",
    ],
)
