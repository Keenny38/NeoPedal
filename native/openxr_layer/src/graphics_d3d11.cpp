/*
 * NeoPedal - OpenXR overlay layer
 * Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * D3D11 sessions (Le Mans Ultimate, rFactor 2 and most OpenXR sim games): copies on the game's immediate
 * context, called from xrEndFrame on the game's render thread. Small rects by UpdateSubresource; big ones (a
 * whole atlas: up to 4 MB) through a dynamic texture (Map WRITE_DISCARD never waits, copied on the GPU), as an
 * UpdateSubresource of a few MB made the driver block the render thread (up to 28 ms). Neither changes any
 * pipeline state, nothing to save or restore. A game that turned on D3D11 multithread protection gets the
 * context locked the same way. OpenXR lets a D3D11 game call xrEndFrame on another thread than the one using
 * the immediate context (submission thread): when xrEndFrame runs on another thread than xrCreateSession and
 * the device is not protected, protection is turned on once for the device (the game's own calls then take
 * the lock too) and that frame copies nothing. Same thread (most games): nothing changed, no lock.
 */

#include "graphics.h"

#include <d3d11_4.h>

#include <cstring>
#include <new>

namespace tpvr {
namespace {

const FormatCandidate kFormats[] = {
    {DXGI_FORMAT_R8G8B8A8_UNORM_SRGB, false, true},
    {DXGI_FORMAT_B8G8R8A8_UNORM_SRGB, true, true},
    {DXGI_FORMAT_R8G8B8A8_UNORM, false, false},
    {DXGI_FORMAT_B8G8R8A8_UNORM, true, false},
};

constexpr uint64_t kDynamicBytes = 64u * 1024u;  // rects from this size copied through the dynamic texture

// Device critical section held for the scope (nothing done when multithread is nullptr)
class ContextLock {
public:
    explicit ContextLock(ID3D11Multithread* multithread) : multithread_(multithread) {
        if (multithread_ != nullptr) {
            multithread_->Enter();
        }
    }
    ~ContextLock() {
        if (multithread_ != nullptr) {
            multithread_->Leave();
        }
    }
    ContextLock(const ContextLock&) = delete;
    ContextLock& operator=(const ContextLock&) = delete;

private:
    ID3D11Multithread* multithread_;
};

class D3D11Backend final : public GraphicsBackend {
public:
    // Made in xrCreateSession: its thread taken as the one using the immediate context
    explicit D3D11Backend(ID3D11Device* device) : device_(device), session_thread_(GetCurrentThreadId()) {
        device_->AddRef();
        device_->GetImmediateContext(&context_);
        if (context_ != nullptr &&
            FAILED(context_->QueryInterface(__uuidof(ID3D11Multithread), reinterpret_cast<void**>(&multithread_)))) {
            multithread_ = nullptr;  // before Windows 10 Creators Update
        }
    }

    ~D3D11Backend() override {
        release_dynamic();
        if (multithread_ != nullptr) {
            multithread_->Release();
        }
        if (context_ != nullptr) {
            context_->Release();
        }
        device_->Release();
    }

    bool valid() const { return context_ != nullptr; }

    uint32_t api() const override { return TPVR_GRAPHICS_D3D11; }

    const FormatCandidate* format_candidates(size_t& count) const override {
        count = sizeof(kFormats) / sizeof(kFormats[0]);
        return kFormats;
    }

    bool set_swapchain(XrSwapchain swapchain, PFN_xrEnumerateSwapchainImages enumerate, int64_t format) override {
        textures_.clear();
        if (format_ != static_cast<DXGI_FORMAT>(format)) {
            release_dynamic();  // other format: dynamic texture made again
            dynamic_failed_ = false;
        }
        format_ = static_cast<DXGI_FORMAT>(format);
        uint32_t count = 0;
        if (XR_FAILED(enumerate(swapchain, 0, &count, nullptr)) || count == 0 || count > 16) {
            return false;
        }
        std::vector<XrSwapchainImageD3D11KHR> images(count, {XR_TYPE_SWAPCHAIN_IMAGE_D3D11_KHR, nullptr, nullptr});
        if (XR_FAILED(enumerate(swapchain, count, &count, reinterpret_cast<XrSwapchainImageBaseHeader*>(images.data())))) {
            return false;
        }
        for (uint32_t index = 0; index < count; ++index) {
            if (images[index].texture == nullptr) {
                textures_.clear();
                return false;
            }
            textures_.push_back(images[index].texture);  // owned by runtime until swapchain destroyed
        }
        return true;
    }

    bool clear_swapchain() override {
        textures_.clear();
        return true;  // D3D11 keeps resources alive until GPU work using them finished
    }

    bool upload(uint32_t image_index, const uint8_t* pixels, uint32_t width, uint32_t height) override {
        return copy(image_index, pixels, width, Rect{0, 0, width, height});
    }

