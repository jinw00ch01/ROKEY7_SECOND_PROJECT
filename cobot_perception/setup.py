from setuptools import find_packages, setup

package_name = 'cobot_perception'

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
    description='Perception pipeline: hand-eye transform, depth filtering, and grasp pose generation',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'perception_transform = cobot_perception.perception_transform_node:main',
        ],
    },
)
