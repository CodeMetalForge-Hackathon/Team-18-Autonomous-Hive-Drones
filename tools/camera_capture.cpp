// Direct SDK capture for external robot supervision. Does not command the rover.
// Build with vendor headers and run beside stream_aurora900.dll (x64).
#define NOMINMAX
#include <windows.h>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include "deptrum/device.h"
#include "deptrum/stream.h"

using namespace deptrum;
using namespace deptrum::stream;

int main(int argc, char** argv) {
  std::cout.setf(std::ios::unitbuf);
  auto dll = LoadLibraryA("stream_aurora900.dll");
  if (!dll) { std::cerr << "Cannot load vendor DLL: " << GetLastError() << '\n'; return 1; }
  using GetManager = std::shared_ptr<DeviceManager>(*)();
  auto getManager = reinterpret_cast<GetManager>(GetProcAddress(dll,
      "?GetInstance@DeviceManager@stream@deptrum@@SA?AV?$shared_ptr@VDeviceManager@stream@deptrum@@@std@@XZ"));
  if (!getManager) { std::cerr << "SDK entry point missing\n"; return 1; }
  auto manager = getManager();
  std::vector<DeviceInformation> devices;
  int code = manager->GetDeviceList(devices);
  std::cout << "Enumerate: " << code << "; devices: " << devices.size() << '\n';
  for (auto& device : devices) std::cout << device.model << " " << device.ir_camera.port_path << '\n';
  if (code || devices.empty()) return 2;
  if (argc < 2) return 0;
  std::filesystem::path output = argv[1];
  std::filesystem::create_directories(output);
  auto device = manager->CreateDevice(devices[0]);
  if (!device) return 3;
  code = device->Open();
  std::cout << "Open: " << code << '\n';
  if (code) return 4;
  std::vector<std::tuple<FrameMode, FrameMode, FrameMode>> modes;
  code = device->GetSupportedFrameMode(modes);
  std::cout << "Modes: " << code << "; count: " << modes.size() << '\n';
  if (code || modes.empty()) { device->Close(); return 5; }
  for (size_t i=0;i<modes.size();++i) std::cout << "Mode " << i << ": " << std::get<0>(modes[i]) << ',' << std::get<1>(modes[i]) << ',' << std::get<2>(modes[i]) << '\n';
  auto mode = modes.back();
  code = device->SetMode(std::get<0>(mode), std::get<1>(mode), std::get<2>(mode));
  std::cout << "SetMode: " << code << '\n';
  Stream* stream = nullptr;
  code = device->CreateStream(stream, {kRgbd});
  std::cout << "CreateStream: " << code << '\n';
  if (code || !stream) { device->Close(); return 6; }
  code = stream->Start();
  std::cout << "Start: " << code << '\n';
  bool saved = false;
  if (!code) for (int attempt=0; attempt<12; ++attempt) {
    StreamFrames frames;
    code = stream->GetFrames(frames, 2000);
    std::cout << "Frames: " << code << " count: " << frames.count << '\n';
    if (code) continue;
    for (auto& frame : frames.frame_ptr) {
      if (!frame || !frame->data || frame->size <= 0 || frame->size > 100000000) continue;
      std::cout << "Frame type=" << frame->frame_type << " format=" << frame->image_format
                << " " << frame->cols << "x" << frame->rows << " bytes=" << frame->size << '\n';
      std::string stem = "frame-" + std::to_string(frame->frame_type);
      std::ofstream raw(output / (stem + ".raw"), std::ios::binary);
      raw.write(static_cast<const char*>(frame->data.get()), frame->size);
      std::ofstream metadata(output / (stem + ".json"));
      metadata << "{\"width\":" << frame->cols << ",\"height\":" << frame->rows
               << ",\"format\":" << frame->image_format << ",\"type\":" << frame->frame_type
               << ",\"configured_rgb_mode\":" << std::get<1>(mode)
               << ",\"bytes\":" << frame->size << ",\"timestamp\":" << frame->timestamp << "}";
      saved = true;
    }
    if (saved) break;
  }
  stream->Stop(); device->DestroyStream(stream); device->Close();
  return saved ? 0 : 7;
}
