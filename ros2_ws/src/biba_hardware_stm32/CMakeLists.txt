cmake_minimum_required(VERSION 3.16)
project(biba_hardware_stm32)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

# ros2_control dependencies are required only for the (still-pending)
# pluginlib SystemInterface target. Mark them OPTIONAL so the package
# builds on dev machines without the full ros2_control stack — the
# vendored proto + Stm32Link still compile and unit-test.
find_package(hardware_interface QUIET)
find_package(pluginlib QUIET)
find_package(rclcpp QUIET)
find_package(rclcpp_lifecycle QUIET)

# Vendored wire protocol (kept byte-identical to firmware/src/proto/ via
# tests/test_biba_proto_drift.py — see proto/README.txt).
add_library(biba_proto STATIC proto/biba_proto.c)
target_include_directories(biba_proto PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/proto>
)
set_target_properties(biba_proto PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Pure-logic objects: SPI transport + Stm32Link. No rclcpp / hardware_interface
# dependency, so they build standalone and are unit-testable on any
# Linux dev box.
add_library(biba_stm32_link STATIC
  src/spi_transport.cpp
  src/stm32_link.cpp
)
target_include_directories(biba_stm32_link PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
target_link_libraries(biba_stm32_link PUBLIC biba_proto)
set_target_properties(biba_stm32_link PROPERTIES POSITION_INDEPENDENT_CODE ON)

# SystemInterface plugin — built only when the full ros2_control stack
# is available (i.e. inside the biba-ros2-control docker image). The
# package still builds standalone on dev boxes for the gtest below.
if(hardware_interface_FOUND AND pluginlib_FOUND AND rclcpp_FOUND AND rclcpp_lifecycle_FOUND)
  add_library(${PROJECT_NAME} SHARED src/biba_stm32_system.cpp)
  target_include_directories(${PROJECT_NAME} PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  target_link_libraries(${PROJECT_NAME} biba_stm32_link)
  ament_target_dependencies(${PROJECT_NAME}
    hardware_interface
    pluginlib
    rclcpp
    rclcpp_lifecycle
  )
  pluginlib_export_plugin_description_file(
    hardware_interface biba_hardware_stm32_plugin.xml)

  install(TARGETS ${PROJECT_NAME}
    EXPORT export_${PROJECT_NAME}
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
  )
  install(DIRECTORY include/ DESTINATION include)
  install(FILES biba_hardware_stm32_plugin.xml DESTINATION share/${PROJECT_NAME})

  ament_export_dependencies(
    hardware_interface
    pluginlib
    rclcpp
    rclcpp_lifecycle
  )
  ament_export_include_directories(include)
  ament_export_libraries(${PROJECT_NAME})
endif()

if(BUILD_TESTING)
  find_package(ament_lint_auto QUIET)
  if(ament_lint_auto_FOUND)
    # Skip style-only linters (uncrustify/cpplint/copyright). The package
    # is hand-formatted; functional correctness is enforced by the gtest
    # below and by tests/test_biba_proto_drift.py.
    set(ament_cmake_copyright_FOUND TRUE)
    set(ament_cmake_cpplint_FOUND TRUE)
    set(ament_cmake_uncrustify_FOUND TRUE)
    ament_lint_auto_find_test_dependencies()
  endif()

  find_package(ament_cmake_gtest QUIET)
  if(ament_cmake_gtest_FOUND)
    ament_add_gtest(test_stm32_link test/test_stm32_link.cpp)
    if(TARGET test_stm32_link)
      target_link_libraries(test_stm32_link biba_stm32_link)
    endif()
  endif()
endif()

ament_package()
