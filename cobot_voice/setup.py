from setuptools import find_packages, setup
import glob

package_name = 'cobot_voice'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/resource', glob.glob('resource/*')),
        ('share/' + package_name + '/resource', glob.glob('resource/.env')),
        ('share/' + package_name + '/config', glob.glob('config/*.json')),
    ],
    install_requires=['setuptools', 'python-dotenv'],
    zip_safe=True,
    maintainer='choijinwoo',
    maintainer_email='choijinwoo@todo.todo',
    description='Voice processing and command parsing for cobot2',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'voice_processing = cobot_voice.voice_processing_node:main',
            'command_parser = cobot_voice.command_parser_node:main',
            'firebase_state_bridge = cobot_voice.firebase_state_bridge:main',
            'voice_web_demo = cobot_voice.voice_web_demo:main',
            'web_voice_bridge_server = cobot_voice.web_voice_bridge_server:main',
        ],
    },
)
