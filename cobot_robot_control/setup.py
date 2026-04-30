from setuptools import find_packages, setup

package_name = 'cobot_robot_control'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='choijinwoo',
    maintainer_email='choijinwoo@todo.todo',
    description='Robot control package for Doosan cobot pick-and-place operations',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'robot_control = cobot_robot_control.robot_control_node:main',
        ],
    },
)