    bool upload_rect(uint32_t image_index, const uint8_t* pixels, uint32_t width, uint32_t height,
                     const Rect& rect) override {
        if (rect.width == 0 || rect.height == 0 || static_cast<uint64_t>(rect.x) + rect.width > width ||
            static_cast<uint64_t>(rect.y) + rect.height > height) {
            return upload(image_index, pixels, width, height);
        }
        return copy(image_index, pixels, width, rect);  // rest of the image already holds the same pixels
    }

private:
    // Rect of pixels (width columns, tightly packed) copied to the same place of the acquired image
    bool copy(uint32_t image_index, const uint8_t* pixels, uint32_t width, const Rect& rect) {
        if (image_index >= textures_.size() || pixels == nullptr || rect.width == 0 || rect.height == 0) {
            return false;
        }
        const uint8_t* first = pixels + (static_cast<size_t>(rect.y) * width + rect.x) * 4u;
        const bool protect = multithread_ != nullptr && multithread_->GetMultithreadProtected() != FALSE;
        if (!protect && multithread_ != nullptr && !protection_refused_ && GetCurrentThreadId() != session_thread_) {
            if (protect_device()) {
                return false;  // a game call may have started without the lock: copied on the next frame
            }
        }
        const ContextLock lock(protect ? multithread_ : nullptr);
        const bool big = static_cast<uint64_t>(rect.width) * rect.height * 4u >= kDynamicBytes;
        if (!big || !copy_dynamic(textures_[image_index], first, width, rect)) {
            const D3D11_BOX box = {rect.x, rect.y, 0, rect.x + rect.width, rect.y + rect.height, 1};
            context_->UpdateSubresource(textures_[image_index], 0, &box, first, width * 4u, 0);
        }
        return true;
    }

    // xrEndFrame on another thread than xrCreateSession, device not protected: multithread protection turned on
    // (kept for the device's life, the game may rely on it from now on). False when the device refuses it
    // (device made single threaded): copies then done as before, without lock.
    bool protect_device() {
        multithread_->SetMultithreadProtected(TRUE);
        if (multithread_->GetMultithreadProtected() == FALSE) {
            protection_refused_ = true;
            log_message("D3D11: xrEndFrame not on the session thread, multithread protection refused");
            return false;
        }
        log_message("D3D11: xrEndFrame not on the session thread, multithread protection turned on");
        return true;
    }

    // Rect written to the same place of the dynamic texture (new memory: never waits for the GPU), then copied to
    // the image on the GPU. False when the dynamic texture cannot be used (UpdateSubresource then).
    bool copy_dynamic(ID3D11Texture2D* texture, const uint8_t* first, uint32_t width, const Rect& rect) {
        if (!ensure_dynamic(rect.x + rect.width, rect.y + rect.height)) {
            return false;
        }
        D3D11_MAPPED_SUBRESOURCE mapped = {};
        if (FAILED(context_->Map(dynamic_, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped)) || mapped.pData == nullptr) {
            return false;
        }
        uint8_t* target = static_cast<uint8_t*>(mapped.pData) + static_cast<size_t>(rect.y) * mapped.RowPitch +
                          static_cast<size_t>(rect.x) * 4u;
        for (uint32_t row = 0; row < rect.height; ++row) {
            std::memcpy(target + static_cast<size_t>(row) * mapped.RowPitch, first + static_cast<size_t>(row) * width * 4u,
                        static_cast<size_t>(rect.width) * 4u);
        }
        context_->Unmap(dynamic_, 0);
        const D3D11_BOX box = {rect.x, rect.y, 0, rect.x + rect.width, rect.y + rect.height, 1};
        context_->CopySubresourceRegion(texture, 0, rect.x, rect.y, 0, dynamic_, 0, &box);
        return true;
    }

    // Dynamic texture of the swapchain format, at least width x height (made again only to grow)
    bool ensure_dynamic(uint32_t width, uint32_t height) {
        if (dynamic_ != nullptr && dynamic_width_ >= width && dynamic_height_ >= height) {
            return true;
        }
        if (dynamic_failed_) {
            return false;
        }
        release_dynamic();
        D3D11_TEXTURE2D_DESC desc = {};
        desc.Width = width;
        desc.Height = height;
        desc.MipLevels = 1;
        desc.ArraySize = 1;
        desc.Format = format_;
        desc.SampleDesc.Count = 1;
        desc.Usage = D3D11_USAGE_DYNAMIC;
        desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        desc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        if (FAILED(device_->CreateTexture2D(&desc, nullptr, &dynamic_)) || dynamic_ == nullptr) {
            dynamic_ = nullptr;
            dynamic_failed_ = true;  // not tried again for this format
            log_message("D3D11 dynamic texture not created: UpdateSubresource used");
            return false;
        }
        dynamic_width_ = width;
        dynamic_height_ = height;
        return true;
    }

    void release_dynamic() {
        if (dynamic_ != nullptr) {
            dynamic_->Release();
            dynamic_ = nullptr;
        }
        dynamic_width_ = dynamic_height_ = 0;
    }

    ID3D11Device* device_;
    ID3D11DeviceContext* context_ = nullptr;
    ID3D11Multithread* multithread_ = nullptr;
    const DWORD session_thread_;  // thread of xrCreateSession
    bool protection_refused_ = false;
    std::vector<ID3D11Texture2D*> textures_;
    DXGI_FORMAT format_ = DXGI_FORMAT_UNKNOWN;
    ID3D11Texture2D* dynamic_ = nullptr;
    uint32_t dynamic_width_ = 0;
    uint32_t dynamic_height_ = 0;
    bool dynamic_failed_ = false;
};

}  // namespace

std::unique_ptr<GraphicsBackend> create_d3d11_backend(const XrGraphicsBindingD3D11KHR& binding) {
    if (binding.device == nullptr) {
        return nullptr;
    }
    std::unique_ptr<D3D11Backend> backend(new (std::nothrow) D3D11Backend(binding.device));
    if (!backend || !backend->valid()) {
        return nullptr;
    }
    return backend;
}

}  // namespace tpvr
