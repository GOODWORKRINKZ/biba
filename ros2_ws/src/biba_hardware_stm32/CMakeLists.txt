cmake_minimum_required(VERSION 3.16)
project(biba_hardware_stm32)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(hardware_interface REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)

# TODO: добавить add_library(${PROJECT_NAME} SHARED src/biba_hardware_stm32.cpp)
# и pluginlib_export_plugin_description_file, когда появится реализация
# SystemInterface. Сейчас пакет экспортирует только зависимости.

ament_export_dependencies(
  hardware_interface
  pluginlib
  rclcpp
  rclcpp_lifecycle
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
