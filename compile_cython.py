import sys
import os
from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy

script_dir = os.path.dirname(os.path.abspath(__file__))

source_file = os.path.join(script_dir, "canvas_cython_helpers.pyx")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("No command provided, defaulting to 'build_ext --inplace'")
        sys.argv.extend(['build_ext', '--inplace'])

    setup(
        ext_modules=cythonize(
            Extension(
                "canvas_cython_helpers",
                sources=[source_file],
                include_dirs=[numpy.get_include()],
            )
        ),
    )