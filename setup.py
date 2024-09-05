from setuptools import setup

setup(
    name='lickRemoteObserving',
    version='1.4',    
    description='',
    url='https://github.com/bpholden/lickRemoteObserving',
    author='Brad Holden',
    author_email='holden@ucolick.org',
    license='BSD 2-clause',
    packages=['lickRemoteObserving'],
    install_requires=['python>=3.7',
                      'pyyaml',
                      'requests',
                      'packaging',                     
                      ],

    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',  
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOSX :: MacOS',         
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)