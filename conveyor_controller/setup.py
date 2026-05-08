from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'conveyor_controller'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='aes',
    maintainer_email='aes@todo.todo',
    description='ROS 2 serial bridge for controlling an Arduino UNO conveyor stepper motor.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'conveyor_serial_node = conveyor_controller.conveyor_serial_node:main',
        ],
    },
)
