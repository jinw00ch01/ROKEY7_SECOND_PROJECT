from setuptools import find_packages, setup

package_name = 'cobot_policy'

setup(
    name=package_name,
    version='0.0.1',
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
    description='Policy selector for cobot sorting tasks',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'policy_selector = cobot_policy.policy_selector_node:main',
        ],
    },
)
