// Direct SDK capture for external robot supervision. Does not command the rover.
// Build with vendor headers and run beside stream_aurora900.dll (x64).
#define NOMINMAX
#include <windows.h>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include <cstdlib>
#include <io.h>
#include <fcntl.h>
#include "deptrum/device.h"
#include "deptrum/stream.h"

using namespace deptrum;
using namespace deptrum::stream;

bool pipeWrite(int fd, const void* data, unsigned count) {
  auto bytes = static_cast<const char*>(data);
  while (count) {
    int written = _write(fd, bytes, count);
    if (written <= 0) return false;
    bytes += written; count -= written;
  }
  return true;
}

int main(int argc, char** argv) {
  bool pipeMode = argc > 1 && std::string(argv[1]) == "--pipe";
  int binaryFd = -1;
  if (pipeMode) {
    binaryFd = _dup(_fileno(stdout));
    _setmode(binaryFd, _O_BINARY);
    // Keep vendor diagnostics out of the binary frame protocol.
    _dup2(_fileno(stderr), _fileno(stdout));
    SetStdHandle(STD_OUTPUT_HANDLE, GetStdHandle(STD_ERROR_HANDLE));
  }
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
  int requested = pipeMode ? 0 : (argc > 2 ? std::atoi(argv[2]) : 1);
  if (!pipeMode && (requested < 1 || requested > 300)) { std::cerr << "Frame count must be 1..300\n"; return 8; }
  std::filesystem::path output = argv[1];
  if (!pipeMode) std::filesystem::create_directories(output);
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
  int saved = 0;
  int failures = 0;
  bool pipeOk = true;
  if (!code) for (int attempt=0; pipeOk && (pipeMode ? failures<12 : attempt<requested+12 && saved<requested); ++attempt) {
    StreamFrames frames;
    code = stream->GetFrames(frames, 2000);
    std::cout << "Frames: " << code << " count: " << frames.count << '\n';
    if (code) { ++failures; continue; }
    failures = 0;
    auto destination = output;
    if (!pipeMode && requested > 1) {
      destination /= "sample-" + std::to_string(saved);
      std::filesystem::create_directories(destination);
    }
    bool hasRgb = false;
    for (auto& frame : frames.frame_ptr) {
      if (!frame || !frame->data || frame->size <= 0 || frame->size > 100000000) continue;
      if (pipeMode) {
        if (frame->frame_type != 1) continue;
        uint32_t header[4] = {0x314d5246, static_cast<uint32_t>(frame->cols),
                              static_cast<uint32_t>(frame->rows), static_cast<uint32_t>(frame->size)};
        uint64_t timestamps[2] = {static_cast<uint64_t>(frame->timestamp),
          static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
              std::chrono::system_clock::now().time_since_epoch()).count())};
        pipeOk = pipeWrite(binaryFd, header, sizeof(header)) &&
                 pipeWrite(binaryFd, timestamps, sizeof(timestamps)) &&
                 pipeWrite(binaryFd, frame->data.get(), frame->size);
        hasRgb = true;
        continue;
      }
      if (requested > 1 && frame->frame_type != 1) continue;
      std::cout << "Frame type=" << frame->frame_type << " format=" << frame->image_format
                << " " << frame->cols << "x" << frame->rows << " bytes=" << frame->size << '\n';
      std::string stem = "frame-" + std::to_string(frame->frame_type);
      std::ofstream raw(destination / (stem + ".raw"), std::ios::binary);
      raw.write(static_cast<const char*>(frame->data.get()), frame->size);
      std::ofstream metadata(destination / (stem + ".json"));
      metadata << "{\"width\":" << frame->cols << ",\"height\":" << frame->rows
               << ",\"format\":" << frame->image_format << ",\"type\":" << frame->frame_type
               << ",\"configured_rgb_mode\":" << std::get<1>(mode)
               << ",\"bytes\":" << frame->size << ",\"timestamp\":" << frame->timestamp
               << ",\"host_time_ms\":" << std::chrono::duration_cast<std::chrono::milliseconds>(
                   std::chrono::system_clock::now().time_since_epoch()).count() << "}";
      if (frame->frame_type == 1) hasRgb = true;
    }
    if (hasRgb) ++saved;
  }
  stream->Stop(); device->DestroyStream(stream); device->Close();
  if (binaryFd >= 0) _close(binaryFd);
  return (pipeMode ? !pipeOk : saved == requested) ? 0 : 7;
}
