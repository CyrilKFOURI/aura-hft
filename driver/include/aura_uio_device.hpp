#pragma once

#include <cstdint>
#include <cstddef>
#include <string>
#include <stdexcept>
#include <memory>
#include <vector>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <fstream>
#include <iostream>

namespace aura::driver {

/**
 * @brief Low-level RAII wrapper for Linux Userspace I/O (UIO) devices.
 * Supports zero-copy mmap register access and an in-memory mock mode for CI/testing.
 */
class UioDevice {
public:
    explicit UioDevice(const std::string& dev_path, size_t map_size = 4096)
        : m_dev_path(dev_path), m_map_size(map_size), m_is_mock(false) {
        
        m_fd = ::open(dev_path.c_str(), O_RDWR | O_SYNC);
        if (m_fd < 0) {
            throw std::runtime_error("Failed to open UIO device: " + dev_path);
        }

        void* mapped = ::mmap(nullptr, m_map_size, PROT_READ | PROT_WRITE, MAP_SHARED, m_fd, 0);
        if (mapped == MAP_FAILED) {
            ::close(m_fd);
            throw std::runtime_error("Failed to mmap UIO device: " + dev_path);
        }

        m_base_addr = static_cast<volatile uint8_t*>(mapped);
    }

    /**
     * @brief Creates an in-memory mock UIO device (for testing without physical FPGA hardware).
     */
    static std::unique_ptr<UioDevice> create_mock(size_t map_size = 4096) {
        auto dev = std::unique_ptr<UioDevice>(new UioDevice());
        dev->m_map_size = map_size;
        dev->m_is_mock = true;
        dev->m_mock_storage.resize(map_size, 0);
        dev->m_base_addr = static_cast<volatile uint8_t*>(dev->m_mock_storage.data());
        return dev;
    }

    ~UioDevice() {
        if (!m_is_mock && m_base_addr != nullptr) {
            ::munmap(const_cast<uint8_t*>(m_base_addr), m_map_size);
            if (m_fd >= 0) {
                ::close(m_fd);
            }
        }
    }

    // Move-only semantics
    UioDevice(const UioDevice&) = delete;
    UioDevice& operator=(const UioDevice&) = delete;

    UioDevice(UioDevice&& other) noexcept 
        : m_dev_path(std::move(other.m_dev_path)),
          m_map_size(other.m_map_size),
          m_fd(other.m_fd),
          m_base_addr(other.m_base_addr),
          m_is_mock(other.m_is_mock),
          m_mock_storage(std::move(other.m_mock_storage)) {
        other.m_fd = -1;
        other.m_base_addr = nullptr;
    }

    UioDevice& operator=(UioDevice&& other) noexcept {
        if (this != &other) {
            if (!m_is_mock && m_base_addr != nullptr) {
                ::munmap(const_cast<uint8_t*>(m_base_addr), m_map_size);
                if (m_fd >= 0) ::close(m_fd);
            }
            m_dev_path = std::move(other.m_dev_path);
            m_map_size = other.m_map_size;
            m_fd = other.m_fd;
            m_base_addr = other.m_base_addr;
            m_is_mock = other.m_is_mock;
            m_mock_storage = std::move(other.m_mock_storage);

            other.m_fd = -1;
            other.m_base_addr = nullptr;
        }
        return *this;
    }

    [[nodiscard]] inline volatile uint32_t* reg_ptr(uint32_t byte_offset) const {
        if (byte_offset + sizeof(uint32_t) > m_map_size) {
            throw std::out_of_range("Register offset out of range: " + std::to_string(byte_offset));
        }
        return reinterpret_cast<volatile uint32_t*>(m_base_addr + byte_offset);
    }

    [[nodiscard]] inline uint32_t read32(uint32_t byte_offset) const noexcept {
        return *reinterpret_cast<volatile uint32_t*>(m_base_addr + byte_offset);
    }

    inline void write32(uint32_t byte_offset, uint32_t value) noexcept {
        *reinterpret_cast<volatile uint32_t*>(m_base_addr + byte_offset) = value;
    }

    [[nodiscard]] bool is_mock() const noexcept { return m_is_mock; }
    [[nodiscard]] size_t size() const noexcept { return m_map_size; }

private:
    UioDevice() : m_map_size(0), m_fd(-1), m_base_addr(nullptr), m_is_mock(true) {}

    std::string m_dev_path;
    size_t m_map_size{0};
    int m_fd{-1};
    volatile uint8_t* m_base_addr{nullptr};
    bool m_is_mock{false};
    std::vector<uint8_t> m_mock_storage;
};

} // namespace aura::driver
