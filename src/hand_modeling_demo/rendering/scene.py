from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import cos, exp, pi, sin, tan
from typing import Mapping

from panda3d.core import (
    AmbientLight,
    BitMask32,
    CardMaker,
    CollisionHandlerQueue,
    CollisionNode,
    CollisionRay,
    CollisionTraverser,
    CullFaceAttrib,
    DirectionalLight,
    Material,
    Point2,
    Point3,
    Shader,
    Vec3 as PandaVec3,
)

from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import InteractionMode, Vec2, Vec3, midpoint
from hand_modeling_demo.gestures.pointers import PointerState
from hand_modeling_demo.model.entities import create_primitive
from hand_modeling_demo.rendering.mesh_bridge import mesh_to_collision_node, mesh_to_geom_node


class HighlightRole(Enum):
    NONE = "none"
    LEFT = "left"
    RIGHT = "right"
    COMMON = "common"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PickResult:
    entity_id: str
    position: Vec3
    normal: Vec3
    depth: float


class PandaScene:
    min_distance = 1.5
    max_distance = 100.0
    pick_tolerance_pixels = 16.0
    pick_hold_tolerance_pixels = 24.0
    outline_width_pixels = 3.0

    def __init__(
        self,
        base,
        settings: Settings,
        viewport_size: tuple[int, int],
    ) -> None:
        self.base = base
        self.settings = settings
        self.viewport_size = viewport_size
        self.root = base.render.attachNewNode("hand-modeling-scene")
        self._nodes: dict[str, object] = {}
        self._geometry_nodes: dict[str, object] = {}
        self._outline_nodes: dict[str, object] = {}
        self._highlight_roles: dict[str, HighlightRole] = {}
        self._last_hover_ids: dict[HandSide, str] = {}
        self._pointer_nodes: dict[HandSide, object] = {}
        self._camera_gesture_node = None
        self._camera_gesture_mode = InteractionMode.NEUTRAL
        self._camera_gesture_positions: dict[HandSide, Vec2] = {}
        self._preview_node = None
        self._preview_kind = None
        self._yaw = 0.0
        self._pitch = 0.0
        self._distance = 12.0
        self._focus = Vec3(0.0, 0.0, 0.0)
        self.base.setBackgroundColor(0.0, 0.0, 0.0, 1.0)
        self.base.camLens.setAspectRatio(viewport_size[0] / viewport_size[1])
        self._material = self._make_material()
        self._outline_shader = self._make_outline_shader()
        self._light_nodes = self._setup_lighting()
        self._apply_camera()

        self._ray = CollisionRay()
        ray_node = CollisionNode("hand-pointer-ray")
        ray_node.addSolid(self._ray)
        ray_node.setFromCollideMask(BitMask32.bit(1))
        ray_node.setIntoCollideMask(BitMask32.allOff())
        self._ray_path = self.base.camera.attachNewNode(ray_node)
        self._queue = CollisionHandlerQueue()
        self._traverser = CollisionTraverser("hand-pointer-picker")
        self._traverser.addCollider(self._ray_path, self._queue)

    def resize_viewport(self, width: int, height: int) -> None:
        self.viewport_size = (max(1, width), max(1, height))
        self.base.camLens.setAspectRatio(
            self.viewport_size[0] / self.viewport_size[1]
        )
        self._update_outline_viewports()

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._nodes))

    @property
    def visible_pointer_sides(self) -> tuple[HandSide, ...]:
        return tuple(sorted(self._pointer_nodes, key=lambda side: side.value))

    @property
    def has_preview(self) -> bool:
        return self._preview_node is not None

    @property
    def camera_gesture_visible(self) -> bool:
        return bool(
            self._camera_gesture_node is not None
            and not self._camera_gesture_node.isHidden()
        )

    @property
    def camera_position(self) -> Vec3:
        point = self.base.camera.getPos(self.base.render)
        return Vec3(float(point.x), float(point.y), float(point.z))

    @property
    def focus_point(self) -> Vec3:
        return self._focus

    @property
    def distance(self) -> float:
        return self._distance

    @property
    def yaw(self) -> float:
        return self._yaw

    @property
    def pitch(self) -> float:
        return self._pitch

    def sync(self, store) -> None:
        wanted = set(store.ids())
        for entity_id in set(self._nodes) - wanted:
            self._nodes.pop(entity_id).removeNode()
            self._geometry_nodes.pop(entity_id, None)
            self._outline_nodes.pop(entity_id, None)
            self._highlight_roles.pop(entity_id, None)
        for entity_id in store.ids():
            entity = store.get(entity_id)
            node = self._nodes.get(entity_id)
            if node is None:
                node = self.root.attachNewNode(f"entity-{entity_id}")
                node.setTag("entity_id", entity_id)
                geometry = node.attachNewNode(mesh_to_geom_node(entity.mesh, f"mesh-{entity_id}"))
                geometry.setColor(0.78, 0.80, 0.82, 1.0)
                geometry.setMaterial(self._material, 1)
                outline = geometry.copyTo(node)
                outline.setName(f"outline-{entity_id}")
                outline.setShader(self._outline_shader)
                outline.setShaderInput(
                    "outline_viewport",
                    float(self.viewport_size[0]),
                    float(self.viewport_size[1]),
                )
                outline.setShaderInput("outline_width_pixels", self.outline_width_pixels)
                outline.setLightOff(1)
                outline.setTextureOff(1)
                outline.setDepthWrite(False)
                outline.setBin("fixed", 10)
                outline.setAttrib(
                    CullFaceAttrib.make(CullFaceAttrib.MCullCounterClockwise), 1
                )
                outline.hide()
                collision = mesh_to_collision_node(entity.mesh, f"collision-{entity_id}")
                collision.setIntoCollideMask(BitMask32.bit(1))
                collision_path = node.attachNewNode(collision)
                collision_path.setTag("entity_id", entity_id)
                self._nodes[entity_id] = node
                self._geometry_nodes[entity_id] = geometry
                self._outline_nodes[entity_id] = outline
                self._highlight_roles[entity_id] = HighlightRole.NONE
            transform = entity.transform
            node.setPos(transform.position.x, transform.position.y, transform.position.z)
            node.setScale(transform.scale)
            node.setHpr(0.0, 0.0, transform.roll)

    def pick(self, pointer: Vec2) -> PickResult | None:
        center_hit = self._pick_exact(pointer)
        if center_hit is not None:
            return center_hit
        return self._pick_around(pointer, self.pick_tolerance_pixels)

    def _pick_exact(self, pointer: Vec2) -> PickResult | None:
        self._ray.setFromLens(
            self.base.camNode,
            pointer.x * 2.0 - 1.0,
            1.0 - pointer.y * 2.0,
        )
        self._queue.clearEntries()
        self._traverser.traverse(self.root)
        self._queue.sortEntries()
        camera = self.base.camera.getPos(self.base.render)
        for entry in self._queue.getEntries():
            path = entry.getIntoNodePath()
            entity_id = path.getNetTag("entity_id")
            if not entity_id:
                continue
            point = entry.getSurfacePoint(self.base.render)
            normal = entry.getSurfaceNormal(self.base.render)
            return PickResult(
                entity_id,
                Vec3(float(point.x), float(point.y), float(point.z)),
                Vec3(float(normal.x), float(normal.y), float(normal.z)),
                float((point - camera).length()),
            )
        return None

    def _pick_around(
        self,
        pointer: Vec2,
        radius_pixels: float,
        *,
        entity_id: str | None = None,
    ) -> PickResult | None:
        width, height = self.viewport_size
        x_radius = radius_pixels / max(1, width)
        y_radius = radius_pixels / max(1, height)
        offsets = tuple(
            (offset_x * scale, offset_y * scale)
            for scale in (0.5, 1.0)
            for offset_x, offset_y in (
                (-x_radius, 0.0),
                (x_radius, 0.0),
                (0.0, -y_radius),
                (0.0, y_radius),
                (-x_radius, -y_radius),
                (-x_radius, y_radius),
                (x_radius, -y_radius),
                (x_radius, y_radius),
            )
        )
        hits = []
        for offset_x, offset_y in offsets:
            sample = Vec2(
                min(1.0, max(0.0, pointer.x + offset_x)),
                min(1.0, max(0.0, pointer.y + offset_y)),
            )
            hit = self._pick_exact(sample)
            if hit is not None and (entity_id is None or hit.entity_id == entity_id):
                hits.append(hit)
        return min(hits, key=lambda hit: hit.depth, default=None)

    def pick_all(self, pointers: Mapping[HandSide, PointerState]) -> dict[HandSide, str | None]:
        hover_ids: dict[HandSide, str | None] = {}
        for side, pointer in pointers.items():
            result = self.pick(pointer.position)
            previous = self._last_hover_ids.get(side)
            if result is None and previous is not None:
                result = self._pick_around(
                    pointer.position,
                    self.pick_hold_tolerance_pixels,
                    entity_id=previous,
                )
            hover_ids[side] = result.entity_id if result is not None else None
            if result is None:
                self._last_hover_ids.pop(side, None)
            else:
                self._last_hover_ids[side] = result.entity_id
        for missing_side in set(self._last_hover_ids) - set(pointers):
            self._last_hover_ids.pop(missing_side, None)
        return hover_ids

    def set_highlights(self, hover_ids: Mapping[HandSide, str | None]) -> None:
        left = hover_ids.get(HandSide.LEFT)
        right = hover_ids.get(HandSide.RIGHT)
        hovered = {entity_id for entity_id in (left, right) if entity_id is not None}
        self._reset_highlights(keep_errors=hovered)
        if left is not None and left == right:
            if self.highlight_for(left) is not HighlightRole.ERROR:
                self._set_highlight(left, HighlightRole.COMMON)
            return
        if left is not None and self.highlight_for(left) is not HighlightRole.ERROR:
            self._set_highlight(left, HighlightRole.LEFT)
        if right is not None and self.highlight_for(right) is not HighlightRole.ERROR:
            self._set_highlight(right, HighlightRole.RIGHT)

    def show_union_failure(self, entity_ids: tuple[str, ...]) -> None:
        for entity_id in entity_ids:
            self._set_highlight(entity_id, HighlightRole.ERROR)

    def highlight_for(self, entity_id: str) -> HighlightRole:
        return self._highlight_roles.get(entity_id, HighlightRole.NONE)

    def set_pointers(self, pointers: Mapping[HandSide, PointerState]) -> None:
        for side in set(self._pointer_nodes) - set(pointers):
            self._pointer_nodes.pop(side).removeNode()
        colors = {
            HandSide.LEFT: (0.15, 0.75, 1.0, 1.0),
            HandSide.RIGHT: (1.0, 0.55, 0.15, 1.0),
        }
        for side, pointer in pointers.items():
            node = self._pointer_nodes.get(side)
            if node is None:
                card = CardMaker(f"{side.value}-pointer")
                card.setFrame(-0.018, 0.018, -0.018, 0.018)
                node = self.base.aspect2d.attachNewNode(card.generate())
                node.setColor(*colors[side])
                self._pointer_nodes[side] = node
            aspect = self.base.camLens.getAspectRatio()
            node.setPos(
                (pointer.position.x * 2.0 - 1.0) * aspect,
                0.0,
                1.0 - pointer.position.y * 2.0,
            )

    def set_camera_gesture(
        self,
        mode: InteractionMode,
        pointers: Mapping[HandSide, PointerState],
        *,
        motion_enabled: bool = True,
    ) -> None:
        camera_modes = {
            InteractionMode.CAMERA_PAN,
            InteractionMode.CAMERA_ZOOM,
            InteractionMode.CAMERA_ORBIT,
        }
        if mode not in camera_modes:
            self._camera_gesture_mode = InteractionMode.NEUTRAL
            self._camera_gesture_positions.clear()
            if self._camera_gesture_node is not None:
                self._camera_gesture_node.hide()
            for node in self._pointer_nodes.values():
                node.show()
            return

        if motion_enabled:
            self._apply_camera_gesture_motion(mode, pointers)
        else:
            self._camera_gesture_mode = mode
            self._camera_gesture_positions.clear()

        left = pointers.get(HandSide.LEFT)
        right = pointers.get(HandSide.RIGHT)
        if left is not None and right is not None:
            position = midpoint(left.position, right.position)
        elif right is not None:
            position = right.position
        elif left is not None:
            position = left.position
        else:
            return

        if self._camera_gesture_node is None:
            self._camera_gesture_node = self._make_open_hand_indicator()
        for node in self._pointer_nodes.values():
            node.hide()
        aspect = self.base.camLens.getAspectRatio()
        self._camera_gesture_node.setPos(
            (position.x * 2.0 - 1.0) * aspect,
            0.0,
            1.0 - position.y * 2.0,
        )
        self._camera_gesture_node.show()

    def _apply_camera_gesture_motion(
        self,
        mode: InteractionMode,
        pointers: Mapping[HandSide, PointerState],
    ) -> None:
        positions = {side: pointer.position for side, pointer in pointers.items()}
        required = (
            {HandSide.LEFT, HandSide.RIGHT}
            if mode in (InteractionMode.CAMERA_PAN, InteractionMode.CAMERA_ZOOM)
            else {HandSide.RIGHT}
        )
        if not required.issubset(positions):
            self._camera_gesture_mode = mode
            self._camera_gesture_positions.clear()
            return
        if (
            mode is not self._camera_gesture_mode
            or not required.issubset(self._camera_gesture_positions)
        ):
            self._camera_gesture_mode = mode
            self._camera_gesture_positions = positions
            return

        previous = self._camera_gesture_positions
        self._camera_gesture_positions = positions
        if mode is InteractionMode.CAMERA_PAN:
            current_center = midpoint(positions[HandSide.LEFT], positions[HandSide.RIGHT])
            previous_center = midpoint(previous[HandSide.LEFT], previous[HandSide.RIGHT])
            delta = _bounded_delta(
                _camera_delta_from_screen(current_center - previous_center)
            )
            if delta != Vec2(0.0, 0.0):
                self.pan(delta)
        elif mode is InteractionMode.CAMERA_ZOOM:
            current_distance = positions[HandSide.LEFT].distance_to(positions[HandSide.RIGHT])
            previous_distance = previous[HandSide.LEFT].distance_to(previous[HandSide.RIGHT])
            amount = _bounded_scalar(current_distance - previous_distance)
            if amount != 0.0:
                self.zoom(amount)
        elif mode is InteractionMode.CAMERA_ORBIT:
            raw = positions[HandSide.RIGHT] - previous[HandSide.RIGHT]
            delta = _bounded_delta(_camera_delta_from_screen(raw))
            if delta != Vec2(0.0, 0.0):
                self.orbit(delta)

    def set_preview(self, preview) -> None:
        if preview is None:
            if self._preview_node is not None:
                self._preview_node.removeNode()
            self._preview_node = None
            self._preview_kind = None
            return
        if self._preview_node is None or self._preview_kind is not preview.kind:
            if self._preview_node is not None:
                self._preview_node.removeNode()
            self._preview_node = self.root.attachNewNode("creation-preview")
            mesh = create_primitive(preview.kind)
            geometry = self._preview_node.attachNewNode(
                mesh_to_geom_node(mesh, f"preview-{preview.kind.value}")
            )
            geometry.setColor(0.82, 1.0, 0.15, 0.82)
            geometry.setTransparency(True)
            geometry.setRenderModeThickness(2.5)
            self._preview_kind = preview.kind
        center = preview.world_center
        self._preview_node.setPos(center.x, center.y, center.z)
        self._preview_node.setScale(preview.scale)
        self._preview_node.setRenderModeWireframe()

    def screen_plane_point(self, pointer: Vec2, depth: float) -> Vec3:
        origin, direction = self.screen_ray(pointer)
        _, _, forward = self.camera_basis()
        plane = Vec3(
            self.camera_position.x + forward.x * depth,
            self.camera_position.y + forward.y * depth,
            self.camera_position.z + forward.z * depth,
        )
        denominator = _dot(direction, forward)
        if abs(denominator) < 1e-8:
            raise RuntimeError("pointer ray is parallel to camera plane")
        amount = _dot(_subtract(plane, origin), forward) / denominator
        return Vec3(
            origin.x + direction.x * amount,
            origin.y + direction.y * amount,
            origin.z + direction.z * amount,
        )

    def depth_of(self, point: Vec3) -> float:
        _, _, forward = self.camera_basis()
        return _dot(_subtract(point, self.camera_position), forward)

    def screen_ray(self, pointer: Vec2) -> tuple[Vec3, Vec3]:
        near, far = Point3(), Point3()
        if not self.base.camLens.extrude(
            Point2(pointer.x * 2.0 - 1.0, 1.0 - pointer.y * 2.0), near, far
        ):
            raise RuntimeError("camera lens could not extrude pointer")
        near_world = self.base.render.getRelativePoint(self.base.camera, near)
        far_world = self.base.render.getRelativePoint(self.base.camera, far)
        ray = PandaVec3(far_world - near_world)
        ray.normalize()
        return (
            Vec3(float(near_world.x), float(near_world.y), float(near_world.z)),
            Vec3(float(ray.x), float(ray.y), float(ray.z)),
        )

    def camera_basis(self) -> tuple[Vec3, Vec3, Vec3]:
        quaternion = self.base.camera.getQuat(self.base.render)
        right, up, forward = quaternion.getRight(), quaternion.getUp(), quaternion.getForward()
        return (
            Vec3(float(right.x), float(right.y), float(right.z)),
            Vec3(float(up.x), float(up.y), float(up.z)),
            Vec3(float(forward.x), float(forward.y), float(forward.z)),
        )

    def pan(self, delta: Vec2) -> None:
        right, up, _ = self.camera_basis()
        vertical_fov = float(self.base.camLens.getFov().y) * pi / 180.0
        vertical_span = 2.0 * self._distance * tan(vertical_fov / 2.0)
        horizontal_span = vertical_span * self.base.camLens.getAspectRatio()
        sensitivity = self.settings.pan_gain / 4.0
        amount_x = -delta.x * horizontal_span * sensitivity
        amount_y = -delta.y * vertical_span * sensitivity
        self._focus = Vec3(
            self._focus.x + right.x * amount_x + up.x * amount_y,
            self._focus.y + right.y * amount_x + up.y * amount_y,
            self._focus.z + right.z * amount_x + up.z * amount_y,
        )
        self._apply_camera()

    def zoom(self, amount: float) -> None:
        factor = exp(-amount * self.settings.zoom_gain * 0.5)
        self._distance = min(
            self.max_distance,
            max(self.min_distance, self._distance * factor),
        )
        self._apply_camera()

    def orbit(self, delta: Vec2) -> None:
        self._yaw += delta.x * self.settings.orbit_gain
        self._pitch = min(85.0, max(-85.0, self._pitch - delta.y * self.settings.orbit_gain))
        self._apply_camera()

    def clear(self) -> None:
        for node in self._nodes.values():
            node.removeNode()
        for node in self._pointer_nodes.values():
            node.removeNode()
        self._nodes.clear()
        self._geometry_nodes.clear()
        self._outline_nodes.clear()
        self._pointer_nodes.clear()
        self._highlight_roles.clear()
        self._last_hover_ids.clear()
        self._camera_gesture_mode = InteractionMode.NEUTRAL
        self._camera_gesture_positions.clear()
        if self._camera_gesture_node is not None:
            self._camera_gesture_node.hide()
        self.set_preview(None)

    def close(self) -> None:
        self.clear()
        self._traverser.removeCollider(self._ray_path)
        self._ray_path.removeNode()
        self.root.removeNode()

    def _apply_camera(self) -> None:
        yaw = self._yaw * pi / 180.0
        pitch = self._pitch * pi / 180.0
        offset = Vec3(
            self._distance * sin(yaw) * cos(pitch),
            -self._distance * cos(yaw) * cos(pitch),
            self._distance * sin(pitch),
        )
        self.base.camera.setPos(
            self._focus.x + offset.x,
            self._focus.y + offset.y,
            self._focus.z + offset.z,
        )
        self.base.camera.lookAt(self._focus.x, self._focus.y, self._focus.z)

    def _make_material(self) -> Material:
        material = Material("rhino-like-shaded-material")
        material.setAmbient((0.30, 0.31, 0.33, 1.0))
        material.setDiffuse((0.72, 0.75, 0.79, 1.0))
        material.setSpecular((0.20, 0.22, 0.25, 1.0))
        material.setShininess(28.0)
        return material

    def _make_outline_shader(self) -> Shader:
        """Build an inverted-hull shader with a screen-space pixel width.

        Expanding in clip space keeps the visible rim independent of model
        scale and camera distance.  The viewport conversion also keeps the
        requested width stable across window sizes and aspect ratios.
        """
        vertex = """
#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ProjectionMatrix;
uniform vec2 outline_viewport;
uniform float outline_width_pixels;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;

void main() {
    vec4 clip_position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vec3 view_normal = normalize(mat3(p3d_ModelViewMatrix) * p3d_Normal);
    vec4 projected_normal = p3d_ProjectionMatrix * vec4(view_normal, 0.0);
    vec2 pixel_direction = vec2(
        projected_normal.x * outline_viewport.x,
        projected_normal.y * outline_viewport.y
    );
    float direction_length = length(pixel_direction);
    if (direction_length > 0.00001) {
        pixel_direction /= direction_length;
        vec2 ndc_per_pixel = vec2(2.0) / outline_viewport;
        clip_position.xy += (
            pixel_direction * ndc_per_pixel * outline_width_pixels * clip_position.w
        );
    }
    gl_Position = clip_position;
}
"""
        fragment = """
#version 130
uniform vec4 outline_color;
out vec4 p3d_FragColor;

void main() {
    p3d_FragColor = outline_color;
}
"""
        return Shader.make(Shader.SL_GLSL, vertex, fragment)

    def _update_outline_viewports(self) -> None:
        width, height = self.viewport_size
        for outline in self._outline_nodes.values():
            outline.setShaderInput("outline_viewport", float(width), float(height))

    def _make_open_hand_indicator(self):
        root = self.base.aspect2d.attachNewNode("camera-gesture-open-hand")
        color = (0.88, 0.96, 1.0, 1.0)

        def add_part(name: str, frame: tuple[float, float, float, float], x: float, z: float, roll: float = 0.0):
            card = CardMaker(name)
            card.setFrame(*frame)
            part = root.attachNewNode(card.generate())
            part.setColor(*color)
            part.setPos(x, 0.0, z)
            part.setR(roll)

        add_part("palm", (-0.030, 0.030, -0.030, 0.028), 0.0, -0.006)
        finger_specs = (
            (-0.022, 0.050),
            (-0.008, 0.060),
            (0.007, 0.064),
            (0.022, 0.052),
        )
        for index, (x, top) in enumerate(finger_specs):
            add_part(f"finger-{index}", (-0.005, 0.005, 0.0, top), x, 0.014)
        add_part("thumb", (-0.005, 0.005, -0.002, 0.040), -0.032, -0.002, -48.0)
        root.setTransparency(True)
        root.setBin("fixed", 30)
        root.setDepthTest(False)
        root.setDepthWrite(False)
        root.hide()
        return root

    def _setup_lighting(self) -> tuple[object, ...]:
        ambient = AmbientLight("modeling-ambient")
        ambient.setColor((0.34, 0.36, 0.40, 1.0))
        ambient_path = self.root.attachNewNode(ambient)

        key = DirectionalLight("modeling-key")
        key.setColor((0.92, 0.95, 1.0, 1.0))
        key_path = self.root.attachNewNode(key)
        key_path.setHpr(-35.0, -45.0, 0.0)

        rim = DirectionalLight("modeling-rim")
        rim.setColor((0.25, 0.30, 0.38, 1.0))
        rim_path = self.root.attachNewNode(rim)
        rim_path.setHpr(145.0, 25.0, 0.0)

        for light_path in (ambient_path, key_path, rim_path):
            self.root.setLight(light_path)
        return ambient_path, key_path, rim_path

    def _reset_highlights(self, *, keep_errors: set[str] | None = None) -> None:
        keep_errors = keep_errors or set()
        for entity_id in self._nodes:
            if (
                entity_id in keep_errors
                and self._highlight_roles.get(entity_id) is HighlightRole.ERROR
            ):
                continue
            self._set_highlight(entity_id, HighlightRole.NONE)

    def _set_highlight(self, entity_id: str, role: HighlightRole) -> None:
        if entity_id not in self._nodes:
            return
        colors = {
            HighlightRole.NONE: (1.0, 1.0, 1.0, 1.0),
            HighlightRole.LEFT: (0.15, 0.75, 1.0, 1.0),
            HighlightRole.RIGHT: (1.0, 0.55, 0.15, 1.0),
            HighlightRole.COMMON: (0.75, 1.0, 0.20, 1.0),
            HighlightRole.ERROR: (1.0, 0.05, 0.05, 1.0),
        }
        outline = self._outline_nodes[entity_id]
        if role is HighlightRole.NONE:
            outline.hide()
        else:
            outline.setShaderInput("outline_color", colors[role])
            outline.show()
        self._highlight_roles[entity_id] = role


