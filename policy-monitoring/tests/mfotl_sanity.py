import os
from os.path import isdir
from os.path import join
from posixpath import abspath
from posixpath import dirname

from monpoly.monpoly import Monpoly
from util import docker

from .common import run_tests


def run_test():
    pwd = dirname(abspath(__file__))
    tests_dir = join(pwd, "..", "mfotl-policies")
    tests = [t for t in os.listdir(tests_dir) if isdir(join(tests_dir, t))]

    # Test that MonPoly can be run on this system via Docker
    if not docker.is_inside_docker():
        Monpoly.install_docker_image()

    # Run all tests
    run_tests(tests_dir, tests, local_sig_file=False)
    # run_tests(tests_dir, tests=["unauthorized_connections"], local_sig_file=False)


if __name__ == "__main__":
    run_test()
