from setuptools import find_packages, setup
from glob import glob
import os

package_name = 'cobot_db'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'sql'), glob('sql/*.sql')),
    ],
    install_requires=[
        'setuptools',
        'supabase>=2.0',
        'python-dotenv>=1.0',
    ],
    zip_safe=True,
    maintainer='choijinwoo',
    maintainer_email='choijinwoo@todo.todo',
    description='Supabase persistence layer for cobot2 (exception logs, inventory).',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'cobot_db_example = cobot_db.integration_example:main',
        ],
    },
)
