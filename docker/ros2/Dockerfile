# BiBa ROS2 service image — builds ros2_ws/ on top of the
# biba-ros2-control base and ships biba-controller/stm32_link/ alongside
# for the bridge node to import at runtime.
#
# Build context expected: repository root (so we can COPY both
# ros2_ws/ and biba-controller/).

ARG BASE_IMAGE=ghcr.io/goodworkrinkz/biba/biba-ros2-control
ARG BASE_TAG=latest
FROM ${BASE_IMAGE}:${BASE_TAG}

ARG DEBIAN_FRONTEND=noninteractive

# Runtime deps used by the bridge: spidev (SPI master) + numeric helpers
# already in biba-controller's requirements.txt.
COPY biba-controller/requirements.txt /tmp/biba-controller-requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/biba-controller-requirements.txt \
    && rm /tmp/biba-controller-requirements.txt

WORKDIR /opt/biba

# Vendor stm32_link/ as a Python module on PYTHONPATH. We only need the
# stm32_link sub-package; copying the whole biba-controller/ tree keeps
# imports identical to the legacy runtime ("from stm32_link.client …").
COPY biba-controller /opt/biba/biba-controller
ENV PYTHONPATH=/opt/biba/biba-controller:${PYTHONPATH}
ENV BIBA_CONTROLLER_PATH=/opt/biba/biba-controller

# Build ros2_ws/.
COPY ros2_ws /opt/biba/ros2_ws
WORKDIR /opt/biba/ros2_ws
RUN . /opt/ros/humble/setup.sh \
    && colcon build --merge-install --event-handlers console_direct+

# Source the workspace overlay on shell entry.
RUN echo "source /opt/biba/ros2_ws/install/setup.bash" >> /root/.bashrc

ENV ROS_DOMAIN_ID=42 \
    RMW_IMPLEMENTATION=rmw_zenoh_cpp

WORKDIR /opt/biba

# Default command launches the bridge node. Compose overrides this for
# robot_state_publisher / other services.
CMD ["bash", "-lc", "source /opt/ros/humble/setup.bash && source /opt/biba/ros2_ws/install/setup.bash && ros2 run biba_stm32_bridge biba_stm32_bridge_node"]
