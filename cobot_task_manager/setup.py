from setuptools import find_packages, setup

package_name = 'cobot_task_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='choijinwoo',
    maintainer_email='choijinwoo@todo.todo',
    description='Task manager for cobot pick-and-place pipeline',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'task_manager = cobot_task_manager.task_manager_node:main',
        ],
    },
)