def _dot(first: Vec3, second: Vec3) -> float:
    return first.x * second.x + first.y * second.y + first.z * second.z


def _subtract(first: Vec3, second: Vec3) -> Vec3:
    return Vec3(first.x - second.x, first.y - second.y, first.z - second.z)


def _bounded_delta(delta: Vec2) -> Vec2:
    deadzone = 0.0008
    maximum = 0.06
    magnitude = delta.distance_to(Vec2(0.0, 0.0))
    if magnitude <= deadzone:
        return Vec2(0.0, 0.0)
    if magnitude > maximum:
        return delta * (maximum / magnitude)
    return delta


def _camera_delta_from_screen(delta: Vec2) -> Vec2:
    """Convert screen-down hand motion to the mouse camera coordinate system.

    Suppress a small secondary component so natural hand drift does not make
    a mostly horizontal or vertical gesture rotate along both axes.
    """
    converted = Vec2(delta.x, -delta.y)
    horizontal, vertical = abs(converted.x), abs(converted.y)
    cross_axis_ratio = 0.35
    if horizontal > vertical and vertical <= horizontal * cross_axis_ratio:
        return Vec2(converted.x, 0.0)
    if vertical > horizontal and horizontal <= vertical * cross_axis_ratio:
        return Vec2(0.0, converted.y)
    return converted


def _bounded_scalar(value: float) -> float:
    if abs(value) <= 0.0008:
        return 0.0
    return max(-0.06, min(0.06, value))
