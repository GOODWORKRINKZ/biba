// Copyright 2026 BiBa maintainers. MIT license.
//
// ros2_control SystemInterface for BiBa composition C. Owns
// /dev/spidev0.0 via Stm32Link, exposes two diff-drive joints
// (wheel_left_joint, wheel_right_joint) with position+velocity state
// interfaces and a velocity command interface each.
//
// Joint names follow the existing biba_description URDF macro:
//   left_wheel_joint, right_wheel_joint
//
// Wheels are brushless RC-ESC driven and have no encoders, so the read
// loop runs open-loop: it pings the STM32 to verify the link is alive
// and reports the most recently *commanded* velocity as the joint state
// while integrating it into a synthetic position. This is sufficient
// for diff_drive_controller to produce odometry that matches the
// commanded twist.
#ifndef BIBA_HARDWARE_STM32__BIBA_STM32_SYSTEM_HPP_
#define BIBA_HARDWARE_STM32__BIBA_STM32_SYSTEM_HPP_

#include <memory>
#include <string>
#include <vector>

#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_interface_return_values.hpp"
#include "rclcpp_lifecycle/state.hpp"

#include "biba_hardware_stm32/stm32_link.hpp"

namespace biba_hardware_stm32
{

class BibaStm32SystemHardware : public hardware_interface::SystemInterface
{
public:
  BibaStm32SystemHardware();

  hardware_interface::CallbackReturn on_init(
    const hardware_interface::HardwareInfo & info) override;

  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;

  hardware_interface::CallbackReturn on_activate(
    const rclcpp_lifecycle::State & previous_state) override;
  hardware_interface::CallbackReturn on_deactivate(
    const rclcpp_lifecycle::State & previous_state) override;
  hardware_interface::CallbackReturn on_shutdown(
    const rclcpp_lifecycle::State & previous_state) override;

  hardware_interface::return_type read(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;
  hardware_interface::return_type write(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

  // Test seam: replace the SPI link with a fake before on_activate.
  void set_link_for_testing(std::unique_ptr<Stm32Link> link);

private:
  static constexpr std::size_t kJointCount = 2;
  static constexpr std::size_t kLeft = 0;
  static constexpr std::size_t kRight = 1;

  // Per-joint state (rad / rad·s) and command (rad·s).
  std::array<double, kJointCount> position_state_{0.0, 0.0};
  std::array<double, kJointCount> velocity_state_{0.0, 0.0};
  std::array<double, kJointCount> velocity_command_{0.0, 0.0};

  // Hardware parameters parsed in on_init.
  std::string spi_device_;
  std::uint32_t spi_speed_hz_ = 1'000'000;
  double max_wheel_speed_rad_s_ = 20.0;  // rad/s at normalised setpoint = 1.0

  std::unique_ptr<Stm32Link> link_;
};

}  // namespace biba_hardware_stm32

#endif  // BIBA_HARDWARE_STM32__BIBA_STM32_SYSTEM_HPP_
