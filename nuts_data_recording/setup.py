from setuptools import find_packages, setup

package_name = 'nuts_data_recording'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(include=[
        'nuts_data_recording',
    ]),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey4090',
    maintainer_email='rokey4090@todo.todo',
    description='Data recording package for nuts calibration',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'data_recording = nuts_data_recording.data_recording:main',
        ],
    },
)
