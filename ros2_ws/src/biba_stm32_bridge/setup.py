from setuptools import find_packages, setup

package_name = "biba_stm32_bridge"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="BiBa maintainers",
    maintainer_email="dev@biba.local",
    description="SPI ↔ ROS2 bridge поверх biba-controller/stm32_link/.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "biba_stm32_bridge_node = biba_stm32_bridge.bridge_node:main",
        ],
    },
)
