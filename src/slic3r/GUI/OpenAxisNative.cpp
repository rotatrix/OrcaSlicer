#include "OpenAxisController.hpp"
#include "OpenAxisOverlay.hpp"
#include "OpenAxisCameraMath.hpp"
#include "GLCanvas3D.hpp"
#include "GUI_App.hpp"
#include "Plater.hpp"
#include "PartPlate.hpp"
#include <glad/gl.h>
#include <imgui/imgui.h>
#include <openaxis/logging.hpp>
#include <sstream>
#include <cmath>
#include <limits>
#include <boost/log/trivial.hpp>
#include <wx/dialog.h>
#include <wx/modalhook.h>

namespace Slic3r::GUI {
using openaxis::Value;
namespace {
openaxis::Vec3 vector(const Vec3d &v) { return {v.x(), v.y(), v.z()}; }
Vec3d vector(openaxis::Vec3 v) { return {v.x, v.y, v.z}; }
Value bounds_value(const BoundingBoxf3 &b) {
    if (!b.defined)
        return nullptr;
    return {{"min", {b.min.x(), b.min.y(), b.min.z()}},
            {"max", {b.max.x(), b.max.y(), b.max.z()}}};
}
} // namespace
bool OpenAxisController::modal_dialog_open() {
    // Native file choosers need not appear in wxTopLevelWindows.
    if (wxModalDialogHook::GetOpenCount() > 0)
        return true;
#ifdef __APPLE__
    if (wxDialog::OSXHasModalDialogsOpen())
        return true;
#endif
    for (auto node = wxTopLevelWindows.GetFirst(); node; node = node->GetNext())
        if (auto *dialog = dynamic_cast<wxDialog *>(node->GetData()); dialog && dialog->IsShown() && dialog->IsModal())
            return true;
    return false;
}
Camera &OpenAxisController::active_camera() const { return m_camera; }
void OpenAxisController::initialize_native() {}
void OpenAxisController::context_changed() {}
std::string OpenAxisController::context_key() const {
    if (!viewport_available()) return "unavailable";
    return std::to_string(m_canvas->get_model()->id().id) + "/" +
        std::to_string(m_canvas->openaxis_scene_revision()) + "/" +
        std::to_string(reinterpret_cast<std::uintptr_t>(m_canvas)) + "/" +
        std::to_string(wxGetApp().plater()->get_partplate_list().get_curr_plate_index()) + "/" +
        std::to_string(m_width) + "/" + std::to_string(m_height) + "/" + std::to_string(m_scale);
}
bool OpenAxisController::write_camera(const openaxis::Pose &p) {
    if (!m_focused || !viewport_available())
        return false;
    // Native camera listeners also see adapter writes. Their realized result is
    // already returned to the SDK; do not emit a duplicate input notification.
    struct Writing {
        bool &flag;
        Writing(bool &f) : flag(f) { flag = true; }
        ~Writing() { flag = false; }
    } writing(m_writing_camera);
    auto &c = active_camera();
    auto q = openaxis::Quat::from_rotvec(p.r);
    const Vec3d position = vector(p.t), forward = vector(q.rotate({0, 0, -1}));
    // Keep the native target on-axis at the pivot's depth, without turning toward
    // an off-center pivot. Retain the previous distance for a pivot behind the eye.
    const std::optional<double> depth = m_pivot
        ? std::optional<double>((vector(*m_pivot) - position).dot(forward)) : std::nullopt;
    // Projection is a native user preference. On a mismatch preserve its scale;
    // realized-pose readback lets the SDK rebase onto the native projection.
    const auto scale = OpenAxisCameraMath::view_scale(c.get_distance(), c.get_zoom(),
        c.get_viewport()[3], c.get_type() == Camera::EType::Perspective, depth, p.fov,
        c.get_type() == Camera::EType::Ortho ? p.ortho_extent : 0.0);
    c.set_external_view(position, position + scale.distance * forward, vector(q.rotate({0, 1, 0})), scale.zoom);
    m_canvas->update_openaxis_projection();
    m_last_view = c.get_view_matrix();
    m_last_zoom = c.get_zoom();
    m_last_projection = c.get_type();
    redraw();
    return true;
}
Value OpenAxisController::fact(const std::string &name) {
    if (!m_focused || !viewport_available()) return nullptr;
    auto &c = active_camera();
    if (name == "document.id") return std::to_string(m_canvas->get_model()->id().id);
    if (name == "world.orientation") return {{"forward", {0, 1, 0}}, {"up", {0, 0, 1}}, {"handedness", "right"}};
    if (name == "camera.view_target") return openaxis::vector_value(vector(c.get_target()));
    if (name == "viewport.aspect") return double(m_width) / m_height;
    const bool inside = m_x >= 0 && m_x < m_width && m_y >= 0 && m_y < m_height;
    if (name == "viewport.cursor" && inside)
        return {{"x", 2. * m_x / m_width - 1}, {"y", 1 - 2. * m_y / m_height}};
    const auto &volumes = m_canvas->get_volumes().volumes;
    const auto &selected = m_canvas->get_selection().get_volume_idxs();
    if (name == "model.bounds" || name == "selection.bounds") {
        BoundingBoxf3 bounds;
        for (unsigned i = 0; i < volumes.size(); ++i)
            if (volumes[i]->is_active && !volumes[i]->disabled && (name == "model.bounds" || selected.count(i)))
                bounds.merge(volumes[i]->transformed_bounding_box());
        return bounds_value(bounds);
    }
    const bool center = name == "pick.viewport_center" || name == "pick.viewport_center.selection";
    const bool cursor = name == "pick.cursor" || name == "pick.cursor.selection";
    if ((center || cursor) && (center || inside)) {
        const bool only = name.find(".selection") != std::string::npos;
        const Vec2d pixel(center ? m_width * .5 : m_x, center ? m_height * .5 : m_y);
        Value result = {{"markerPosition", {pixel.x() / m_scale, pixel.y() / m_scale}}};
        double closest = std::numeric_limits<double>::max();
        auto test = [&](const SceneRaycasterItem &item, const Transform3d &transform, const GLVolume *volume) {
            Vec3f point, normal;
            if (!item.is_active() || !item.get_raycaster()->closest_hit(pixel, transform, c, point, normal, nullptr)) return;
            const Vec3d world = transform * point.cast<double>();
            const Vec3d world_normal = (transform.linear().inverse().transpose() * normal.cast<double>()).normalized();
            if (!item.use_back_faces() && world_normal.dot(c.get_dir_forward()) >= 0) return;
            const double distance = (world - c.get_position()).squaredNorm();
            if (distance >= closest) return;
            closest = distance;
            result = {{"point", openaxis::vector_value(vector(world))}, {"markerPosition", {pixel.x() / m_scale, pixel.y() / m_scale}}};
            if (volume) result["bounds"] = bounds_value(volume->transformed_bounding_box());
        };
        for (const auto &item : *m_canvas->get_raycasters_for_picking(SceneRaycaster::EType::Volume)) {
            const int id = SceneRaycaster::decode_id(SceneRaycaster::EType::Volume, item->get_id());
            if (id >= 0 && size_t(id) < volumes.size() && !volumes[id]->disabled && (!only || selected.count(id)))
                test(*item, item->get_transform(), volumes[id]);
        }
        // Plate meshes already contain their world placement. Exclude the
        // plate toolbar icons, which share the Bed raycaster category.
        if (!only && c.is_looking_downward())
            for (const auto &item : *m_canvas->get_raycasters_for_picking(SceneRaycaster::EType::Bed)) {
                const int id = SceneRaycaster::decode_id(SceneRaycaster::EType::Bed, item->get_id());
                if (id >= 0 && id % PartPlate::GRABBER_COUNT == 0)
                    test(*item, item->get_transform(), nullptr);
            }
        // Rendered toolpaths are separate from the model mesh raycasters.
        if (!only)
            if (const auto hit = m_canvas->openaxis_gcode_hit(pixel)) {
                const double distance = (*hit - c.get_position()).squaredNorm();
                if (distance < closest)
                    result = {{"point", openaxis::vector_value(vector(*hit))},
                              {"markerPosition", {pixel.x() / m_scale, pixel.y() / m_scale}}};
            }
        return result;
    }
    return nullptr;
}
void OpenAxisController::render_indicator(GLCanvas3D &canvas) {
    if (&canvas != m_canvas) return;
    if (!m_pivot || !viewport_available() || context_key() != m_context) return;
    const Vec4d clip = active_camera().get_projection_matrix().matrix() * active_camera().get_view_matrix().matrix() * Vec4d(m_pivot->x, m_pivot->y, m_pivot->z, 1);
    if (!OpenAxisOverlay::visible({clip.x(), clip.y(), clip.z(), clip.w()})) return;
    // Orca's ImGui display size is already in framebuffer pixels.
    const ImVec2 pixel(float((clip.x() / clip.w() + 1) * .5 * m_width), float((1 - clip.y() / clip.w()) * .5 * m_height));
    float depth = 1.f;
    glReadPixels(std::clamp(int(pixel.x), 0, m_width - 1),
                 std::clamp(m_height - 1 - int(pixel.y), 0, m_height - 1),
                 1, 1, GL_DEPTH_COMPONENT, GL_FLOAT, &depth);
    const int alpha = (clip.z() / clip.w() + 1) * .5 > depth + 1e-5 ? 64 : 255;
    auto *draw = ImGui::GetBackgroundDrawList();
    draw->AddCircle(pixel, float(4.75 * m_scale), IM_COL32(0, 0, 0, alpha), 32, float(1.5 * m_scale));
    draw->AddCircleFilled(pixel, float(4 * m_scale), IM_COL32(0, 255, 0, alpha));
}
void OpenAxisController::render_overlay() {
    if (!m_diagnostics_visible || !viewport_available())
        return;
    const auto frame = m_collector.presentation();
    const std::string status = "Rotatrix: " + m_connection.status().state +
        " | Focus: " + (m_focused ? "Yes" : "No") +
        " | Gesture: " + (m_session.active() ? "Active" : "Idle");
    ImGui::GetBackgroundDrawList()->AddText(
        {12.f * float(m_scale), 12.f * float(m_scale)}, IM_COL32_WHITE, status.c_str());
    if (frame.context != context_key())
        return;
    const auto &camera = active_camera();
    const auto &v = camera.get_viewport();
    OpenAxisOverlay::Viewport viewport{double(v[0]),
                                       double(v[1]),
                                       double(v[2]),
                                       double(v[3]),
                                       double(m_height),
                                       1.0};
    auto pixel = [](const std::array<double, 2> &p) { return ImVec2(float(p[0]), float(p[1])); };
    auto clip = [&](openaxis::Vec3 p) {
        const Vec4d q =
            camera.get_projection_matrix().matrix() * camera.get_view_matrix().matrix() * Vec4d(p.x, p.y, p.z, 1);
        return OpenAxisOverlay::Clip{q.x(), q.y(), q.z(), q.w()};
    };
    auto color = [](const std::string &tone, double opacity = 1) {
        const auto &c = openaxis::diagnostic_colors().at(tone);
        return IM_COL32(c[0], c[1], c[2], int(255 * opacity));
    };
    auto *draw = ImGui::GetBackgroundDrawList();
    auto lo = pixel(viewport.pixel(v[0], viewport.top())),
         hi = pixel(viewport.pixel(v[0] + v[2], viewport.top() + v[3]));
    draw->PushClipRect(lo, hi, true);
    for (const auto &segment : frame.segments) {
        auto a = clip(segment.start), b = clip(segment.end);
        if (OpenAxisOverlay::clip_segment(a, b))
            draw->AddLine(pixel(viewport.project(a)), pixel(viewport.project(b)),
                          color(segment.tone, segment.opacity), float(segment.width));
    }
    for (const auto &marker : frame.markers) {
        auto p = pixel(OpenAxisOverlay::framebuffer_point(marker.point, m_scale));
        auto c = color(marker.tone, .65);
        draw->AddLine({p.x - 9, p.y}, {p.x + 9, p.y}, IM_COL32_BLACK, 4);
        draw->AddLine({p.x, p.y - 9}, {p.x, p.y + 9}, IM_COL32_BLACK, 4);
        draw->AddLine({p.x - 9, p.y}, {p.x + 9, p.y}, c, 2);
        draw->AddLine({p.x, p.y - 9}, {p.x, p.y + 9}, c, 2);
        std::istringstream labels(marker.label);
        std::string label;
        float y = p.y - 8;
        while (std::getline(labels, label)) {
            draw->AddText({p.x + 13, y + 1}, IM_COL32_BLACK, label.c_str());
            draw->AddText({p.x + 12, y}, c, label.c_str());
            y += 15;
        }
    }
    // Leave room for the 80-logical-pixel viewcube and its surrounding margin.
    const float text_x = lo.x + 120;
    const float line_height = ImGui::GetTextLineHeightWithSpacing();
    float y = std::max(lo.y + 24, hi.y - 24 - float(frame.lines.size()) * line_height);
    for (const auto &line : frame.lines) {
        draw->AddText({text_x + 1, y + 1}, IM_COL32_BLACK, line.text.c_str());
        draw->AddText({text_x, y}, color(line.tone), line.text.c_str());
        y += line_height;
    }
    draw->PopClipRect();
}
} // namespace Slic3r::GUI
