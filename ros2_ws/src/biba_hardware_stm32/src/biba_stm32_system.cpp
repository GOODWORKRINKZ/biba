// Copyright 2026 BiBa maintainers. MIT license.
#include "biba_hardware_stm32/biba_stm32_system.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <utility>

#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "rclcpp/rclcpp.hpp"

namespace biba_hardware_stm32
{

namespace
{
constexpr const char * kLeftJoint = "left_wheel_joint";
constexpr const char * kRightJoint = "right_wheel_joint";

double clamp_unit(double v)
{
  if (v > 1.0) {return 1.0;}
  if (v < -1.0) {return -1.0;}
  return v;
}
}  // namespace

BibaStm32SystemHardware::BibaStm32SystemHardware() = default;

void BibaStm32SystemHardware::set_link_for_testing(std::unique_ptr<Stm32Link> link)
{
  link_ = std::move(link);
}

hardware_interface::CallbackReturn BibaStm32SystemHardware::on_init(
  const hardware_interface::HardwareInfo & info)
{
  if (hardware_interface::SystemInterface::on_init(info) !=
    hardware_interface::CallbackReturn::SUCCESS)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }

  if (info.joints.size() != kJointCount) {
    RCLCPP_FATAL(
      rclcpp::get_logger("BibaStm32SystemHardware"),
      "Expected %zu joints, got %zu", kJointCount, info.joints.size());
    return hardware_interface::CallbackReturn::ERROR;
  }
  if (info.joints[kLeft].name != kLeftJoint || info.joints[kRight].name != kRightJoint) {
    RCLCPP_FATAL(
      rclcpp::get_logger("BibaStm32SystemHardware"),
      "Joint names must be [%s, %s], got [%s, %s]",
      kLeftJoint, kRightJoint,
      info.joints[kLeft].name.c_str(), info.joints[kRight].name.c_str());
    return hardware_interface::CallbackReturn::ERROR;
  }

  auto get_param = [&](const std::string & key, const std::string & fallback) {
      auto it = info.hardware_parameters.find(key);
      return it != info.hardware_parameters.end() ? it->second : fallback;
    };

  spi_device_ = get_param("spi_device", "/dev/spidev0.0");
  try {
    spi_speed_hz_ = static_cast<std::uint32_t>(
      std::stoul(get_param("spi_speed_hz", "1000000")));
    max_wheel_speed_rad_s_ = std::stod(get_param("max_wheel_speed", "20.0"));
  } catch (const std::exception & e) {
    RCLCPP_FATAL(
      rclcpp::get_logger("BibaStm32SystemHardware"),
      "Failed to parse hardware_parameters: %s", e.what());
    return hardware_interface::CallbackReturn::ERROR;
  }

  if (max_wheel_speed_rad_s_ <= 0.0) {
    RCLCPP_FATAL(
      rclcpp::get_logger("BibaStm32SystemHardware"),
      "max_wheel_speed must be > 0, got %f", max_wheel_speed_rad_s_);
    return hardware_interface::CallbackReturn::ERROR;
  }

  // Allow tests to inject a fake link before on_init by skipping
  // construction here. Production path: build the linux SPI transport.
  if (!link_) {
    auto transport = std::make_unique<SpiTransportLinux>();
    link_ = std::make_unique<Stm32Link>(std::move(transport));
  }

  return hardware_interface::CallbackReturn::SUCCESS;
}

std::vector<hardware_interface::StateInterface>
BibaStm32SystemHardware::export_state_interfaces()
{
  std::vector<hardware_interface::StateInterface> ifaces;
  for (std::size_t i = 0; i < kJointCount; ++i) {
    const auto & name = info_.joints[i].name;
    ifaces.emplace_back(
      name, hardware_interface::HW_IF_POSITION, &position_state_[i]);
    ifaces.emplace_back(
      name, hardware_interface::HW_IF_VELOCITY, &velocity_state_[i]);
  }
  return ifaces;
}

std::vector<hardware_interface::CommandInterface>
BibaStm32SystemHardware::export_command_interfaces()
{
  std::vector<hardware_interface::CommandInterface> ifaces;
  for (std::size_t i = 0; i < kJointCount; ++i) {
    ifaces.emplace_back(
      info_.joints[i].name, hardware_interface::HW_IF_VELOCITY,
      &velocity_command_[i]);
  }
  return ifaces;
}

hardware_interface::CallbackReturn BibaStm32SystemHardware::on_activate(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  position_state_ = {0.0, 0.0};
  velocity_state_ = {0.0, 0.0};
  velocity_command_ = {0.0, 0.0};

  SpiConfig cfg;
  cfg.device = spi_device_;
  cfg.speed_hz = spi_speed_hz_;
  if (!link_->open(cfg)) {
    RCLCPP_ERROR(
      rclcpp::get_logger("BibaStm32SystemHardware"),
      "Failed to open SPI device %s", spi_device_.c_str());
    return hardware_interface::CallbackReturn::ERROR;
  }

  Telemetry tlm;
  if (!link_->arm(true, tlm)) {
    RCLCPP_WARN(
      rclcpp::get_logger("BibaStm32SystemHardware"),
      "ARM exchange failed; STM32 watchdog will keep motors disabled.");
  }
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn BibaStm32SystemHardware::on_deactivate(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  if (link_ && link_->is_open()) {
    Telemetry tlm;
    Setpoint zero{0.0, 0.0};
    link_->set_setpoint(zero, tlm);
    link_->arm(false, tlm);
  }
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn BibaStm32SystemHardware::on_shutdown(
  const rclcpp_lifecycle::State & previous_state)
{
  on_deactivate(previous_state);
  if (link_) {
    link_->close();
  }
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::return_type BibaStm32SystemHardware::read(
  const rclcpp::Time & /*time*/, const rclcpp::Duration & period)
{
  // Open-loop: report last commanded velocity as state and integrate
  // it into position. A failed ping is logged but does not abort the
  // controller — the STM32 watchdog handles motor safety.
  Telemetry tlm;
  if (link_ && link_->is_open()) {
    if (!link_->ping(tlm)) {
      RCLCPP_WARN_THROTTLE(
        rclcpp::get_logger("BibaStm32SystemHardware"),
        *rclcpp::Clock::make_shared(), 1000,
        "STM32 ping failed (CRC/transport)");
    }
  }
  for (std::size_t i = 0; i < kJointCount; ++i) {
    velocity_state_[i] = velocity_command_[i];
    position_state_[i] += velocity_command_[i] * period.seconds();
  }
  return hardware_interface::return_type::OK;
}

hardware_interface::return_type BibaStm32SystemHardware::write(
  const rclcpp::Time & /*time*/, const rclcpp::Duration & /*period*/)
{
  if (!link_ || !link_->is_open()) {
    return hardware_interface::return_type::ERROR;
  }

  Setpoint sp;
  sp.left = clamp_unit(velocity_command_[kLeft] / max_wheel_speed_rad_s_);
  sp.right = clamp_unit(velocity_command_[kRight] / max_wheel_speed_rad_s_);

  Telemetry tlm;
  if (!link_->set_setpoint(sp, tlm)) {
    return hardware_interface::return_type::ERROR;
  }
  return hardware_interface::return_type::OK;
}

}  // namespace biba_hardware_stm32

PLUGINLIB_EXPORT_CLASS(
  biba_hardware_stm32::BibaStm32SystemHardware,
  hardware_interface::SystemInterface)
